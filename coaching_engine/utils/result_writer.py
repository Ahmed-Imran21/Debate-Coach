import json
from pathlib import Path
from typing import List

from ..models.feedback import FeedbackItem
from ..models.scores import CoachingScores


def save_coaching_results(
    session_id: str,
    feedback: List[FeedbackItem],
    scores: CoachingScores,
    sessions_dir: str = "sessions",
) -> Path:
    """
    Save the complete coaching results for a session.

    Creates:

        sessions/
        └── <session_id>/
            └── feedback.json

    The file contains:
        - session ID
        - coaching scores
        - overall score
        - all coaching feedback
    """

    if not isinstance(session_id, str):
        raise TypeError("session_id must be a string.")

    if not session_id.strip():
        raise ValueError("session_id cannot be empty.")

    if not isinstance(feedback, list):
        raise TypeError("feedback must be a list.")

    if not isinstance(scores, CoachingScores):
        raise TypeError(
            "scores must be a CoachingScores instance."
        )

    session_directory = (
        Path(sessions_dir) / session_id
    )

    if not session_directory.exists():
        raise FileNotFoundError(
            f"Session directory not found: "
            f"{session_directory}"
        )

    if not session_directory.is_dir():
        raise ValueError(
            f"Session path is not a directory: "
            f"{session_directory}"
        )

    feedback_data = []

    for item in feedback:
        if not isinstance(item, FeedbackItem):
            raise TypeError(
                "Every feedback item must be a "
                "FeedbackItem instance."
            )

        feedback_data.append(
            {
                "category": item.category,
                "title": item.title,
                "issue": item.issue,
                "severity": item.severity,
                "evidence": item.evidence,
                "explanation": item.explanation,
                "recommendation": item.recommendation,
                "metadata": item.metadata,
            }
        )

    result = {
        "session_id": session_id,
        "scores": scores.as_dict(),
        "feedback": feedback_data,
    }

    output_path = (
        session_directory / "feedback.json"
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            result,
            file,
            indent=4,
            ensure_ascii=False,
        )

    return output_path