"""
Whisper (transcription) key usage for the admin dashboard.

Write path: record_whisper_usage() is WhisperClient's on_usage hook
(wired in app/services/engine.py), called once per transcription
attempt: successful, failed or rate-limited. One row per attempt in
whisper_usage_events (migrations/0007), so it survives restarts and
new deployments like key_usage does for the LLM keys.

Read path: get_whisper_usage_snapshot() gives the dashboard each
configured Whisper key's figures over rolling windows (last minute,
last hour, last 24 hours), which is how Groq enforces RPM/RPD and
ASH/ASD.
- Requests count every attempt: a failed call still uses the key's
  request allowance.
- Audio counts successful transcriptions only.
Key values are never read or returned, only key ids.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, func, select

from app.db.database import SessionLocal
from app.models.whisper_usage import OUTCOMES, WhisperUsageEvent

logger = logging.getLogger(__name__)

RETENTION = timedelta(days=30)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------
# Write path
# ---------------------------------------------------------------

def record_whisper_usage(key_id: str, *, audio_seconds: float, outcome: str, session_factory=None) -> None:
    """
    One row per attempt, and prune this key's rows older than 30
    days. Best-effort: never raises, because a dashboard counter must
    not break a transcription (WhisperClient also guards the call).
    """

    if outcome not in OUTCOMES:
        logger.warning("Ignoring Whisper usage with unknown outcome %r", outcome)
        return

    now = _now()
    db = (session_factory or SessionLocal)()
    try:
        db.add(
            WhisperUsageEvent(
                key_id=key_id,
                occurred_at=now,
                audio_seconds=max(0.0, float(audio_seconds or 0.0)),
                outcome=outcome,
            )
        )
        db.execute(
            delete(WhisperUsageEvent).where(
                WhisperUsageEvent.key_id == key_id,
                WhisperUsageEvent.occurred_at < now - RETENTION,
            )
        )
        db.commit()
    except Exception:
        logger.exception("Could not record Whisper usage for %s", key_id)
        db.rollback()
    finally:
        db.close()


# ---------------------------------------------------------------
# Read path: for GET /admin/stats
# ---------------------------------------------------------------

def whisper_label(key_id: str) -> str:
    return f"Whisper large-v3 — Key {key_id.rsplit('_', 1)[-1]} (transcription)"


def get_whisper_usage_snapshot(whisper_client, session_factory=None, now: datetime | None = None) -> list[dict]:
    """
    One entry per configured Whisper key (whisper_client.get_status(),
    which carries ids and limits, never key values), including keys
    never used yet (all zeros, last_used_at None).
    """

    now = now or _now()
    minute, hour, day = now - timedelta(minutes=1), now - timedelta(hours=1), now - timedelta(hours=24)
    keys = whisper_client.get_status()
    ids = [k["key_id"] for k in keys]

    E = WhisperUsageEvent
    ok = E.outcome == "ok"
    db = (session_factory or SessionLocal)()
    try:
        rows = {
            row.key_id: row
            for row in db.execute(
                select(
                    E.key_id,
                    func.count().filter(E.occurred_at >= minute).label("requests_last_minute"),
                    func.count().filter(E.occurred_at >= hour).label("requests_last_hour"),
                    func.count().filter(E.occurred_at >= day).label("requests_last_24h"),
                    func.coalesce(func.sum(E.audio_seconds).filter(and_(ok, E.occurred_at >= hour)), 0.0).label("audio_last_hour"),
                    func.coalesce(func.sum(E.audio_seconds).filter(and_(ok, E.occurred_at >= day)), 0.0).label("audio_last_24h"),
                    func.count().filter(and_(E.outcome == "failed", E.occurred_at >= day)).label("failed_last_24h"),
                    func.count().filter(and_(E.outcome == "rate_limited", E.occurred_at >= day)).label("rate_limited_last_24h"),
                    func.max(E.occurred_at).label("last_used_at"),
                )
                .where(E.key_id.in_(ids), E.occurred_at <= now)
                .group_by(E.key_id)
            )
        } if ids else {}
    finally:
        db.close()

    snapshot = []
    for key in keys:
        row = rows.get(key["key_id"])
        last_used = row.last_used_at if row else None
        if last_used is not None and last_used.tzinfo is None:  # SQLite drops the zone
            last_used = last_used.replace(tzinfo=timezone.utc)
        snapshot.append(
            {
                "key_id": key["key_id"],
                "label": whisper_label(key["key_id"]),
                "requests_last_minute": row.requests_last_minute if row else 0,
                "requests_last_hour": row.requests_last_hour if row else 0,
                "requests_last_24h": row.requests_last_24h if row else 0,
                "requests_per_minute_limit": key["rpm_limit"],
                "requests_per_day_limit": key["rpd_limit"],
                "audio_seconds_last_hour": round(float(row.audio_last_hour), 1) if row else 0.0,
                "audio_seconds_last_24h": round(float(row.audio_last_24h), 1) if row else 0.0,
                "audio_seconds_per_hour_limit": key["ash_limit"],
                "audio_seconds_per_day_limit": key["asd_limit"],
                "failed_last_24h": row.failed_last_24h if row else 0,
                "rate_limited_last_24h": row.rate_limited_last_24h if row else 0,
                "last_used_at": last_used,
            }
        )
    return snapshot
