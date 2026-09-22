"""
record_usage()'s atomic upsert (app/services/key_usage.py) uses
genuinely Postgres-specific SQL — ON CONFLICT ... DO UPDATE,
::jsonb casts — matching the real key_usage table
(migrations/0001_admin_dashboard.sql). The rest of this suite's
SQLite harness (tests/api/conftest.py) can't run it, so these
tests point key_usage's own SessionLocal at a real Postgres
instance instead of app.db.database's (which the root conftest
already redirects to a fake, never-connected URL for every other
test). Skips entirely if nothing is listening on that instance,
so the suite stays runnable without local Postgres set up.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("GCP_PROJECT_ID", "test-project")
os.environ.setdefault("GCP_STORAGE_BUCKET", "test-bucket")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@127.0.0.1:1/never")

from app.services import key_usage  # noqa: E402

REAL_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://coaching_app:localdevpassword@127.0.0.1:5433/debate_coach_dev",
)


@pytest.fixture
def real_session_local(monkeypatch):
    engine = create_engine(REAL_DATABASE_URL, pool_pre_ping=True)

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM key_usage LIMIT 0"))
    except OperationalError:
        engine.dispose()
        pytest.skip(
            f"No reachable Postgres with a key_usage table at {REAL_DATABASE_URL} "
            "(set TEST_DATABASE_URL to point elsewhere, or start the local dev "
            "instance and run migrations/0001_admin_dashboard.sql)."
        )

    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(key_usage, "SessionLocal", session_factory)

    yield session_factory

    engine.dispose()


@pytest.fixture
def key_id(real_session_local):
    """A key_id namespaced to this test run; cleaned up before and after."""
    kid = f"test_key_usage_{os.getpid()}"

    def _clean():
        session = real_session_local()
        session.execute(
            text("DELETE FROM key_usage WHERE key_id = :k"), {"k": kid}
        )
        session.commit()
        session.close()

    _clean()
    yield kid
    _clean()


def _row(real_session_local, kid: str):
    session = real_session_local()
    try:
        return session.execute(
            text("SELECT * FROM key_usage WHERE key_id = :k"), {"k": kid}
        ).mappings().first()
    finally:
        session.close()


@dataclass
class _FakeGroqUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class _FakeGeminiUsage:
    prompt_token_count: int
    candidates_token_count: int
    total_token_count: int


def test_first_call_inserts_a_row(real_session_local, key_id):
    key_usage.record_usage(
        key_id,
        "groq",
        ok=True,
        usage=_FakeGroqUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )

    row = _row(real_session_local, key_id)
    assert row["request_count"] == 1
    assert row["prompt_tokens"] == 10
    assert row["completion_tokens"] == 5
    assert row["total_tokens"] == 15
    assert row["window_reset_at"] > row["window_start"]


def test_second_call_within_window_increments(real_session_local, key_id):
    key_usage.record_usage(
        key_id, "groq", ok=True,
        usage=_FakeGroqUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )
    key_usage.record_usage(
        key_id, "groq", ok=True,
        usage=_FakeGroqUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
    )

    row = _row(real_session_local, key_id)
    assert row["request_count"] == 2
    assert row["prompt_tokens"] == 13
    assert row["completion_tokens"] == 7
    assert row["total_tokens"] == 20


def test_failed_call_still_increments_requests_but_not_tokens(real_session_local, key_id):
    key_usage.record_usage(key_id, "groq", ok=False)

    row = _row(real_session_local, key_id)
    assert row["request_count"] == 1
    assert row["prompt_tokens"] == 0
    assert row["total_tokens"] == 0


def test_gemini_usage_fields_are_extracted_correctly(real_session_local, key_id):
    key_usage.record_usage(
        key_id, "gemini", ok=True,
        usage=_FakeGeminiUsage(
            prompt_token_count=100, candidates_token_count=40, total_token_count=140
        ),
    )

    row = _row(real_session_local, key_id)
    assert (row["prompt_tokens"], row["completion_tokens"], row["total_tokens"]) == (100, 40, 140)


def test_lapsed_window_resets_instead_of_accumulating(real_session_local, key_id):
    key_usage.record_usage(
        key_id, "groq", ok=True,
        usage=_FakeGroqUsage(prompt_tokens=999, completion_tokens=999, total_tokens=1998),
    )

    # Force the window into the past, as if it lapsed with nobody
    # calling in to reset it.
    session = real_session_local()
    session.execute(
        text(
            "UPDATE key_usage SET window_reset_at = :past WHERE key_id = :k"
        ),
        {"past": datetime.now(timezone.utc) - timedelta(minutes=1), "k": key_id},
    )
    session.commit()
    session.close()

    key_usage.record_usage(
        key_id, "groq", ok=True,
        usage=_FakeGroqUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )

    row = _row(real_session_local, key_id)
    assert row["request_count"] == 1
    assert row["total_tokens"] == 2
    assert row["window_reset_at"] > datetime.now(timezone.utc)


def test_rate_limit_headers_are_stored_and_persist_across_calls_without_them(
    real_session_local, key_id
):
    key_usage.record_usage(
        key_id, "groq", ok=True,
        usage=_FakeGroqUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        rate_limit_headers={"x-ratelimit-remaining-requests": "27"},
    )
    row = _row(real_session_local, key_id)
    assert row["last_rate_limit_headers"] == {"x-ratelimit-remaining-requests": "27"}

    # Gemini-shaped call with no headers shouldn't wipe the last
    # real snapshot — COALESCE keeps the previous value.
    key_usage.record_usage(key_id, "groq", ok=True, usage=None, rate_limit_headers=None)
    row = _row(real_session_local, key_id)
    assert row["last_rate_limit_headers"] == {"x-ratelimit-remaining-requests": "27"}


def test_gemini_fresh_window_resets_at_next_midnight_pacific():
    now = datetime(2026, 9, 22, 18, 0, tzinfo=timezone.utc)  # 11:00 PT
    start, reset_at = key_usage._fresh_window("gemini", now)

    assert start == now
    reset_pt = reset_at.astimezone(key_usage._PACIFIC)
    assert (reset_pt.hour, reset_pt.minute, reset_pt.second) == (0, 0, 0)
    assert reset_pt.date() == (now.astimezone(key_usage._PACIFIC).date() + timedelta(days=1))


def test_groq_fresh_window_is_rolling_24h():
    now = datetime(2026, 9, 22, 18, 0, tzinfo=timezone.utc)
    start, reset_at = key_usage._fresh_window("groq", now)

    assert start == now
    assert reset_at == now + timedelta(hours=24)
