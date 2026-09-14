import json
import shutil

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from api.client import APIClient

from session_manager import SessionManager
from session import STATUS_COMPLETED, STATUS_FAILED

from server.audio_convert import (
    AudioConversionError,
    normalize_audio_to_wav,
)
from server.concurrency import PipelineExecutor
from server.pipeline import run_session_pipeline
from server.schemas import (
    FeedbackItemResponse,
    ScoreBreakdown,
    SessionCreatedResponse,
    SessionResultsResponse,
    SessionStatusResponse,
    SystemStatusResponse,
)


# ============================================================
# APPLICATION STATE
#
# Exactly one APIClient and one PipelineExecutor for the whole
# process, shared by every request — the same principle main.py
# already followed for a single CLI session, now serving many
# concurrent users.
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    print("\nInitializing API system...")

    api_client = APIClient()

    print(
        f"Loaded {len(api_client.get_keys())} API keys."
    )

    app.state.api_client = api_client
    app.state.session_manager = SessionManager()
    app.state.pipeline_executor = PipelineExecutor()

    yield

    print("\nShutting down...")

    app.state.pipeline_executor.shutdown(wait=False)
    app.state.api_client.shutdown()


app = FastAPI(
    title="Debate Coach API",
    lifespan=lifespan,
)


# ============================================================
# CREATE SESSION (upload audio)
# ============================================================

@app.post(
    "/sessions",
    response_model=SessionCreatedResponse,
    status_code=202,
)
async def create_session(audio: UploadFile = File(...)):
    """
    Upload a recorded debate speech and start the analysis
    pipeline in the background.

    Returns immediately (202 Accepted) with a session_id the
    client polls via GET /sessions/{session_id} for progress,
    and GET /sessions/{session_id}/results once completed.
    """

    session_manager: SessionManager = app.state.session_manager
    api_client: APIClient = app.state.api_client
    pipeline_executor: PipelineExecutor = (
        app.state.pipeline_executor
    )

    session = session_manager.create_session()

    # -------------------------------------------------
    # Save the raw upload to a temp file inside the
    # session directory, then normalize it to the exact
    # 16kHz mono 16-bit PCM WAV format the rest of the
    # pipeline assumes.
    # -------------------------------------------------

    raw_upload_path = (
        session.session_directory / f"upload_{audio.filename}"
    )

    try:

        with open(raw_upload_path, "wb") as destination:
            shutil.copyfileobj(audio.file, destination)

        normalize_audio_to_wav(
            input_path=raw_upload_path,
            output_path=session.audio_path,
        )

    except AudioConversionError as error:

        session.mark_failed(error=str(error))

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    finally:

        raw_upload_path.unlink(missing_ok=True)

    session.mark_uploaded()

    # -------------------------------------------------
    # Kick off the pipeline in the background.
    #
    # This request returns immediately; the pipeline runs
    # on the shared PipelineExecutor, bounded independently
    # of this HTTP request/response cycle.
    # -------------------------------------------------

    submitted = pipeline_executor.submit(
        session.session_id,
        run_session_pipeline,
        session,
        api_client,
    )

    if not submitted:

        raise HTTPException(
            status_code=409,
            detail=(
                "A pipeline job for this session is already "
                "running."
            ),
        )

    return SessionCreatedResponse(
        session_id=session.session_id,
        status=session.status,
    )


# ============================================================
# SESSION STATUS
# ============================================================

@app.get(
    "/sessions/{session_id}",
    response_model=SessionStatusResponse,
)
async def get_session_status(session_id: str):

    session_manager: SessionManager = app.state.session_manager

    try:
        session = session_manager.load_session(session_id)

    except FileNotFoundError:

        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found.",
        )

    return SessionStatusResponse(
        **session.to_status_dict()
    )


# ============================================================
# SESSION RESULTS
# ============================================================

@app.get(
    "/sessions/{session_id}/results",
    response_model=SessionResultsResponse,
)
async def get_session_results(session_id: str):

    session_manager: SessionManager = app.state.session_manager

    try:
        session = session_manager.load_session(session_id)

    except FileNotFoundError:

        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found.",
        )

    if session.status == STATUS_FAILED:

        raise HTTPException(
            status_code=422,
            detail=(
                f"Session failed: "
                f"{session.error or 'unknown error'}"
            ),
        )

    if session.status != STATUS_COMPLETED:

        raise HTTPException(
            status_code=409,
            detail=(
                f"Session is not completed yet "
                f"(status='{session.status}')."
            ),
        )

    if not session.feedback_path.exists():

        raise HTTPException(
            status_code=500,
            detail=(
                "Session is marked completed but "
                "feedback.json is missing."
            ),
        )

    with open(
        session.feedback_path,
        "r",
        encoding="utf-8",
    ) as file:

        feedback_data = json.load(file)

    return SessionResultsResponse(
        session_id=session_id,
        status=session.status,
        scores=ScoreBreakdown(**feedback_data["scores"]),
        feedback=[
            FeedbackItemResponse(**item)
            for item in feedback_data["feedback"]
        ],
    )


# ============================================================
# SYSTEM STATUS (API keys + queue)
# ============================================================

@app.get(
    "/system/status",
    response_model=SystemStatusResponse,
)
async def get_system_status():

    api_client: APIClient = app.state.api_client

    return SystemStatusResponse(
        queue_size=api_client.get_queue_size(),
        keys=api_client.get_status(),
    )


# ============================================================
# ERROR HANDLING
# ============================================================

@app.exception_handler(FileNotFoundError)
async def file_not_found_handler(request, exc):

    return JSONResponse(
        status_code=404,
        content={"detail": str(exc)},
    )