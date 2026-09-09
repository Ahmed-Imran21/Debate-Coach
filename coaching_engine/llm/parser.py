import json
from typing import Any, Dict, List

from ..models.feedback import FeedbackItem


VALID_CATEGORIES = {
    "argumentation",
    "rebuttal",
    "structure",
    "persuasion",
    "logic",
}

VALID_SEVERITIES = {
    "high",
    "medium",
    "low",
    "positive",
}


def parse_feedback_response(
    response: str,
) -> List[FeedbackItem]:
    """
    Parse an LLM response into FeedbackItem objects.

    The LLM is expected to return:

        {
            "feedback": [
                {
                    "category": "...",
                    "title": "...",
                    "issue": "...",
                    "severity": "...",
                    "evidence": [...],
                    "explanation": "...",
                    "recommendation": "...",
                    "metadata": {...}
                }
            ]
        }

    Args:
        response:
            Raw response returned by the LLM.

    Returns:
        A list of FeedbackItem objects.

    Raises:
        ValueError:
            If the response is invalid or does not follow the
            expected structure.
    """

    if not response or not response.strip():
        raise ValueError("LLM response is empty.")

    try:
        data = json.loads(response)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "LLM response is not valid JSON."
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            "LLM response must be a JSON object."
        )

    feedback_data = data.get("feedback")

    if not isinstance(feedback_data, list):
        raise ValueError(
            "LLM response must contain a 'feedback' list."
        )

    feedback_items: List[FeedbackItem] = []

    for index, item in enumerate(feedback_data):

        if not isinstance(item, dict):
            raise ValueError(
                f"Feedback item {index} must be a JSON object."
            )

        category = item.get("category")
        title = item.get("title")
        issue = item.get("issue")
        severity = item.get("severity")

        if not isinstance(category, str):
            raise ValueError(
                f"Feedback item {index} has an invalid category."
            )

        if category not in VALID_CATEGORIES:
            raise ValueError(
                f"Feedback item {index} has unsupported category: "
                f"{category}"
            )

        if not isinstance(title, str) or not title.strip():
            raise ValueError(
                f"Feedback item {index} has an invalid title."
            )

        if not isinstance(issue, str) or not issue.strip():
            raise ValueError(
                f"Feedback item {index} has an invalid issue."
            )

        if severity not in VALID_SEVERITIES:
            raise ValueError(
                f"Feedback item {index} has invalid severity: "
                f"{severity}"
            )

        evidence = item.get("evidence", [])

        if evidence is None:
            evidence = []

        if not isinstance(evidence, list):
            raise ValueError(
                f"Feedback item {index} has invalid evidence."
            )

        evidence = [
            str(value)
            for value in evidence
        ]

        explanation = item.get("explanation")

        if explanation is not None:
            explanation = str(explanation)

        recommendation = item.get("recommendation")

        if recommendation is not None:
            recommendation = str(recommendation)

        metadata = item.get("metadata", {})

        if metadata is None:
            metadata = {}

        if not isinstance(metadata, dict):
            raise ValueError(
                f"Feedback item {index} has invalid metadata."
            )

        feedback_items.append(
            FeedbackItem(
                category=category,
                title=title.strip(),
                issue=issue.strip(),
                severity=severity,
                evidence=evidence,
                explanation=explanation.strip()
                if explanation
                else None,
                recommendation=recommendation.strip()
                if recommendation
                else None,
                metadata=metadata,
            )
        )

    return feedback_items