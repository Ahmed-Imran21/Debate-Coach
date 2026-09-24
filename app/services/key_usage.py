import json
import logging

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.db.database import SessionLocal
from app.models.key_usage import KeyUsage


logger = logging.getLogger(__name__)

_PACIFIC = ZoneInfo("America/Los_Angeles")

# ---------------------------------------------------------------
# Display config — the "identifier -> label -> soft limits"
# mapping. Deliberately NOT a full per-key dict: labels are
# something to actually control by hand, but request/token
# limits already exist, correctly, in api/config.py's KEY_CONFIGS
# (APIKey.limits.rpd/.tpd) — duplicating them here would just be
# a second place for the two numbers to drift apart. Soft limits
# default to those real provider limits and only need an entry
# below to run tighter than that on the dashboard specifically.
# ---------------------------------------------------------------

FRIENDLY_MODEL_NAMES: dict[str, str] = {
    "openai/gpt-oss-120b": "gpt-oss-120b",
    "llama-3.3-70b-versatile": "llama-3.3-70b",
    "gemini-2.5-flash": "gemini-2.5-flash",
}

# key_id -> (soft_request_limit, soft_token_limit). Empty by
# default; add an entry to run a key's dashboard warning threshold
# below its real provider limit.
SOFT_LIMIT_OVERRIDES: dict[str, tuple[int, int]] = {}


def display_label(api_key) -> str:
    friendly = FRIENDLY_MODEL_NAMES.get(api_key.model, api_key.model)
    key_number = api_key.id.rsplit("_", 1)[-1]
    return f"{friendly} — Key {key_number}"


def _soft_limits(api_key) -> tuple[int, int]:
    return SOFT_LIMIT_OVERRIDES.get(
        api_key.id,
        (api_key.limits.rpd, api_key.limits.tpd),
    )


# ---------------------------------------------------------------
# Window reset semantics — confirmed different per provider
# (2026-09-22): Groq's own x-ratelimit-reset-* headers express a
# duration until refill (a rolling window, not a fixed clock
# time); Gemini's documented daily quota resets at a fixed clock
# time, midnight Pacific — not UTC, and not rolling. The existing
# api/rate_limiter.py treats both as UTC-midnight for its own
# in-memory enforcement, which is a reasonable internal
# approximation for throttling but not accurate enough for this
# table, which is meant to reconcile against what actually
# happened per provider.
# ---------------------------------------------------------------

def _fresh_window(provider: str, now: datetime) -> tuple[datetime, datetime]:
    if provider == "gemini":
        return now, _next_midnight_pacific(now)
    # groq, and any future provider without its own rule: rolling
    # 24h from now, the same shape Groq's reset-* headers imply.
    return now, now + timedelta(hours=24)


def _next_midnight_pacific(now: datetime) -> datetime:
    now_pt = now.astimezone(_PACIFIC)
    next_midnight_pt = now_pt.replace(
        hour=0, minute=0, second=0, microsecond=0
    ) + timedelta(days=1)
    return next_midnight_pt.astimezone(timezone.utc)


# ---------------------------------------------------------------
# Token extraction — Groq (OpenAI-shaped) vs Gemini field names
# differ; both are handled explicitly rather than guessed at.
# ---------------------------------------------------------------

def _extract_tokens(provider: str, usage: Any) -> tuple[int, int, int]:
    if usage is None:
        return 0, 0, 0

    if provider == "groq":
        prompt = getattr(usage, "prompt_tokens", 0) or 0
        completion = getattr(usage, "completion_tokens", 0) or 0
        total = getattr(usage, "total_tokens", None)

    elif provider == "gemini":
        prompt = getattr(usage, "prompt_token_count", 0) or 0
        completion = getattr(usage, "candidates_token_count", 0) or 0
        total = getattr(usage, "total_token_count", None)

    else:
        return 0, 0, 0

    if total is None:
        total = prompt + completion

    return prompt, completion, total


# ---------------------------------------------------------------
# Write path — called from api/client.py's on_usage hook
# ---------------------------------------------------------------

