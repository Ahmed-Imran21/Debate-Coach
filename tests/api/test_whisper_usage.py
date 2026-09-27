"""
Whisper (transcription) key usage on the admin dashboard.

- WhisperClient reports every attempt through its on_usage hook: ok,
  failed or rate-limited (the real queue and worker run; only the
  Groq call itself is replaced).
- app/services/whisper_usage.py persists one row per attempt and
  turns them into the dashboard's rolling figures.
- GET /v1/admin/stats returns them as whisper_keys, and the LLM keys
  output is unchanged.
"""

import os
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture
def wav(tmp_path) -> Path:
    """A real 2.5-second silent WAV, so the client measures real audio time."""
    path = tmp_path / "speech.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(b"\x00\x00" * 40000)
    return path


@pytest.fixture
def whisper_client(monkeypatch):
    """A WhisperClient with one fake key (the real keys are hidden)."""
    from api.whisper import WhisperClient

    for name in list(os.environ):
        if name.startswith(WhisperClient.KEY_PREFIX):
            monkeypatch.delenv(name)
    monkeypatch.setenv(f"{WhisperClient.KEY_PREFIX}1", "test-value-not-a-key")

    clients = []

    def make(on_usage, execute):
        client = WhisperClient(worker_count=1, on_usage=on_usage)
        client._execute = execute
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.shutdown()


class RateLimited(Exception):
    status_code = 429


# ---------------------------------------------------------------
# Every attempt is reported
# ---------------------------------------------------------------

def test_a_transcription_reports_its_usage(whisper_client, wav):
    calls = []
    client = whisper_client(lambda key_id, **kw: calls.append((key_id, kw)), lambda key, request: "transcript")

    assert client.transcribe(wav, max_wait_seconds=10) == "transcript"
    assert calls == [("groq_whisper_large_v3_1", {"audio_seconds": 2.5, "outcome": "ok"})]


@pytest.mark.parametrize(
    "error, outcome",
    [(RuntimeError("provider exploded"), "failed"), (RateLimited("slow down"), "rate_limited"), (RuntimeError("HTTP 429 Too Many Requests"), "rate_limited")],
    ids=["failure", "rate-limit-status", "rate-limit-message"],
)
def test_a_failed_transcription_reports_a_failure(whisper_client, wav, error, outcome):
    calls = []

    def boom(key, request):
        raise error

    client = whisper_client(lambda key_id, **kw: calls.append((key_id, kw)), boom)

    with pytest.raises(type(error)):
        client.transcribe(wav, max_wait_seconds=10)
    assert calls == [("groq_whisper_large_v3_1", {"audio_seconds": 2.5, "outcome": outcome})]


def test_a_broken_hook_never_breaks_the_transcription(whisper_client, wav):
    def broken(key_id, **kw):
        raise RuntimeError("database down")

    client = whisper_client(broken, lambda key, request: "transcript")
    assert client.transcribe(wav, max_wait_seconds=10) == "transcript"


def test_the_app_wires_the_hook_to_the_database_writer(monkeypatch):
    from app.services import engine
    from app.services.whisper_usage import record_whisper_usage

    seen = {}

    class FakeAPIClient:
        def __init__(self, on_usage=None, on_whisper_usage=None):
            seen.update(on_usage=on_usage, on_whisper_usage=on_whisper_usage)

    monkeypatch.setattr(engine, "APIClient", FakeAPIClient)
    monkeypatch.setattr(engine, "_api_client", None)
    engine.start()

    assert seen["on_whisper_usage"] is record_whisper_usage


# ---------------------------------------------------------------
# Persisting and reading back
# ---------------------------------------------------------------

