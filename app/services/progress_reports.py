"""
AI progress reports: which sessions to compare, the once-per-UTC-day
limit, and storing the result. The LLM call itself is
progress_report/service.py.

Order of checks in generate(), cheapest first, so neither refusal
ever reaches the LLM:
  1. a report already exists for this user today -> AlreadyGeneratedToday
  2. fewer than 2 usable completed sessions      -> NotEnoughSessions
  3. summarise, call the LLM, validate           -> ProgressReportFailed
  4. insert; the (user_id, report_date) unique constraint refuses a
     second row even if two generations finish at the same moment.
A row is written only after step 3 succeeds, so a failed attempt
never uses up the day.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.progress_report import ProgressReport
from app.models.session import DebateSession, SessionStatus
from app.models.user import User
from app.models.video_analysis import VideoAnalysis
from app.services import storage
from progress_report import prompt as prompt_module
from progress_report import service as report_service

logger = logging.getLogger(__name__)

ALLOWED_SESSION_COUNTS = (3, 5, 7)
MIN_SESSIONS = 2


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def next_available_at(now: datetime) -> datetime:
    """The next UTC midnight: when a new day's report is allowed."""
    return datetime.combine(now.astimezone(timezone.utc).date() + timedelta(days=1), time.min, tzinfo=timezone.utc)


class AlreadyGeneratedToday(Exception):
    def __init__(self, next_at: datetime):
        super().__init__(f"next report available at {next_at.isoformat()}")
        self.next_at = next_at


class NotEnoughSessions(Exception):
    def __init__(self, usable: int):
        super().__init__(f"{usable} usable completed session(s)")
        self.usable = usable


@dataclass
class SessionInputs:
    session_id: uuid.UUID
    scores: dict
    feedback: list
    raw_metrics: Optional[dict]
    visual_feedback: Optional[list]


def todays_report(db: Session, user: User, today: date) -> Optional[ProgressReport]:
    return db.scalar(
        select(ProgressReport).where(ProgressReport.user_id == user.id, ProgressReport.report_date == today)
    )


def latest_report(db: Session, user: User) -> Optional[ProgressReport]:
    return db.scalar(
        select(ProgressReport)
        .where(ProgressReport.user_id == user.id)
        .order_by(ProgressReport.report_date.desc(), ProgressReport.created_at.desc())
        .limit(1)
    )


def _optional_json(object_key: Optional[str]):
    if not object_key:
        return None
    try:
        return storage.download_json(object_key)
    except (storage.ObjectNotFoundError, ValueError):
        return None


def load_session_inputs(db: Session, user: User, count: int) -> list[SessionInputs]:
    """
    The user's newest `count` completed sessions, oldest first. A
    session whose feedback.json is missing or unreadable is skipped
    (logged); a missing raw_metrics or visual feedback just leaves
    those parts of its summary as "unknown".
    """

    rows = list(
        db.scalars(
            select(DebateSession)
            .where(
                DebateSession.user_id == user.id,
                DebateSession.status == SessionStatus.completed,
                DebateSession.coaching_object_key.is_not(None),
            )
            .order_by(DebateSession.created_at.desc(), DebateSession.id.desc())
            .limit(count)
        )
    )
    rows.reverse()

    videos = {
        v.session_id: v
        for v in db.scalars(select(VideoAnalysis).where(VideoAnalysis.session_id.in_([r.id for r in rows])))
    }

    inputs: list[SessionInputs] = []
    for row in rows:
        coaching = _optional_json(row.coaching_object_key)
        if not isinstance(coaching, dict) or not isinstance(coaching.get("scores"), dict):
            logger.warning("progress report: skipping session %s, feedback.json missing or unreadable", row.id)
            continue

        video = videos.get(row.id)
        visual = None
        if video is not None and video.coaching_status == "completed":
            document = _optional_json(video.feedback_key)
            if isinstance(document, dict) and isinstance(document.get("visual_feedback"), list):
                visual = document["visual_feedback"]

        raw_metrics = _optional_json(row.raw_metrics_object_key)
        inputs.append(
            SessionInputs(
                session_id=row.id,
                scores=coaching["scores"],
                feedback=coaching.get("feedback") if isinstance(coaching.get("feedback"), list) else [],
                raw_metrics=raw_metrics if isinstance(raw_metrics, dict) else None,
                visual_feedback=visual,
            )
        )
    return inputs


def build_summaries(inputs: list[SessionInputs]) -> list[dict]:
    return [
        prompt_module.summarize_session(i, len(inputs), s.scores, s.raw_metrics, s.feedback, s.visual_feedback)
        for i, s in enumerate(inputs)
    ]


def generate(
    db: Session,
    user: User,
    session_count: int,
    api_client,
    now: Callable[[], datetime] = utc_now,
) -> ProgressReport:
    if session_count not in ALLOWED_SESSION_COUNTS:
        raise ValueError(f"session_count must be one of {ALLOWED_SESSION_COUNTS}")

    started = now()
    today = started.astimezone(timezone.utc).date()

    if todays_report(db, user, today) is not None:
        raise AlreadyGeneratedToday(next_available_at(started))

    inputs = load_session_inputs(db, user, session_count)
    if len(inputs) < MIN_SESSIONS:
        raise NotEnoughSessions(len(inputs))

    bullets = report_service.generate_bullets(build_summaries(inputs), api_client)

    report = ProgressReport(
        user_id=user.id,
        report_date=today,
        created_at=now(),
        session_count_requested=session_count,
        session_count_used=len(inputs),
        session_ids=[str(s.session_id) for s in inputs],
        content={"bullets": bullets},
        model=report_service.MODEL,
        prompt_version=prompt_module.PROMPT_VERSION,
    )
    db.add(report)
    try:
        db.commit()
    except IntegrityError:
        # Another generation for this user finished first today.
        db.rollback()
        raise AlreadyGeneratedToday(next_available_at(started))
    db.refresh(report)
    return report
