"""
Share links: owner management (/v1/sessions/{id}/share) and the PUBLIC
report (/v1/shared/{token}). Real signed access tokens; the public
endpoint is called with no credentials at all.

The stored documents in these fixtures deliberately carry everything
that must never leak (the session's real id inside video_analysis,
device details, internal anchor ids, feedback metadata, object keys),
so the whitelist is tested against real-shaped data.
"""

import hashlib
import json
import re
import uuid

import pytest

SHARED = "/v1/shared/"
NOT_AVAILABLE = {"detail": "Not Found"}


@pytest.fixture
def api(app_module, db, fake_storage, fake_jobs, video_flag):
    from fastapi.testclient import TestClient

    from app.core.security import create_access_token
    from app.db.database import get_db

    app = app_module.app
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    def call(method, path, user=None, body=None):
        headers = {"Authorization": f"Bearer {create_access_token(str(user.id))}"} if user else {}
        return client.request(method, path, json=body, headers=headers)

    yield call
    app.dependency_overrides.clear()


def completed_session(db, fake_storage, owner, title="Space funding practice", motion_id="space-funding", visual=True):
    from app.models.session import DebateSession, SessionStatus
    from app.models.video_analysis import VideoAnalysis

    sid = uuid.uuid4()
    prefix = f"users/{owner.id}/sessions/{sid}/"
    keys = {
        "coaching_object_key": prefix + "feedback.json",
        "raw_metrics_object_key": prefix + "raw_metrics.json",
        "speech_content_object_key": prefix + "speech_content.json",
        "analysis_object_key": prefix + "analysis.json",
        "audio_object_key": prefix + "recording.wav",
        "upload_object_key": prefix + "upload.webm",
    }
    blobs = {
        "feedback.json": {
            "session_id": str(sid),
            "scores": {"quantitative": 85.0, "argumentation": 60.0, "rebuttal": None, "structure": 40.0,
                       "persuasion": 60.0, "logic": 40.0, "overall": 57.5, "secret_extra": 1.0},
            "feedback": [
                {"category": "argumentation", "title": "Insufficient evidence", "issue": "No data.", "severity": "high",
                 "evidence": ["We cannot justify spending billions."], "explanation": "Why.", "recommendation": "Add a statistic.",
                 "metadata": {"also_affects": ["logic"], "internal": str(sid)}},
            ],
        },
        "raw_metrics.json": {"session_id": str(sid), "speech": {"words_per_minute": 148.3, "speech_duration": 56.2, "word_count": 139},
                             "pauses": {"count": 5, "longest_duration": 2.9}, "fillers": {"count": 0, "instances": []},
                             "stutters": {"count": 0, "instances": []}},
        "speech_content.json": {"session_id": str(sid), "segments": [{"text": "FULL TRANSCRIPT TEXT"}]},
        "analysis.json": {"session_id": str(sid), "audio_file": prefix + "recording.wav"},
    }
    for name, doc in blobs.items():
        fake_storage.blobs[prefix + name] = json.dumps(doc).encode()

    row = DebateSession(id=sid, user_id=owner.id, title=title, status=SessionStatus.completed, motion_id=motion_id, **keys)
    db.add(row)
    if visual:
        fake_storage.blobs[prefix + "visual_result.json"] = json.dumps({
            "session_id": str(sid), "schema": "x", "computed_at": "2026-09-26T00:00:00Z",
            "source_summary": {"platform": "web", "device_tier": "high", "runtime_version": "1"},
            "quality": {"context": {"setting": "camera_audience", "uses_notes": False}, "warnings": ["low_light"],
                        "face_tracked_ratio": 0.9},
            "metrics": {"camera_facing_ratio": {"key": "camera_facing_ratio", "value": 0.72, "status": "ok", "confidence": "high",
                                                "unit": "ratio", "basis": "speech", "coverage": 0.9, "definition_version": "v1"}},
            "events": [{"type": "gaze_away", "start": 1.0}],
            "series": {"camera_facing": [0.1, 0.2]},
        }).encode()
        fake_storage.blobs[prefix + "visual_feedback.json"] = json.dumps({
            "model": "m", "prompt_version": "p",
            "correlated_moments": [{
                "id": "m1", "rule_id": "r1", "polarity": "improve", "salience": 0.9,
                "anchor": {"argument_unit_id": f"{sid}-seg-3", "type": "claim"},
                "start": 3.0, "end": 7.5, "excerpt_word_range": [4, 9], "excerpt_text": "prestige projects",
                "observations": [{"id": "o1", "kind": "event", "event_ref": "e1", "type": "gaze_away", "duration_s": 2.1, "direction": "down"}],
            }],
            "visual_feedback": [{"id": "v1", "category": "gaze", "polarity": "improve", "moment_id": "m1",
                                 "metric_keys": ["camera_facing_ratio"], "observation_ids": ["o1"], "coaching": "Look up more."}],
            "summary": "INTERNAL SUMMARY",
            "validation": {"retried": False, "dropped_items": 0},
        }).encode()
        db.add(VideoAnalysis(session_id=sid, user_id=owner.id, status="processed", coaching_status="completed",
                             result_key=prefix + "visual_result.json", feedback_key=prefix + "visual_feedback.json"))
    db.commit()
    return row


