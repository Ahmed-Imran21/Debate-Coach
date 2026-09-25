import enum
import uuid

from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class SessionStatus(str, enum.Enum):
    """
    Mirrors the stages in app/services/pipeline.py exactly.

    Every value here is written by the pipeline runner as it
    moves through the same steps the CLI pipeline already ran,
    so the web client can show real progress rather than a
    generic spinner.
    """

    created = "created"
    queued = "queued"
    converting = "converting"
    transcribing = "transcribing"
    analyzing_audio = "analyzing_audio"
    calculating_metrics = "calculating_metrics"
    analyzing_speech = "analyzing_speech"
    coaching = "coaching"
    completed = "completed"
    failed = "failed"


# Ordered for progress display. Terminal states are excluded.
PIPELINE_STAGES = [
    SessionStatus.queued,
    SessionStatus.converting,
    SessionStatus.transcribing,
    SessionStatus.analyzing_audio,
    SessionStatus.calculating_metrics,
    SessionStatus.analyzing_speech,
    SessionStatus.coaching,
]


class DebateSession(Base):
    __tablename__ = "sessions"

    # Serves GET /v1/sessions/progress: one user's completed sessions
    # by created_at. Also created by migrations/0003 on existing
    # databases (create_all() never alters an existing table).
    __table_args__ = (
        Index("ix_sessions_user_status_created", "user_id", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status"),
        default=SessionStatus.created,
        nullable=False,
    )

    # ---------------------------------------------------------
    # Object storage keys (S3/R2), not local filesystem paths
    # ---------------------------------------------------------

    upload_object_key: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )

    audio_object_key: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )

    transcription_object_key: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )

    analysis_object_key: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )

    raw_metrics_object_key: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )

    speech_content_object_key: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )

    coaching_object_key: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )

    # ---------------------------------------------------------
    # Progress and results
    # ---------------------------------------------------------

    # Set when a request is parked by api/scheduler.py waiting
    # for key capacity. Surfaced to the client so a long wait
    # reads as "queued for N seconds" and not as a stall.
    queue_wait_seconds: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    # Denormalized headline numbers so the session list renders
    # without fetching every report from object storage.
    overall_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    duration_seconds: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    words_per_minute: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    feedback_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Per-category coaching scores (0-100), copied from feedback.json
    # when coaching completes so the progress graph never reads
    # object storage. score_rebuttal is None when the speech had
    # nothing to rebut ("not scored", not zero). Added by
    # migrations/0003; older sessions filled by
    # scripts/backfill_category_scores.py.
    score_argumentation: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_rebuttal: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_structure: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_persuasion: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_logic: Mapped[float | None] = mapped_column(Float, nullable=True)

    error_message: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )

    extra: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # ---------------------------------------------------------
    # Timestamps
    # ---------------------------------------------------------

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="sessions")

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    @property
    def progress(self) -> float:
        """
        Fraction of the pipeline completed, 0.0 to 1.0.
        """

        if self.status == SessionStatus.completed:
            return 1.0

        if self.status in (
            SessionStatus.created,
            SessionStatus.failed,
        ):
            return 0.0

        try:
            index = PIPELINE_STAGES.index(self.status)
        except ValueError:
            return 0.0

        return round(
            index / len(PIPELINE_STAGES),
            2,
        )
