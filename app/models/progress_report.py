"""
One AI progress report per user per UTC day (migrations/0004).
"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProgressReport(Base):
    __tablename__ = "progress_reports"

    __table_args__ = (
        # The once-per-day limit itself: the database refuses a second
        # row for the same user and UTC day, even if two generations
        # finish at the same moment.
        UniqueConstraint("user_id", "report_date", name="uq_progress_reports_user_day"),
        CheckConstraint("session_count_requested IN (3, 5, 7)", name="progress_reports_session_count_requested_check"),
        CheckConstraint("session_count_used BETWEEN 2 AND 7", name="progress_reports_session_count_used_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # UTC calendar day of generation.
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    session_count_requested: Mapped[int] = mapped_column(Integer, nullable=False)
    session_count_used: Mapped[int] = mapped_column(Integer, nullable=False)

    # Session ids compared, oldest first; {"bullets": [...]}, at most 5.
    session_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)

    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
