import uuid

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.models.session import DebateSession, SessionStatus
from app.models.user import User
from app.models.video_analysis import VideoAnalysis
from app.routes.deps import get_current_user
from app.schemas.session import (
    ALLOWED_CONTENT_TYPES,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionOut,
    SessionReportOut,
    SessionStartRequest,
)
from app.services import jobs, pipeline, storage, visual_signals
from visual_analysis import config as visual_config
from visual_analysis.signals import SignalValidationError


router = APIRouter(prefix="/sessions", tags=["sessions"])


# Statuses from which a run may be started. Anything else is
# either already running or already done.
STARTABLE = {
    SessionStatus.created,
    SessionStatus.failed,
}


def _get_owned_session(
    session_id: uuid.UUID,
    current_user: User,
    db: Session,
) -> DebateSession:

    debate_session = db.get(DebateSession, session_id)

    if (
        debate_session is None
        or debate_session.user_id != current_user.id
    ):
        # The same 404 whether it does not exist or belongs to
        # someone else. Do not leak which sessions exist.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    return debate_session


def _video_row(db: Session, session_id: uuid.UUID) -> VideoAnalysis | None:
    if not settings.video_analysis_enabled:
        return None
    return db.get(VideoAnalysis, session_id)


def _video_rows(db: Session, session_ids: list[uuid.UUID]) -> dict[uuid.UUID, VideoAnalysis]:
    if not settings.video_analysis_enabled or not session_ids:
        return {}
    rows = (
        db.query(VideoAnalysis)
        .filter(VideoAnalysis.session_id.in_(session_ids))
        .all()
    )
    return {row.session_id: row for row in rows}


def _session_out(debate_session: DebateSession, video: VideoAnalysis | None) -> SessionOut:
    out = SessionOut.model_validate(debate_session)
    if video is not None:
        out.video_analysis_status = video.status
        out.video_unavailable_reason = video.unavailable_reason
        out.visual_coaching_status = video.coaching_status
    return out


def _require_video_enabled() -> None:
    if not settings.video_analysis_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )


# ============================================================
# CREATE
# ============================================================

@router.post(
    "",
    response_model=SessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    payload: SessionCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionCreateResponse:
    """
    Reserve a session and return a short-lived URL to upload
    the recording to.

    The audio goes straight from the client to object storage,
    so the API server never handles the bytes.
    """

    content_type = payload.content_type.split(";")[0].strip().lower()

    suffix = ALLOWED_CONTENT_TYPES.get(content_type)

    if suffix is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unsupported audio format. Supported types: "
                + ", ".join(sorted(ALLOWED_CONTENT_TYPES))
            ),
        )

    debate_session = DebateSession(
        user_id=current_user.id,
        title=payload.title,
        status=SessionStatus.created,
    )

    db.add(debate_session)
    db.commit()
    db.refresh(debate_session)

    object_key = storage.build_object_key(
        current_user.id,
        debate_session.id,
        f"upload{suffix}",
    )

    debate_session.upload_object_key = object_key

    # One video_analyses row per session that asked for it; its
    # absence means "not_requested". Ignored when the feature is
    # off so old and new clients behave identically.
    if settings.video_analysis_enabled and payload.video_analysis == "requested":
        db.add(
            VideoAnalysis(
                session_id=debate_session.id,
                user_id=current_user.id,
                status="awaiting_upload",
            )
        )

    db.commit()

    upload_url = storage.generate_presigned_upload_url(
        object_key=object_key,
        content_type=content_type,
    )

    return SessionCreateResponse(
        id=debate_session.id,
        status=debate_session.status,
        upload_url=upload_url,
        upload_headers={"Content-Type": content_type},
        expires_in_seconds=settings.storage_url_expiry_seconds,
    )


# ============================================================
# START
# ============================================================

@router.post(
    "/{session_id}/start",
    response_model=SessionOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_analysis(
    session_id: uuid.UUID,
    payload: SessionStartRequest | None = Body(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionOut:
    """
    Begin analysis. Call this once the upload PUT has returned
    a 200 (and, if visual analysis was requested, once the
    signal upload has been acknowledged).

    Returns immediately. The pipeline runs in the background
    and takes minutes, so poll GET /sessions/{id} for progress.

    The optional body carries the video outcome. No body, or no
    `video` field, behaves exactly as this route did before the
    field existed.
    """

    debate_session = _get_owned_session(
        session_id,
        current_user,
        db,
    )

    if debate_session.status not in STARTABLE:

        if jobs.is_running(session_id):
            # Already in flight. Treat a retry as a no-op so
            # the client can safely repeat the call.
            return _session_out(debate_session, _video_row(db, session_id))

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This session has already been analyzed."
            ),
        )

    if not debate_session.upload_object_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No audio has been uploaded yet.",
        )

    try:
        size = storage.object_size(
            debate_session.upload_object_key
        )

    except storage.ObjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "The upload did not complete. Upload the "
                "recording again, then start the analysis."
            ),
        ) from None

    if size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded recording is empty.",
        )

    if size > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                "The recording is larger than "
                f"{settings.max_upload_mb} MB."
            ),
        )

    video_row = _video_row(db, session_id)

    if settings.video_analysis_enabled and payload is not None and payload.video is not None:

        if payload.video.status == "uploaded":
            if video_row is None or not video_row.signal_track_key:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "No visual signal track has been stored for "
                        "this session. Upload it, then start."
                    ),
                )
            # Leave "received" as is; the pipeline moves it on.

        else:
            if video_row is None:
                video_row = VideoAnalysis(
                    session_id=debate_session.id,
                    user_id=current_user.id,
                )
                db.add(video_row)
            video_row.status = "unavailable"
            video_row.unavailable_reason = payload.video.reason

    debate_session.status = SessionStatus.queued
    debate_session.error_message = None
    db.commit()
    db.refresh(debate_session)

    submitted = jobs.submit(
        session_id,
        pipeline.build_job(session_id),
    )

    if not submitted:
        # Another request queued it between our status check
        # and here. Nothing to do.
        pass

    return _session_out(debate_session, video_row)


