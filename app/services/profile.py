"""
The profile page: username and bio, practice streak, weekly goal and
personal bests. Everything is computed on request from the user's own
completed sessions, so deleting a session updates all of it.

Days and weeks follow the user's own time zone (stored from the
browser), falling back to UTC until it's known. A session belongs to
the local day it was recorded (created_at), the same date the session
list shows.
"""

import logging
import math
import re
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Iterable
from zoneinfo import ZoneInfo, available_timezones

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.profile import DEFAULT_WEEKLY_GOAL, SessionDeliveryScore, UserProfile
from app.models.session import DebateSession, SessionStatus
from app.models.user import User
from app.services import storage

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# VALIDATION
# ============================================================

USERNAME_MIN, USERNAME_MAX = 3, 20
_USERNAME = re.compile(r"[a-z0-9_]+")
BIO_MAX = 160
GOAL_MIN, GOAL_MAX = 1, 7
TIME_ZONE_MAX = 64

USERNAME_LENGTH_MESSAGE = "A username must be 3 to 20 characters."
USERNAME_CHARS_MESSAGE = "A username can only use lowercase letters, numbers and underscores."
USERNAME_TAKEN_MESSAGE = "That username is taken."
BIO_LENGTH_MESSAGE = "A bio can be at most 160 characters."
BIO_PLAIN_MESSAGE = "A bio can only contain plain text."
GOAL_MESSAGE = "The weekly goal must be between 1 and 7 sessions."
TIME_ZONE_MESSAGE = "That time zone isn't recognised."


class ProfileFieldError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class UsernameTakenError(ProfileFieldError):
    def __init__(self) -> None:
        super().__init__("username", USERNAME_TAKEN_MESSAGE)


def normalize_username(raw: str | None) -> str | None:
    """Trimmed and lowercased; None (no username) when blank."""

    if raw is None:
        return None
    value = raw.strip().lower()
    if not value:
        return None
    if not USERNAME_MIN <= len(value) <= USERNAME_MAX:
        raise ProfileFieldError("username", USERNAME_LENGTH_MESSAGE)
    # ASCII only: str.isalnum() would let other scripts' letters in.
    if not _USERNAME.fullmatch(value):
        raise ProfileFieldError("username", USERNAME_CHARS_MESSAGE)
    return value


def normalize_bio(raw: str | None) -> str | None:
    """
    Plain text: line breaks kept (as \\n), tabs become spaces, outer
    whitespace trimmed, None when blank. Any other control character
    is refused. Length is in characters (code points), the same unit
    as the varchar(160) column and the page's counter.
    """

    if raw is None:
        return None
    value = raw.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ").strip()
    if not value:
        return None
    if any(ch != "\n" and unicodedata.category(ch) == "Cc" for ch in value):
        raise ProfileFieldError("bio", BIO_PLAIN_MESSAGE)
    if len(value) > BIO_MAX:
        raise ProfileFieldError("bio", BIO_LENGTH_MESSAGE)
    return value


def validate_weekly_goal(raw: Any) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or not GOAL_MIN <= raw <= GOAL_MAX:
        raise ProfileFieldError("weekly_goal", GOAL_MESSAGE)
    return raw


@lru_cache(maxsize=1)
def _known_time_zones() -> frozenset[str]:
    return frozenset(available_timezones())


def validate_time_zone(raw: Any) -> str:
    """An IANA name the server knows (e.g. "Asia/Karachi"), as the browser reports it."""

    if not isinstance(raw, str) or not 0 < len(raw) <= TIME_ZONE_MAX or raw not in _known_time_zones():
        raise ProfileFieldError("time_zone", TIME_ZONE_MESSAGE)
    return raw


def _zone(name: str | None) -> ZoneInfo:
    if name:
        try:
            return ZoneInfo(name)
        except Exception:  # noqa: BLE001  (a stored name the server no longer knows)
            logger.warning("Unknown stored time zone %r; using UTC", name)
    return ZoneInfo("UTC")


# ============================================================
# STREAK AND WEEK
# ============================================================