def test_each_attempt_is_stored_as_one_row(factory, db):
    from app.models.key_usage import KeyUsage
    from app.models.whisper_usage import WhisperUsageEvent
    from app.services.whisper_usage import record_whisper_usage

    record_whisper_usage("groq_whisper_large_v3_1", audio_seconds=61.5, outcome="ok", session_factory=factory)
    record_whisper_usage("groq_whisper_large_v3_1", audio_seconds=30.0, outcome="failed", session_factory=factory)
    record_whisper_usage("groq_whisper_large_v3_2", audio_seconds=12.0, outcome="rate_limited", session_factory=factory)
    record_whisper_usage("groq_whisper_large_v3_2", audio_seconds=5.0, outcome="nonsense", session_factory=factory)

    rows = [(r.key_id, r.audio_seconds, r.outcome) for r in db.query(WhisperUsageEvent).order_by(WhisperUsageEvent.id)]
    assert rows == [
        ("groq_whisper_large_v3_1", 61.5, "ok"),
        ("groq_whisper_large_v3_1", 30.0, "failed"),
        ("groq_whisper_large_v3_2", 12.0, "rate_limited"),
    ]
    assert db.query(KeyUsage).count() == 0  # the LLM table is never touched


def test_rows_older_than_thirty_days_are_pruned(factory, db):
    from app.models.whisper_usage import WhisperUsageEvent
    from app.services.whisper_usage import record_whisper_usage

    old = datetime.now(timezone.utc) - timedelta(days=31)
    db.add_all([
        WhisperUsageEvent(key_id="groq_whisper_large_v3_1", occurred_at=old, audio_seconds=1, outcome="ok"),
        WhisperUsageEvent(key_id="groq_whisper_large_v3_2", occurred_at=old, audio_seconds=1, outcome="ok"),
    ])
    db.commit()

    record_whisper_usage("groq_whisper_large_v3_1", audio_seconds=2, outcome="ok", session_factory=factory)

    db.expire_all()
    left = sorted((r.key_id, r.audio_seconds) for r in db.query(WhisperUsageEvent))
    # This key's old row is gone; another key's is pruned on its own next write.
    assert left == [("groq_whisper_large_v3_1", 2.0), ("groq_whisper_large_v3_2", 1.0)]


class FakeWhisperClient:
    def get_status(self):
        return [
            {"key_id": f"groq_whisper_large_v3_{n}", "rpm_limit": 20, "rpd_limit": 2000, "ash_limit": 7200, "asd_limit": 28800,
             "total_requests": 999}
            for n in (1, 2)
        ]


def test_the_snapshot_gives_rolling_figures_in_whisper_units(factory, db):
    from app.models.whisper_usage import WhisperUsageEvent
    from app.services.whisper_usage import get_whisper_usage_snapshot

    def event(minutes_ago, seconds, outcome, key="groq_whisper_large_v3_1"):
        return WhisperUsageEvent(key_id=key, occurred_at=NOW - timedelta(minutes=minutes_ago), audio_seconds=seconds, outcome=outcome)

    db.add_all([
        event(0.5, 60.0, "ok"),            # last minute
        event(30, 90.0, "ok"),             # last hour
        event(45, 40.0, "failed"),         # last hour, failed: no audio
        event(120, 300.0, "ok"),           # last 24h
        event(600, 10.0, "rate_limited"),  # last 24h
        event(60 * 30, 999.0, "ok"),       # older than 24h: in no window
    ])
    db.commit()

    first, unused = get_whisper_usage_snapshot(FakeWhisperClient(), session_factory=factory, now=NOW)

    assert first == {
        "key_id": "groq_whisper_large_v3_1",
        "label": "Whisper large-v3 — Key 1 (transcription)",
        "requests_last_minute": 1,
        "requests_last_hour": 3,
        "requests_last_24h": 5,
        "requests_per_minute_limit": 20,
        "requests_per_day_limit": 2000,
        "audio_seconds_last_hour": 150.0,
        "audio_seconds_last_24h": 450.0,
        "audio_seconds_per_hour_limit": 7200,
        "audio_seconds_per_day_limit": 28800,
        "failed_last_24h": 1,
        "rate_limited_last_24h": 1,
        "last_used_at": NOW - timedelta(minutes=0.5),
    }
    assert unused["requests_last_24h"] == 0 and unused["audio_seconds_last_24h"] == 0.0 and unused["last_used_at"] is None
    assert "key" not in first and "total_requests" not in first


