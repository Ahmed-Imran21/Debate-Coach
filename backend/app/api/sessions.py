import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.debate_analysis import coaching, delivery_metrics, preprocessing, semantic_analysis
from app.models.session import DebateSession, SessionStatus
from app.models.user import User
from app.schemas.session import SessionCreateResponse, SessionOut
from app.services import storage
from app.services.transcription import AllProvidersFailedError, transcribe

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _get_owned_session(session_id: uuid.UUID, current_user: User, db: Session) -> DebateSession:
    debate_session = db.get(DebateSession, session_id)
    if debate_session is None or debate_session.user_id != current_user.id:
        # Same 404 whether it doesn't exist or belongs to someone else —
        # don't leak which sessions exist.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return debate_session


@router.post("", response_model=SessionCreateResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionCreateResponse:
    debate_session = DebateSession(user_id=current_user.id, status=SessionStatus.created)
    db.add(debate_session)
    db.commit()
    db.refresh(debate_session)

    object_key = storage.build_object_key(current_user.id, debate_session.id, "audio.m4a")
    debate_session.audio_object_key = object_key
    db.commit()

    upload_url = storage.generate_presigned_upload_url(object_key)

    return SessionCreateResponse(id=debate_session.id, upload_url=upload_url, status=debate_session.status)


@router.post("/{session_id}/transcribe", response_model=SessionOut)
async def trigger_transcription(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DebateSession:
    """Called by the client once it has PUT the audio file to the presigned
    upload URL. Downloads the audio from storage, runs it through the
    transcription fallback chain, and stores the result back in storage."""
    debate_session = _get_owned_session(session_id, current_user, db)

    if debate_session.audio_object_key is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No audio uploaded for this session")

    audio_bytes = storage.download_bytes(debate_session.audio_object_key)

    try:
        result = await transcribe(audio_bytes, filename="audio.m4a")
    except AllProvidersFailedError as exc:
        debate_session.status = SessionStatus.failed
        debate_session.error_message = str(exc)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Transcription failed across all providers",
        ) from exc

    transcription_key = storage.build_object_key(current_user.id, debate_session.id, "transcription.json")
    storage.upload_json(transcription_key, {"text": result.text, "words": result.words})

    debate_session.transcription_object_key = transcription_key
    debate_session.transcription_provider = result.provider
    debate_session.status = SessionStatus.transcribed
    db.commit()
    db.refresh(debate_session)

    return debate_session


@router.post("/{session_id}/analyze", response_model=SessionOut)
def run_debate_analysis(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DebateSession:
    """Runs the full debate-analysis pipeline against an already-transcribed
    session: delivery_metrics (deterministic) -> preprocessing ->
    semantic_analysis (LLM, structured JSON) -> coaching (LLM, structured
    JSON). Single-speaker scope only, per current architecture."""
    debate_session = _get_owned_session(session_id, current_user, db)

    if debate_session.transcription_object_key is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session has not been transcribed yet",
        )

    transcription_data = storage.download_json(debate_session.transcription_object_key)
    words = transcription_data.get("words", [])

    # VAD pause data is optional here — wire in your Silero VAD output
    # (from the audio-analysis branch) if/when it's also migrated to
    # object storage. Falls back to word-gap-derived pause stats otherwise.
    vad_segments = None
    if debate_session.analysis_object_key:
        vad_data = storage.download_json(debate_session.analysis_object_key)
        vad_segments = vad_data.get("segments")

    try:
        metrics = delivery_metrics.compute_delivery_metrics(words, vad_segments)

        metrics_key = storage.build_object_key(current_user.id, debate_session.id, "delivery_metrics.json")
        storage.upload_json(metrics_key, metrics)
        debate_session.delivery_metrics_object_key = metrics_key

        llm_input = preprocessing.build_llm_input(words, raw_text=transcription_data.get("text"))
        semantics = semantic_analysis.analyze_semantics(llm_input)

        semantics_key = storage.build_object_key(current_user.id, debate_session.id, "semantic_analysis.json")
        storage.upload_json(semantics_key, semantics)
        debate_session.semantic_analysis_object_key = semantics_key

        debate_session.status = SessionStatus.debate_analyzed
        db.commit()

        report = coaching.generate_coaching_report(metrics, semantics)
        report_key = storage.build_object_key(current_user.id, debate_session.id, "coaching_report.json")
        storage.upload_json(report_key, report)
        debate_session.coaching_report_object_key = report_key
        debate_session.status = SessionStatus.coached

    except (semantic_analysis.SemanticAnalysisError, coaching.CoachingError) as exc:
        debate_session.status = SessionStatus.failed
        debate_session.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    db.commit()
    db.refresh(debate_session)
    return debate_session


@router.get("", response_model=list[SessionOut])
def list_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DebateSession]:
    return (
        db.query(DebateSession)
        .filter(DebateSession.user_id == current_user.id)
        .order_by(DebateSession.created_at.desc())
        .all()
    )


@router.get("/{session_id}", response_model=SessionOut)
def get_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DebateSession:
    return _get_owned_session(session_id, current_user, db)
