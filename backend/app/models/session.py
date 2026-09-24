import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class SessionStatus(str, enum.Enum):
    created = "created"
    uploaded = "uploaded"
    transcribed = "transcribed"
    analyzed = "analyzed"
    debate_analyzed = "debate_analyzed"
    coached = "coached"
    completed = "completed"
    failed = "failed"


class DebateSession(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)

    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status"), default=SessionStatus.created, nullable=False
    )

    # Object storage keys (S3/R2), not local filesystem paths
    audio_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    transcription_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    analysis_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    delivery_metrics_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    semantic_analysis_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    coaching_report_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Which transcription provider actually served this session (for
    # debugging the fallback chain), e.g. "groq", "openai", "local_cpu"
    transcription_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)

    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="sessions")
