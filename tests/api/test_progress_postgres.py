"""
GET /v1/sessions/progress against real Postgres. The SQLite suite
(test_progress.py) stores timestamps as naive strings, so it can't
prove Postgres's own timestamptz comparison puts the rolling-window
edges where the route means them. Runs inside one transaction that
is always rolled back, so nothing is left in the database. Skips if
the local dev instance isn't reachable (same convention as
tests/test_admin_users_postgres.py).
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

REAL_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://coaching_app:localdevpassword@127.0.0.1:5433/debate_coach_dev",
)
TAG = f"pgprogress-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def pg_db():
    engine = create_engine(REAL_DATABASE_URL)
    try:
        connection = engine.connect()
    except OperationalError:
        engine.dispose()
        pytest.skip(f"No reachable Postgres at {REAL_DATABASE_URL}")
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()
        engine.dispose()


@pytest.fixture
def get(app_module, pg_db):
    from fastapi.testclient import TestClient

    from app.core.security import create_access_token
    from app.db.database import get_db

    app = app_module.app
    app.dependency_overrides[get_db] = lambda: pg_db
    client = TestClient(app)

    def _get(user, **params):
        headers = {"Authorization": f"Bearer {create_access_token(str(user.id))}"}
        response = client.get("/v1/sessions/progress", params=params, headers=headers)
        assert response.status_code == 200, response.text
        return response.json()

    yield _get
    app.dependency_overrides.clear()


def _user(db, n):
    from app.models.user import User

    user = User(email=f"{TAG}-{n}@example.test", password_hash="x", first_name="F", last_name="L")
    db.add(user)
    db.flush()
    return user


def _session(db, user, hours_ago, status=None, score=50.0):
    from app.models.session import DebateSession, SessionStatus

    row = DebateSession(
        user_id=user.id,
        status=status or SessionStatus.completed,
        created_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        overall_score=score,
        score_rebuttal=None,
    )
    db.add(row)
    db.flush()
    return row


def test_rolling_window_edges_on_postgres(pg_db, get):
    alice = _user(pg_db, "a")
    rows = {h: _session(pg_db, alice, h).id for h in (23.9, 24.1, 167.9, 168.1, 719.9, 720.1)}

    def returned(range_):
        return {uuid.UUID(p["session_id"]) for p in get(alice, metric="overall", range=range_)}

    assert returned("1d") == {rows[23.9]}
    assert returned("1w") == {rows[23.9], rows[24.1], rows[167.9]}
    assert returned("1m") == {rows[h] for h in (23.9, 24.1, 167.9, 168.1, 719.9)}


def test_count_ranges_order_and_isolation_on_postgres(pg_db, get):
    from app.models.session import SessionStatus

    alice, bob = _user(pg_db, "a"), _user(pg_db, "b")
    mine = [_session(pg_db, alice, h, score=float(h)).id for h in (30, 20, 10, 5, 4, 3, 2)]  # oldest first
    for h in (1, 1.5, 2.5):
        _session(pg_db, bob, h)
    _session(pg_db, alice, 0.5, status=SessionStatus.failed)

    points = get(alice, metric="overall", range="5")

    assert [uuid.UUID(p["session_id"]) for p in points] == mine[-5:]
    assert [p["score"] for p in points] == [10.0, 5.0, 4.0, 3.0, 2.0]
    stamps = [datetime.fromisoformat(p["created_at"]) for p in points]
    assert stamps == sorted(stamps)
    assert all(s.tzinfo is not None for s in stamps)


def test_null_rebuttal_on_postgres(pg_db, get):
    alice = _user(pg_db, "a")
    _session(pg_db, alice, 1)

    assert [p["score"] for p in get(alice, metric="rebuttal", range="5")] == [None]