def share(api, owner, session):
    response = api("POST", f"/v1/sessions/{session.id}/share", owner)
    assert response.status_code == 201, response.text
    return response.json()["token"]


# ---------------------------------------------------------------
# 🔒 The public payload is an exact whitelist
# ---------------------------------------------------------------

EXPECTED_KEYS = {
    "": {"title", "recorded_at", "motion", "motion_not_applied", "scores", "feedback", "delivery", "video_analysis_status",
         "video_unavailable_reason", "visual_coaching_status", "video_analysis", "correlated_moments", "visual_feedback"},
    "motion": {"title", "description"},
    "scores": {"quantitative", "argumentation", "rebuttal", "structure", "persuasion", "logic", "overall"},
    "feedback[]": {"category", "title", "issue", "severity", "evidence", "explanation", "recommendation"},
    "delivery": {"words_per_minute", "speech_duration", "filler_count", "pause_count", "stutter_count"},
    "video_analysis": {"quality", "metrics"},
    "video_analysis.quality": {"context", "warnings"},
    "video_analysis.quality.context": {"setting"},
    "video_analysis.metrics.*": {"status", "value", "confidence"},
    "correlated_moments[]": {"id", "polarity", "anchor", "start", "end", "excerpt_text", "observations", "salience"},
    "correlated_moments[].anchor": {"type"},
    "correlated_moments[].observations[]": {"id", "kind", "type", "duration_s", "direction", "metric", "unit_value", "session_value"},
    "visual_feedback": {"visual_feedback"},
    "visual_feedback.visual_feedback[]": {"id", "category", "polarity", "moment_id", "coaching"},
}


def key_sets(body):
    """Every object's key set in the payload, by a path pattern."""
    found = {}

    def walk(value, path):
        if isinstance(value, dict):
            found.setdefault(path, set()).update(value)
            for key, child in value.items():
                if path == "video_analysis.metrics":
                    walk(child, "video_analysis.metrics.*")
                elif path == "scores":
                    continue
                else:
                    walk(child, f"{path}.{key}" if path else key)
        elif isinstance(value, list):
            for child in value:
                walk(child, f"{path}[]")

    walk(body, "")
    found.pop("video_analysis.metrics", None)  # keyed by metric name, checked per entry
    return found


def test_the_public_payload_has_exactly_the_whitelisted_keys(api, db, fake_storage, make_user):
    owner = make_user("owner@test")
    session = completed_session(db, fake_storage, owner)
    body = api("GET", SHARED + share(api, owner, session)).json()

    assert key_sets(body) == EXPECTED_KEYS


