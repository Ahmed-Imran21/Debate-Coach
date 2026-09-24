import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.rate_limit import PerClientRateLimitMiddleware


def _limited_app(trust: bool, limit: int = 3) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        PerClientRateLimitMiddleware,
        max_requests_per_minute=limit,
        trust_forwarded_for=trust,
    )

    @app.get("/ping")
    def ping():
        return {"ok": True}

    return TestClient(app)


def test_trusted_forwarded_for_uses_last_entry_so_spoofing_cannot_mint_new_buckets(caplog):
    client = _limited_app(trust=True)

    statuses = [
        client.get("/ping", headers={"X-Forwarded-For": f"6.6.6.{i}, 203.0.113.9"}).status_code
        for i in range(4)
    ]

    assert statuses == [200, 200, 200, 429]
    assert "Rate limit exceeded for client 203.0.113.9" in caplog.text


def test_distinct_real_clients_get_distinct_buckets():
    client = _limited_app(trust=True, limit=1)

    assert client.get("/ping", headers={"X-Forwarded-For": "203.0.113.1"}).status_code == 200
    assert client.get("/ping", headers={"X-Forwarded-For": "203.0.113.2"}).status_code == 200
    assert client.get("/ping", headers={"X-Forwarded-For": "203.0.113.1"}).status_code == 429


def test_untrusted_forwarded_for_is_ignored(caplog):
    caplog.set_level(logging.WARNING)
    client = _limited_app(trust=False, limit=1)

    client.get("/ping", headers={"X-Forwarded-For": "203.0.113.1"})
    r = client.get("/ping", headers={"X-Forwarded-For": "203.0.113.2"})

    assert r.status_code == 429
    assert "for client testclient" in caplog.text


def test_blank_last_entry_falls_back_to_connection_address():
    client = _limited_app(trust=True, limit=1)

    client.get("/ping", headers={"X-Forwarded-For": "203.0.113.1, "})
    assert client.get("/ping", headers={"X-Forwarded-For": "203.0.113.2, "}).status_code == 429


ORIGIN = "http://localhost:3000"  # the test environment's ALLOWED_ORIGINS default


@pytest.fixture
def api(app_module):
    return TestClient(app_module.app)


def _preflight(api, origin=ORIGIN, method="GET", headers="authorization"):
    return api.options(
        "/v1/users/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": headers,
        },
    )


@pytest.mark.parametrize(
    "method,headers",
    [
        ("GET", "authorization"),
        ("POST", "authorization,content-type"),
        ("PUT", "authorization,content-type,content-encoding"),
        ("DELETE", "authorization"),
    ],
)
def test_preflight_allows_everything_the_frontend_sends(api, method, headers):
    r = _preflight(api, method=method, headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers["access-control-allow-origin"] == ORIGIN
    # Bearer-token auth only: the API never asks browsers to send cookies.
    assert "access-control-allow-credentials" not in r.headers


@pytest.mark.parametrize(
    "kwargs",
    [
        {"origin": "https://evil.example"},
        {"method": "PATCH"},
        {"headers": "authorization,x-evil"},
    ],
)
def test_preflight_rejects_anything_else(api, kwargs):
    r = _preflight(api, **kwargs)
    assert r.status_code == 400
    assert r.headers.get("access-control-allow-origin") != "https://evil.example"


def test_simple_request_from_unlisted_origin_gets_no_allow_origin(api):
    r = api.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers
