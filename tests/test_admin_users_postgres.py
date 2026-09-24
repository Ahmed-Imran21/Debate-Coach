"""
app/services/admin_users.py against real Postgres: the SQLite suite
(tests/api/test_admin_users.py) can't prove Postgres's own ILIKE,
NULLS LAST, row-value comparison and uuid ordering agree with the
cursor logic. Runs inside one transaction that is always rolled
back, so nothing is left in the database. Skips if the local dev
instance isn't reachable (same convention as tests/test_key_usage.py).
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("GCP_PROJECT_ID", "test-project")
os.environ.setdefault("GCP_STORAGE_BUCKET", "test-bucket")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@127.0.0.1:1/never")

from app.models.session import DebateSession, SessionStatus  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import admin_users  # noqa: E402

REAL_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://coaching_app:localdevpassword@127.0.0.1:5433/debate_coach_dev",
)
BASE = datetime(2030, 1, 1, tzinfo=timezone.utc)  # after any real row, so ours sort first
TAG = f"pgtest-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def db():
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


def _add(db, n, *, created=None, seen=None, first="F", last="L"):
    user = User(
        email=f"{TAG}-{n}@example.test",
        password_hash="x",
        first_name=first,
        last_name=last,
        created_at=created or BASE,
        last_seen_at=seen,
    )
    db.add(user)
    db.flush()
    return user


def _walk(db, **kwargs):
    ids, cursor = [], None
    while True:
        rows, cursor = admin_users.list_users(db, cursor=cursor, **kwargs)
        ids += [r.id for r in rows]
        if cursor is None:
            return ids


def test_newest_walk_with_ties_on_postgres(db):
    users = [_add(db, i, created=BASE - timedelta(minutes=i // 4)) for i in range(30)]

    ids = _walk(db, search=TAG, limit=7)

    assert ids == [u.id for u in sorted(users, key=lambda u: (u.created_at, u.id), reverse=True)]


def test_last_seen_walk_with_nulls_and_ties_on_postgres(db):
    users = [
        _add(db, i, seen=None if i % 4 == 0 else BASE - timedelta(hours=i // 3))
        for i in range(26)
    ]

    ids = _walk(db, search=TAG, sort="last_seen", limit=5)

    by_id = sorted(users, key=lambda u: u.id, reverse=True)
    expected = sorted(by_id, key=lambda u: (u.last_seen_at is None, -(u.last_seen_at or BASE).timestamp()))
    assert ids == [u.id for u in expected]


def test_ilike_search_and_session_counts_on_postgres(db):
    a = _add(db, "a", first="Émile", last="O'Brien")
    b = _add(db, "b", first="x", last="EMILE-SMITH")
    _add(db, "c", first="nobody", last="here")
    for _ in range(2):
        db.add(DebateSession(user_id=a.id, status=SessionStatus.completed))
    db.flush()

    rows, _ = admin_users.list_users(db, search=f"{TAG}-a")
    assert [r.id for r in rows] == [a.id]
    assert rows[0].session_count == 2

    rows, _ = admin_users.list_users(db, search="o'brien")
    assert a.id in {r.id for r in rows}

    rows, _ = admin_users.list_users(db, search="MILE-sm")
    assert [r.id for r in rows] == [b.id]

    rows, _ = admin_users.list_users(db, search="émile o'brien")
    assert [r.id for r in rows] == [a.id]


def test_the_trigram_and_keyset_indexes_exist(db):
    names = set(db.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'users'")).scalars())
    assert {
        "idx_users_created_at_id",
        "idx_users_last_seen_at_id",
        "idx_users_search_trgm",
    } <= names