def test_nothing_private_appears_anywhere_in_the_public_payload(api, db, fake_storage, make_user):
    owner = make_user("owner@test")
    session = completed_session(db, fake_storage, owner)
    response = api("GET", SHARED + share(api, owner, session))
    text = response.text

    for secret in (
        str(session.id), session.id.hex, str(owner.id), owner.id.hex, "owner@test", owner.first_name + " " + owner.last_name,
        "users/", "recording.wav", "https://", "download.test", "upload.test",
        "session_id", "source_summary", "argument_unit_id", "metadata", "audio", "FULL TRANSCRIPT TEXT", "INTERNAL SUMMARY",
        "secret_extra", "series", "events", "rule_id", "excerpt_word_range", "event_ref",
    ):
        assert secret not in text, secret


def test_the_public_payload_carries_the_report(api, db, fake_storage, make_user):
    owner = make_user("owner@test")
    session = completed_session(db, fake_storage, owner)
    body = api("GET", SHARED + share(api, owner, session)).json()

    assert body["title"] == "Space funding practice"
    assert body["motion"] == {"title": "Space exploration", "description": "This house believes that governments should stop funding space exploration."}
    assert body["scores"]["overall"] == 57.5 and body["scores"]["rebuttal"] is None
    assert body["feedback"][0]["title"] == "Insufficient evidence"
    assert body["delivery"] == {"words_per_minute": 148.3, "speech_duration": 56.2, "filler_count": 0, "pause_count": 5, "stutter_count": 0}
    assert body["video_analysis"]["metrics"]["camera_facing_ratio"] == {"status": "ok", "value": 0.72, "confidence": "high"}
    assert body["visual_feedback"]["visual_feedback"][0]["coaching"] == "Look up more."


def test_public_responses_are_not_cached_indexed_or_referred(api, db, fake_storage, make_user):
    owner = make_user("owner@test")
    token = share(api, owner, completed_session(db, fake_storage, owner))

    for response in (api("GET", SHARED + token), api("GET", SHARED + "x" * 43)):
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["x-robots-tag"] == "noindex, nofollow"
        assert response.headers["referrer-policy"] == "no-referrer"


def test_the_public_page_stays_in_sync_with_the_session(api, db, fake_storage, make_user):
    owner = make_user("owner@test")
    session = completed_session(db, fake_storage, owner)
    token = share(api, owner, session)

    session.title = "Renamed"
    db.commit()
    doc = json.loads(fake_storage.blobs[session.coaching_object_key])
    doc["feedback"][0]["title"] = "Updated finding"
    fake_storage.blobs[session.coaching_object_key] = json.dumps(doc).encode()

    body = api("GET", SHARED + token).json()
    assert body["title"] == "Renamed" and body["feedback"][0]["title"] == "Updated finding"


# ---------------------------------------------------------------
# 🔒 Revoking, replacing, and one token per session
# ---------------------------------------------------------------

def test_a_revoked_token_is_not_available(api, db, fake_storage, make_user):
    owner = make_user("owner@test")
    session = completed_session(db, fake_storage, owner)
    token = share(api, owner, session)
    assert api("GET", SHARED + token).status_code == 200

    assert api("DELETE", f"/v1/sessions/{session.id}/share", owner).status_code == 204

    response = api("GET", SHARED + token)
    assert (response.status_code, response.json()) == (404, NOT_AVAILABLE)
    assert api("GET", f"/v1/sessions/{session.id}/share", owner).json() == {"sharing": False, "created_at": None}


def test_creating_a_new_link_kills_the_old_one(api, db, fake_storage, make_user):
    owner = make_user("owner@test")
    session = completed_session(db, fake_storage, owner)
    old = share(api, owner, session)
    new = share(api, owner, session)

    assert old != new
    assert api("GET", SHARED + old).status_code == 404
    assert api("GET", SHARED + new).status_code == 200


