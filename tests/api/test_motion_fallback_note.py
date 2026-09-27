"""
When a session had a practice motion but its coaching fell back to the
rule-based path (which can't read a motion), the report says so. The
flag is motion_not_applied, on the owner's report and on the shared
page's payload.
"""

import json
import uuid

import pytest

FALLBACK = {"llm_errors": {"synthesis": "RuntimeError: provider down"}}


@pytest.fixture
def api(app_module, db, fake_storage, fake_jobs, video_flag):
    from fastapi.testclient import TestClient

    from app.core.security import create_access_token
    from app.db.database import get_db

    app = app_module.app
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    def call(method, path, user=None):
        headers = {"Authorization": f"Bearer {create_access_token(str(user.id))}"} if user else {}
        return client.request(method, path, headers=headers)

    yield call
    app.dependency_overrides.clear()


def completed(db, fake_storage, owner, motion_id, extra):
    from app.models.session import DebateSession, SessionStatus

    sid = uuid.uuid4()
    prefix = f"users/{owner.id}/sessions/{sid}/"
    keys = {k: prefix + f for k, f in (("coaching_object_key", "feedback.json"), ("raw_metrics_object_key", "raw_metrics.json"),
                                       ("speech_content_object_key", "speech_content.json"), ("analysis_object_key", "analysis.json"))}
    for key in keys.values():
        fake_storage.blobs[key] = json.dumps({"scores": {"overall": 50.0}, "feedback": []} if key.endswith("feedback.json") else {}).encode()
    row = DebateSession(id=sid, user_id=owner.id, status=SessionStatus.completed, motion_id=motion_id, extra=extra, **keys)
    db.add(row)
    db.commit()
    return row


@pytest.mark.parametrize(
    "motion_id, extra, expected",
    [
        ("carbon-tax", FALLBACK, True),
        (None, FALLBACK, False),  # no motion: nothing to say
        ("carbon-tax", None, False),  # the LLM coached it
        ("carbon-tax", {"llm_errors": {"something_else": "x"}}, False),
        ("carbon-tax", {"llm_errors": {}}, False),
        ("carbon-tax", {"other": 1}, False),
    ],
    ids=["motion-and-fallback", "no-motion", "no-fallback", "other-error", "empty-errors", "unrelated-extra"],
)
def test_the_report_flags_a_motion_the_fallback_couldnt_use(api, db, fake_storage, make_user, motion_id, extra, expected):
    owner = make_user("owner@test")
    session = completed(db, fake_storage, owner, motion_id, extra)

    report = api("GET", f"/v1/sessions/{session.id}/report", owner)
    assert report.status_code == 200
    assert report.json()["motion_not_applied"] is expected


def test_the_shared_page_carries_the_same_flag(api, db, fake_storage, make_user):
    owner = make_user("owner@test")
    session = completed(db, fake_storage, owner, "carbon-tax", FALLBACK)
    token = api("POST", f"/v1/sessions/{session.id}/share", owner).json()["token"]

    body = api("GET", f"/v1/shared/{token}").json()
    assert body["motion_not_applied"] is True
    assert "llm_errors" not in json.dumps(body) and "provider down" not in json.dumps(body)


def test_a_rerun_clears_a_stale_fallback_from_an_earlier_run():
    from app.models.session import DebateSession
    from app.services.pipeline import _record_llm_errors

    session = DebateSession(motion_id="carbon-tax", extra={"llm_errors": {"synthesis": "old"}, "keep": 1})
    _record_llm_errors(session, {})
    assert session.extra == {"keep": 1}

    _record_llm_errors(session, {"synthesis": "new"})
    assert session.extra == {"keep": 1, "llm_errors": {"synthesis": "new"}}

    untouched = DebateSession(extra=None)
    _record_llm_errors(untouched, {})
    assert untouched.extra is None
