import json
import re

from typing import Any, Callable, Dict, List, Optional

from api.client import APIClient

from .llm.client import LLMClient
from .llm.parser import parse_feedback_response
from .llm.prompts import (
    FEEDBACK_RESPONSE_SCHEMA,
    SYSTEM_PROMPT,
    build_qualitative_prompt,
)

from .qualitative_feedback.argumentation import analyze_argumentation
from .qualitative_feedback.logic import analyze_logic
from .qualitative_feedback.persuasion import analyze_persuasion
from .qualitative_feedback.rebuttal import analyze_rebuttal
from .qualitative_feedback.structure import analyze_structure

from .qualitative_feedback.feedback_aggregator import (
    aggregate_feedback,
    build_coaching_scores,
)

from .quantitative_feedback import analyze_quantitative_feedback

from .models.feedback import FeedbackItem
from .models.scores import CoachingScores

from .utils.loader import load_session
from .utils.validators import validate_session


# ============================================================
# QUALITATIVE CATEGORIES
#
# Each category has two independent producers:
#
#   1. A deterministic rule module that reads the semantic
#      labels in speech_content.json. It never calls an LLM
#      and always runs.
#
#   2. An optional LLM pass that produces richer, evidence-
#      backed feedback for the same category.
#
# The deterministic pass is the floor. If the LLM pass fails
# for a category, that category still produces feedback.
# ============================================================

DETERMINISTIC_ANALYZERS = {
    "argumentation": analyze_argumentation,
    "rebuttal": analyze_rebuttal,
    "structure": analyze_structure,
    "persuasion": analyze_persuasion,
    "logic": analyze_logic,
}

CATEGORY_SYSTEM_PROMPTS = {
    "argumentation": (
        "You are an expert debate coach specializing "
        "in argumentation analysis."
    ),
    "rebuttal": (
        "You are an expert debate coach specializing "
        "in rebuttal and counterargument analysis."
    ),
    "structure": (
        "You are an expert debate coach specializing "
        "in speech structure and organization."
    ),
    "persuasion": (
        "You are an expert debate coach specializing "
        "in persuasion and rhetorical effectiveness."
    ),
    "logic": (
        "You are an expert debate coach specializing "
        "in logical reasoning and fallacy detection."
    ),
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

    where feedback is a deduplicated, severity-ordered list of
    FeedbackItem and scores is a CoachingScores instance.
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

        feedback: List[FeedbackItem] = []

        # ----------------------------------------------------
        # 1. Quantitative (deterministic, raw_metrics.json)
        # ----------------------------------------------------

        feedback.extend(
            analyze_quantitative_feedback(session)
        )

        # ----------------------------------------------------
        # 2. Qualitative rules (deterministic, labels only)
        # ----------------------------------------------------

        for category, analyzer in DETERMINISTIC_ANALYZERS.items():
            feedback.extend(
                analyzer(session)
            )

        # ----------------------------------------------------
        # 3. Qualitative LLM pass (optional, per category)
        # ----------------------------------------------------

        if self.use_llm and self.llm_client is not None:
            feedback.extend(
                self._run_llm_analysis(
                    session.speech_content
                )
            )

        # ----------------------------------------------------
        # 4. Aggregate and score
        # ----------------------------------------------------

        aggregated = aggregate_feedback(feedback)

        scores = build_coaching_scores(aggregated)

        return aggregated, scores

    # --------------------------------------------------------
    # LLM analysis
    # --------------------------------------------------------

    def _run_llm_analysis(
        self,
        speech_content: Dict[str, Any],
    ) -> List[FeedbackItem]:

        results: List[FeedbackItem] = []

        for category in DETERMINISTIC_ANALYZERS:

            try:
                results.extend(
                    self._analyze_category(
                        category=category,
                        speech_content=speech_content,
                    )
                )

            except Exception as error:

                # One failed category must not discard the
                # feedback already produced for the others.
                # The deterministic pass has already covered
                # this category, so the run stays useful.

                self.llm_errors[category] = (
                    f"{type(error).__name__}: {error}"
                )

        return results

    def _analyze_category(
        self,
        category: str,
        speech_content: Dict[str, Any],
    ) -> List[FeedbackItem]:

        user_prompt = build_qualitative_prompt(
            category=category,
            speech_content=speech_content,
        )

        system_prompt = (
            f"{CATEGORY_SYSTEM_PROMPTS[category]}\n\n"
            f"{SYSTEM_PROMPT.strip()}\n\n"
            "Return a single JSON object matching this schema "
            "exactly, with no prose and no markdown fences:\n"
            f"{json.dumps(FEEDBACK_RESPONSE_SCHEMA)}"
        )

        response = self.llm_client.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_schema=FEEDBACK_RESPONSE_SCHEMA,
            temperature=0.2,
            on_queued=self.on_queued,
        )

        return parse_feedback_response(
            _strip_code_fences(response)
        )
