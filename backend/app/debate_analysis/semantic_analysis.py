"""
semantic_analysis.py — the ONLY module in this package allowed to call an
LLM for judgment about argument content. Delivery metrics stay in
delivery_metrics.py (deterministic); this module handles meaning.

Hard rule: the model must return structured JSON and nothing else. No
freeform prose anywhere in this pipeline. If the model returns something
that doesn't parse as JSON, this raises rather than silently falling back
to a prose blob.

Scope: single-speaker only for this version. Do not add opponent/rebuttal
analysis here until the pipeline produces turn-segmentation data — see
project notes on why that's deferred.
"""

import json
from typing import Any

from groq import Groq
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings

_client = Groq(api_key=settings.groq_api_key)

# A general-purpose Groq chat model — separate concern from
# settings.groq_model, which is the Whisper transcription model.
_ANALYSIS_MODEL = "llama-3.3-70b-versatile"

_SYSTEM_PROMPT = """You are a debate analysis engine. You will be given the \
cleaned transcript of ONE speaker's debate speech (single-speaker only — \
there is no opponent turn to analyze). Analyze the substance of what was \
argued and respond with ONLY a JSON object, no prose before or after it, \
matching exactly this schema:

{
  "main_claims": [{"claim": string, "quote_snippet": string}],
  "arguments": [{"summary": string, "supporting_claims": [string], "strength": "strong"|"moderate"|"weak"}],
  "fallacies": [{"type": string, "explanation": string, "quote_snippet": string}],
  "persuasion_techniques": [{"technique": string, "explanation": string}],
  "strengths": [string],
  "weaknesses": [string]
}

Rules:
- quote_snippet fields must be short (under 15 words) and drawn from the transcript.
- If a category has nothing to report, return an empty list for it — never omit a key.
- Do not invent claims/arguments not present in the transcript.
- Output must be valid JSON and nothing else."""


class SemanticAnalysisError(Exception):
    pass


@retry(reraise=True, stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _call_llm(cleaned_transcript: str) -> str:
    response = _client.chat.completions.create(
        model=_ANALYSIS_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": cleaned_transcript},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return response.choices[0].message.content


_REQUIRED_KEYS = {
    "main_claims",
    "arguments",
    "fallacies",
    "persuasion_techniques",
    "strengths",
    "weaknesses",
}


def analyze_semantics(preprocessed: dict[str, Any]) -> dict[str, Any]:
    """Takes the output of preprocessing.build_llm_input(...) and returns
    the parsed, schema-checked JSON. This is what gets written to
    semantic_analysis.json."""
    cleaned_transcript = preprocessed["cleaned_transcript"]

    if not cleaned_transcript.strip():
        # Nothing substantive to analyze (e.g. a very short or filler-only
        # clip) — return a valid empty-shaped result instead of calling the
        # LLM on nothing.
        return {key: [] for key in _REQUIRED_KEYS}

    raw_output = _call_llm(cleaned_transcript)

    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise SemanticAnalysisError(f"Model did not return valid JSON: {exc}") from exc

    missing = _REQUIRED_KEYS - parsed.keys()
    if missing:
        raise SemanticAnalysisError(f"Model output missing required keys: {missing}")

    return parsed
