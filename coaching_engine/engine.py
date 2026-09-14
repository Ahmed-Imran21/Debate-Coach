from typing import Callable, Optional

from api.client import APIClient

from .llm.client import LLMClient
from .llm.parser import parse_llm_response
from .llm.prompts import (
    build_argumentation_prompt,
    build_logic_prompt,
    build_persuasion_prompt,
    build_rebuttal_prompt,
    build_structure_prompt,
)

from .qualitative_feedback.feedback_aggregator import aggregate_feedback
from .quantitative_feedback import calculate_quantitative_score

from .utils.loader import load_session_data
from .models.feedback import FeedbackItem
from .models.scores import Scores


class CoachingEngine:
    def __init__(
        self,
        sessions_dir: str = "sessions",
        llm_client: Optional[LLMClient] = None,
        api_client: Optional[APIClient] = None,
        on_queued: Optional[Callable[[float], None]] = None,
    ):
        self.sessions_dir = sessions_dir

        self.on_queued = on_queued

        if llm_client is not None:
            self.llm_client = llm_client
        else:
            self.llm_client = LLMClient(api_client=api_client)

    def analyze_session(
        self,
        session_id: str,
    ):
        session_data = load_session_data(
            session_id=session_id,
            sessions_dir=self.sessions_dir,
        )

        quantitative_score = calculate_quantitative_score(
            session_data
        )

        qualitative_feedback = self._run_llm_analysis(
            session_data
        )

        feedback = aggregate_feedback(
            qualitative_feedback
        )

        scores = Scores(
            categories={
                "quantitative": quantitative_score,
                "argumentation": qualitative_feedback["argumentation"]["score"],
                "rebuttal": qualitative_feedback["rebuttal"]["score"],
                "structure": qualitative_feedback["structure"]["score"],
                "persuasion": qualitative_feedback["persuasion"]["score"],
                "logic": qualitative_feedback["logic"]["score"],
            }
        )

        return feedback, scores

    def _run_llm_analysis(self, session_data):
        results = {}

        # -----------------------------
        # Argumentation
        # -----------------------------
        argumentation_prompt = build_argumentation_prompt(
            session_data
        )

        results["argumentation"] = parse_llm_response(
            self.llm_client.generate(
                system_prompt=(
                    "You are an expert debate coach specializing "
                    "in argumentation analysis."
                ),
                user_prompt=argumentation_prompt,
                response_schema={},
                temperature=0.2,
                on_queued=self.on_queued,
            )
        )

        # -----------------------------
        # Rebuttal
        # -----------------------------
        rebuttal_prompt = build_rebuttal_prompt(
            session_data
        )

        results["rebuttal"] = parse_llm_response(
            self.llm_client.generate(
                system_prompt=(
                    "You are an expert debate coach specializing "
                    "in rebuttal and counterargument analysis."
                ),
                user_prompt=rebuttal_prompt,
                response_schema={},
                temperature=0.2,
                on_queued=self.on_queued,
            )
        )

        # -----------------------------
        # Structure
        # -----------------------------
        structure_prompt = build_structure_prompt(
            session_data
        )

        results["structure"] = parse_llm_response(
            self.llm_client.generate(
                system_prompt=(
                    "You are an expert debate coach specializing "
                    "in speech structure and organization."
                ),
                user_prompt=structure_prompt,
                response_schema={},
                temperature=0.2,
                on_queued=self.on_queued,
            )
        )

        # -----------------------------
        # Persuasion
        # -----------------------------
        persuasion_prompt = build_persuasion_prompt(
            session_data
        )

        results["persuasion"] = parse_llm_response(
            self.llm_client.generate(
                system_prompt=(
                    "You are an expert debate coach specializing "
                    "in persuasion and rhetorical effectiveness."
                ),
                user_prompt=persuasion_prompt,
                response_schema={},
                temperature=0.2,
                on_queued=self.on_queued,
            )
        )

        # -----------------------------
        # Logic
        # -----------------------------
        logic_prompt = build_logic_prompt(
            session_data
        )

        results["logic"] = parse_llm_response(
            self.llm_client.generate(
                system_prompt=(
                    "You are an expert debate coach specializing "
                    "in logical reasoning and fallacy detection."
                ),
                user_prompt=logic_prompt,
                response_schema={},
                temperature=0.2,
                on_queued=self.on_queued,
            )
        )

        return results