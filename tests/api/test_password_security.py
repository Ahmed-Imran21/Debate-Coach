"""
Password handling: hash format, salting, verification, and that
neither the password nor its hash ever comes back in a response.
"""

import pytest

from app.core import security

PASSWORD = "SuperSecretPw123"


@pytest.fixture
def client(app_module, db, fake_storage, fake_jobs, video_flag):
    from fastapi.testclient import TestClient

    from app.db.database import get_db

    app = app_module.app
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _signup(client, email="u@test.com", password=PASSWORD, **overrides):
    body = {"email": email, "password": password, "first_name": "A", "last_name": "B", **overrides}
    return client.post("/v1/auth/signup", json=body)


def test_bcrypt_cost_12_with_per_hash_salt():
    a, b = security.hash_password(PASSWORD), security.hash_password(PASSWORD)
    assert a.startswith("$2b$12$") and len(a) == 60
    assert a != b
    assert security.verify_password(PASSWORD, a)
    assert not security.verify_password(PASSWORD.lower(), a)


def test_stored_value_is_a_hash_not_the_password(client, db):
    from app.models.user import User

    assert _signup(client).status_code == 201
    stored = db.query(User).filter(User.email == "u@test.com").one().password_hash
    assert PASSWORD not in stored
    assert security.verify_password(PASSWORD, stored)


def test_no_password_or_hash_in_any_auth_response(client):
    responses = [_signup(client)]
    token = responses[0].json()["access_token"]
    responses.append(client.post("/v1/auth/login", json={"email": "u@test.com", "password": PASSWORD}))
    responses.append(client.get("/v1/users/me", headers={"Authorization": f"Bearer {token}"}))

    for r in responses:
        assert r.status_code in (200, 201), r.text
        assert PASSWORD not in r.text
        assert "$2b$" not in r.text
        assert "password" not in r.text


@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "short7!"},
        {"password": "LongEnough99", "first_name": ""},
        {"password": "LongEnough99", "email": "not-an-email"},
    ],
)
def test_validation_errors_do_not_echo_password(client, overrides):
    r = _signup(client, **{"password": PASSWORD, **overrides})
    assert r.status_code == 422
    assert overrides["password"] not in r.text
    assert all("input" not in err for err in r.json()["detail"])
    assert isinstance(r.json()["detail"][0]["msg"], str)


def test_login_errors_are_identical_for_unknown_email_and_wrong_password(client):
    _signup(client)
    wrong = client.post("/v1/auth/login", json={"email": "u@test.com", "password": "wrong-guess-1"})
    unknown = client.post("/v1/auth/login", json={"email": "ghost@test.com", "password": "wrong-guess-1"})
    assert (wrong.status_code, wrong.json()) == (unknown.status_code, unknown.json()) == (
        401,
        {"detail": "Incorrect email or password."},
    )


def test_unknown_email_still_runs_a_full_bcrypt_verify(client, monkeypatch):
    """Without this, an unknown email returns ~50x faster, revealing which emails exist."""
    from app.routes import auth

    calls = []
    real = auth.verify_password
    monkeypatch.setattr(auth, "verify_password", lambda pw, h: calls.append(h) or real(pw, h))

    client.post("/v1/auth/login", json={"email": "ghost@test.com", "password": "wrong-guess-1"})
    assert calls == [auth._TIMING_EQUALIZER_HASH]
    assert calls[0].startswith("$2b$12$")
