"""
The ported analysis pipeline.

This is the same sequence server/pipeline.py already ran for
the local CLI, with two differences:

    1. Files come from and go back to object storage instead of
       living permanently on the server's disk.
    2. Progress is written to the sessions table instead of a
       local session.json.

Everything between those two ends is unchanged. raw_metrics/,
speech_analysis/, coaching_engine/, audio/ and api/ are imported
and called exactly as they were, so the web product runs the
same analysis the CLI produced rather than a reduced copy of it.

The working directory is a temp dir laid out the way every one
of those modules expects:

    <workdir>/<session_id>/
        recording.wav
        transcription.json
        analysis.json
        raw_metrics.json
        speech_content.json
        feedback.json

It is deleted when the run finishes, successfully or not.
"""

import logging
import shutil
import tempfile
import traceback

from pathlib import Path
from typing import Any, Callable
from uuid import UUID

from sqlalchemy.orm import Session as DbSession

from audio.audio_analyzer import analyze_audio
from audio.transcriber import transcribe_audio

from raw_metrics.metrics import analyze_metrics

from speech_analysis.speech_analyzer import analyze_speech

from coaching_engine.engine import CoachingEngine
from coaching_engine.utils.result_writer import save_coaching_results

from app.db.database import SessionLocal
from app.models.session import DebateSession, SessionStatus
from app.services import engine, storage
from app.services.audio_convert import (
    AudioConversionError,
    normalize_audio_to_wav,
)


logger = logging.getLogger(__name__)


# Artifacts written by the pipeline, mapped to the column that
# stores their object key. Uploaded in this order.
ARTIFACTS: list[tuple[str, str]] = [
    ("transcription.json", "transcription_object_key"),
    ("analysis.json", "analysis_object_key"),
    ("raw_metrics.json", "raw_metrics_object_key"),
    ("speech_content.json", "speech_content_object_key"),
    ("feedback.json", "coaching_object_key"),
]


class PipelineError(RuntimeError):
    pass


# ============================================================
# ENTRY POINT
# ============================================================

def run_session_pipeline(session_id: UUID) -> None:
    """
    Run the full pipeline for one session.

    Called on a worker thread by app/services/jobs.py, so it
    opens its own database session rather than borrowing the
    request-scoped one, which is already closed by the time
    this starts.
    """

    db = SessionLocal()

    try:
        debate_session = db.get(DebateSession, session_id)

        if debate_session is None:
            logger.error(
                "Pipeline started for unknown session %s",
                session_id,
            )
            return

        workdir = Path(
            tempfile.mkdtemp(prefix="debate-coach-")
        )

        try:
            _run(db, debate_session, workdir)

        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    except Exception as error:

        logger.error(
            "Pipeline failed for session %s:\n%s",
            session_id,
            traceback.format_exc(),
        )

        _fail(
            db,
            session_id,
            f"{type(error).__name__}: {error}",
        )

    finally:
        db.close()


# ============================================================
# STAGES
# ============================================================

