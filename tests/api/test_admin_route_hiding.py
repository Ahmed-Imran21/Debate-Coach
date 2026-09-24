"""
To anyone who isn't an admin, /v1/admin/* must answer exactly as a
path that doesn't exist: same status, same body, no Allow or
WWW-Authenticate header, no trailing-slash redirect. And the API
docs, which list every route, are off unless explicitly enabled.
"""

import pytest

ADMIN_PATHS = ["/v1/admin/whoami", "/v1/admin/stats", "/v1/admin/users"]
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


@pytest.mark.parametrize(
    "method, admin_path, unknown_path",
    [
        # Malformed parameters must not surface as a 422 that proves the
        # route exists: require_admin answers before they're validated.
        ("GET", "/v1/admin/users?limit=abc&sort=bogus&cursor=%25%25", UNKNOWN_PATH + "?limit=abc&sort=bogus&cursor=%25%25"),
        ("GET", "/v1/admin/users?search=" + "x" * 500, UNKNOWN_PATH + "?search=" + "x" * 500),
        ("DELETE", "/v1/admin/users/00000000-0000-0000-0000-000000000000", UNKNOWN_PATH + "/00000000-0000-0000-0000-000000000000"),
        ("DELETE", "/v1/admin/users/not-a-uuid", UNKNOWN_PATH + "/not-a-uuid"),
        ("GET", "/v1/admin/users/00000000-0000-0000-0000-000000000000", UNKNOWN_PATH + "/00000000-0000-0000-0000-000000000000"),
    ],
)
def test_user_management_routes_match_an_unknown_path_for_non_admins(api, make_user, method, admin_path, unknown_path):
    client, bearer = api
    for headers in ({}, {"Authorization": "Bearer not-a-jwt"}, bearer(make_user("someone@test.com"))):
        real = client.request(method, admin_path, headers=headers)
        fake = client.request(method, unknown_path, headers=headers)
        assert _fingerprint(real) == _fingerprint(fake), (method, admin_path, headers)
        assert real.status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"json": {"password": "guess"}},
        {"json": {}},
        {"content": b"{not json", "headers": {"content-type": "application/json"}},
        {"content": b"password=x", "headers": {"content-type": "application/x-www-form-urlencoded"}},
    ],
)
def test_force_delete_body_never_reveals_the_route_to_non_admins(api, make_user, body):
    """
    The delete takes a password body. FastAPI parses a declared body
    before any dependency runs, so malformed JSON would 422 ahead of
    require_admin's 404; the route reads its body only after the admin
    check instead. Every body shape must look like a nonexistent path.
    """
    client, bearer = api
    target = "00000000-0000-0000-0000-000000000000"
    for auth in ({}, {"Authorization": "Bearer not-a-jwt"}, bearer(make_user("someone@test.com"))):
        kwargs = dict(body)
        headers = {**auth, **kwargs.pop("headers", {})}
        real = client.request("DELETE", f"/v1/admin/users/{target}", headers=headers, **kwargs)
        fake = client.request("DELETE", f"{UNKNOWN_PATH}/{target}", headers=headers, **kwargs)
        assert _fingerprint(real) == _fingerprint(fake), (body, auth)
        assert real.status_code == 404


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
