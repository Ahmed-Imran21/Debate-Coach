"""
coaching.py — the final synthesis layer. Combines the deterministic
delivery metrics with the LLM-derived semantic analysis into one coaching
report. Makes one LLM call (Groq) to turn the two structured inputs into
structured, actionable coaching output — still JSON, never freeform prose
stored as-is; the JSON fields themselves contain short natural-language
strings, but the shape is fixed and validated.
"""

import json
from typing import Any

from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

_client = Groq(api_key=settings.groq_api_key)
_COACHING_MODEL = "llama-3.3-70b-versatile"

_SYSTEM_PROMPT = """You are a debate coach. You will be given two JSON \
objects: `delivery_metrics` (deterministic facts about pacing, filler \
words, and pauses) and `semantic_analysis` (an analysis of the speaker's \
arguments, claims, fallacies, and persuasion techniques). Combine them \
into ONE coaching report for the speaker. Respond with ONLY a JSON object, \
no prose before or after it, matching exactly this schema:

{
  "overall_summary": string,
  "top_strengths": [string],
  "top_areas_to_improve": [string],
  "delivery_feedback": string,
  "argument_feedback": string,
  "action_items": [string]
}

Rules:
- Ground every point in the specific numbers/findings you were given — do not invent facts not present in the two input objects.
- Keep each string field concise (a few sentences at most for the feedback fields, one sentence per list item).
- top_strengths, top_areas_to_improve, and action_items should each have 2-5 items.
- Output must be valid JSON and nothing else."""


class CoachingError(Exception):
    pass


_REQUIRED_KEYS = {
    "overall_summary",
    "top_strengths",
    "top_areas_to_improve",
    "delivery_feedback",
    "argument_feedback",
    "action_items",
}


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _call_llm(delivery_metrics: dict[str, Any], semantic_analysis: dict[str, Any]) -> str:
    user_payload = json.dumps(
        {"delivery_metrics": delivery_metrics, "semantic_analysis": semantic_analysis}
    )
    response = _client.chat.completions.create(
        model=_COACHING_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_payload},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    return response.choices[0].message.content


def generate_coaching_report(
    delivery_metrics: dict[str, Any],
    semantic_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Entry point for this module. Returns the parsed, schema-checked
    JSON that gets written to coaching_report.json."""
    raw_output = _call_llm(delivery_metrics, semantic_analysis)

    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise CoachingError(f"Model did not return valid JSON: {exc}") from exc

    missing = _REQUIRED_KEYS - parsed.keys()
    if missing:
        raise CoachingError(f"Model output missing required keys: {missing}")

    # Keep the raw inputs alongside the narrative report so the client can
    # render charts/numbers without a second round trip.
    parsed["delivery_snapshot"] = delivery_metrics
    parsed["semantic_snapshot"] = semantic_analysis
    return parsed