def local_date(moment: datetime, zone: ZoneInfo) -> date:
    # SQLite hands timestamps back naive; they were stored as UTC.
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(zone).date()


@dataclass(frozen=True)
class Streak:
    current: int
    longest: int
    practised_today: bool


def compute_streak(days: Iterable[date], today: date) -> Streak:
    """
    days: the local dates with at least one completed session.

    The current streak runs back from today, or from yesterday if
    there's nothing today yet: a streak lasts until the end of the
    first day without practice. The longest is the longest run ever.
    """

    practised = set(days)
    practised_today = today in practised

    if practised_today:
        anchor = today
    elif today - timedelta(days=1) in practised:
        anchor = today - timedelta(days=1)
    else:
        anchor = None

    current = 0
    if anchor is not None:
        day = anchor
        while day in practised:
            current += 1
            day -= timedelta(days=1)

    longest = run = 0
    previous: date | None = None
    for day in sorted(practised):
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day

    return Streak(current=current, longest=max(longest, current), practised_today=practised_today)


def week_bounds(today: date) -> tuple[date, date]:
    """Monday and Sunday of the week containing today."""

    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)


# ============================================================
# PERSONAL BESTS
# ============================================================

# Display order on the page. Delivery is the coaching engine's
# "quantitative" category.
BEST_COLUMNS: dict[str, str | None] = {
    "overall": "overall_score",
    "quantitative": None,  # from session_delivery_scores
    "argumentation": "score_argumentation",
    "rebuttal": "score_rebuttal",
    "structure": "score_structure",
    "persuasion": "score_persuasion",
    "logic": "score_logic",
}