def test_a_session_has_at_most_one_active_link(api, db, fake_storage, make_user):
    from app.models.session_share import SessionShare

    owner = make_user("owner@test")
    session = completed_session(db, fake_storage, owner)
    for _ in range(3):
        share(api, owner, session)

    rows = db.query(SessionShare).filter_by(session_id=session.id).all()
    assert sorted(r.revoked_at is None for r in rows) == [False, False, True]


def test_the_database_itself_refuses_a_second_active_link(db, fake_storage, make_user):
    from sqlalchemy.exc import IntegrityError

    from app.models.session_share import SessionShare

    owner = make_user("owner@test")
    session = completed_session(db, fake_storage, owner)
    db.add(SessionShare(session_id=session.id, token_hash="a" * 64))
    db.commit()
    db.add(SessionShare(session_id=session.id, token_hash="b" * 64))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_a_token_for_one_session_never_returns_another(api, db, fake_storage, make_user):
    owner, other = make_user("owner@test"), make_user("other@test")
    mine = completed_session(db, fake_storage, owner, title="Mine")
    theirs = completed_session(db, fake_storage, other, title="Theirs", motion_id=None)
    my_token, their_token = share(api, owner, mine), share(api, other, theirs)

    assert api("GET", SHARED + my_token).json()["title"] == "Mine"
    assert api("GET", SHARED + their_token).json()["title"] == "Theirs"


# ---------------------------------------------------------------
# 🔒 Only the owner manages a link
# ---------------------------------------------------------------

@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_another_user_gets_404_and_changes_nothing(api, db, fake_storage, make_user, method):
    owner, intruder = make_user("owner@test"), make_user("intruder@test")
    session = completed_session(db, fake_storage, owner)
    token = share(api, owner, session)

    response = api(method, f"/v1/sessions/{session.id}/share", intruder)

    assert response.status_code == 404
    assert api("GET", SHARED + token).status_code == 200  # the owner's link still works


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_managing_a_link_requires_sign_in(api, db, fake_storage, make_user, method):
    session = completed_session(db, fake_storage, make_user("owner@test"))
    assert api(method, f"/v1/sessions/{session.id}/share").status_code == 401


def test_only_a_finished_report_can_be_shared(api, db, make_user):
    from app.models.session import DebateSession, SessionStatus

    owner = make_user("owner@test")
    row = DebateSession(user_id=owner.id, status=SessionStatus.coaching)
    db.add(row)
    db.commit()
    assert api("POST", f"/v1/sessions/{row.id}/share", owner).status_code == 409


# ---------------------------------------------------------------
# 🔒 Every failure looks the same
# ---------------------------------------------------------------

def test_every_unavailable_case_is_the_same_plain_404(api, db, fake_storage, make_user):
    from app.models.session import SessionStatus
    from app.services.accounts import delete_user_account

    owner = make_user("owner@test")
    cases = {}

    cases["malformed"] = "not-a-token"
    cases["well-formed but unknown"] = "A" * 43

    s1 = completed_session(db, fake_storage, owner)
    cases["revoked"] = share(api, owner, s1)
    api("DELETE", f"/v1/sessions/{s1.id}/share", owner)

    s2 = completed_session(db, fake_storage, owner)
    cases["replaced"] = share(api, owner, s2)
    share(api, owner, s2)

    s3 = completed_session(db, fake_storage, owner)
    cases["session deleted"] = share(api, owner, s3)
    assert api("DELETE", f"/v1/sessions/{s3.id}", owner).status_code == 204

    s4 = completed_session(db, fake_storage, owner)
    cases["report files missing"] = share(api, owner, s4)
    del fake_storage.blobs[s4.coaching_object_key]

    s5 = completed_session(db, fake_storage, owner)
    cases["session no longer completed"] = share(api, owner, s5)
    s5.status = SessionStatus.failed
    db.commit()

    doomed = make_user("doomed@test")
    s6 = completed_session(db, fake_storage, doomed)
    cases["account deleted"] = share(api, doomed, s6)
    delete_user_account(db, doomed)

    responses = {name: api("GET", SHARED + token) for name, token in cases.items()}
    responses["no token at all"] = api("GET", SHARED)

    for name, response in responses.items():
        assert (response.status_code, response.json()) == (404, NOT_AVAILABLE), name
    assert len({r.content for r in responses.values()}) == 1


