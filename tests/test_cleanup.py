"""
app/services/cleanup.py touches session rows outside any FastAPI
request (called from the lifespan hook and a background thread),
so it opens its own SessionLocal exactly like app/services/
pipeline.py and app/services/key_usage.py do — pointed at a real
local Postgres instance here for the same reason key_usage's own
tests are (see tests/test_key_usage.py's docstring): the SQLite
harness the rest of the API-route suite uses is a per-request
override of FastAPI's get_db dependency, which nothing here goes
through. Skips entirely if nothing is listening on that instance.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("GCP_PROJECT_ID", "test-project")
os.environ.setdefault("GCP_STORAGE_BUCKET", "test-bucket")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@127.0.0.1:1/never")

from app.models.session import DebateSession, SessionStatus  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import cleanup, storage  # noqa: E402

REAL_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://coaching_app:localdevpassword@127.0.0.1:5433/debate_coach_dev",
)


@pytest.fixture
def real_session_local(monkeypatch):
    engine = create_engine(REAL_DATABASE_URL, pool_pre_ping=True)

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM sessions LIMIT 0"))
    except OperationalError:
        engine.dispose()
        pytest.skip(
            f"No reachable Postgres with a sessions table at {REAL_DATABASE_URL} "
            "(set TEST_DATABASE_URL to point elsewhere, or start the local dev instance)."
        )

    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(cleanup, "SessionLocal", session_factory)

    yield session_factory

    engine.dispose()


@pytest.fixture
def deleted_prefixes(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(storage, "delete_prefix", lambda prefix: calls.append(prefix) or 0)
    return calls


@pytest.fixture
def user(real_session_local):
    db = real_session_local()
    row = User(
        email=f"cleanup-test-{uuid.uuid4()}@test.com",
        password_hash="x",
        first_name="T",
        last_name="U",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    user_id = row.id
    db.close()

    yield user_id

    db = real_session_local()
    db.query(User).filter(User.id == user_id).delete()
    db.commit()
    db.close()


def _make_session(real_session_local, user_id, status: SessionStatus, created_at=None, **extra) -> uuid.UUID:
    db = real_session_local()
    row = DebateSession(
        id=uuid.uuid4(),
        user_id=user_id,
        status=status,
        created_at=created_at or datetime.now(timezone.utc),
        **extra,
    )
    db.add(row)
    db.commit()
    session_id = row.id
    db.close()
    return session_id


def _fetch(real_session_local, session_id):
    db = real_session_local()
    row = db.get(DebateSession, session_id)
    db.close()
    return row


# ---------------------------------------------------------------
# reap_stuck_pipelines
# ---------------------------------------------------------------

@pytest.mark.parametrize(
    "status",
    [
        SessionStatus.queued,
        SessionStatus.converting,
        SessionStatus.transcribing,
        SessionStatus.analyzing_audio,
        SessionStatus.calculating_metrics,
        SessionStatus.analyzing_speech,
        SessionStatus.coaching,
    ],
)
def test_reap_stuck_pipelines_fails_every_non_terminal_stage(real_session_local, user, status):
    sid = _make_session(real_session_local, user, status)

    count = cleanup.reap_stuck_pipelines()

    assert count >= 1
    row = _fetch(real_session_local, sid)
    assert row.status == SessionStatus.failed
    assert row.error_message == cleanup._INTERRUPTED_MESSAGE


def test_reap_stuck_pipelines_never_touches_completed(real_session_local, user):
    sid = _make_session(real_session_local, user, SessionStatus.completed)

    cleanup.reap_stuck_pipelines()

    row = _fetch(real_session_local, sid)
    assert row.status == SessionStatus.completed
    assert row.error_message is None


def test_reap_stuck_pipelines_never_touches_created_or_already_failed(real_session_local, user):
    created_id = _make_session(real_session_local, user, SessionStatus.created)
    failed_id = _make_session(real_session_local, user, SessionStatus.failed, error_message="original reason")

    cleanup.reap_stuck_pipelines()

    assert _fetch(real_session_local, created_id).status == SessionStatus.created
    row = _fetch(real_session_local, failed_id)
    assert row.status == SessionStatus.failed
    assert row.error_message == "original reason"


def test_reap_stuck_pipelines_returns_zero_when_nothing_stuck(real_session_local, user):
    _make_session(real_session_local, user, SessionStatus.completed)
    assert cleanup.reap_stuck_pipelines() == 0


# ---------------------------------------------------------------
# reap_abandoned_uploads
# ---------------------------------------------------------------

def test_reap_abandoned_uploads_deletes_a_stale_created_session_and_its_storage(
    real_session_local, user, deleted_prefixes
):
    old = datetime.now(timezone.utc) - cleanup.ABANDONED_UPLOAD_GRACE_PERIOD - timedelta(minutes=1)
    sid = _make_session(real_session_local, user, SessionStatus.created, created_at=old)

    count = cleanup.reap_abandoned_uploads()

    assert count >= 1
    assert _fetch(real_session_local, sid) is None
    assert f"users/{user}/sessions/{sid}/" in deleted_prefixes


def test_reap_abandoned_uploads_leaves_a_recent_created_session_alone(
    real_session_local, user, deleted_prefixes
):
    recent = datetime.now(timezone.utc) - timedelta(minutes=5)
    sid = _make_session(real_session_local, user, SessionStatus.created, created_at=recent)

    cleanup.reap_abandoned_uploads()

    assert _fetch(real_session_local, sid) is not None
    assert deleted_prefixes == []


@pytest.mark.parametrize(
    "status",
    [SessionStatus.completed, SessionStatus.failed, SessionStatus.queued, SessionStatus.coaching],
)
def test_reap_abandoned_uploads_never_touches_non_created_status_regardless_of_age(
    real_session_local, user, deleted_prefixes, status
):
    ancient = datetime.now(timezone.utc) - timedelta(days=365)
    sid = _make_session(real_session_local, user, status, created_at=ancient)

    cleanup.reap_abandoned_uploads()

    assert _fetch(real_session_local, sid) is not None
    assert deleted_prefixes == []


def test_reap_abandoned_uploads_returns_zero_when_nothing_abandoned(real_session_local, user, deleted_prefixes):
    _make_session(real_session_local, user, SessionStatus.created)
    assert cleanup.reap_abandoned_uploads() == 0
    assert deleted_prefixes == []
