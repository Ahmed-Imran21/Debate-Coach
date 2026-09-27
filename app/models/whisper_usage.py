"""
One Whisper (transcription) attempt, for the admin dashboard
(migrations/0007). Display only: api/whisper.py's in-memory counters
still do the actual scheduling.
"""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


OUTCOMES = ("ok", "failed", "rate_limited")


class WhisperUsageEvent(Base):
    __tablename__ = "whisper_usage_events"

    __table_args__ = (
        Index("ix_whisper_usage_events_key_time", "key_id", "occurred_at"),
        CheckConstraint(
            "outcome IN ('ok', 'failed', 'rate_limited')",
            name="whisper_usage_events_outcome_check",
        ),
    )

    # BIGINT on Postgres (bigserial); INTEGER on SQLite, where only an
    # INTEGER PRIMARY KEY autoincrements.
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    key_id: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    audio_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
