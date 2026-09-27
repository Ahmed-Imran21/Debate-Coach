"""
A shareable read-only link to one session's report (migrations/0006).
Only the SHA-256 of the token is stored.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CHAR, DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SessionShare(Base):
    __tablename__ = "session_shares"

    __table_args__ = (
        # At most one active link per session.
        Index(
            "uq_session_shares_one_active",
            "session_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Hex SHA-256 of the token; the token itself is never stored.
    token_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False, unique=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
