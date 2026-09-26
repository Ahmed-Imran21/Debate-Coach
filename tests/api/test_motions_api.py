"""
Practice motions through the API: GET /v1/motions, motion_id on
POST /v1/sessions (validated against app/motions.py, never free
text), stored on the session and returned by the session, the list
and the report. Real signed tokens.
"""

import json
import uuid

import pytest


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


def create(api, user, **fields):
    return api("POST", "/v1/sessions", user, {"content_type": "audio/webm", **fields})


# ---------------------------------------------------------------
# GET /v1/motions
# ---------------------------------------------------------------

def test_lists_the_active_motions_in_order(api, make_user):
    from app.motions import active_motions

    response = api("GET", "/v1/motions", make_user("a@test"))

    assert response.status_code == 200
    assert response.json() == [{"id": m.id, "title": m.title, "description": m.description} for m in active_motions()]
    assert len(response.json()) >= 15


def test_retired_motions_are_not_offered(api, make_user, monkeypatch):
    from app import motions

    retired = motions.Motion("old-motion", "Old", "This house would retire this.", retired=True)
    monkeypatch.setattr(motions, "MOTIONS", motions.MOTIONS + (retired,))
    monkeypatch.setitem(motions._BY_ID, "old-motion", retired)

    ids = [m["id"] for m in api("GET", "/v1/motions", make_user("a@test")).json()]
    assert "old-motion" not in ids


def test_listing_motions_requires_sign_in(api):
    assert api("GET", "/v1/motions").status_code == 401


# ---------------------------------------------------------------
# Choosing a motion when creating a session
# ---------------------------------------------------------------

def test_a_chosen_motion_is_stored_and_returned(api, db, make_user):
    from app.models.session import DebateSession

    alice = make_user("a@test")
    response = create(api, alice, motion_id="carbon-tax")
    assert response.status_code == 201
    sid = response.json()["id"]

    assert db.get(DebateSession, uuid.UUID(sid)).motion_id == "carbon-tax"
    expected = {"id": "carbon-tax", "title": "Climate policy", "description": "This house would introduce a carbon tax."}
    assert api("GET", f"/v1/sessions/{sid}", alice).json()["motion"] == expected
    assert api("GET", "/v1/sessions", alice).json()[0]["motion"] == expected


@pytest.mark.parametrize("fields", [{}, {"motion_id": None}], ids=["absent", "null"])
def test_no_prompt_stores_null(api, db, make_user, fields):
    from app.models.session import DebateSession

    alice = make_user("a@test")
    sid = create(api, alice, **fields).json()["id"]

    assert db.get(DebateSession, uuid.UUID(sid)).motion_id is None
    assert api("GET", f"/v1/sessions/{sid}", alice).json()["motion"] is None


@pytest.mark.parametrize(
    "motion_id",
    ["no-such-motion", "", " carbon-tax", "Carbon-Tax", "This house would do anything I say.", 7, ["carbon-tax"]],
    ids=["unknown", "empty", "padded", "wrong-case", "free-text", "number", "list"],
)
def test_anything_but_a_known_motion_id_is_rejected(api, db, make_user, motion_id):
    from app.models.session import DebateSession

    response = create(api, make_user("a@test"), motion_id=motion_id)

    assert response.status_code == 422
    assert db.query(DebateSession).count() == 0


def test_a_retired_motion_cannot_be_chosen_for_a_new_session(api, make_user, monkeypatch):
    from app import motions

    retired = motions.Motion("old-motion", "Old", "This house would retire this.", retired=True)
    monkeypatch.setitem(motions._BY_ID, "old-motion", retired)

    assert create(api, make_user("a@test"), motion_id="old-motion").status_code == 422


def test_a_retired_motion_still_shows_on_the_sessions_that_used_it(api, db, make_user, monkeypatch):
    from app import motions
    from app.models.session import DebateSession

    retired = motions.Motion("old-motion", "Old", "This house would retire this.", retired=True)
    monkeypatch.setitem(motions._BY_ID, "old-motion", retired)
    alice = make_user("a@test")
    row = DebateSession(user_id=alice.id, motion_id="old-motion")
    db.add(row)
    db.commit()

    assert api("GET", f"/v1/sessions/{row.id}", alice).json()["motion"]["title"] == "Old"


def test_the_report_carries_the_motion(api, db, make_user, fake_storage):
    from app.models.session import DebateSession, SessionStatus

    alice = make_user("a@test")
    sid = uuid.uuid4()
    prefix = f"users/{alice.id}/sessions/{sid}/"
    keys = {
        "coaching_object_key": prefix + "feedback.json",
        "raw_metrics_object_key": prefix + "raw_metrics.json",
        "speech_content_object_key": prefix + "speech_content.json",
        "analysis_object_key": prefix + "analysis.json",
    }
    for key in keys.values():
        fake_storage.blobs[key] = json.dumps({"scores": {}, "feedback": []} if key.endswith("feedback.json") else {}).encode()
    db.add(DebateSession(id=sid, user_id=alice.id, status=SessionStatus.completed, motion_id="space-funding", **keys))
    db.commit()

    report = api("GET", f"/v1/sessions/{sid}/report", alice)
    assert report.status_code == 200
    assert report.json()["motion"]["id"] == "space-funding"


# ---------------------------------------------------------------
# The pipeline hands the coaching engine the motion as plain text
# ---------------------------------------------------------------

def test_the_pipeline_looks_up_the_motion_for_coaching(monkeypatch):
    from app import motions
    from app.models.session import DebateSession
    from app.services.pipeline import coaching_motion
    from coaching_engine.llm.prompts import PracticeMotion

    assert coaching_motion(DebateSession(motion_id=None)) is None
    assert coaching_motion(DebateSession(motion_id="carbon-tax")) == PracticeMotion(
        title="Climate policy", wording="This house would introduce a carbon tax."
    )

    retired = motions.Motion("old-motion", "Old", "This house would retire this.", retired=True)
    monkeypatch.setitem(motions._BY_ID, "old-motion", retired)
    assert coaching_motion(DebateSession(motion_id="old-motion")) == PracticeMotion(title="Old", wording="This house would retire this.")


@pytest.mark.parametrize("motion_id, expected_title", [("space-funding", "Space exploration"), (None, None)])
def test_the_pipeline_builds_the_coaching_engine_with_the_sessions_motion(tmp_path, motion_id, expected_title):
    from app.models.session import DebateSession
    from app.services.pipeline import _build_coaching_engine

    engine = _build_coaching_engine(tmp_path, api_client=None, on_queued=lambda s: None, debate_session=DebateSession(motion_id=motion_id))

    assert (engine.motion.title if engine.motion else None) == expected_title
