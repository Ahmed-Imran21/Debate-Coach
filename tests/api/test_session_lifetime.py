"""
Session lifetime: the absolute cap on total session age, enforced
at refresh time independent of how often the client refreshes.

Before this, every refresh minted a brand-new refresh token whose
own "exp" reset to a fresh refresh_token_expire_days from that
moment — so a session kept alive by periodic refreshing (exactly
what web/'s Heartbeat does) never actually ended. session_start is
carried forward unchanged across reissues so that clock can't be
reset just by using the session.
"""

from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.core import security
from app.core.config import settings


@pytest.fixture
def client(app_module, db, fake_storage, fake_jobs, video_flag):
    from fastapi.testclient import TestClient

    from app.db.database import get_db

    app = app_module.app
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def user(make_user):
    return make_user("u@test.com")


def _decode(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def _refresh_token_with_session_start(user_id, age_days: float) -> str:
    """A refresh token whose own per-token exp is still valid, but
    whose session started `age_days` ago."""
    started = datetime.now(timezone.utc) - timedelta(days=age_days)
    return security.create_refresh_token(str(user_id), session_start=int(started.timestamp()))


def test_signup_and_login_each_mint_a_fresh_session_start(client, db):
    r = client.post(
        "/v1/auth/signup",
        json={"email": "s@test.com", "password": "CorrectHorse1", "first_name": "A", "last_name": "B"},
    )
    assert r.status_code == 201, r.text
    signup_start = _decode(r.json()["refresh_token"])["session_start"]

    r = client.post("/v1/auth/login", json={"email": "s@test.com", "password": "CorrectHorse1"})
    assert r.status_code == 200, r.text
    login_start = _decode(r.json()["refresh_token"])["session_start"]

    now = int(datetime.now(timezone.utc).timestamp())
    assert now - 5 <= signup_start <= now
    assert now - 5 <= login_start <= now


def test_repeated_refreshing_never_extends_session_start(client, user):
    """
    The exact bug this fixes: web/'s Heartbeat refreshes on a
    timer with no real user interaction behind it. Chaining five
    refreshes in a row (standing in for five hours of an open,
    forgotten tab) must not push the absolute deadline out — each
    new token must carry the same original session_start forward.
    """
    token = _refresh_token_with_session_start(user.id, age_days=10)
    original_start = _decode(token)["session_start"]

    for _ in range(5):
        r = client.post("/v1/auth/refresh", json={"refresh_token": token})
        assert r.status_code == 200, r.text
        token = r.json()["refresh_token"]
        assert _decode(token)["session_start"] == original_start


def test_refresh_one_day_past_the_cap_is_rejected(client, user):
    token = _refresh_token_with_session_start(user.id, age_days=settings.refresh_token_expire_days + 1)
    r = client.post("/v1/auth/refresh", json={"refresh_token": token})
    assert r.status_code == 401
    assert r.json()["detail"] == "Your session has expired. Please log in again."


def test_refresh_one_day_before_the_cap_still_succeeds(client, user):
    token = _refresh_token_with_session_start(user.id, age_days=settings.refresh_token_expire_days - 1)
    r = client.post("/v1/auth/refresh", json={"refresh_token": token})
    assert r.status_code == 200, r.text


def test_refresh_token_predating_the_session_start_claim_falls_back_to_its_own_iat(client, user):
    """
    A refresh token minted by the pre-fix backend has no
    session_start claim at all. It must be treated as if the
    session started at that token's own iat, not as brand new
    (which would silently grant every pre-existing session a full
    fresh window) and not as instantly expired (nothing distinguishes
    it from a legitimate token at the point of this deploy).
    """
    now = datetime.now(timezone.utc)
    old_iat = now - timedelta(days=settings.refresh_token_expire_days - 1)
    payload = {
        "sub": str(user.id),
        "type": "refresh",
        "iat": old_iat,
        "exp": now + timedelta(days=settings.refresh_token_expire_days),
        # no session_start
    }
    legacy_token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    r = client.post("/v1/auth/refresh", json={"refresh_token": legacy_token})
    assert r.status_code == 200, r.text
    assert _decode(r.json()["refresh_token"])["session_start"] == int(old_iat.timestamp())


def test_refresh_token_predating_the_claim_and_already_past_the_cap_is_rejected(client, user):
    now = datetime.now(timezone.utc)
    old_iat = now - timedelta(days=settings.refresh_token_expire_days + 1)
    payload = {
        "sub": str(user.id),
        "type": "refresh",
        "iat": old_iat,
        "exp": now + timedelta(days=settings.refresh_token_expire_days),
    }
    legacy_token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    r = client.post("/v1/auth/refresh", json={"refresh_token": legacy_token})
    assert r.status_code == 401


def test_access_token_cannot_be_used_at_the_refresh_endpoint(client, user):
    access = security.create_access_token(str(user.id))
    r = client.post("/v1/auth/refresh", json={"refresh_token": access})
    assert r.status_code == 401
    assert r.json()["detail"] == "Expected a refresh token"
