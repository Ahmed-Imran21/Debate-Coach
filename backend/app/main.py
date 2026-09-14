from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, sessions, users
from app.core.config import settings
from app.core.rate_limit import PerClientRateLimitMiddleware
from app.db.database import Base, engine

# Create tables on startup. For anything beyond local dev, replace this
# with Alembic migrations (`alembic upgrade head`) run as a deploy step.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Debate Coach API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(PerClientRateLimitMiddleware, max_requests_per_minute=60)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(sessions.router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
