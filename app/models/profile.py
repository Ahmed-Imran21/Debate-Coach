"""
The profile page's own data (migrations/0008).

UserProfile: optional username and bio, the weekly goal and the
user's time zone. One row per user at most, created the first time
they save something; no row means every default. Kept out of the
users table on purpose, so nothing that reads users (admin, shares,
exports) can ever pick up the username or bio.

SessionDeliveryScore: a cache of each completed session's Delivery
(quantitative) score, which otherwise lives only in feedback.json.
Filled by app/services/profile.py on first use.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


DEFAULT_WEEKLY_GOAL = 3


class UserProfile(Base):
    __tablename__ = "user_profiles"

    __table_args__ = (
        # Postgres only: SQLite has no regex operator.
        CheckConstraint("username ~ '^[a-z0-9_]{3,20}$'", name="user_profiles_username_format").ddl_if(
            dialect="postgresql"
        ),
        CheckConstraint("weekly_goal BETWEEN 1 AND 7", name="user_profiles_weekly_goal_range"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    username: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bio: Mapped[str | None] = mapped_column(String(160), nullable=True)
    weekly_goal: Mapped[int] = mapped_column(SmallInteger, default=DEFAULT_WEEKLY_GOAL, nullable=False)
    time_zone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


# Case-insensitive uniqueness, enforced by the database.
Index("uq_user_profiles_username_lower", func.lower(UserProfile.username), unique=True)


class SessionDeliveryScore(Base):
    __tablename__ = "session_delivery_scores"

    __table_args__ = (
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="session_delivery_scores_range"),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # None: the session's feedback.json has no usable Delivery score.
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
