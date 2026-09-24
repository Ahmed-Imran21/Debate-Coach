"""
The admin user list: keyset (cursor) pagination, substring search,
and a per-row session count — each built to cost the same on page
1,000 as on page 1. See migrations/0002_admin_user_management.sql
for the indexes these queries are shaped around.
"""

import base64
import binascii
import json
import uuid

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import and_, func, literal_column, or_, select, tuple_
from sqlalchemy.orm import Session

from app.models.session import DebateSession
from app.models.user import User


Sort = Literal["newest", "last_seen"]

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


class InvalidCursorError(ValueError):
    pass


@dataclass(frozen=True)
class UserRow:
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    created_at: datetime
    last_seen_at: datetime | None
    session_count: int


def _normalize_search(search: str | None) -> str:
    return (search or "").strip().lower()


def encode_cursor(sort: Sort, search: str | None, row: UserRow) -> str:
    at = row.created_at if sort == "newest" else row.last_seen_at
    payload = {
        "sort": sort,
        "q": _normalize_search(search),
        "at": at.isoformat() if at is not None else None,
        "id": str(row.id),
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def decode_cursor(raw: str, sort: Sort, search: str | None) -> tuple[datetime | None, uuid.UUID]:
    """
    The cursor records the sort and search it was issued for; reusing
    it with different ones would resume from a position in a different
    ordering, so that's refused rather than silently misread.
    """
    try:
        padded = raw + "=" * (-len(raw) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
        if payload["sort"] != sort or payload["q"] != _normalize_search(search):
            raise InvalidCursorError("cursor is for a different sort or search")
        at = datetime.fromisoformat(payload["at"]) if payload["at"] is not None else None
        if at is None and sort == "newest":
            raise InvalidCursorError("newest cursor without a timestamp")
        return at, uuid.UUID(payload["id"])
    except InvalidCursorError:
        raise
    except (binascii.Error, UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError("malformed cursor") from exc


# Must match idx_users_search_trgm's expression exactly (migration
# 0002), constants inline rather than bound, or the index won't apply.
SEARCH_TEXT = (
    User.email
    + literal_column("' '")
    + User.first_name
    + literal_column("' '")
    + User.last_name
)


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_users(
    db: Session,
    *,
    sort: Sort = "newest",
    search: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
    cursor: str | None = None,
) -> tuple[list[UserRow], str | None]:
    limit = max(1, min(limit, MAX_PAGE_SIZE))

    page = select(
        User.id,
        User.email,
        User.first_name,
        User.last_name,
        User.created_at,
        User.last_seen_at,
    )

    term = _normalize_search(search)
    if term:
        # One ILIKE over the joined fields, served by the trigram index
        # on that same expression (idx_users_search_trgm); an OR across
        # the three columns made Postgres fall back to a full scan. The
        # term's own % and _ are escaped so they match literally.
        page = page.where(
            SEARCH_TEXT.ilike(f"%{_escape_like(term)}%", escape="\\")
        )

    if sort == "newest":
        if cursor:
            at, after_id = decode_cursor(cursor, sort, search)
            page = page.where(tuple_(User.created_at, User.id) < tuple_(at, after_id))
        page = page.order_by(User.created_at.desc(), User.id.desc())
    else:
        # Users never seen come last, in id order. A cursor inside that
        # group only moves along id; one before it also admits the whole
        # group, which follows every seen user.
        if cursor:
            at, after_id = decode_cursor(cursor, sort, search)
            if at is None:
                page = page.where(and_(User.last_seen_at.is_(None), User.id < after_id))
            else:
                page = page.where(
                    or_(
                        tuple_(User.last_seen_at, User.id) < tuple_(at, after_id),
                        User.last_seen_at.is_(None),
                    )
                )
        page = page.order_by(User.last_seen_at.desc().nulls_last(), User.id.desc())

    # One row past the page tells us whether another page exists.
    page = page.limit(limit + 1).subquery("page")

    # Counted only for the rows already on this page (the LIMIT is
    # inside the subquery above), each an index lookup on
    # sessions.user_id: one statement, never a query per user, and
    # never a pass over the whole sessions table.
    session_count = (
        select(func.count())
        .select_from(DebateSession)
        .where(DebateSession.user_id == page.c.id)
        .correlate(page)
        .scalar_subquery()
    )

    outer = select(page, session_count.label("session_count"))
    if sort == "newest":
        outer = outer.order_by(page.c.created_at.desc(), page.c.id.desc())
    else:
        outer = outer.order_by(page.c.last_seen_at.desc().nulls_last(), page.c.id.desc())

    rows = [UserRow(**row._mapping) for row in db.execute(outer)]

    next_cursor = None
    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = encode_cursor(sort, search, rows[-1])

    return rows, next_cursor
