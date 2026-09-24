"""
Reclaims two kinds of orphaned session rows this app's own
architecture can leave behind (see app/services/jobs.py's own
docstring: pipeline tracking is a plain in-process set, lost on
every restart, by design, until this outgrows one container):

1. A session stuck mid-pipeline (queued/converting/.../coaching)
   with no worker actually running it. Happens whenever the
   process restarts or crashes while a run was in flight.
   reap_stuck_pipelines() is meant to be called once, at startup,
   before jobs.start() lets any new pipeline begin — at that exact
   moment nothing in THIS process could have moved a session into
   one of these statuses yet, so anything found there is
   unambiguously left over from a previous process, never a
   session actually in flight right now. Marked "failed" (with a
   clear reason), not deleted: real uploaded audio may already
   exist for it, and "failed" is already a STARTABLE status
   (app/routes/sessions.py), so retrying it is a normal
   POST .../start away.

2. A session that had a presigned upload URL issued
   (status "created") and never got any further — never uploaded
   to, or uploaded to but never started. reap_abandoned_uploads()
   runs periodically. The presigned URL itself
   (settings.storage_url_expiry_seconds, 15 minutes) already makes
   anything past that unable to ever be completed;
   ABANDONED_UPLOAD_GRACE_PERIOD is set well beyond it so this
   never races a real, merely slow upload still in progress.
   Storage is cleared the same way DELETE /sessions/{id} already
   does, in case the PUT itself did succeed but the client never
   called /start afterward.

Neither one ever looks at "completed" sessions, or "created"/
in-progress ones within their own grace window, regardless of how
long the row has otherwise existed.
"""

import logging
import threading

from datetime import datetime, timedelta, timezone

from app.db.database import SessionLocal
from app.models.session import DebateSession, SessionStatus
from app.services import storage


logger = logging.getLogger(__name__)

ABANDONED_UPLOAD_GRACE_PERIOD = timedelta(hours=2)
SWEEP_INTERVAL_SECONDS = 30 * 60

_STUCK_STATUSES = (
    SessionStatus.queued,
    SessionStatus.converting,
    SessionStatus.transcribing,
    SessionStatus.analyzing_audio,
    SessionStatus.calculating_metrics,
    SessionStatus.analyzing_speech,
    SessionStatus.coaching,
)

_INTERRUPTED_MESSAGE = (
    "Processing was interrupted by a server restart. "
    "Start the analysis again."
)

_thread: threading.Thread | None = None
_stop_event = threading.Event()


def reap_stuck_pipelines() -> int:
    db = SessionLocal()

    try:
        stuck = (
            db.query(DebateSession)
            .filter(DebateSession.status.in_(_STUCK_STATUSES))
            .all()
        )

        for row in stuck:
            row.status = SessionStatus.failed
            row.error_message = _INTERRUPTED_MESSAGE

        if stuck:
            db.commit()
            logger.warning(
                "Marked %s session(s) failed after an interrupted "
                "pipeline run: %s",
                len(stuck),
                [str(row.id) for row in stuck],
            )

        return len(stuck)

    finally:
        db.close()


def reap_abandoned_uploads() -> int:
    cutoff = datetime.now(timezone.utc) - ABANDONED_UPLOAD_GRACE_PERIOD
    db = SessionLocal()

    try:
        abandoned = (
            db.query(DebateSession)
            .filter(
                DebateSession.status == SessionStatus.created,
                DebateSession.created_at < cutoff,
            )
            .all()
        )

        for row in abandoned:
            storage.delete_prefix(
                f"users/{row.user_id}/sessions/{row.id}/"
            )
            db.delete(row)

        if abandoned:
            db.commit()
            logger.info(
                "Deleted %s abandoned, never-started session(s).",
                len(abandoned),
            )

        return len(abandoned)

    finally:
        db.close()


def _sweep_loop() -> None:
    # wait() itself is the sleep; it returns True (and the loop
    # exits) the moment shutdown() sets the event, rather than
    # blocking shutdown for up to SWEEP_INTERVAL_SECONDS.
    while not _stop_event.wait(SWEEP_INTERVAL_SECONDS):
        try:
            reap_abandoned_uploads()
        except Exception:
            logger.exception("Abandoned-upload sweep failed.")


def start() -> None:
    global _thread

    if _thread is not None:
        return

    _stop_event.clear()
    _thread = threading.Thread(
        target=_sweep_loop,
        name="cleanup-sweep",
        daemon=True,
    )
    _thread.start()


def shutdown() -> None:
    global _thread

    _stop_event.set()
    _thread = None
