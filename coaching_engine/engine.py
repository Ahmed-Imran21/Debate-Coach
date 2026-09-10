from .llm.client import LLMClient
from .llm.parser import parse_feedback_response
from .llm.prompts import (
    SYSTEM_PROMPT,
    build_qualitative_prompt,
)

from typing import List, Tuple

from .models.feedback import FeedbackItem
from .models.scores import CoachingScores

from .qualitative_feedback.argumentation import (
    analyze_argumentation,
)
from .qualitative_feedback.feedback_aggregator import (
    aggregate_feedback,
    build_coaching_scores,
)
from .qualitative_feedback.logic import (
    analyze_logic,
)
from .qualitative_feedback.persuasion import (
    analyze_persuasion,
)
from .qualitative_feedback.rebuttal import (
    analyze_rebuttal,
)
from .qualitative_feedback.structure import (
    analyze_structure,
)

from .quantitative_feedback import (
    analyze_quantitative_feedback,
)

from .utils.loader import load_session
from .utils.validators import validate_session


QUALITATIVE_CATEGORIES = [
    "argumentation",
    "rebuttal",
    "structure",
    "persuasion",
    "logic",
]


class CoachingEngine:
    """
    Main orchestration layer for the coaching engine.

    The engine:

        1. Loads the session.
        2. Validates the input.
        3. Runs deterministic quantitative analysis.
        4. Runs deterministic semantic analysis.
        5. Runs LLM-based qualitative analysis.
        6. Aggregates all feedback.
        7. Calculates coaching scores.

    The engine is responsible for orchestration only.
    Analysis logic remains inside the individual modules.
    """

    def __init__(
        self,
        sessions_dir: str = "sessions",
        llm_client: LLMClient | None = None,
    ):
        self.sessions_dir = sessions_dir

        self.llm_client = llm_client or LLMClient()

    def _run_llm_analysis(
        self,
        speech_content: dict,
    ) -> List[FeedbackItem]:
        """
        Run LLM-based qualitative analysis for all coaching
        categories.

        Each category receives its own focused prompt so that
        the model evaluates one qualitative dimension at a time.
        """

        feedback: List[FeedbackItem] = []

        for category in QUALITATIVE_CATEGORIES:
            prompt = build_qualitative_prompt(
                category=category,
                speech_content=speech_content,
            )

            response = self.llm_client.generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
            )

            category_feedback = parse_feedback_response(
                response
            )

            feedback.extend(category_feedback)

        return feedback

    def analyze_session(
        self,
        session_id: str,
    ) -> Tuple[List[FeedbackItem], CoachingScores]:
        """
        Analyze a complete debate session.

        Returns:
            A tuple containing:

            - aggregated feedback
            - coaching scores
        """

        session = load_session(
            session_id=session_id,
            sessions_dir=self.sessions_dir,
        )

        validate_session(session)

        feedback: List[FeedbackItem] = []

        # --------------------------------------------------
        # 1. Quantitative analysis
        # --------------------------------------------------

        quantitative_feedback = (
            analyze_quantitative_feedback(session)
        )

        feedback.extend(quantitative_feedback)

        # --------------------------------------------------
        # 2. Deterministic semantic analysis
        # --------------------------------------------------

        semantic_feedback = []

        semantic_feedback.extend(
            analyze_argumentation(session)
        )

        semantic_feedback.extend(
            analyze_rebuttal(session)
        )

        semantic_feedback.extend(
            analyze_structure(session)
        )

        semantic_feedback.extend(
            analyze_persuasion(session)
        )

        semantic_feedback.extend(
            analyze_logic(session)
        )

        feedback.extend(semantic_feedback)

        # --------------------------------------------------
        # 3. LLM qualitative analysis
        # --------------------------------------------------

        llm_feedback = self._run_llm_analysis(
            speech_content=session.speech_content
        )

        feedback.extend(llm_feedback)

        # --------------------------------------------------
        # 4. Aggregate feedback
        # --------------------------------------------------

        aggregated_feedback = aggregate_feedback(
            feedback
        )

        # --------------------------------------------------
        # 5. Calculate scores
        # --------------------------------------------------

        scores = build_coaching_scores(
            aggregated_feedback
        )

        return aggregated_feedback, scores