def record_usage(
    key_id: str,
    provider: str,
    *,
    ok: bool,
    usage: Any = None,
    rate_limit_headers: dict | None = None,
) -> None:
    """
    One atomic upsert per call, right alongside the existing
    usage_tracker.record_*() calls in api/client.py — this
    module has no dependency on api/ or vice versa; the hook
    (APIClient(on_usage=...), wired in app/services/engine.py)
    is what connects them, matching the layering
    speech_analysis/'s SpeechAnalysisValidationError already
    established: api/ (like speech_analysis/, audio/) never
    imports from app/.

    ok=False (a rate-limited or otherwise failed call) still
    counts as a request — the key's real rate-limit budget was
    consumed either way — but contributes zero tokens, since a
    failed call has none to report.

    The single UPSERT below handles three cases in one atomic
    statement: no row yet (INSERT), row within its current
    window (increment), row whose window has already lapsed
    (reset to just this call's counts, start a fresh window).
    Concurrent calls are safe: Postgres serializes UPDATEs to the
    same row, so two racing calls can't both reset the same
    lapsed window — whichever commits second sees the first's
    already-fresh window and just increments into it normally.
    """

    prompt_tokens, completion_tokens, total_tokens = (
        _extract_tokens(provider, usage) if ok else (0, 0, 0)
    )

    now = datetime.now(timezone.utc)
    fresh_start, fresh_reset_at = _fresh_window(provider, now)
    headers_json = json.dumps(rate_limit_headers) if rate_limit_headers else None

    db = SessionLocal()

    try:
        db.execute(
            text(
                """
                INSERT INTO key_usage (
                    key_id, provider, request_count, prompt_tokens,
                    completion_tokens, total_tokens, window_start,
                    window_reset_at, last_rate_limit_headers,
                    created_at, updated_at
                ) VALUES (
                    :key_id, :provider, 1, :prompt_tokens,
                    :completion_tokens, :total_tokens, :fresh_start,
                    :fresh_reset_at, CAST(:headers AS jsonb), :now, :now
                )
                ON CONFLICT (key_id) DO UPDATE SET
                    request_count = CASE
                        WHEN key_usage.window_reset_at <= :now THEN 1
                        ELSE key_usage.request_count + 1
                    END,
                    prompt_tokens = CASE
                        WHEN key_usage.window_reset_at <= :now THEN :prompt_tokens
                        ELSE key_usage.prompt_tokens + :prompt_tokens
                    END,
                    completion_tokens = CASE
                        WHEN key_usage.window_reset_at <= :now THEN :completion_tokens
                        ELSE key_usage.completion_tokens + :completion_tokens
                    END,
                    total_tokens = CASE
                        WHEN key_usage.window_reset_at <= :now THEN :total_tokens
                        ELSE key_usage.total_tokens + :total_tokens
                    END,
                    window_start = CASE
                        WHEN key_usage.window_reset_at <= :now THEN :fresh_start
                        ELSE key_usage.window_start
                    END,
                    window_reset_at = CASE
                        WHEN key_usage.window_reset_at <= :now THEN :fresh_reset_at
                        ELSE key_usage.window_reset_at
                    END,
                    last_rate_limit_headers = COALESCE(
                        CAST(:headers AS jsonb), key_usage.last_rate_limit_headers
                    ),
                    updated_at = :now
                """
            ),
            {
                "key_id": key_id,
                "provider": provider,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "fresh_start": fresh_start,
                "fresh_reset_at": fresh_reset_at,
                "headers": headers_json,
                "now": now,
            },
        )
        db.commit()

    except Exception:
        # Best-effort: a dashboard-counter failure must never
        # break the actual LLM call it's reporting on.
        logger.exception("Could not record key usage for %s", key_id)
        db.rollback()

    finally:
        db.close()


# ---------------------------------------------------------------
# Read path — for GET /admin/stats
# ---------------------------------------------------------------

def get_usage_snapshot(api_client) -> list[dict]:
    """
    One entry per currently configured key (api_client.get_keys()),
    including keys never yet used (all-zero row). A row whose
    window has already lapsed but hasn't been reset by a new call
    yet (the key just hasn't been used since) is displayed as 0,
    not its stale pre-lapse counts.
    """

    db = SessionLocal()
    try:
        rows = {row.key_id: row for row in db.query(KeyUsage).all()}
    finally:
        db.close()

    now = datetime.now(timezone.utc)
    snapshot = []

    for api_key in api_client.get_keys():
        row = rows.get(api_key.id)
        lapsed = row is not None and row.window_reset_at <= now

        requests_used = 0 if (row is None or lapsed) else row.request_count
        prompt_tokens = 0 if (row is None or lapsed) else row.prompt_tokens
        completion_tokens = 0 if (row is None or lapsed) else row.completion_tokens
        tokens_used = 0 if (row is None or lapsed) else row.total_tokens

        soft_requests, soft_tokens = _soft_limits(api_key)

        snapshot.append(
            {
                "key_id": api_key.id,
                "label": display_label(api_key),
                "provider": api_key.provider,
                "requests_used": requests_used,
                "requests_limit": soft_requests,
                "requests_remaining": max(0, soft_requests - requests_used),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "tokens_used": tokens_used,
                "tokens_limit": soft_tokens,
                "tokens_remaining": max(0, soft_tokens - tokens_used),
                "window_reset_at": (
                    None if (row is None or lapsed) else row.window_reset_at.isoformat()
                ),
                "last_rate_limit_headers": (
                    None if row is None else row.last_rate_limit_headers
                ),
            }
        )

    return snapshot
