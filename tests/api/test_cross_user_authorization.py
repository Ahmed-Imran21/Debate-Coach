"""
Cross-user authorization: User A must never read, start, mutate,
delete or obtain a download URL for anything owned by User B.

Uses real signed access tokens (get_current_user is NOT
overridden), so the actual JWT decode + user lookup path runs.
"""

import gzip
import json
import uuid

import pytest

from tests.visual_analysis.synthetic import simple_track


@pytest.fixture
def token_client(app_module, db, fake_storage, fake_jobs, video_flag):
    from fastapi.testclient import TestClient

    from app.core.security import create_access_token
    from app.db.database import get_db

    app = app_module.app
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    def headers_for(user):
        return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}

    yield client, headers_for
    app.dependency_overrides.clear()


@pytest.fixture
def victim_session(db, make_user, fake_storage):
    """A fully completed session owned by User B, with every artifact present."""
    from app.models.session import DebateSession, SessionStatus
    from app.models.video_analysis import VideoAnalysis

    owner = make_user("b@test")
    sid = uuid.uuid4()
    prefix = f"users/{owner.id}/sessions/{sid}/"

    keys = {
        "upload_object_key": prefix + "upload.webm",
        "audio_object_key": prefix + "recording.wav",
        "transcription_object_key": prefix + "transcription.json",
        "analysis_object_key": prefix + "analysis.json",
        "raw_metrics_object_key": prefix + "raw_metrics.json",
        "speech_content_object_key": prefix + "speech_content.json",
        "coaching_object_key": prefix + "coaching.json",
    }
    for key in keys.values():
        fake_storage.blobs[key] = json.dumps({"secret": "b-private"}).encode()

    row = DebateSession(id=sid, user_id=owner.id, title="B's speech", status=SessionStatus.completed, **keys)
    db.add(row)
    db.add(
        VideoAnalysis(
            session_id=sid,
            user_id=owner.id,
            status="awaiting_upload",
            result_key=prefix + "visual_result.json",
            feedback_key=prefix + "visual_feedback.json",
        )
    )
    fake_storage.blobs[prefix + "visual_result.json"] = b"{}"
    fake_storage.blobs[prefix + "visual_feedback.json"] = b"{}"
    db.commit()

    return owner, sid, prefix


def _blob_snapshot(fake_storage):
    return dict(fake_storage.blobs)


def test_owner_can_read_own_report(token_client, victim_session):
    """Positive control: the fixture is valid, so the 404s below mean denial, not breakage."""
    client, headers_for = token_client
    owner, sid, prefix = victim_session

    r = client.get(f"/v1/sessions/{sid}/report", headers=headers_for(owner))
    assert r.status_code == 200, r.text
    assert r.json()["audio_url"] == f"https://download.test/{prefix}recording.wav"


@pytest.mark.parametrize(
    "method,path_tpl",
    [
        ("GET", "/v1/sessions/{sid}"),
        ("GET", "/v1/sessions/{sid}/report"),
        ("POST", "/v1/sessions/{sid}/start"),
        ("DELETE", "/v1/sessions/{sid}"),
    ],
)
def test_other_user_is_denied(token_client, victim_session, make_user, fake_storage, fake_jobs, db, method, path_tpl):
    client, headers_for = token_client
    owner, sid, prefix = victim_session
    attacker = make_user("a@test")
    before = _blob_snapshot(fake_storage)

    r = client.request(method, path_tpl.format(sid=sid), headers=headers_for(attacker))

    # 404, identical to a nonexistent session: never confirm B's session exists.
    assert r.status_code == 404, r.text
    assert r.json() == {"detail": "Session not found"}
    assert "b-private" not in r.text
    assert prefix not in r.text

    # Nothing of B's was touched.
    assert fake_storage.blobs == before
    assert fake_storage.deleted_prefixes == []
    assert fake_jobs == []

    from app.models.session import DebateSession, SessionStatus

    db.expire_all()
    still_there = db.get(DebateSession, sid)
    assert still_there is not None
    assert still_there.status == SessionStatus.completed


