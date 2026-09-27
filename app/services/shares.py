"""
Share links for session reports.

Tokens are 32 random bytes (secrets.token_urlsafe(32): 43 URL-safe
characters, 256 bits), never derived from the session id, and only
their SHA-256 is stored, so a database leak doesn't leak working
links. A session has at most one active link (a partial unique
index); "Create new link" and "Stop sharing" revoke the current one
immediately.

resolve() is the only public entry point. Every way it can fail
(malformed token, unknown, revoked, replaced, session deleted or not
completed, report files missing) returns None, and the route turns
every None into the same plain 404.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.session import DebateSession, SessionStatus
from app.models.session_share import SessionShare
from app.models.video_analysis import VideoAnalysis
from app.motions import get_motion, motion_not_applied
from app.schemas.share import (
    SharedDelivery,
    SharedFeedbackItem,
    SharedMoment,
    SharedMotion,
    SharedReportOut,
    SharedVideoAnalysis,
    SharedVisualFeedback,
)
from app.services import storage

logger = logging.getLogger(__name__)

TOKEN_BYTES = 32
# token_urlsafe(32) is always exactly 43 characters of [A-Za-z0-9_-].
_TOKEN_FORMAT = re.compile(r"[A-Za-z0-9_-]{43}")

SCORE_KEYS = ("quantitative", "argumentation", "rebuttal", "structure", "persuasion", "logic", "overall")


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------
# Owner side
# ------------------------------------------------------------

def active_share(db: Session, session_id) -> Optional[SessionShare]:
    return db.scalar(
        select(SessionShare).where(SessionShare.session_id == session_id, SessionShare.revoked_at.is_(None))
    )


def shared_session_ids(db: Session, session_ids: list) -> set:
    if not session_ids:
        return set()
    return set(
        db.scalars(
            select(SessionShare.session_id).where(
                SessionShare.session_id.in_(session_ids), SessionShare.revoked_at.is_(None)
            )
        )
    )


def revoke(db: Session, session_id) -> None:
    share = active_share(db, session_id)
    if share is not None:
        share.revoked_at = _now()
        db.commit()


def create_or_replace(db: Session, session_id) -> tuple[str, SessionShare]:
    """
    Revoke the current link (if any) and issue a new one. Returns the
    token, the only time it exists outside the owner's browser.
    """

    for attempt in range(2):
        current = active_share(db, session_id)
        if current is not None:
            current.revoked_at = _now()
            db.flush()

        token = new_token()
        share = SessionShare(session_id=session_id, token_hash=hash_token(token), created_at=_now())
        db.add(share)
        try:
            db.commit()
        except IntegrityError:
            # A simultaneous create for the same session won the
            # one-active-link index; revoke that one and try again.
            db.rollback()
            if attempt == 1:
                raise
            continue
        db.refresh(share)
        return token, share

    raise RuntimeError("unreachable")


# ------------------------------------------------------------
# Public side
# ------------------------------------------------------------

def resolve(db: Session, token: str) -> Optional[DebateSession]:
    """The completed session an active token points to, or None."""

    if not isinstance(token, str) or not _TOKEN_FORMAT.fullmatch(token):
        return None

    digest = hash_token(token)
    share = db.scalar(
        select(SessionShare).where(SessionShare.token_hash == digest, SessionShare.revoked_at.is_(None))
    )
    if share is None or not hmac.compare_digest(share.token_hash, digest):
        return None

    session = db.get(DebateSession, share.session_id)
    if session is None or session.status != SessionStatus.completed or not session.coaching_object_key:
        return None
    return session


def _json(object_key: Optional[str]):
    if not object_key:
        return None
    try:
        return storage.download_json(object_key)
    except (storage.ObjectNotFoundError, ValueError):
        return None


def _number(value) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _count(section) -> Optional[int]:
    value = section.get("count") if isinstance(section, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def build_shared_report(db: Session, session: DebateSession) -> Optional[SharedReportOut]:
    """
    The public report, rebuilt from the stored documents on every
    request (so it always matches the session as it is now), through
    the whitelist models in app/schemas/share.py. None if the core
    report can't be read.
    """

    coaching = _json(session.coaching_object_key)
    if not isinstance(coaching, dict):
        return None

    raw_scores = coaching.get("scores") if isinstance(coaching.get("scores"), dict) else {}
    feedback = []
    for item in coaching.get("feedback") or []:
        try:
            feedback.append(SharedFeedbackItem.model_validate(item))
        except ValidationError:
            continue

    raw = _json(session.raw_metrics_object_key)
    raw = raw if isinstance(raw, dict) else {}
    speech = raw.get("speech") if isinstance(raw.get("speech"), dict) else {}

    motion = get_motion(session.motion_id)

    report = SharedReportOut(
        title=session.title,
        recorded_at=session.created_at,
        motion=SharedMotion(title=motion.title, description=motion.description) if motion else None,
        motion_not_applied=motion_not_applied(session),
        scores={key: _number(raw_scores.get(key)) for key in SCORE_KEYS},
        feedback=feedback,
        delivery=SharedDelivery(
            words_per_minute=_number(speech.get("words_per_minute")),
            speech_duration=_number(speech.get("speech_duration")),
            filler_count=_count(raw.get("fillers")),
            pause_count=_count(raw.get("pauses")),
            stutter_count=_count(raw.get("stutters")),
        ),
    )

    video = db.scalar(select(VideoAnalysis).where(VideoAnalysis.session_id == session.id))
    if video is not None:
        report.video_analysis_status = video.status
        report.video_unavailable_reason = video.unavailable_reason
        report.visual_coaching_status = video.coaching_status

        # Visual parts are best-effort, as on the owner's report: a
        # missing or malformed document drops that part, nothing else.
        try:
            result = _json(video.result_key)
            if isinstance(result, dict):
                report.video_analysis = SharedVideoAnalysis.model_validate(result)
        except ValidationError:
            report.video_analysis = None
        try:
            document = _json(video.feedback_key)
            if isinstance(document, dict):
                report.correlated_moments = [SharedMoment.model_validate(m) for m in document.get("correlated_moments") or []]
                report.visual_feedback = SharedVisualFeedback.model_validate(document)
        except ValidationError:
            report.correlated_moments = None
            report.visual_feedback = None

    return report
