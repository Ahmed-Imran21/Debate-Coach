import json
from typing import Dict, List, Tuple, Union

from ..models.feedback import FeedbackItem
from .prompts import CONTENT_CATEGORIES, NOT_APPLICABLE


VALID_SEVERITIES = {"high", "medium", "low", "positive"}

MAX_EVIDENCE = 3

RubricLevel = Union[int, str]


def _parse_item(index: int, item: object) -> FeedbackItem:
    if not isinstance(item, dict):
        raise ValueError(f"Feedback item {index} must be a JSON object.")

    category = item.get("category")
    if category not in CONTENT_CATEGORIES:
        raise ValueError(f"Feedback item {index} has unsupported category: {category!r}")

    severity = item.get("severity")
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"Feedback item {index} has invalid severity: {severity!r}")

    text = {}
    for field in ("title", "issue", "explanation", "recommendation"):
        value = item.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Feedback item {index} field '{field}' must be a non-empty string.")
        text[field] = value.strip()

    # Supporting fields are trimmed, not fatal: one stray entry must not
    # discard an otherwise good response.
    evidence = [e.strip() for e in item.get("evidence") or [] if isinstance(e, str) and e.strip()]

    also_affects: List[str] = []
    for other in item.get("also_affects") or []:
        if other in CONTENT_CATEGORIES and other != category and other not in also_affects:
            also_affects.append(other)

    return FeedbackItem(
        category=category,
        title=text["title"],
        issue=text["issue"],
        severity=severity,
        evidence=evidence[:MAX_EVIDENCE],
        explanation=text["explanation"],
        recommendation=text["recommendation"],
        metadata={"also_affects": also_affects} if also_affects else {},
    )


def _parse_level(category: str, entry: object) -> RubricLevel:
    if not isinstance(entry, dict):
        raise ValueError(f"Rubric entry for {category} must be an object.")

    level = entry.get("level")

    if level == NOT_APPLICABLE:
        if category != "rebuttal":
            raise ValueError(f"'{NOT_APPLICABLE}' is only valid for rebuttal, not {category}.")
        return NOT_APPLICABLE

    if isinstance(level, str) and level.strip().isdigit():
        level = int(level.strip())

    if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= 5:
        raise ValueError(f"Rubric level for {category} must be 1-5, got {level!r}.")

    return level


def parse_synthesis_response(
    response: str,
) -> Tuple[List[FeedbackItem], Dict[str, RubricLevel], Dict[str, str]]:
    """
    Returns (feedback items, rubric levels by category, rubric reasons
    by category). Raises ValueError if the response can't be used; the
    engine then falls back to its deterministic rules.
    """

    if not response or not response.strip():
        raise ValueError("LLM response is empty.")

    try:
        data = json.loads(response)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM response is not valid JSON.") from exc

    if not isinstance(data, dict):
        raise ValueError("LLM response must be a JSON object.")

    feedback_data = data.get("feedback")
    if not isinstance(feedback_data, list) or not feedback_data:
        raise ValueError("LLM response must contain a non-empty 'feedback' list.")

    items = [_parse_item(index, item) for index, item in enumerate(feedback_data)]

    rubric_data = data.get("rubric")
    if not isinstance(rubric_data, dict):
        raise ValueError("LLM response must contain a 'rubric' object.")

    missing = [c for c in CONTENT_CATEGORIES if c not in rubric_data]
    if missing:
        raise ValueError(f"Rubric is missing categories: {missing}")

    levels = {c: _parse_level(c, rubric_data[c]) for c in CONTENT_CATEGORIES}
    reasons = {
        c: rubric_data[c].get("reason", "").strip()
        for c in CONTENT_CATEGORIES
        if isinstance(rubric_data[c].get("reason"), str)
    }

    opposing_view = rubric_data["rebuttal"].get("opposing_view")
    if isinstance(opposing_view, str) and opposing_view.strip():
        reasons["rebuttal_opposing_view"] = opposing_view.strip()

    return items, levels, reasons