def test_deleting_the_session_or_account_removes_the_link_rows(api, db, fake_storage, make_user):
    from app.models.session_share import SessionShare
    from app.services.accounts import delete_user_account

    owner = make_user("owner@test")
    s1, s2 = completed_session(db, fake_storage, owner), completed_session(db, fake_storage, owner)
    share(api, owner, s1)
    share(api, owner, s2)

    api("DELETE", f"/v1/sessions/{s1.id}", owner)
    assert db.query(SessionShare).filter_by(session_id=s1.id).count() == 0

    delete_user_account(db, owner)
    assert db.query(SessionShare).count() == 0


# ---------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------

def test_tokens_are_long_random_and_stored_only_as_a_hash(api, db, fake_storage, make_user):
    from app.models.session_share import SessionShare

    owner = make_user("owner@test")
    session = completed_session(db, fake_storage, owner)
    tokens = [share(api, owner, session) for _ in range(20)]

    assert len(set(tokens)) == 20
    for token in tokens:
        assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token)  # 32 random bytes = 256 bits
        assert session.id.hex not in token.lower() and str(session.id) not in token

    rows = db.query(SessionShare).all()
    stored = {r.token_hash for r in rows}
    assert stored == {hashlib.sha256(t.encode()).hexdigest() for t in tokens}
    for row in rows:
        assert all(t not in (row.token_hash, str(row.id)) for t in tokens)


def test_a_token_is_never_derived_from_the_session_id(monkeypatch):
    from app.services import shares

    calls = []
    monkeypatch.setattr(shares.secrets, "token_urlsafe", lambda n: calls.append(n) or "Z" * 43)
    assert shares.new_token() == "Z" * 43
    assert calls == [32]


# ---------------------------------------------------------------
# The owner's session list
# ---------------------------------------------------------------

def test_the_session_list_marks_shared_sessions(api, db, fake_storage, make_user):
    owner = make_user("owner@test")
    shared_one = completed_session(db, fake_storage, owner, title="A")
    completed_session(db, fake_storage, owner, title="B")
    share(api, owner, shared_one)

    flags = {row["title"]: row["shared"] for row in api("GET", "/v1/sessions", owner).json()}
    assert flags == {"A": True, "B": False}
    assert api("GET", f"/v1/sessions/{shared_one.id}", owner).json()["shared"] is True


# ---------------------------------------------------------------
# Rate limit on the public lookup
# ---------------------------------------------------------------

def test_public_lookups_have_their_own_tighter_rate_limit():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.rate_limit import PerClientRateLimitMiddleware

    app = FastAPI()
    app.add_middleware(PerClientRateLimitMiddleware, max_requests_per_minute=100, path_limits={"/v1/shared/": 3})

    @app.get("/v1/shared/{token}")
    def lookup(token: str):
        return {}

    @app.get("/v1/other")
    def other():
        return {}

    client = TestClient(app)
    assert [client.get(f"/v1/shared/{i}").status_code for i in range(4)] == [200, 200, 200, 429]
    assert client.get("/v1/other").status_code == 200  # other paths keep the global budget


def test_the_app_registers_the_shared_lookup_limit(app_module):
    from app.core.rate_limit import PerClientRateLimitMiddleware

    [limiter] = [m for m in app_module.app.user_middleware if m.cls is PerClientRateLimitMiddleware]
    assert limiter.kwargs["path_limits"] == {"/v1/shared/": 20}
