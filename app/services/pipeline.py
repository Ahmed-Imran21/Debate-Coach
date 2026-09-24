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

import json
import logging
import shutil
import tempfile
import traceback

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from audio.audio_analyzer import analyze_audio
from audio.transcriber import transcribe_audio

from raw_metrics.metrics import analyze_metrics

from speech_analysis.llm.client import SpeechAnalysisValidationError
from speech_analysis.speech_analyzer import analyze_speech

from coaching_engine.engine import CoachingEngine
from coaching_engine.utils.result_writer import save_coaching_results

from visual_analysis.pipeline import VideoAnalysisResult, run_pipeline
from visual_analysis.schema import VisualSignalTrack
from visual_analysis.signals import check_duration
from visual_coaching.service import generate_visual_coaching

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.session import DebateSession, SessionStatus
from app.models.video_analysis import SessionMetric, VideoAnalysis
from app.services import engine, storage, visual_signals
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

        # speech_analysis/ has no storage dependency of its own (see
        # SpeechAnalysisValidationError's docstring), so persisting
        # the raw LLM response that failed validation happens here —
        # this is the outer boundary that has both. debate_session
        # is still in scope even though workdir (the local copy) is
        # already gone by this point (the inner `finally:
        # shutil.rmtree` above already ran); the raw text lives on
        # the exception object itself, not on disk, so that's fine.
        # Best-effort: a storage failure here must not shadow the
        # original error or stop _fail() from recording it below.
        if isinstance(error, SpeechAnalysisValidationError):
            try:
                storage.upload_bytes(
                    storage.build_object_key(
                        debate_session.user_id,
                        debate_session.id,
                        "speech_analysis_failure.json",
                    ),
                    error.raw_response.encode("utf-8"),
                    content_type="application/json",
                )
            except Exception:
                logger.error(
                    "Could not persist the failing speech-analysis "
                    "response for session %s.",
                    session_id,
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
    # 4b. Visual delivery analysis (optional, best-effort)
    # ---------------------------------------------------------

    video_result = _run_video_analysis(
        db=db,
        debate_session=debate_session,
        session_directory=session_directory,
        user_id=user_id,
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
    # 5b. Visual coaching (optional, best-effort, separate LLM call)
    # ---------------------------------------------------------

    _run_visual_coaching(
        db=db,
        debate_session=debate_session,
        session_directory=session_directory,
        user_id=user_id,
        video_result=video_result,
        api_client=api_client,
        on_queued=on_queued,
    )

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
# VISUAL ANALYSIS (optional, best-effort)
# ============================================================

# The result's own status vocabulary ("complete | partial |
# insufficient_data") is deliberately not the same as the
# video_analyses.status column's ("processed | partial |
# insufficient_data | ..."); see visual_analysis/pipeline.py's
# module docstring. Every value not listed here passes through
# unchanged.
_RESULT_STATUS_TO_DB_STATUS: dict[str, str] = {"complete": "processed"}


def _run_video_analysis(
    db: DbSession,
    debate_session: DebateSession,
    session_directory: Path,
    user_id: UUID,
) -> Optional[dict]:
    """
    Only acts on a video_analyses row already in "received" state,
    meaning a signal track was uploaded before /start (see
    app/routes/sessions.py's start_analysis: "Leave 'received' as
    is; the pipeline moves it on."). Every other state -- no row
    (not requested), "unavailable" (the client already reported its
    own reason), or a terminal state from an earlier run -- is left
    untouched.

    A failure here is never a session failure: visual delivery
    analysis is an optional extra on top of the audio/transcript
    pipeline, so any exception is caught, logged, and turned into
    video_row.status = "failed" without raising further.

    Returns the result dict on success (so _run_visual_coaching,
    later in the same pipeline run, can reuse it without a redundant
    GCS round-trip), else None.
    """

    if not settings.video_analysis_enabled:
        return None

    video_row = db.get(VideoAnalysis, debate_session.id)
    if video_row is None or video_row.status != "received" or not video_row.signal_track_key:
        return None

    video_row.status = "processing"
    video_row.processing_started_at = datetime.now(timezone.utc)
    db.commit()

    try:
        analysis = json.loads((session_directory / "analysis.json").read_text(encoding="utf-8"))

        track: VisualSignalTrack = visual_signals.load_track(
            video_row.signal_track_key,
            expected_session_id=str(debate_session.id),
        )

        mismatch_reason = check_duration(track, analysis.get("total_duration"))
        if mismatch_reason:
            video_row.status = "unavailable"
            video_row.unavailable_reason = mismatch_reason
            db.commit()
            return None

        result: VideoAnalysisResult = run_pipeline(track, analysis["speech_segments"])
        result_key = visual_signals.store_result(user_id, debate_session.id, result)

        _record_session_metrics(db, debate_session, user_id, track, result)

        video_row.status = _RESULT_STATUS_TO_DB_STATUS.get(result.status, result.status)
        video_row.schema_version = result.schema_version
        video_row.metrics_version = result.metrics_version
        video_row.platform = track.source.platform
        video_row.runtime_version = track.source.runtime.version
        video_row.quality = result.quality
        video_row.result_key = result_key
        db.commit()

        return result.to_dict()

    except Exception:
        logger.exception(
            "Video analysis failed for session %s",
            debate_session.id,
        )
        db.rollback()

        video_row = db.get(VideoAnalysis, debate_session.id)
        if video_row is not None:
            video_row.status = "failed"
            db.commit()

        return None


def _record_session_metrics(
    db: DbSession,
    debate_session: DebateSession,
    user_id: UUID,
    track: VisualSignalTrack,
    result: VideoAnalysisResult,
) -> None:
    """
    One SessionMetric row per metric, upserted on (session_id,
    metric_key, definition_version) -- the pipeline does not
    normally re-process a track (see the "received"-only guard
    above), but this stays correct if it ever does.
    """

    for key, m in result.metrics.items():
        row = db.scalar(
            select(SessionMetric).where(
                SessionMetric.session_id == debate_session.id,
                SessionMetric.metric_key == key,
                SessionMetric.definition_version == m["definition_version"],
            )
        )
        if row is None:
            row = SessionMetric(
                session_id=debate_session.id,
                user_id=user_id,
                metric_key=key,
                definition_version=m["definition_version"],
            )
            db.add(row)

        row.value = m["value"]
        row.unit = m["unit"]
        row.coverage = m["coverage"]
        row.confidence = m["confidence"]
        row.status = m["status"]
        row.platform = track.source.platform
        row.recorded_at = datetime.now(timezone.utc)

    db.commit()


def _run_visual_coaching(
    db: DbSession,
    debate_session: DebateSession,
    session_directory: Path,
    user_id: UUID,
    video_result: Optional[dict],
    api_client,
    on_queued: Optional[Callable[[float], None]],
) -> None:
    """
    §7.1: after the existing coaching stage, if the video row's
    status is "processed" or "partial", run the separate visual
    coaching LLM call and store its output. Every other outcome from
    _run_video_analysis (not requested, unavailable, insufficient_data,
    failed, or the flag being off, which leaves video_result None) is
    left untouched -- there is nothing to coach on.

    A failure here is never a session failure and never touches the
    already-stored metrics/moments: it only ever changes
    coaching_status, matching §7.1's "Failure -> failed; metrics and
    moments are still stored and shown."
    """

    if not settings.video_analysis_enabled or video_result is None:
        return

    video_row = db.get(VideoAnalysis, debate_session.id)
    if video_row is None or video_row.status not in ("processed", "partial"):
        return

    video_row.coaching_status = "pending"
    db.commit()

    try:
        transcription = json.loads((session_directory / "transcription.json").read_text(encoding="utf-8"))
        analysis = json.loads((session_directory / "analysis.json").read_text(encoding="utf-8"))
        raw_metrics = json.loads((session_directory / "raw_metrics.json").read_text(encoding="utf-8"))
        speech_content = json.loads((session_directory / "speech_content.json").read_text(encoding="utf-8"))

        outcome = generate_visual_coaching(
            session_id=str(debate_session.id),
            transcription=transcription,
            audio_analysis=analysis,
            raw_metrics=raw_metrics,
            speech_content=speech_content,
            video_analysis=video_result,
            api_client=api_client,
            on_queued=on_queued,
        )

        stored_key = visual_signals.store_feedback(user_id, debate_session.id, outcome.document)

        video_row.coaching_status = outcome.status
        video_row.feedback_key = stored_key
        db.commit()

    except Exception:
        logger.exception(
            "Visual coaching failed for session %s",
            debate_session.id,
        )
        db.rollback()

        video_row = db.get(VideoAnalysis, debate_session.id)
        if video_row is not None:
            video_row.coaching_status = "failed"
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
