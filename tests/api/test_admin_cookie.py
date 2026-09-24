"""
dc_admin_session's attributes on both branches of _tokens_for
(app/routes/auth.py). Production is cross-site (Vercel frontend,
Cloud Run backend), so the browser drops any Set-Cookie on these
responses that isn't SameSite=None; Secure — including the one
that clears the cookie for a non-admin.
"""

import pytest


@pytest.fixture
def client(app_module, db, fake_storage, fake_jobs, video_flag, monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.db.database import get_db

    monkeypatch.setattr(settings, "admin_emails", "boss@test.com")
    app = app_module.app
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _admin_cookie_header(response) -> str:
    headers = [h for h in response.headers.get_list("set-cookie") if h.startswith("dc_admin_session=")]
    assert len(headers) == 1, response.headers.get_list("set-cookie")
    return headers[0].lower()


def _signup(client, email):
    return client.post(
        "/v1/auth/signup",
        json={"email": email, "password": "CorrectHorse1", "first_name": "A", "last_name": "B"},
    )


def test_admin_gets_the_cookie_cross_site_safe(client):
    header = _admin_cookie_header(_signup(client, "boss@test.com"))
    assert "samesite=none" in header
    assert "secure" in header
    assert "httponly" in header
    assert "max-age=0" not in header


def test_non_admin_clearing_cookie_is_also_cross_site_safe(client):
    header = _admin_cookie_header(_signup(client, "someone@test.com"))
    assert header.startswith('dc_admin_session="";') or header.startswith("dc_admin_session=;")
    assert "max-age=0" in header
    assert "samesite=none" in header
    assert "secure" in header