# ============================================================
# VISUAL SIGNALS
# ============================================================

@router.put("/{session_id}/visual-signals")
async def upload_visual_signals(
    session_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """
    Store the browser's VisualSignalTrack for a session that
    requested visual analysis. Body is gzip (preferred) or plain
    JSON, at most 2 MB compressed / 12 MB decompressed.

    Idempotent while the session has not started visual
    processing: a second upload replaces the first.
    """

    _require_video_enabled()

    debate_session = _get_owned_session(session_id, current_user, db)

    video_row = db.get(VideoAnalysis, session_id)

    if video_row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Visual analysis was not requested for this session.",
        )

    if video_row.processing_started_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Visual analysis has already started for this session.",
        )

    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > visual_config.MAX_COMPRESSED_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Signal track is too large.",
        )

    raw = await request.body()

    try:
        data = visual_signals.decode_body(
            raw,
            request.headers.get("content-encoding"),
            request.headers.get("content-type"),
        )
        track = visual_signals.parse_track(data, str(session_id))

    except SignalValidationError as error:
        if error.code == "payload_too_large":
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={"code": error.code, "message": error.detail},
            ) from None
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": error.code, "message": error.detail},
        ) from None

    key = visual_signals.store_track(current_user.id, debate_session.id, track)

    video_row.signal_track_key = key
    video_row.status = "received"
    video_row.schema_version = track.schema_version
    video_row.platform = track.source.platform
    video_row.runtime_version = track.source.runtime.version
    video_row.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"status": "received", "frames": track.frame_count}


# ============================================================
# READ
# ============================================================

@router.get("", response_model=list[SessionOut])
def list_sessions(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SessionOut]:

    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    rows = (
        db.query(DebateSession)
        .filter(DebateSession.user_id == current_user.id)
        .order_by(DebateSession.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    videos = _video_rows(db, [row.id for row in rows])

    return [_session_out(row, videos.get(row.id)) for row in rows]


@router.get("/{session_id}", response_model=SessionOut)
def get_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionOut:
    debate_session = _get_owned_session(
        session_id,
        current_user,
        db,
    )
    return _session_out(debate_session, _video_row(db, session_id))


@router.get(
    "/{session_id}/report",
    response_model=SessionReportOut,
)
def get_session_report(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionReportOut:
    """
    The full coaching result: scores, every feedback item, the
    deterministic metrics, and the labelled speech segments.
    """

    debate_session = _get_owned_session(
        session_id,
        current_user,
        db,
    )

    if debate_session.status != SessionStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This session has not finished analyzing yet."
            ),
        )

    if not debate_session.coaching_object_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The report for this session is missing.",
        )

    try:
        coaching = storage.download_json(
            debate_session.coaching_object_key
        )

        raw_metrics = (
            storage.download_json(
                debate_session.raw_metrics_object_key
            )
            if debate_session.raw_metrics_object_key
            else {}
        )

        speech_content = (
            storage.download_json(
                debate_session.speech_content_object_key
            )
            if debate_session.speech_content_object_key
            else {}
        )

        analysis = (
            storage.download_json(
                debate_session.analysis_object_key
            )
            if debate_session.analysis_object_key
            else {}
        )

    except storage.ObjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The report for this session is missing.",
        ) from None

    audio_url = None

    if debate_session.audio_object_key:
        audio_url = storage.generate_presigned_download_url(
            debate_session.audio_object_key
        )

    report = SessionReportOut(
        id=debate_session.id,
        title=debate_session.title,
        status=debate_session.status,
        created_at=debate_session.created_at,
        scores=coaching.get("scores", {}),
        feedback=coaching.get("feedback", []),
        raw_metrics=raw_metrics,
        speech_content=speech_content,
        analysis=analysis,
        audio_url=audio_url,
    )

    video_row = _video_row(db, session_id)

    if video_row is not None:
        report.video_analysis_status = video_row.status
        report.video_unavailable_reason = video_row.unavailable_reason
        report.visual_coaching_status = video_row.coaching_status

        # A missing document is not an error for the report as a
        # whole; the speech feedback is unaffected.
        if video_row.result_key:
            try:
                report.video_analysis = storage.download_json(video_row.result_key)
            except storage.ObjectNotFoundError:
                report.video_analysis = None

        if video_row.feedback_key:
            try:
                feedback_doc = storage.download_json(video_row.feedback_key)
            except storage.ObjectNotFoundError:
                feedback_doc = None
            if isinstance(feedback_doc, dict):
                report.correlated_moments = feedback_doc.get("correlated_moments")
                report.visual_feedback = feedback_doc

    return report


# ============================================================
# DELETE
# ============================================================

@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:

    debate_session = _get_owned_session(
        session_id,
        current_user,
        db,
    )

    if jobs.is_running(session_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This session is still being analyzed. "
                "Wait for it to finish, then delete it."
            ),
        )

    storage.delete_prefix(
        f"users/{current_user.id}/sessions/{session_id}/"
    )

    db.delete(debate_session)
    db.commit()