def test_other_user_cannot_upload_visual_signals(token_client, victim_session, make_user, fake_storage, db):
    client, headers_for = token_client
    owner, sid, prefix = victim_session
    attacker = make_user("a@test")
    before = _blob_snapshot(fake_storage)

    body = gzip.compress(json.dumps(simple_track(str(sid))).encode())
    r = client.put(
        f"/v1/sessions/{sid}/visual-signals",
        content=body,
        headers={**headers_for(attacker), "Content-Encoding": "gzip", "Content-Type": "application/json"},
    )

    assert r.status_code == 404, r.text
    assert fake_storage.blobs == before

    from app.models.video_analysis import VideoAnalysis

    db.expire_all()
    assert db.get(VideoAnalysis, sid).signal_track_key is None


def test_other_user_list_excludes_victim_sessions(token_client, victim_session, make_user):
    client, headers_for = token_client
    owner, sid, _ = victim_session
    attacker = make_user("a@test")

    r = client.get("/v1/sessions", headers=headers_for(attacker))
    assert r.status_code == 200
    assert r.json() == []

    r = client.get("/v1/sessions", headers=headers_for(owner))
    assert [s["id"] for s in r.json()] == [str(sid)]


def test_denial_is_indistinguishable_from_nonexistent(token_client, victim_session, make_user):
    client, headers_for = token_client
    attacker = make_user("a@test")
    _, sid, _ = victim_session

    theirs = client.get(f"/v1/sessions/{sid}/report", headers=headers_for(attacker))
    missing = client.get(f"/v1/sessions/{uuid.uuid4()}/report", headers=headers_for(attacker))
    assert (theirs.status_code, theirs.json()) == (missing.status_code, missing.json())


def test_new_session_object_keys_are_scoped_to_creator(token_client, make_user):
    """A create request can't steer its upload URL into another user's prefix."""
    client, headers_for = token_client
    attacker = make_user("a@test")

    r = client.post(
        "/v1/sessions",
        json={"content_type": "audio/webm", "title": "t", "user_id": str(uuid.uuid4())},
        headers=headers_for(attacker),
    )
    assert r.status_code in (201, 422), r.text
    if r.status_code == 201:
        assert f"/users/{attacker.id}/sessions/" in r.json()["upload_url"]


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/v1/sessions"),
        ("POST", "/v1/sessions"),
        ("GET", "/v1/sessions/{sid}"),
        ("GET", "/v1/sessions/{sid}/report"),
        ("POST", "/v1/sessions/{sid}/start"),
        ("PUT", "/v1/sessions/{sid}/visual-signals"),
        ("DELETE", "/v1/sessions/{sid}"),
        ("GET", "/v1/users/me"),
        ("POST", "/v1/users/heartbeat"),
        ("GET", "/v1/admin/whoami"),
        ("GET", "/v1/admin/stats"),
    ],
)
def test_unauthenticated_requests_rejected(token_client, victim_session, method, path):
    client, _ = token_client
    _, sid, _ = victim_session

    r = client.request(method, path.format(sid=sid))
    assert r.status_code == 401, r.text


def test_refresh_token_cannot_be_used_as_access_token(token_client, victim_session):
    from app.core.security import create_refresh_token

    client, _ = token_client
    owner, sid, _ = victim_session

    r = client.get(
        f"/v1/sessions/{sid}/report",
        headers={"Authorization": f"Bearer {create_refresh_token(str(owner.id))}"},
    )
    assert r.status_code == 401


def _b64(obj) -> str:
    import base64

    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def test_forged_tokens_rejected(token_client, victim_session):
    """Wrong secret, alg=none, and expired tokens all fail."""
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    from app.core.config import settings

    client, _ = token_client
    owner, sid, _ = victim_session
    url = f"/v1/sessions/{sid}/report"
    claims = {"sub": str(owner.id), "type": "access"}

    wrong_secret = jwt.encode(claims, "not-the-secret", algorithm="HS256")
    alg_none = f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(claims)}."
    expired = jwt.encode(
        {**claims, "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    for token in (wrong_secret, alg_none, expired):
        r = client.get(url, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401, token


@pytest.mark.parametrize("path", ["/v1/admin/whoami", "/v1/admin/stats"])
def test_non_admin_gets_403_on_admin_routes(token_client, make_user, monkeypatch, path):
    from app.core.config import settings

    monkeypatch.setattr(settings, "admin_emails", "boss@test")
    client, headers_for = token_client

    r = client.get(path, headers=headers_for(make_user("a@test")))
    assert r.status_code == 403