def _run(
    db: DbSession,
    debate_session: DebateSession,
    workdir: Path,
) -> None:

    session_id = str(debate_session.id)
    user_id = debate_session.user_id

    session_directory = workdir / session_id
    session_directory.mkdir(parents=True, exist_ok=True)

    def mark(status: SessionStatus) -> None:
        debate_session.status = status
        debate_session.queue_wait_seconds = None
        db.commit()

    def on_queued(estimated_wait_seconds: float) -> None:
        """
        Called by api/scheduler.py when a request has to wait
        for key capacity. Recorded so the client can show the
        wait instead of appearing frozen.
        """
        debate_session.queue_wait_seconds = round(
            estimated_wait_seconds,
            1,
        )
        db.commit()

    # ---------------------------------------------------------
    # 0. Fetch the upload and normalize it
    # ---------------------------------------------------------

    mark(SessionStatus.converting)

    if not debate_session.upload_object_key:
        raise PipelineError(
            "Session has no uploaded audio."
        )

    upload_suffix = Path(
        debate_session.upload_object_key
    ).suffix or ".bin"

    upload_path = session_directory / f"upload{upload_suffix}"

    storage.download_file(
        debate_session.upload_object_key,
        upload_path,
    )

    audio_path = session_directory / "recording.wav"

    try:
        normalize_audio_to_wav(
            input_path=upload_path,
            output_path=audio_path,
        )

    except AudioConversionError as error:
        raise PipelineError(
            "The uploaded file could not be read as audio."
        ) from error

    upload_path.unlink(missing_ok=True)

    audio_key = storage.build_object_key(
        user_id,
        debate_session.id,
        "recording.wav",
    )

    storage.upload_file(
        audio_key,
        audio_path,
        content_type="audio/wav",
    )

    debate_session.audio_object_key = audio_key
    db.commit()

    # ---------------------------------------------------------
    # 1. Transcribe
    # ---------------------------------------------------------

    mark(SessionStatus.transcribing)

    api_client = engine.get_api_client()

    transcribe_audio(
        audio_path=audio_path,
        session_id=session_id,
        session_directory=session_directory,
        whisper_client=api_client.whisper_client,
    )

    # ---------------------------------------------------------
    # 2. Audio analysis (Silero VAD)
    # ---------------------------------------------------------

    mark(SessionStatus.analyzing_audio)

    analyze_audio(
        audio_path=audio_path,
        session_id=session_id,
        session_directory=session_directory,
    )

    # ---------------------------------------------------------
    # 3. Raw deterministic metrics
    # ---------------------------------------------------------

    mark(SessionStatus.calculating_metrics)

    _, raw_metrics = analyze_metrics(
        session_id=session_id,
        session_directory=session_directory,
    )

    # ---------------------------------------------------------
    # 4. Semantic speech analysis (LLM, structured JSON)
    # ---------------------------------------------------------

    mark(SessionStatus.analyzing_speech)

    analyze_speech(
        session_id=session_id,
        session_directory=session_directory,
        api_client=api_client,
        on_queued=on_queued,
    )

    # ---------------------------------------------------------
    # 5. Coaching analysis
    # ---------------------------------------------------------

    mark(SessionStatus.coaching)

    coaching_engine = CoachingEngine(
        sessions_dir=str(workdir),
        api_client=api_client,
        on_queued=on_queued,
    )

    feedback, scores = coaching_engine.analyze_session(
        session_id=session_id,
    )

    save_coaching_results(
        session_id=session_id,
        feedback=feedback,
        scores=scores,
        sessions_dir=str(workdir),
    )

    if coaching_engine.llm_errors:
        # Categories where the LLM pass failed still produced
        # deterministic feedback, so the run is not a failure.
        # Record which ones degraded for debugging.
        debate_session.extra = {
            **(debate_session.extra or {}),
            "llm_errors": coaching_engine.llm_errors,
        }

    # ---------------------------------------------------------
    # 6. Publish artifacts
    # ---------------------------------------------------------

    _upload_artifacts(
        debate_session=debate_session,
        session_directory=session_directory,
        user_id=user_id,
    )

    _record_summary(
        debate_session=debate_session,
        raw_metrics=raw_metrics,
        scores=scores,
        feedback_count=len(feedback),
    )

    debate_session.status = SessionStatus.completed
    debate_session.queue_wait_seconds = None
    debate_session.error_message = None

    db.commit()


# ============================================================
# PUBLISHING
# ============================================================

def _upload_artifacts(
    debate_session: DebateSession,
    session_directory: Path,
    user_id: UUID,
) -> None:

    for filename, column in ARTIFACTS:

        path = session_directory / filename

        if not path.exists():
            continue

        object_key = storage.build_object_key(
            user_id,
            debate_session.id,
            filename,
        )

        storage.upload_file(
            object_key,
            path,
            content_type="application/json",
        )

        setattr(debate_session, column, object_key)


def _record_summary(
    debate_session: DebateSession,
    raw_metrics: dict[str, Any],
    scores: Any,
    feedback_count: int,
) -> None:
    """
    Copy the handful of numbers the session list needs into
    columns, so listing sessions does not mean fetching every
    report out of object storage.
    """

    speech = raw_metrics.get("speech", {})

    debate_session.duration_seconds = speech.get(
        "speech_duration"
    )

    debate_session.words_per_minute = speech.get(
        "words_per_minute"
    )

    debate_session.overall_score = scores.overall
    debate_session.feedback_count = feedback_count


# ============================================================
# FAILURE
# ============================================================

def _fail(
    db: DbSession,
    session_id: UUID,
    message: str,
) -> None:

    try:
        db.rollback()

        debate_session = db.get(DebateSession, session_id)

        if debate_session is None:
            return

        debate_session.status = SessionStatus.failed
        debate_session.queue_wait_seconds = None
        debate_session.error_message = message[:1024]

        db.commit()

    except Exception:
        logger.exception(
            "Could not record failure for session %s",
            session_id,
        )


# ============================================================
# JOB FACTORY
# ============================================================

def build_job(session_id: UUID) -> Callable[[], None]:
    """
    Returns a zero-argument callable for app/services/jobs.py.
    """

    def job() -> None:
        run_session_pipeline(session_id)

    return job
