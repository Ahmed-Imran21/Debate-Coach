"""
GET and PUT /v1/profile: the signed-in user's own profile, streak,
weekly goal and personal bests.

Uses real signed access tokens (get_current_user is NOT overridden),
so the actual JWT decode + user lookup path runs. "Now" is pinned by
patching app.services.profile._utcnow.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

URL = "/v1/profile"
KARACHI = ZoneInfo("Asia/Karachi")


@pytest.fixture
def api(app_module, db, fake_storage, fake_jobs, video_flag):
    from fastapi.testclient import TestClient

    from app.core.security import create_access_token
    from app.db.database import get_db

    app = app_module.app
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    def call(method, path=URL, user=None, body=None):
        headers = {"Authorization": f"Bearer {create_access_token(str(user.id))}"} if user else {}
        return client.request(method, path, headers=headers, json=body)

    yield call
    app.dependency_overrides.clear()


@pytest.fixture
def now(monkeypatch):
    from app.services import profile

    def set_now(moment: datetime) -> None:
        monkeypatch.setattr(profile, "_utcnow", lambda: moment.astimezone(timezone.utc))

    set_now(datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc))
    return set_now


@pytest.fixture
def downloads(monkeypatch, fake_storage):
    """Counts feedback.json reads (the Delivery score cache fills from these)."""

    from app.services import storage

    seen: list[str] = []
    inner = storage.download_json

    def counting(key):
        seen.append(key)
        return inner(key)

    monkeypatch.setattr(storage, "download_json", counting)
    return seen


@pytest.fixture
def add_session(db, fake_storage):
    from app.models.session import DebateSession, SessionStatus

    def _add(user, created_at, status=SessionStatus.completed, title=None, delivery=50.0, **scores):
        sid = uuid.uuid4()
        key = f"users/{user.id}/sessions/{sid}/feedback.json"
        fake_storage.blobs[key] = json.dumps({"scores": {"quantitative": delivery, "overall": 50.0}}).encode()
        values = {
            "overall_score": 50.0,
            "score_argumentation": 50.0,
            "score_rebuttal": 50.0,
            "score_structure": 50.0,
            "score_persuasion": 50.0,
            "score_logic": 50.0,
        }
        values.update(scores)
        row = DebateSession(
            id=sid,
            user_id=user.id,
            status=status,
            title=title,
            created_at=created_at.astimezone(timezone.utc),
            coaching_object_key=key,
            **values,
        )
        db.add(row)
        db.commit()
        return row

    return _add


def local(y, m, d, hh=12, mm=0, zone=KARACHI):
    return datetime(y, m, d, hh, mm, tzinfo=zone)


# ============================================================
# Sign-in and defaults
# ============================================================


@pytest.mark.parametrize("method, body", [("GET", None), ("PUT", {"bio": "x"})])
def test_sign_in_is_required(api, method, body):
    assert api(method, body=body).status_code == 401


def test_a_new_user_gets_every_default_and_no_row_is_created(api, db, make_user, now):
    from app.models.profile import UserProfile

    user = make_user("new@test")
    r = api("GET", user=user)
    assert r.status_code == 200
    body = r.json()
    assert body["first_name"] == "T" and body["last_name"] == "U"
    assert (body["username"], body["bio"], body["weekly_goal"], body["time_zone"]) == (None, None, 3, None)
    assert body["completed_sessions"] == 0
    assert body["streak"] == {"current": 0, "longest": 0, "practised_today": False}
    assert body["week"] == {"completed": 0, "goal": 3, "goal_met": False, "starts_on": "2026-09-21", "ends_on": "2026-09-27"}
    assert all(b["score"] is None and b["session_id"] is None for b in body["personal_bests"])
    assert db.get(UserProfile, user.id) is None


# ============================================================
# Username and bio
# ============================================================


def test_saving_username_and_bio(api, make_user, now):
    user = make_user("a@test")
    r = api("PUT", user=user, body={"username": "  Debate_Fan ", "bio": "First line\r\nSecond line"})
    assert r.status_code == 200, r.text
    assert r.json()["username"] == "debate_fan"
    assert r.json()["bio"] == "First line\nSecond line"
    assert api("GET", user=user).json()["username"] == "debate_fan"


def test_only_the_fields_sent_change(api, make_user, now):
    user = make_user("a@test")
    api("PUT", user=user, body={"username": "keeper", "bio": "Hello"})
    api("PUT", user=user, body={"bio": "Changed"})
    body = api("GET", user=user).json()
    assert (body["username"], body["bio"]) == ("keeper", "Changed")

    api("PUT", user=user, body={"username": None})
    body = api("GET", user=user).json()
    assert (body["username"], body["bio"]) == (None, "Changed")
    api("PUT", user=user, body={"bio": "   "})
    assert api("GET", user=user).json()["bio"] is None


def test_a_taken_username_is_refused_case_insensitively(api, make_user, now):
    a, b = make_user("a@test"), make_user("b@test")
    assert api("PUT", user=a, body={"username": "debater"}).status_code == 200

    for attempt in ("debater", "Debater", "DEBATER", " DeBaTeR "):
        r = api("PUT", user=b, body={"username": attempt, "bio": "should not save"})
        assert r.status_code == 409, attempt
        assert r.json()["detail"] == "That username is taken."
    body = api("GET", user=b).json()
    assert (body["username"], body["bio"]) == (None, None)

    # Re-saving your own username is not a clash.
    assert api("PUT", user=a, body={"username": "Debater"}).status_code == 200
    # Once released, it's free.
    api("PUT", user=a, body={"username": ""})
    assert api("PUT", user=b, body={"username": "debater"}).status_code == 200


@pytest.mark.parametrize("body, message", [
    ({"username": "ab"}, "A username must be 3 to 20 characters."),
    ({"username": "x" * 21}, "A username must be 3 to 20 characters."),
    ({"username": "no-dashes"}, "A username can only use lowercase letters, numbers and underscores."),
    ({"bio": "x" * 161}, "A bio can be at most 160 characters."),
    ({"bio": "bell\x07"}, "A bio can only contain plain text."),
    ({"weekly_goal": 0}, "The weekly goal must be between 1 and 7 sessions."),
    ({"weekly_goal": 8}, "The weekly goal must be between 1 and 7 sessions."),
    ({"weekly_goal": None}, "The weekly goal must be between 1 and 7 sessions."),
    ({"time_zone": "Mars/Olympus"}, "That time zone isn't recognised."),
])
def test_invalid_input_saves_nothing(api, make_user, now, body, message):
    user = make_user("a@test")
    api("PUT", user=user, body={"username": "original", "bio": "Original bio", "weekly_goal": 4})

    # Every other field in the request is valid, but nothing is saved.
    r = api("PUT", user=user, body={"username": "changed", "bio": "Changed bio", "weekly_goal": 5, **body})
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == message
    after = api("GET", user=user).json()
    assert (after["username"], after["bio"], after["weekly_goal"]) == ("original", "Original bio", 4)


@pytest.mark.parametrize("body", [{"weekly_goal": "3"}, {"weekly_goal": 3.5}, {"username": 123}, {"is_admin": True}, {"user_id": str(uuid.uuid4())}])
def test_wrong_types_and_unknown_fields_are_refused(api, make_user, now, body):
    assert api("PUT", user=make_user("a@test"), body=body).status_code == 422


# ============================================================
# Streak
# ============================================================


def test_streak_counts_local_days_in_the_users_time_zone(api, make_user, add_session, now):
    user = make_user("pk@test")
    api("PUT", user=user, body={"time_zone": "Asia/Karachi"})

    # Three evenings in Karachi. The last one, 01:30 on the 23rd
    # locally, is still the 22nd in UTC.
    add_session(user, local(2026, 9, 21, 22, 0))
    add_session(user, local(2026, 9, 22, 22, 0))
    add_session(user, local(2026, 9, 23, 1, 30))
    now(local(2026, 9, 23, 9, 0))

    assert api("GET", user=user).json()["streak"] == {"current": 3, "longest": 3, "practised_today": True}

    # The same sessions counted in UTC: today (the 23rd) has nothing,
    # and the 22nd has two, so it's 2 days and "practise today".
    api("PUT", user=user, body={"time_zone": "UTC"})
    assert api("GET", user=user).json()["streak"] == {"current": 2, "longest": 2, "practised_today": False}


def test_a_streak_lasts_until_the_end_of_today_in_local_time(api, make_user, add_session, now):
    user = make_user("pk@test")
    api("PUT", user=user, body={"time_zone": "Asia/Karachi"})
    add_session(user, local(2026, 9, 21, 20, 0))
    add_session(user, local(2026, 9, 22, 20, 0))

    now(local(2026, 9, 23, 0, 0))  # just after midnight: not practised yet today
    assert api("GET", user=user).json()["streak"] == {"current": 2, "longest": 2, "practised_today": False}

    now(local(2026, 9, 23, 23, 59))  # the last minute of today
    assert api("GET", user=user).json()["streak"] == {"current": 2, "longest": 2, "practised_today": False}

    now(local(2026, 9, 24, 0, 0))  # a whole day missed: reset, longest kept
    assert api("GET", user=user).json()["streak"] == {"current": 0, "longest": 2, "practised_today": False}


def test_only_completed_sessions_count_toward_the_streak(api, make_user, add_session, now):
    from app.models.session import SessionStatus

    user = make_user("a@test")
    now(datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc))
    add_session(user, datetime(2026, 9, 21, 9, 0, tzinfo=timezone.utc))
    add_session(user, datetime(2026, 9, 22, 9, 0, tzinfo=timezone.utc), status=SessionStatus.failed)
    add_session(user, datetime(2026, 9, 23, 9, 0, tzinfo=timezone.utc), status=SessionStatus.coaching)
    add_session(user, datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc), status=SessionStatus.created)

    body = api("GET", user=user).json()
    assert body["streak"] == {"current": 0, "longest": 1, "practised_today": False}
    assert body["completed_sessions"] == 1


# ============================================================
# Weekly goal
# ============================================================


def test_the_week_runs_monday_to_sunday_in_local_time(api, make_user, add_session, now):
    user = make_user("pk@test")
    api("PUT", user=user, body={"time_zone": "Asia/Karachi", "weekly_goal": 2})

    add_session(user, local(2026, 9, 20, 23, 50))  # Sunday of the week before
    add_session(user, local(2026, 9, 21, 0, 10))  # Monday 00:10: this week (still Sunday in UTC)
    add_session(user, local(2026, 9, 27, 23, 50))  # Sunday 23:50: this week
    now(local(2026, 9, 27, 23, 55))

    week = api("GET", user=user).json()["week"]
    assert week == {"completed": 2, "goal": 2, "goal_met": True, "starts_on": "2026-09-21", "ends_on": "2026-09-27"}

    # Monday: a new week starts at local midnight.
    add_session(user, local(2026, 9, 28, 0, 5))
    now(local(2026, 9, 28, 0, 10))
    week = api("GET", user=user).json()["week"]
    assert week == {"completed": 1, "goal": 2, "goal_met": False, "starts_on": "2026-09-28", "ends_on": "2026-10-04"}


def test_sessions_beyond_the_goal_still_count(api, make_user, add_session, now):
    from app.models.session import SessionStatus

    user = make_user("a@test")
    now(datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc))
    for day in (21, 22, 23, 24):
        add_session(user, datetime(2026, 9, day, 9, 0, tzinfo=timezone.utc))
    add_session(user, datetime(2026, 9, 25, 9, 0, tzinfo=timezone.utc), status=SessionStatus.failed)

    week = api("GET", user=user).json()["week"]
    assert (week["completed"], week["goal"], week["goal_met"]) == (4, 3, True)

    week = api("PUT", user=user, body={"weekly_goal": 7}).json()["week"]
    assert (week["completed"], week["goal"], week["goal_met"]) == (4, 7, False)


# ============================================================
# Personal bests
# ============================================================


def bests(body):
    return {b["category"]: b for b in body["personal_bests"]}


def test_personal_bests_use_completed_sessions_only(api, make_user, add_session, now):
    from app.models.session import SessionStatus

    user = make_user("a@test")
    t = datetime(2026, 9, 10, 9, 0, tzinfo=timezone.utc)
    s1 = add_session(user, t, title="Carbon tax", overall_score=62.0, score_logic=80.0, score_rebuttal=None, delivery=71.0)
    s2 = add_session(user, t + timedelta(days=1), overall_score=70.0, score_logic=60.0, score_rebuttal=None, delivery=64.0)
    # Higher everywhere, but not completed: never counts.
    for status in (SessionStatus.failed, SessionStatus.coaching, SessionStatus.created):
        add_session(user, t + timedelta(days=2), status=status, overall_score=99.0, score_logic=99.0, score_rebuttal=99.0, delivery=99.0)

    b = bests(api("GET", user=user).json())
    assert (b["overall"]["score"], b["overall"]["session_id"]) == (70.0, str(s2.id))
    assert b["overall"]["title"] is None  # the page shows "Session of <date>"
    assert (b["logic"]["score"], b["logic"]["session_id"], b["logic"]["title"]) == (80.0, str(s1.id), "Carbon tax")
    assert (b["quantitative"]["score"], b["quantitative"]["session_id"]) == (71.0, str(s1.id))
    assert b["overall"]["created_at"].startswith("2026-09-11")
    # Rebuttal was never scored: "No score yet", not a zero.
    assert b["rebuttal"] == {"category": "rebuttal", "score": None, "session_id": None, "title": None, "created_at": None}


def test_rebuttal_best_skips_unscored_sessions(api, make_user, add_session, now):
    user = make_user("a@test")
    t = datetime(2026, 9, 10, 9, 0, tzinfo=timezone.utc)
    add_session(user, t, score_rebuttal=None)
    scored = add_session(user, t + timedelta(days=1), score_rebuttal=35.0)
    add_session(user, t + timedelta(days=2), score_rebuttal=None)

    rebuttal = bests(api("GET", user=user).json())["rebuttal"]
    assert (rebuttal["score"], rebuttal["session_id"]) == (35.0, str(scored.id))


def test_the_delivery_score_is_read_once_then_cached(api, db, make_user, add_session, downloads, now):
    from app.models.profile import SessionDeliveryScore

    user = make_user("a@test")
    t = datetime(2026, 9, 10, 9, 0, tzinfo=timezone.utc)
    a = add_session(user, t, delivery=55.0)
    b = add_session(user, t + timedelta(days=1), delivery=None)  # no usable Delivery score

    assert bests(api("GET", user=user).json())["quantitative"]["score"] == 55.0
    assert sorted(downloads) == sorted([a.coaching_object_key, b.coaching_object_key])
    cached = {row.session_id: row.score for row in db.query(SessionDeliveryScore)}
    assert cached == {a.id: 55.0, b.id: None}

    downloads.clear()
    assert bests(api("GET", user=user).json())["quantitative"]["score"] == 55.0
    assert downloads == []


def test_a_storage_error_is_not_cached(api, db, make_user, add_session, fake_storage, monkeypatch, now):
    from app.models.profile import SessionDeliveryScore
    from app.services import storage

    user = make_user("a@test")
    add_session(user, datetime(2026, 9, 10, 9, 0, tzinfo=timezone.utc), delivery=66.0)
    working = storage.download_json

    def broken(key):
        raise RuntimeError("storage unavailable")

    monkeypatch.setattr(storage, "download_json", broken)
    r = api("GET", user=user)
    assert r.status_code == 200
    assert bests(r.json())["quantitative"]["score"] is None
    assert db.query(SessionDeliveryScore).count() == 0

    monkeypatch.setattr(storage, "download_json", working)
    assert bests(api("GET", user=user).json())["quantitative"]["score"] == 66.0


def test_deleting_a_session_updates_streak_week_and_bests(api, db, make_user, add_session, now):
    from app.models.profile import SessionDeliveryScore

    user = make_user("a@test")
    now(datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc))
    add_session(user, datetime(2026, 9, 22, 9, 0, tzinfo=timezone.utc), overall_score=60.0, delivery=60.0)
    top = add_session(user, datetime(2026, 9, 23, 9, 0, tzinfo=timezone.utc), overall_score=90.0, delivery=90.0)

    before = api("GET", user=user).json()
    assert before["streak"]["current"] == 2 and before["week"]["completed"] == 2
    assert bests(before)["overall"]["session_id"] == str(top.id)
    assert db.query(SessionDeliveryScore).count() == 2

    assert api("DELETE", f"/v1/sessions/{top.id}", user=user).status_code == 204

    after = api("GET", user=user).json()
    assert after["streak"] == {"current": 1, "longest": 1, "practised_today": False}
    assert after["week"]["completed"] == 1
    assert bests(after)["overall"]["score"] == 60.0
    assert bests(after)["quantitative"]["score"] == 60.0
    assert db.query(SessionDeliveryScore).count() == 1  # the deleted session's cache row went with it


# ============================================================
# One user never sees another's profile or stats
# ============================================================


def test_each_user_only_ever_gets_their_own_profile_and_stats(api, make_user, add_session, now):
    a, b = make_user("a@test"), make_user("b@test")
    api("PUT", user=a, body={"username": "alpha", "bio": "A's bio", "weekly_goal": 1, "time_zone": "Asia/Karachi"})
    a_session = add_session(a, datetime(2026, 9, 23, 9, 0, tzinfo=timezone.utc), title="A's speech", overall_score=95.0)

    body = api("GET", user=b).json()
    assert (body["username"], body["bio"], body["weekly_goal"], body["time_zone"]) == (None, None, 3, None)
    assert body["first_name"] == "T" and body["completed_sessions"] == 0
    assert body["streak"]["current"] == 0 and body["week"]["completed"] == 0
    assert all(x["session_id"] is None for x in body["personal_bests"])
    assert str(a_session.id) not in json.dumps(body) and "alpha" not in json.dumps(body)

    # B's save touches only B's row.
    api("PUT", user=b, body={"username": "bravo", "bio": "B's bio", "weekly_goal": 7, "time_zone": "UTC"})
    body = api("GET", user=a).json()
    assert (body["username"], body["bio"], body["weekly_goal"], body["time_zone"]) == ("alpha", "A's bio", 1, "Asia/Karachi")
    assert bests(body)["overall"]["session_id"] == str(a_session.id)


@pytest.mark.parametrize("path", ["/v1/profile/{id}", "/v1/profile?user_id={id}", "/v1/profile/alpha"])
def test_there_is_no_way_to_ask_for_someone_elses_profile(api, make_user, now, path):
    a, b = make_user("a@test"), make_user("b@test")
    api("PUT", user=a, body={"username": "alpha", "bio": "secret"})
    r = api("GET", path.format(id=a.id), user=b)
    assert r.status_code in (404, 405) or "secret" not in r.text
    assert "secret" not in r.text and "alpha" not in r.text


def test_username_and_bio_never_appear_on_the_shared_page_or_account_endpoints(api, db, make_user, add_session, fake_storage, now):
    user = make_user("private@example.com")
    api("PUT", user=user, body={"username": "hidden_name", "bio": "hidden bio text"})
    session = add_session(user, datetime(2026, 9, 23, 9, 0, tzinfo=timezone.utc))
    prefix = f"users/{user.id}/sessions/{session.id}/"
    for field, name in (("raw_metrics_object_key", "raw_metrics.json"), ("speech_content_object_key", "speech_content.json"), ("analysis_object_key", "analysis.json")):
        setattr(session, field, prefix + name)
        fake_storage.blobs[prefix + name] = b"{}"
    fake_storage.blobs[session.coaching_object_key] = json.dumps({"scores": {"overall": 50.0}, "feedback": []}).encode()
    db.commit()

    token = api("POST", f"/v1/sessions/{session.id}/share", user=user).json()["token"]
    for path, who in ((f"/v1/shared/{token}", None), ("/v1/users/me", user), (f"/v1/sessions/{session.id}/report", user), ("/v1/sessions", user)):
        r = api("GET", path, user=who)
        assert r.status_code == 200, path
        assert "hidden_name" not in r.text and "hidden bio text" not in r.text, path


def test_deleting_the_account_deletes_the_profile(api, db, make_user, add_session, now):
    from app.models.profile import SessionDeliveryScore, UserProfile
    from app.services.accounts import delete_user_account

    user = make_user("a@test")
    api("PUT", user=user, body={"username": "leaving", "bio": "bye"})
    add_session(user, datetime(2026, 9, 23, 9, 0, tzinfo=timezone.utc))
    api("GET", user=user)  # fills the Delivery cache
    assert db.query(SessionDeliveryScore).count() == 1

    user_id = user.id
    delete_user_account(db, user)
    db.expire_all()
    assert db.get(UserProfile, user_id) is None
    assert db.query(SessionDeliveryScore).count() == 0
