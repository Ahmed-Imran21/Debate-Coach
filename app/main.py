import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.rate_limit import PerClientRateLimitMiddleware
from app.db.database import Base, engine as db_engine
from app.routes import auth, sessions, users
from app.services import engine, jobs
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

    yield

    logger.info("Shutting down.")

    # Stop accepting new pipeline work first, then drain the
    # API queues. Doing it the other way round would leave
    # in-flight pipeline threads blocked on a dead queue.
    jobs.shutdown(wait=False)
    engine.shutdown()


app = FastAPI(
    title="Debate Coach API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    PerClientRateLimitMiddleware,
    max_requests_per_minute=settings.request_rate_limit_per_minute,
    trust_forwarded_for=settings.trust_forwarded_for,
)


app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(sessions.router, prefix=API_PREFIX)


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
