"""
DELETE /v1/users/me — re-authentication, real deletion of every
owned row and object, and that deletion itself is what invalidates
every outstanding token (no separate revocation step exists or is
needed).
"""

import uuid

import pytest

from app.core.security import create_access_token, create_refresh_token, hash_password


@pytest.fixture
def token_client(app_module, db, fake_storage, fake_jobs, video_flag):
    from fastapi.testclient import TestClient

    from app.db.database import get_db

    app = app_module.app
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    def headers_for(user):
        return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}

    yield client, headers_for
    app.dependency_overrides.clear()


PASSWORD = "CorrectHorse1"


@pytest.fixture
def user_with_password(db):
    from app.models.user import User

    user = User(email="u@test.com", password_hash=hash_password(PASSWORD), first_name="A", last_name="B")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def owned_session(db, user_with_password, fake_storage):
    from app.models.session import DebateSession, SessionStatus
    from app.models.video_analysis import VideoAnalysis

    sid = uuid.uuid4()
    prefix = f"users/{user_with_password.id}/sessions/{sid}/"
    row = DebateSession(
        id=sid,
        user_id=user_with_password.id,
        status=SessionStatus.completed,
        audio_object_key=prefix + "recording.wav",
    )
    db.add(row)
    db.add(VideoAnalysis(session_id=sid, user_id=user_with_password.id, status="awaiting_upload"))
    fake_storage.blobs[prefix + "recording.wav"] = b"audio"
    fake_storage.blobs[prefix + "raw.json"] = b"{}"
    db.commit()
    return sid


def test_wrong_password_is_rejected_and_nothing_is_touched(
    token_client, user_with_password, owned_session, db, fake_storage
):
    client, headers_for = token_client
    before_blobs = dict(fake_storage.blobs)

    r = client.request(
        "DELETE",
        "/v1/users/me",
        json={"password": "not-the-password"},
        headers=headers_for(user_with_password),
    )

    assert r.status_code == 401
    assert r.json() == {"detail": "Incorrect password."}
    assert fake_storage.deleted_prefixes == []
    assert fake_storage.blobs == before_blobs

    from app.models.user import User

    db.expire_all()
    assert db.get(User, user_with_password.id) is not None


def test_correct_password_deletes_the_account_its_sessions_and_its_storage(
    token_client, user_with_password, owned_session, db, fake_storage
):
    client, headers_for = token_client
    user_id = user_with_password.id

    r = client.request(
        "DELETE",
        "/v1/users/me",
        json={"password": PASSWORD},
        headers=headers_for(user_with_password),
    )

    assert r.status_code == 204
    assert r.text == ""
    assert fake_storage.deleted_prefixes == [f"users/{user_id}/"]
    assert not any(k.startswith(f"users/{user_id}/") for k in fake_storage.blobs)

    from app.models.session import DebateSession
    from app.models.user import User
    from app.models.video_analysis import VideoAnalysis

    db.expire_all()
    assert db.get(User, user_id) is None
    assert db.get(DebateSession, owned_session) is None
    assert db.get(VideoAnalysis, owned_session) is None


def test_access_token_stops_working_immediately_after_deletion(
    token_client, user_with_password
):
    client, headers_for = token_client
    headers = headers_for(user_with_password)

    r = client.request("DELETE", "/v1/users/me", json={"password": PASSWORD}, headers=headers)
    assert r.status_code == 204

    r = client.get("/v1/users/me", headers=headers)
    assert r.status_code == 401
    assert r.json() == {"detail": "User not found"}


def test_refresh_token_stops_working_immediately_after_deletion(
    token_client, user_with_password
):
    client, headers_for = token_client
    refresh_token = create_refresh_token(str(user_with_password.id))

    r = client.request(
        "DELETE", "/v1/users/me", json={"password": PASSWORD}, headers=headers_for(user_with_password)
    )
    assert r.status_code == 204

    r = client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert r.status_code == 401
    assert r.json() == {"detail": "User not found"}


def test_deleting_one_account_does_not_touch_another_users_data(
    token_client, user_with_password, owned_session, make_user, db, fake_storage
):
    client, headers_for = token_client
    other = make_user("other@test.com")
    other_prefix = f"users/{other.id}/sessions/{uuid.uuid4()}/"
    fake_storage.blobs[other_prefix + "recording.wav"] = b"other-audio"

    r = client.request(
        "DELETE", "/v1/users/me", json={"password": PASSWORD}, headers=headers_for(user_with_password)
    )
    assert r.status_code == 204

    from app.models.user import User

    db.expire_all()
    assert db.get(User, other.id) is not None
    assert other_prefix + "recording.wav" in fake_storage.blobs


def test_no_auth_token_is_rejected_before_any_password_check(token_client):
    client, _ = token_client
    r = client.request("DELETE", "/v1/users/me", json={"password": PASSWORD})
    assert r.status_code == 401