def _score(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or not 0 <= value <= 100:
        return None
    return float(value)


def _read_delivery_score(object_key: str) -> tuple[bool, float | None]:
    """(cacheable, score). A storage error isn't cached, so it's retried next time."""

    try:
        document = storage.download_json(object_key)
    except storage.ObjectNotFoundError:
        return True, None
    except Exception:  # noqa: BLE001
        logger.warning("Could not read %s for the Delivery score", object_key, exc_info=True)
        return False, None

    scores = document.get("scores") if isinstance(document, dict) else None
    return True, _score(scores.get("quantitative")) if isinstance(scores, dict) else None


def delivery_scores(db: Session, sessions: list[Any]) -> dict[uuid.UUID, float | None]:
    """
    Each completed session's Delivery score, read from
    session_delivery_scores, filling in any session not cached yet
    from its feedback.json (once).
    """

    ids = [row.id for row in sessions]
    known: dict[uuid.UUID, float | None] = {}
    for start in range(0, len(ids), 500):
        chunk = ids[start : start + 500]
        for session_id, score in db.execute(
            select(SessionDeliveryScore.session_id, SessionDeliveryScore.score).where(
                SessionDeliveryScore.session_id.in_(chunk)
            )
        ):
            known[session_id] = score

    missing = [row for row in sessions if row.id not in known and row.coaching_object_key]
    if not missing:
        return known

    with ThreadPoolExecutor(max_workers=min(8, len(missing))) as pool:
        results = list(pool.map(lambda row: _read_delivery_score(row.coaching_object_key), missing))

    fresh = []
    for row, (cacheable, score) in zip(missing, results):
        known[row.id] = score
        if cacheable:
            fresh.append(SessionDeliveryScore(session_id=row.id, score=score))

    if fresh:
        db.add_all(fresh)
        try:
            db.commit()
        except IntegrityError:
            # Another request cached the same sessions first (or a
            # session was deleted meanwhile). The values in hand are
            # still right; the cache fills on a later request.
            db.rollback()

    return known


def personal_bests(sessions: list[Any], delivery: dict[uuid.UUID, float | None]) -> list[dict[str, Any]]:
    """
    The highest score per category over completed sessions. A missing
    score (rebuttal "not scored", no Delivery score) is skipped, never
    treated as zero. A tie goes to the earlier session: the first time
    that score was reached.
    """

    ordered = sorted(sessions, key=lambda row: (_as_utc(row.created_at), str(row.id)))
    bests = []
    for category, column in BEST_COLUMNS.items():
        best = None
        best_score = None
        for row in ordered:
            value = _score(delivery.get(row.id) if column is None else getattr(row, column))
            if value is not None and (best_score is None or value > best_score):
                best, best_score = row, value
        bests.append(
            {
                "category": category,
                "score": best_score,
                "session_id": best.id if best else None,
                "title": best.title if best else None,
                "created_at": best.created_at if best else None,
            }
        )
    return bests


def _as_utc(moment: datetime) -> datetime:
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment


# ============================================================
# READ AND UPDATE
# ============================================================

def get_profile_row(db: Session, user: User) -> UserProfile | None:
    return db.get(UserProfile, user.id)


def build_profile(db: Session, user: User, now: datetime | None = None) -> dict[str, Any]:
    """The whole /v1/profile payload, for the current user only."""

    profile = get_profile_row(db, user)
    zone = _zone(profile.time_zone if profile else None)
    goal = profile.weekly_goal if profile else DEFAULT_WEEKLY_GOAL
    today = local_date(now or _utcnow(), zone)

    sessions = db.execute(
        select(
            DebateSession.id,
            DebateSession.title,
            DebateSession.created_at,
            DebateSession.coaching_object_key,
            *(getattr(DebateSession, column) for column in BEST_COLUMNS.values() if column),
        ).where(
            DebateSession.user_id == user.id,
            DebateSession.status == SessionStatus.completed,
        )
    ).all()

    days = [local_date(row.created_at, zone) for row in sessions]
    streak = compute_streak(days, today)
    monday, sunday = week_bounds(today)
    this_week = sum(1 for day in days if monday <= day <= sunday)

    return {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": profile.username if profile else None,
        "bio": profile.bio if profile else None,
        "weekly_goal": goal,
        "time_zone": profile.time_zone if profile else None,
        "completed_sessions": len(sessions),
        "streak": {
            "current": streak.current,
            "longest": streak.longest,
            "practised_today": streak.practised_today,
        },
        "week": {
            "completed": this_week,
            "goal": goal,
            "goal_met": this_week >= goal,
            "starts_on": monday,
            "ends_on": sunday,
        },
        "personal_bests": personal_bests(sessions, delivery_scores(db, sessions)),
    }


def _username_taken(db: Session, username: str, user_id: uuid.UUID) -> bool:
    return (
        db.execute(
            select(UserProfile.user_id).where(
                func.lower(UserProfile.username) == username.lower(),
                UserProfile.user_id != user_id,
            )
        ).first()
        is not None
    )


def update_profile(db: Session, user: User, changes: dict[str, Any]) -> None:
    """
    Applies the fields present in changes (username, bio, weekly_goal,
    time_zone), all validated before anything is written. A blank
    username or bio clears it. Raises ProfileFieldError, or
    UsernameTakenError when another user has the username (compared
    case-insensitively).
    """

    values: dict[str, Any] = {}
    if "username" in changes:
        values["username"] = normalize_username(changes["username"])
    if "bio" in changes:
        values["bio"] = normalize_bio(changes["bio"])
    if "weekly_goal" in changes:
        values["weekly_goal"] = validate_weekly_goal(changes["weekly_goal"])
    if "time_zone" in changes:
        values["time_zone"] = validate_time_zone(changes["time_zone"])

    if not values:
        return

    username = values.get("username")
    if username is not None and _username_taken(db, username, user.id):
        raise UsernameTakenError()

    profile = get_profile_row(db, user)
    if profile is None:
        profile = UserProfile(user_id=user.id, weekly_goal=DEFAULT_WEEKLY_GOAL)
        db.add(profile)
    elif all(getattr(profile, field) == value for field, value in values.items()):
        return  # nothing changed (e.g. the page re-reporting the same time zone)

    for field, value in values.items():
        setattr(profile, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if username is not None and _username_taken(db, username, user.id):
            raise UsernameTakenError() from None
        raise
