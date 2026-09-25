import re

from typing import Any, Callable, Dict, List, Optional

from api.client import APIClient

from .llm.client import LLMClient
from .llm.parser import parse_synthesis_response
from .llm.prompts import (
    build_synthesis_prompt,
    build_synthesis_system_prompt,
)

from .qualitative_feedback.argumentation import analyze_argumentation
from .qualitative_feedback.logic import analyze_logic
from .qualitative_feedback.persuasion import analyze_persuasion
from .qualitative_feedback.rebuttal import analyze_rebuttal
from .qualitative_feedback.structure import analyze_structure

from .qualitative_feedback.feedback_aggregator import (
    aggregate_feedback,
    build_fallback_scores,
    build_rubric_scores,
    cap_content,
    dedupe_by_theme,
    top_delivery,
)

from .quantitative_feedback import analyze_quantitative_feedback

from .models.feedback import FeedbackItem
from .models.scores import CoachingScores

from .utils.loader import load_session
from .utils.validators import validate_session


# ============================================================
# QUALITATIVE FEEDBACK
#
# One LLM call reads the whole speech and returns a few
# synthesized feedback items plus a rubric level per content
# category (coaching_engine/llm/prompts.py). Five separate
# per-category calls, alongside five rule modules flagging the
# same gaps, used to produce 35-45 items for a sub-minute speech
# — "no evidence" alone nine times — and the repetition dragged
# every score down.
#
# The call is tried twice. The deterministic rule modules are
# the fallback if both attempts fail or return something
# unusable: their items are merged per underlying issue and
# capped, and scored by the formula with content categories
# held to level 3 (build_fallback_scores). Every session still
# gets feedback.
# ============================================================

SYNTHESIS_ATTEMPTS = 2

DETERMINISTIC_ANALYZERS = {
    "argumentation": analyze_argumentation,
    "rebuttal": analyze_rebuttal,
    "structure": analyze_structure,
    "persuasion": analyze_persuasion,
    "logic": analyze_logic,
}


# ============================================================
# JSON EXTRACTION
# ============================================================

_FENCE_PATTERN = re.compile(
    r"^\s*```(?:json)?\s*|\s*```\s*$",
    re.IGNORECASE,
)


def _strip_code_fences(response: str) -> str:
    """
    Remove markdown code fences from an LLM response.

    The provider adapters in api/providers/ do not request a
    JSON response format, so models occasionally wrap valid
    JSON in a fenced block. Stripping the fence here keeps
    the structured-JSON contract intact without changing the
    shared API layer.
    """

    return _FENCE_PATTERN.sub("", response).strip()


# ============================================================
# COACHING ENGINE
# ============================================================

class CoachingEngine:
    """
    Produces the full coaching result for one analyzed session.

    Inputs (already on disk, written by earlier pipeline steps):

        <sessions_dir>/<session_id>/raw_metrics.json
        <sessions_dir>/<session_id>/speech_content.json

    Output:

        (feedback, scores)

    where feedback is at most 8 severity-ordered FeedbackItems (up
    to 6 on content, up to 2 on delivery) and scores is a
    CoachingScores instance.
    """

    def __init__(
        self,
        sessions_dir: str = "sessions",
        llm_client: Optional[LLMClient] = None,
        api_client: Optional[APIClient] = None,
        on_queued: Optional[Callable[[float], None]] = None,
        use_llm: bool = True,
    ):
        self.sessions_dir = sessions_dir

        self.on_queued = on_queued
        self.use_llm = use_llm

        self.llm_errors: Dict[str, str] = {}
        # The model's one-line reason per rubric level, from the last
        # analyze_session() that used the LLM path.
        self.rubric_reasons: Dict[str, str] = {}

        if llm_client is not None:
            self.llm_client = llm_client
        elif use_llm:
            self.llm_client = LLMClient(api_client=api_client)
        else:
            self.llm_client = None

    # --------------------------------------------------------
    # Public entry point
    # --------------------------------------------------------

    def analyze_session(
        self,
        session_id: str,
    ) -> tuple[List[FeedbackItem], CoachingScores]:

        session = load_session(
            session_id=session_id,
            sessions_dir=self.sessions_dir,
        )

        validate_session(session)

        # Delivery: deterministic, from raw_metrics.json. Every item
        # feeds the delivery score; only the top two are shown.
        delivery = analyze_quantitative_feedback(session)

        synthesis = None

        if self.use_llm and self.llm_client is not None:
            try:
                synthesis = self._synthesize(session.speech_content)
            except Exception as error:
                self.llm_errors["synthesis"] = f"{type(error).__name__}: {error}"

        if synthesis is not None:
            content, levels, self.rubric_reasons = synthesis
            scores = build_rubric_scores(delivery, levels)
            content = cap_content(content)
        else:
            rules = [item for analyze in DETERMINISTIC_ANALYZERS.values() for item in analyze(session)]
            merged = dedupe_by_theme(rules)
            scores = build_fallback_scores(delivery + merged)
            content = cap_content(merged)

        feedback = aggregate_feedback(top_delivery(delivery) + content)

        return feedback, scores

    # --------------------------------------------------------
    # LLM synthesis
    # --------------------------------------------------------

    def _synthesize(self, speech_content: Dict[str, Any]):
        # One retry: in testing ~5% of calls hit a transient connection
        # error (no tokens spent) and ~5% of responses left out part of
        # the rubric. Either way a second attempt almost always
        # succeeds, and it beats falling back to the rules.
        for attempt in range(SYNTHESIS_ATTEMPTS):
            try:
                response = self.llm_client.generate(
                    system_prompt=build_synthesis_system_prompt(),
                    user_prompt=build_synthesis_prompt(speech_content),
                    temperature=0.2,
                    on_queued=self.on_queued,
                )
                return parse_synthesis_response(_strip_code_fences(response))
            except Exception:
                if attempt == SYNTHESIS_ATTEMPTS - 1:
                    raise
