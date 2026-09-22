from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class KeyUsage(Base):
    """
    Persisted usage counters for one API key from
    api/key_registry.py, for the admin dashboard only.

    Deliberately separate from api/config.py's APIUsage (the
    in-memory, per-process object the rate limiter actually
    enforces against): this table survives restarts and is
    self-tracked from real provider responses, not estimated,
    but it is not consulted by the rate limiter — see that
    module's own "this is local accounting ... should be used
    later to reconcile it" note. This table is that reconciliation,
    for display, not enforcement.

    key_id is the natural primary key (api/config.py::load_api_keys()'s
    APIKey.id, e.g. "groq_gpt_oss_120b_1") since the set of keys is
    config-driven (.env), not user data — see migrations/0001_admin_dashboard.sql
    for the full column-by-column rationale, including why
    window_reset_at is computed differently per provider (Groq:
    rolling 24h; Gemini: fixed, next midnight Pacific Time) despite
    both fitting this one schema shape.

    display_label and the soft request/token limits shown on the
    dashboard are NOT columns here — they live in application
    config, so relabeling or re-limiting a key is a code change,
    not a migration.
    """

    __tablename__ = "key_usage"

    key_id: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )

    provider: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    request_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    prompt_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    completion_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    total_tokens: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # No default: the reset time is provider-specific (rolling vs.
    # fixed-clock) and must always be computed explicitly by
    # application code at insert/reset time, never left implicit.
    window_reset_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Latest snapshot only, overwritten each call that returns any
    # (e.g. Groq's x-ratelimit-remaining-requests/-tokens).
    # Supplementary — request_count/*_tokens above are the numbers
    # the dashboard actually trusts; not every provider (Gemini,
    # notably) returns these at all.
    last_rate_limit_headers: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
