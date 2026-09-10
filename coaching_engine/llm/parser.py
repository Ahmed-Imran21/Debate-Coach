import json
from typing import List

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
    Parse a structured Groq response into FeedbackItem objects.

    The Groq API is expected to have already validated the
    response against FEEDBACK_RESPONSE_SCHEMA.
    """

    if not response or not response.strip():
        raise ValueError(
            "LLM response is empty."
        )

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

        # --------------------------------------------------
        # Required fields
        # --------------------------------------------------

        required_fields = {
            "category",
            "title",
            "issue",
            "severity",
            "evidence",
            "explanation",
            "recommendation",
            "metadata",
        }

        missing_fields = (
            required_fields - item.keys()
        )

        if missing_fields:
            raise ValueError(
                f"Feedback item {index} is missing required "
                f"fields: {sorted(missing_fields)}"
            )

        category = item["category"]
        title = item["title"]
        issue = item["issue"]
        severity = item["severity"]
        evidence = item["evidence"]
        explanation = item["explanation"]
        recommendation = item["recommendation"]
        metadata = item["metadata"]

        # --------------------------------------------------
        # Category
        # --------------------------------------------------

        if not isinstance(category, str):
            raise ValueError(
                f"Feedback item {index} has an invalid category."
            )

        if category not in VALID_CATEGORIES:
            raise ValueError(
                f"Feedback item {index} has unsupported category: "
                f"{category}"
            )

        # --------------------------------------------------
        # Text fields
        # --------------------------------------------------

        text_fields = {
            "title": title,
            "issue": issue,
            "explanation": explanation,
            "recommendation": recommendation,
        }

        for field_name, value in text_fields.items():

            if not isinstance(value, str):
                raise ValueError(
                    f"Feedback item {index} field "
                    f"'{field_name}' must be a string."
                )

            if not value.strip():
                raise ValueError(
                    f"Feedback item {index} field "
                    f"'{field_name}' cannot be empty."
                )

        # --------------------------------------------------
        # Severity
        # --------------------------------------------------

        if severity not in VALID_SEVERITIES:
            raise ValueError(
                f"Feedback item {index} has invalid severity: "
                f"{severity}"
            )

        # --------------------------------------------------
        # Evidence
        # --------------------------------------------------

        if not isinstance(evidence, list):
            raise ValueError(
                f"Feedback item {index} evidence must be a list."
            )

        for evidence_item in evidence:

            if not isinstance(
                evidence_item,
                str,
            ):
                raise ValueError(
                    f"Feedback item {index} evidence "
                    "items must be strings."
                )

        # --------------------------------------------------
        # Metadata
        # --------------------------------------------------

        if not isinstance(metadata, dict):
            raise ValueError(
                f"Feedback item {index} metadata must be "
                "an object."
            )

        # --------------------------------------------------
        # Build FeedbackItem
        # --------------------------------------------------

        feedback_items.append(
            FeedbackItem(
                category=category,
                title=title.strip(),
                issue=issue.strip(),
                severity=severity,
                evidence=[
                    value.strip()
                    for value in evidence
                    if value.strip()
                ],
                explanation=explanation.strip(),
                recommendation=recommendation.strip(),
                metadata=metadata,
            )
        )

    return feedback_items