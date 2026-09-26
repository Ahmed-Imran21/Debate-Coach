import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.last_seen import LastSeenMiddleware
from app.core.rate_limit import PerClientRateLimitMiddleware
from app.db.database import Base, engine as db_engine
from app.routes import admin, auth, progress_reports, sessions, users
from app.services import cleanup, engine, jobs
from app.services.audio_convert import ffmpeg_available


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


API_PREFIX = "/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):

    # For anything beyond local development, replace this with
    # Alembic migrations run as a deploy step.
    Base.metadata.create_all(bind=db_engine)

    # Before jobs.start() below lets any new pipeline begin, so a
    # session found mid-pipeline here is guaranteed left over from
    # whatever process ran before this one, never one this process
    # is already running. Logs its own summary internally.
    cleanup.reap_stuck_pipelines()

    if not ffmpeg_available():
        logger.warning(
            "ffmpeg was not found on PATH. Every upload will "
            "fail at the conversion step until it is installed."
        )

    api_client = engine.start()

    key_count = len(api_client.get_keys())

    if key_count == 0:
        logger.warning(
            "No API keys were loaded. Check that the "
            "GROQ_*/GEMINI_* key variables are present in the "
            "environment and follow the naming convention in "
            "api/config.py."
        )
    else:
        logger.info(
            "Loaded %s API keys across the model pools.",
            key_count,
        )

    jobs.start(max_workers=settings.pipeline_workers)

    logger.info(
        "Pipeline pool ready with %s workers.",
        settings.pipeline_workers,
    )

    cleanup.start()

    yield

    logger.info("Shutting down.")

    cleanup.shutdown()

    # Stop accepting new pipeline work first, then drain the
    # API queues. Doing it the other way round would leave
    # in-flight pipeline threads blocked on a dead queue.
    jobs.shutdown(wait=False)
    engine.shutdown()


def api_docs_urls(enabled: bool) -> dict[str, str | None]:
    # redoc too: FastAPI serves /redoc by default unless told not to.
    if enabled:
        return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}
    return {"docs_url": None, "redoc_url": None, "openapi_url": None}


app = FastAPI(
    title="Debate Coach API",
    version="1.0.0",
    lifespan=lifespan,
    # A trailing-slash request to a real route would otherwise get a
    # 307 to the slashless path while an unknown path gets a 404 —
    # enough to discover the admin routes. Nothing in web/ calls a
    # path with a trailing slash.
    redirect_slashes=False,
    **api_docs_urls(settings.api_docs_enabled),
)

ADMIN_PREFIX = f"{API_PREFIX}/admin"


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    # Auth is a Bearer header, never a cookie, so no cross-origin
    # request needs credentials; the admin gate cookie lives on the
    # frontend's own domain (web/app/api/session/route.ts).
    allow_credentials=False,
    # Exactly what web/ sends.
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Content-Encoding"],
)

app.add_middleware(
    PerClientRateLimitMiddleware,
    max_requests_per_minute=settings.request_rate_limit_per_minute,
    trust_forwarded_for=settings.trust_forwarded_for,
)

app.add_middleware(LastSeenMiddleware)


app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(sessions.router, prefix=API_PREFIX)
app.include_router(progress_reports.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)


@app.exception_handler(StarletteHTTPException)
async def admin_routes_look_nonexistent(
    request: Request,
    exc: StarletteHTTPException,
) -> Response:
    # A wrong method on a real path is a 405 (with an Allow header),
    # which confirms the path exists. For the admin routes, answer
    # exactly as an unknown path would. require_admin (deps.py) does
    # the same for every other non-admin case.
    if exc.status_code == 405 and (
        request.url.path == ADMIN_PREFIX
        or request.url.path.startswith(f"{ADMIN_PREFIX}/")
    ):
        exc = StarletteHTTPException(status_code=404, detail="Not Found")
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def validation_error_without_input(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    # FastAPI's default handler echoes each rejected field's value
    # back as "input" — for signup that's the plaintext password.
    # The frontend only reads "msg" (web/lib/api.ts readError).
    errors = [
        {key: value for key, value in error.items() if key != "input"}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(errors)},
    )


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get(f"{API_PREFIX}/status")
def system_status() -> dict:
    """
    Capacity snapshot. Useful when a session sits in the queue
    and you want to know whether the key pool is saturated.
    """

    return {
        **engine.status(),
        "pipelines_running": jobs.in_flight_count(),
        "pipeline_workers": settings.pipeline_workers,
    }
