import uuid

from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Nullable: never set until this user's next authenticated
    # request after the column exists. Touched by the last-seen
    # middleware on every authenticated call and by POST /heartbeat
    # (admin dashboard's "active now" — see migrations/0001_admin_dashboard.sql).
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # passive_deletes lets the database's ON DELETE CASCADE do
    # the work instead of SQLAlchemy loading every session row
    # into memory first.
    sessions = relationship(
        "DebateSession",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
