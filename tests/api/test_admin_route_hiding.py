"""
To anyone who isn't an admin, /v1/admin/* must answer exactly as a
path that doesn't exist: same status, same body, no Allow or
WWW-Authenticate header, no trailing-slash redirect. And the API
docs, which list every route, are off unless explicitly enabled.
"""

import pytest

ADMIN_PATHS = ["/v1/admin/whoami", "/v1/admin/stats"]
UNKNOWN_PATH = "/v1/definitely-not-a-route"
REVEALING_HEADERS = ("allow", "www-authenticate", "location")


@pytest.fixture
def api(app_module, db, fake_storage, fake_jobs, video_flag, monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.core.security import create_access_token
    from app.db.database import get_db

    monkeypatch.setattr(settings, "admin_emails", "boss@test.com")
    app = app_module.app
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app, follow_redirects=False)

    def bearer(user):
        return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}

    yield client, bearer
    app.dependency_overrides.clear()


def _fingerprint(response):
    return (
        response.status_code,
        response.content,
        response.headers.get("content-type"),
        {h: response.headers.get(h) for h in REVEALING_HEADERS},
    )


def _probes(bearer, make_user):
    non_admin = bearer(make_user("someone@test.com"))
    admin = bearer(make_user("boss@test.com"))
    return {
        "no token": ("GET", "", {}),
        "garbage token": ("GET", "", {"Authorization": "Bearer not-a-jwt"}),
        "non-admin token": ("GET", "", non_admin),
        "wrong method, no token": ("POST", "", {}),
        "wrong method, admin token": ("DELETE", "", admin),
        "trailing slash, no token": ("GET", "/", {}),
        "trailing slash, admin token": ("GET", "/", admin),
    }


@pytest.mark.parametrize("admin_path", ADMIN_PATHS)
def test_every_non_admin_probe_matches_an_unknown_path(api, make_user, admin_path):
    client, bearer = api

    for label, (method, suffix, headers) in _probes(bearer, make_user).items():
        real = client.request(method, admin_path + suffix, headers=headers)
        fake = client.request(method, UNKNOWN_PATH + suffix, headers=headers)
        assert _fingerprint(real) == _fingerprint(fake), label
        assert real.status_code == 404, label


def test_admin_still_gets_through(api, make_user):
    client, bearer = api

    r = client.get("/v1/admin/whoami", headers=bearer(make_user("boss@test.com")))
    assert r.status_code == 200
    assert r.json() == {"email": "boss@test.com", "is_admin": True}


def test_non_admin_405s_elsewhere_are_untouched(api):
    """The 405 rewrite is scoped to /v1/admin; other routes keep their real 405."""
    client, _ = api
    r = client.request("PATCH", "/v1/users/me")
    assert r.status_code == 405


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_docs_are_off_by_default(api, path):
    client, _ = api
    assert client.get(path).status_code == 404


def test_api_docs_urls_when_enabled_and_disabled():
    from app.main import api_docs_urls

    assert api_docs_urls(True) == {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}
    assert api_docs_urls(False) == {"docs_url": None, "redoc_url": None, "openapi_url": None}
