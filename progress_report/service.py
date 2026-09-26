"""
The one module in progress_report/ that calls the LLM. Same provider
and model as coaching_engine and visual_coaching, through the shared
key pool, in JSON mode. One retry when the answer is unusable; a
failed request (provider error, or no key capacity within
MAX_WAIT_SECONDS) fails straight away. Either way the caller gets
ProgressReportFailed and stores nothing, so a failure never uses up
the user's daily report.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from api.client import APIClient

from . import prompt as prompt_module
from . import validator as validator_module

logger = logging.getLogger(__name__)

PROVIDER = "groq"
MODEL = "openai/gpt-oss-120b"
ESTIMATED_OUTPUT_TOKENS = 1500
ATTEMPTS = 2

# This runs inside a web request, not a background job: wait at most
# this long for key capacity rather than hold the request open.
MAX_WAIT_SECONDS = 30.0


class ProgressReportFailed(RuntimeError):
    pass


def _call(api_client: APIClient, user_prompt: str, on_queued: Optional[Callable[[float], None]]) -> str:
    messages = [
        {"role": "system", "content": prompt_module.SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    estimated_input_tokens = max(1, sum(len(m["content"]) for m in messages) // 4)
    response = api_client.generate(
        task="progress_report",
        estimated_tokens=estimated_input_tokens + ESTIMATED_OUTPUT_TOKENS,
        provider=PROVIDER,
        model=MODEL,
        messages=messages,
        max_tokens=ESTIMATED_OUTPUT_TOKENS,
        temperature=0.3,
        max_wait_seconds=MAX_WAIT_SECONDS,
        on_queued=on_queued,
        response_format="json",
    )
    if not response.success or not response.content:
        raise ProgressReportFailed(f"LLM request failed: {response.error or 'empty response'}")
    return response.content


def generate_bullets(
    summaries: list[dict],
    api_client: APIClient,
    on_queued: Optional[Callable[[float], None]] = None,
) -> list[str]:
    user_prompt = prompt_module.build_user_prompt(summaries)

    for attempt in range(ATTEMPTS):
        content = _call(api_client, user_prompt, on_queued)
        try:
            outcome = validator_module.validate(content)
        except validator_module.InvalidReport as exc:
            logger.warning("Progress report attempt %d unusable: %s", attempt + 1, exc)
            continue
        if outcome.dropped:
            logger.info("Progress report: dropped %d bullet(s)", outcome.dropped)
        return outcome.bullets

    raise ProgressReportFailed("LLM returned no usable bullets")
