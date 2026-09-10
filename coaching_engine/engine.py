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

from .llm.client import LLMClient
from .llm.parser import parse_feedback_response
from .llm.prompts import (
    FEEDBACK_RESPONSE_SCHEMA,
    SYSTEM_PROMPT,
    build_qualitative_prompt,
)


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
        3. Runs quantitative analysis.
        4. Runs deterministic semantic analysis.
        5. Runs LLM-based qualitative analysis.
        6. Aggregates all feedback.
        7. Calculates coaching scores.

    The engine is responsible only for orchestration.
    Analysis logic remains inside individual modules.
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
        Run LLM-based qualitative analysis.

        Each qualitative category receives a separate focused
        analysis from the LLM.
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
                response_schema=FEEDBACK_RESPONSE_SCHEMA,
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

        Args:
            session_id:
                ID of the session to analyze.

        Returns:
            A tuple containing:

            - aggregated feedback
            - coaching scores
        """

        # --------------------------------------------------
        # 1. Load session
        # --------------------------------------------------

        session = load_session(
            session_id=session_id,
            sessions_dir=self.sessions_dir,
        )

        # --------------------------------------------------
        # 2. Validate session
        # --------------------------------------------------

        validate_session(session)

        feedback: List[FeedbackItem] = []

        # --------------------------------------------------
        # 3. Quantitative analysis
        # --------------------------------------------------

        quantitative_feedback = (
            analyze_quantitative_feedback(session)
        )

        feedback.extend(
            quantitative_feedback
        )

        # --------------------------------------------------
        # 4. Deterministic semantic analysis
        # --------------------------------------------------

        semantic_feedback: List[FeedbackItem] = []

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

        feedback.extend(
            semantic_feedback
        )

        # --------------------------------------------------
        # 5. LLM qualitative analysis
        # --------------------------------------------------

        llm_feedback = self._run_llm_analysis(
            speech_content=session.speech_content
        )

        feedback.extend(
            llm_feedback
        )

        # --------------------------------------------------
        # 6. Aggregate feedback
        # --------------------------------------------------

        aggregated_feedback = aggregate_feedback(
            feedback
        )

        # --------------------------------------------------
        # 7. Calculate scores
        # --------------------------------------------------

        scores = build_coaching_scores(
            aggregated_feedback
        )

        return aggregated_feedback, scores