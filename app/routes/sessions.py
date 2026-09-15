import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.models.session import DebateSession, SessionStatus
from app.models.user import User
from app.routes.deps import get_current_user
from app.schemas.session import (
    ALLOWED_CONTENT_TYPES,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionOut,
    SessionReportOut,
)
from app.services import jobs, pipeline, storage


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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DebateSession:
    """
    Begin analysis. Call this once the upload PUT has returned
    a 200.

    Returns immediately. The pipeline runs in the background
    and takes minutes, so poll GET /sessions/{id} for progress.
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
            return debate_session

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

    return debate_session


# ============================================================
# READ
# ============================================================

@router.get("", response_model=list[SessionOut])
def list_sessions(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DebateSession]:

    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    return (
        db.query(DebateSession)
        .filter(DebateSession.user_id == current_user.id)
        .order_by(DebateSession.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )


@router.get("/{session_id}", response_model=SessionOut)
def get_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DebateSession:
    return _get_owned_session(
        session_id,
        current_user,
        db,
    )


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

    return SessionReportOut(
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
