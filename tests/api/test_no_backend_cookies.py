"""
The backend sets no cookies. The /admin gate cookie is first-party to
the frontend (web/app/api/session/route.ts); one set here could never
reach it in production, since *.run.app and *.vercel.app are both
public suffixes.
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


@pytest.mark.parametrize("email", ["boss@test.com", "someone@test.com"])
def test_signup_login_and_refresh_set_no_cookie(client, email):
    body = {"email": email, "password": "CorrectHorse1", "first_name": "A", "last_name": "B"}

    signup = client.post("/v1/auth/signup", json=body)
    login = client.post("/v1/auth/login", json={"email": email, "password": "CorrectHorse1"})
    refresh = client.post("/v1/auth/refresh", json={"refresh_token": login.json()["refresh_token"]})

    for r in (signup, login, refresh):
        assert r.status_code in (200, 201), r.text
        assert r.headers.get_list("set-cookie") == []