# ---------------------------------------------------------------
# The admin endpoint
# ---------------------------------------------------------------

LLM_KEY_FIELDS = {
    "key_id", "label", "provider", "requests_used", "requests_limit", "requests_remaining", "prompt_tokens",
    "completion_tokens", "tokens_used", "tokens_limit", "tokens_remaining", "window_reset_at", "last_rate_limit_headers",
}


@pytest.fixture
def admin_stats(app_module, db, factory, fake_storage, fake_jobs, video_flag, monkeypatch, make_user):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.core.security import create_access_token
    from app.db.database import get_db
    from app.services import engine, key_usage, storage, whisper_usage

    monkeypatch.setattr(settings, "admin_emails", "boss@test.com")
    monkeypatch.setattr(key_usage, "SessionLocal", factory)
    monkeypatch.setattr(whisper_usage, "SessionLocal", factory)
    monkeypatch.setattr(storage, "total_bytes_used", lambda: 0)

    llm_key = SimpleNamespace(id="groq_gpt_oss_120b_1", provider="groq", model="openai/gpt-oss-120b",
                              limits=SimpleNamespace(rpd=1000, tpd=200000))
    monkeypatch.setattr(engine, "get_api_client", lambda: SimpleNamespace(get_keys=lambda: [llm_key], whisper_client=FakeWhisperClient()))

    app = app_module.app
    app.dependency_overrides[get_db] = lambda: db
    admin = make_user("boss@test.com")

    def get():
        response = TestClient(app).get("/v1/admin/stats", headers={"Authorization": f"Bearer {create_access_token(str(admin.id))}"})
        assert response.status_code == 200, response.text
        return response.json()

    yield get
    app.dependency_overrides.clear()


def test_the_admin_endpoint_returns_the_whisper_figures(admin_stats, factory):
    from app.services.whisper_usage import record_whisper_usage

    record_whisper_usage("groq_whisper_large_v3_1", audio_seconds=75.0, outcome="ok", session_factory=factory)
    record_whisper_usage("groq_whisper_large_v3_1", audio_seconds=20.0, outcome="failed", session_factory=factory)

    body = admin_stats()
    first = body["whisper_keys"][0]

    assert [k["key_id"] for k in body["whisper_keys"]] == ["groq_whisper_large_v3_1", "groq_whisper_large_v3_2"]
    assert first["label"] == "Whisper large-v3 — Key 1 (transcription)"
    assert (first["requests_last_24h"], first["audio_seconds_last_24h"], first["failed_last_24h"]) == (2, 75.0, 1)
    assert first["last_used_at"] is not None
    assert "test-value" not in str(body) and not any("token" in field for field in first)


def test_the_llm_key_output_is_unchanged(admin_stats, factory):
    from app.services.whisper_usage import record_whisper_usage

    record_whisper_usage("groq_whisper_large_v3_1", audio_seconds=75.0, outcome="ok", session_factory=factory)
    body = admin_stats()

    [llm] = body["keys"]
    assert set(llm) == LLM_KEY_FIELDS
    assert llm["key_id"] == "groq_gpt_oss_120b_1" and llm["requests_used"] == 0 and llm["tokens_used"] == 0
    assert set(body) == {"active_users", "total_signups", "keys", "whisper_keys", "storage"}


def test_the_api_client_hands_its_whisper_hook_to_the_whisper_client(monkeypatch):
    import api.client as client_module

    seen = {}

    class StubWhisper:
        def __init__(self, **kwargs):
            seen.update(kwargs)

        def shutdown(self):
            pass

    monkeypatch.setattr(client_module, "WhisperClient", StubWhisper)

    def hook(key_id, **kw):
        return None

    api = client_module.APIClient(on_whisper_usage=hook)
    try:
        assert seen == {"on_usage": hook}
    finally:
        api.shutdown()
