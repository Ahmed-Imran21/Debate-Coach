"""
GET /v1/admin/users and DELETE /v1/admin/users/{id}: cursor
pagination that walks the whole set with no gaps or repeats (ties on
the sort key included), search, per-page session counts, and a
force-delete that removes exactly one user and everything it owns.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

BASE = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
ADMIN_EMAIL = "boss@test.com"


@pytest.fixture
def api(app_module, db, fake_storage, fake_jobs, video_flag, monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.core.security import create_access_token
    from app.db.database import get_db

    monkeypatch.setattr(settings, "admin_emails", ADMIN_EMAIL)
    app = app_module.app
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    def bearer(user):
        return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}

    yield client, bearer
    app.dependency_overrides.clear()


@pytest.fixture
def add_user(db):
    from app.models.user import User

    def _add(email, *, created_at=None, last_seen_at=None, first="F", last="L"):
        user = User(
            email=email,
            password_hash="x",
            first_name=first,
            last_name=last,
            created_at=created_at or BASE,
            last_seen_at=last_seen_at,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _add


@pytest.fixture
def admin(add_user):
    # Oldest of all, so it sorts last and never disturbs expectations.
    return add_user(ADMIN_EMAIL, created_at=BASE - timedelta(days=365))


def _add_session(db, user):
    from app.models.session import DebateSession, SessionStatus

    row = DebateSession(user_id=user.id, status=SessionStatus.completed)
    db.add(row)
    db.commit()
    return row.id


def _walk(client, headers, **params):
    ids, cursor, pages = [], None, 0
    while True:
        query = {**params, **({"cursor": cursor} if cursor else {})}
        r = client.get("/v1/admin/users", params=query, headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        ids += [row["id"] for row in body["users"]]
        pages += 1
        cursor = body["next_cursor"]
        if cursor is None:
            return ids, pages
        assert pages < 100, "pagination did not terminate"


def _newest_order(users):
    return [str(u.id) for u in sorted(users, key=lambda u: (u.created_at, u.id), reverse=True)]


def _last_seen_order(users):
    by_id = sorted(users, key=lambda u: u.id, reverse=True)
    ordered = sorted(
        by_id,
        key=lambda u: (u.last_seen_at is None, -u.last_seen_at.timestamp() if u.last_seen_at else 0),
    )
    return [str(u.id) for u in ordered]


# ---------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------

def test_newest_walk_covers_every_user_once_including_timestamp_ties(api, admin, add_user):
    client, bearer = api
    # Groups of three share a created_at, so only the id tiebreak
    # keeps page boundaries from skipping or repeating users.
    users = [add_user(f"u{i:02d}@test.com", created_at=BASE - timedelta(minutes=i // 3)) for i in range(23)]

    ids, pages = _walk(client, bearer(admin), limit=5)

    assert ids == _newest_order(users + [admin])
    assert len(ids) == len(set(ids)) == 24
    assert pages == 5


def test_last_seen_walk_orders_seen_users_then_never_seen_across_the_boundary(api, admin, add_user):
    client, bearer = api
    users = []
    for i in range(17):
        seen = None if i % 3 == 0 else BASE - timedelta(hours=i // 4)  # ties, and a never-seen group
        users.append(add_user(f"s{i:02d}@test.com", last_seen_at=seen))

    ids, _ = _walk(client, bearer(admin), sort="last_seen", limit=4)

    expected = _last_seen_order(users + [admin])
    assert ids == expected
    assert len(ids) == len(set(ids)) == 18
    never_seen = {str(u.id) for u in users + [admin] if u.last_seen_at is None}
    assert set(ids[-len(never_seen):]) == never_seen


def test_default_page_size_and_cap(api, admin, add_user):
    client, bearer = api
    for i in range(110):
        add_user(f"bulk{i:03d}@test.com", created_at=BASE - timedelta(seconds=i))

    default = client.get("/v1/admin/users", headers=bearer(admin)).json()
    assert len(default["users"]) == 25 and default["next_cursor"]

    capped = client.get("/v1/admin/users", params={"limit": 1000}, headers=bearer(admin)).json()
    assert len(capped["users"]) == 100 and capped["next_cursor"]

    floor = client.get("/v1/admin/users", params={"limit": 0}, headers=bearer(admin)).json()
    assert len(floor["users"]) == 1


def test_last_page_has_no_cursor(api, admin, add_user):
    client, bearer = api
    add_user("only@test.com")
    body = client.get("/v1/admin/users", params={"limit": 5}, headers=bearer(admin)).json()
    assert len(body["users"]) == 2
    assert body["next_cursor"] is None


@pytest.mark.parametrize(
    "cursor_params, reuse_params",
    [
        ({}, {"sort": "last_seen"}),
        ({"search": "u"}, {"search": "test"}),
    ],
)
def test_cursor_is_refused_with_a_different_sort_or_search(api, admin, add_user, cursor_params, reuse_params):
    client, bearer = api
    for i in range(6):
        add_user(f"u{i}@test.com", created_at=BASE - timedelta(minutes=i))

    first = client.get("/v1/admin/users", params={**cursor_params, "limit": 1}, headers=bearer(admin)).json()
    assert first["next_cursor"], "fixture must span more than one page"
    r = client.get(
        "/v1/admin/users",
        params={**reuse_params, "limit": 1, "cursor": first["next_cursor"]},
        headers=bearer(admin),
    )
    assert r.status_code == 400


@pytest.mark.parametrize("cursor", ["garbage", "e30", "eyJzb3J0IjoibmV3ZXN0In0", "!!!"])
def test_malformed_cursor_is_a_400_for_an_admin(api, admin, cursor):
    client, bearer = api
    r = client.get("/v1/admin/users", params={"cursor": cursor}, headers=bearer(admin))
    assert r.status_code == 400
    assert r.json() == {"detail": "Invalid cursor. Start again from the first page."}


# ---------------------------------------------------------------
# Search and row contents
# ---------------------------------------------------------------

def test_search_matches_email_first_or_last_name_case_insensitively(api, admin, add_user):
    client, bearer = api
    by_email = add_user("alice.w@test.com", first="Zed", last="Quinn")
    by_first = add_user("x1@test.com", first="ALICIA", last="Bond")
    by_last = add_user("x2@test.com", first="Bob", last="Malice")
    add_user("nobody@test.com", first="Carol", last="Dunn")

    def emails(term):
        body = client.get("/v1/admin/users", params={"search": term}, headers=bearer(admin)).json()
        return {row["email"] for row in body["users"]}

    assert emails("ALIC") == {by_email.email, by_first.email, by_last.email}
    assert emails("quinn") == {by_email.email}
    assert emails("  bond  ") == {by_first.email}
    assert emails("") == {u for u in emails("@")}  # blank search = no filter
    # The fields are searched as one "email first last" string, so a
    # full name matches across the first/last boundary.
    assert emails("zed quinn") == {by_email.email}
    assert emails("bob malice") == {by_last.email}


def test_search_treats_like_wildcards_literally(api, admin, add_user):
    client, bearer = api
    literal = add_user("50%off_deal@test.com")
    add_user("plain@test.com")

    for term in ("%", "_deal", "50%"):
        body = client.get("/v1/admin/users", params={"search": term}, headers=bearer(admin)).json()
        assert [row["email"] for row in body["users"]] == [literal.email], term


def test_search_pagination_walks_only_matches(api, admin, add_user):
    client, bearer = api
    matches = [add_user(f"team{i:02d}@test.com", created_at=BASE - timedelta(minutes=i // 2)) for i in range(12)]
    for i in range(7):
        add_user(f"other{i}@test.com")

    ids, pages = _walk(client, bearer(admin), search="TEAM", limit=5)

    assert ids == _newest_order(matches)
    assert pages == 3


def test_rows_carry_exactly_the_documented_fields_and_counts(api, db, admin, add_user):
    client, bearer = api
    none = add_user("zero@test.com", created_at=BASE - timedelta(minutes=1))
    one = add_user("one@test.com", created_at=BASE - timedelta(minutes=2), last_seen_at=BASE)
    three = add_user("three@test.com", created_at=BASE - timedelta(minutes=3))
    _add_session(db, one)
    for _ in range(3):
        _add_session(db, three)

    rows = {row["email"]: row for row in client.get("/v1/admin/users", headers=bearer(admin)).json()["users"]}

    assert set(rows["one@test.com"]) == {
        "id", "email", "first_name", "last_name", "created_at", "last_seen_at", "session_count", "is_admin",
    }
    assert rows["zero@test.com"]["session_count"] == 0
    assert rows["one@test.com"]["session_count"] == 1
    assert rows["three@test.com"]["session_count"] == 3
    assert rows["zero@test.com"]["last_seen_at"] is None
    assert rows["one@test.com"]["last_seen_at"] is not None
    assert rows[ADMIN_EMAIL]["is_admin"] is True
    assert rows["three@test.com"]["is_admin"] is False
    assert rows["three@test.com"]["id"] == str(three.id)
    assert none.email in rows


# ---------------------------------------------------------------
# Force-delete
# ---------------------------------------------------------------

@pytest.fixture
def two_users_with_data(db, add_user, fake_storage):
    from app.models.video_analysis import VideoAnalysis

    target = add_user("target@test.com")
    bystander = add_user("bystander@test.com")
    data = {}
    for user in (target, bystander):
        sid = _add_session(db, user)
        db.add(VideoAnalysis(session_id=sid, user_id=user.id, status="processed"))
        prefix = f"users/{user.id}/sessions/{sid}/"
        fake_storage.blobs[prefix + "recording.wav"] = b"audio"
        fake_storage.blobs[prefix + "coaching.json"] = b"{}"
        data[user.id] = sid
    db.commit()
    return target, bystander, data


def test_force_delete_removes_exactly_that_user_and_everything_it_owns(api, db, admin, two_users_with_data, fake_storage):
    from app.models.session import DebateSession
    from app.models.user import User
    from app.models.video_analysis import VideoAnalysis

    client, bearer = api
    target, bystander, sessions = two_users_with_data
    target_id, bystander_id = target.id, bystander.id
    bystander_blobs = {k: v for k, v in fake_storage.blobs.items() if k.startswith(f"users/{bystander_id}/")}

    r = client.delete(f"/v1/admin/users/{target_id}", headers=bearer(admin))

    assert r.status_code == 204, r.text
    assert fake_storage.deleted_prefixes == [f"users/{target_id}/"]
    assert not any(k.startswith(f"users/{target_id}/") for k in fake_storage.blobs)

    db.expire_all()
    assert db.get(User, target_id) is None
    assert db.get(DebateSession, sessions[target_id]) is None
    assert db.get(VideoAnalysis, sessions[target_id]) is None

    assert db.get(User, bystander_id) is not None
    assert db.get(DebateSession, sessions[bystander_id]) is not None
    assert db.get(VideoAnalysis, sessions[bystander_id]) is not None
    assert {k: v for k, v in fake_storage.blobs.items() if k.startswith(f"users/{bystander_id}/")} == bystander_blobs
    assert db.get(User, admin.id) is not None


def test_force_delete_of_nonexistent_user_is_404(api, admin, fake_storage):
    client, bearer = api
    r = client.delete(f"/v1/admin/users/{uuid.uuid4()}", headers=bearer(admin))
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}
    assert fake_storage.deleted_prefixes == []


def test_admin_cannot_force_delete_themselves(api, db, admin, fake_storage):
    from app.models.user import User

    client, bearer = api
    r = client.delete(f"/v1/admin/users/{admin.id}", headers=bearer(admin))
    assert r.status_code == 409
    assert "your own account" in r.json()["detail"]
    assert fake_storage.deleted_prefixes == []
    db.expire_all()
    assert db.get(User, admin.id) is not None


def test_admin_cannot_force_delete_another_admin(api, db, admin, add_user, fake_storage, monkeypatch):
    from app.core.config import settings
    from app.models.user import User

    monkeypatch.setattr(settings, "admin_emails", f"{ADMIN_EMAIL}, Other.Admin@test.com")
    other = add_user("other.admin@test.com")
    client, bearer = api

    r = client.delete(f"/v1/admin/users/{other.id}", headers=bearer(admin))

    assert r.status_code == 409
    assert "ADMIN_EMAILS" in r.json()["detail"]
    assert fake_storage.deleted_prefixes == []
    db.expire_all()
    assert db.get(User, other.id) is not None


def test_force_delete_refused_while_an_analysis_is_running(api, db, admin, two_users_with_data, fake_storage, monkeypatch):
    from app.models.user import User
    from app.services import jobs

    client, bearer = api
    target, _, sessions = two_users_with_data
    monkeypatch.setattr(jobs, "is_running", lambda sid: sid == sessions[target.id])

    r = client.delete(f"/v1/admin/users/{target.id}", headers=bearer(admin))

    assert r.status_code == 409
    assert fake_storage.deleted_prefixes == []
    db.expire_all()
    assert db.get(User, target.id) is not None


def test_self_service_delete_shares_the_running_analysis_guard(api, db, add_user, fake_storage, monkeypatch):
    from app.core.security import hash_password
    from app.models.user import User
    from app.services import jobs

    client, bearer = api
    user = add_user("self@test.com")
    user.password_hash = hash_password("CorrectHorse1")
    db.commit()
    sid = _add_session(db, user)
    monkeypatch.setattr(jobs, "is_running", lambda s: s == sid)

    r = client.request("DELETE", "/v1/users/me", json={"password": "CorrectHorse1"}, headers=bearer(user))

    assert r.status_code == 409
    assert fake_storage.deleted_prefixes == []
    db.expire_all()
    assert db.get(User, user.id) is not None


def test_non_admin_cannot_force_delete(api, db, add_user, two_users_with_data, fake_storage):
    from app.models.user import User

    client, bearer = api
    target, bystander, _ = two_users_with_data

    real = client.delete(f"/v1/admin/users/{target.id}", headers=bearer(bystander))
    fake = client.delete(f"/v1/definitely-not-a-route/{target.id}", headers=bearer(bystander))

    assert (real.status_code, real.content) == (fake.status_code, fake.content) == (404, b'{"detail":"Not Found"}')
    assert fake_storage.deleted_prefixes == []
    db.expire_all()
    assert db.get(User, target.id) is not None
