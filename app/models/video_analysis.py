"""
Video analysis state. Deliberately NOT columns on `sessions`:
the deployed schema is created by create_all(), which adds new
tables but never alters existing ones (no Alembic yet). Keeping
every new field in new tables means a plain deploy is enough.

No row in video_analyses  ==  video_analysis_status "not_requested".
"""

import uuid

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class VideoAnalysis(Base):
    __tablename__ = "video_analyses"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # awaiting_upload | received | processing | processed | partial
    # | insufficient_data | unavailable | failed
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="awaiting_upload")
    unavailable_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # not_requested | pending | completed | failed
    coaching_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_requested")

    schema_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    metrics_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(16), nullable=True)
    runtime_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    quality: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    signal_track_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    result_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    feedback_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Set when the stored track is consumed by analysis; a later
    # re-upload is refused once this is set.
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    # Child-side only. The parent DebateSession is not modified;
    # ON DELETE CASCADE on the FK removes this row when the
    # session row is deleted. Metrics are queried by session_id.
    session = relationship("DebateSession", viewonly=True)


class SessionMetric(Base):
    """
    One row per (session, metric, definition version), so a
    user's history can be queried per metric without opening
    every result document.
    """

    __tablename__ = "session_metrics"

    __table_args__ = (
        UniqueConstraint("session_id", "metric_key", "definition_version", name="uq_session_metric"),
        Index("ix_session_metrics_user_metric_time", "user_id", "metric_key", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    metric_key: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    definition_version: Mapped[str] = mapped_column(String(64), nullable=False)
    coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)

    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
