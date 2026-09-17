"""
The one module in visual_coaching/ that calls the LLM (§7.1).

Orchestrates: build the session timeline and correlated moments
(§6), assemble the deterministic prompt payload that never contains
a raw number (§7.2), call the LLM in JSON mode using the same
provider/model selection as the existing coaching_engine LLM client,
validate the response with one retry on a rules-3-5 (or structural)
violation (§7.5), and return the document ready to persist as
visual_feedback.json. Never raises for an LLM/validation failure --
that's a "failed" outcome with metrics and moments still intact, not
a session failure (§7.1: "Failure -> failed; metrics and moments are
still stored and shown").
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from pydantic import ValidationError

from api.client import APIClient
from session_timeline.correlation import build_correlated_moments
from session_timeline.timeline import build_timeline

from . import prompt as prompt_module
from . import validator as validator_module


logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"
PROMPT_VERSION = "visual-coaching-1.0"

# Same provider/model selection as coaching_engine/llm/client.py's
# LLMClient (§7.1: "same provider/model selection logic as existing
# coaching"). response_format="json" is passed explicitly here even
# though the existing coaching client doesn't pass it -- §7.3 itself
# requires JSON-only output for this call, and §0.3.2 requires JSON
# mode for every LLM call in this feature.
PROVIDER = "groq"
MODEL = "openai/gpt-oss-120b"
ESTIMATED_OUTPUT_TOKENS = 2000


@dataclass
class VisualCoachingOutcome:
    status: str  # "completed" | "failed"
    document: dict


def _call_llm(
    api_client: APIClient,
    user_prompt: str,
    retry_message: Optional[str],
    on_queued: Optional[Callable[[float], None]],
) -> dict:
    messages = [
        {"role": "system", "content": prompt_module.SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    if retry_message:
        messages.append({"role": "user", "content": retry_message})

    estimated_input_tokens = max(1, sum(len(m["content"]) for m in messages) // 4)

    response = api_client.generate(
        task="visual_coaching",
        estimated_tokens=estimated_input_tokens + ESTIMATED_OUTPUT_TOKENS,
        provider=PROVIDER,
        model=MODEL,
        messages=messages,
        max_tokens=ESTIMATED_OUTPUT_TOKENS,
        temperature=0.2,
        on_queued=on_queued,
        response_format="json",
    )

    if not response.success:
        raise RuntimeError(f"Visual coaching LLM request failed: {response.error}")
    if not response.content:
        raise RuntimeError("Visual coaching LLM returned an empty response.")

    return json.loads(response.content)


def _retry_message(violated_rules: list[str]) -> str:
    # "appending a message that lists the violated rules (not the
    # text)" -- so the offending coaching/summary text itself is
    # never echoed back, only the rule names.
    return (
        "Your previous response violated these rules: "
        + ", ".join(violated_rules)
        + ". Return corrected JSON matching the same schema, with every item satisfying all rules."
    )


def generate_visual_coaching(
    session_id: str,
    transcription: dict,
    audio_analysis: dict,
    raw_metrics: dict,
    speech_content: dict,
    video_analysis: dict,
    api_client: APIClient,
    on_queued: Optional[Callable[[float], None]] = None,
) -> VisualCoachingOutcome:
    timeline = build_timeline(session_id, transcription, audio_analysis, raw_metrics, speech_content, video_analysis)
    moments = build_correlated_moments(timeline, video_analysis)

    speech_duration_s = audio_analysis.get("speech_duration", 0.0)
    payload = prompt_module.build_input_payload(video_analysis, moments, speech_content.get("segments", []), speech_duration_s)
    user_prompt = prompt_module.build_user_prompt(payload)

    items: list[dict] = []
    summary = ""
    retried = False
    dropped_items = 0

    try:
        raw = _call_llm(api_client, user_prompt, None, on_queued)
        response = validator_module.parse_response(raw)
        outcome = validator_module.validate(response, payload)

        if outcome.violated_rules:
            retried = True  # set before the retry call, so a retry that itself raises is still recorded as attempted
            retry_raw = _call_llm(api_client, user_prompt, _retry_message(outcome.violated_rules), on_queued)
            retry_response = validator_module.parse_response(retry_raw)
            outcome = validator_module.validate(retry_response, payload)

        items = outcome.items
        summary = outcome.summary
        dropped_items = outcome.dropped_count

    except (RuntimeError, ValidationError, json.JSONDecodeError):
        logger.exception("Visual coaching failed for session %s", session_id)

    status = "completed" if items else "failed"

    document = {
        "schema_version": SCHEMA_VERSION,
        "metrics_version": video_analysis.get("metrics_version"),
        "prompt_version": PROMPT_VERSION,
        "model": MODEL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "correlated_moments": moments,
        "visual_feedback": items,
        "summary": summary,
        "validation": {"retried": retried, "dropped_items": dropped_items},
    }

    return VisualCoachingOutcome(status=status, document=document)
