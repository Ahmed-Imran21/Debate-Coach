"""
§3.6 / §3.7: session creation opt-in, signal upload, start with
the optional video outcome, result fields, ownership, flag-off
behaviour, and backward compatibility of POST /start.
"""

import gzip
import json
import uuid

import pytest

from tests.visual_analysis.synthetic import simple_track


def _create(client, video="requested"):
    r = client.post("/v1/sessions", json={"content_type": "audio/webm", "title": "t", "video_analysis": video})
    assert r.status_code == 201, r.text
    return r.json()


def _put_signals(client, session_id, data=None, gz=True, **headers):
    data = data if data is not None else simple_track(session_id)
    body = json.dumps(data).encode()
    if gz:
        body = gzip.compress(body)
        headers.setdefault("Content-Encoding", "gzip")
    headers.setdefault("Content-Type", "application/json")
    return client.put(f"/v1/sessions/{session_id}/visual-signals", content=body, headers=headers)


# ---------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------

def test_request_upload_start_flow(client_for, make_user, fake_storage, fake_jobs, db):
    user = make_user("a@test")
    c = client_for(user)

    created = _create(c)
    sid = created["id"]

    # awaiting_upload immediately after create
    assert c.get(f"/v1/sessions/{sid}").json()["video_analysis_status"] == "awaiting_upload"

    r = _put_signals(c, sid)
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "received", "frames": 100}
    assert f"users/{user.id}/sessions/{sid}/visual_signals.json.gz" in fake_storage.blobs

    assert c.get(f"/v1/sessions/{sid}").json()["video_analysis_status"] == "received"

    # audio "uploaded" so start passes its size check
    fake_storage.sizes[f"users/{user.id}/sessions/{sid}/upload.webm"] = 1000

    r = c.post(f"/v1/sessions/{sid}/start", json={"video": {"status": "uploaded"}})
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "queued"
    assert r.json()["video_analysis_status"] == "received"
    assert fake_jobs == [uuid.UUID(sid)]


def test_reupload_replaces_until_processing_starts(client_for, make_user, fake_storage, db):
    from app.models.video_analysis import VideoAnalysis
    from datetime import datetime, timezone

    c = client_for(make_user("a@test"))
    sid = _create(c)["id"]

    assert _put_signals(c, sid).status_code == 200
    second = simple_track(sid, duration_s=12.0)
    assert _put_signals(c, sid, data=second).status_code == 200
    assert _put_signals(c, sid, data=second).json()["frames"] == 120

    row = db.get(VideoAnalysis, uuid.UUID(sid))
    row.processing_started_at = datetime.now(timezone.utc)
    db.commit()

    r = _put_signals(c, sid)
    assert r.status_code == 409


def test_plain_json_upload_also_accepted(client_for, make_user):
    c = client_for(make_user("a@test"))
    sid = _create(c)["id"]
    r = _put_signals(c, sid, gz=False)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------
# Rejections
# ---------------------------------------------------------------

def test_upload_without_request_is_409(client_for, make_user):
    c = client_for(make_user("a@test"))
    sid = _create(c, video="not_requested")["id"]
    r = _put_signals(c, sid)
    assert r.status_code == 409


def test_invalid_track_is_422_with_code(client_for, make_user):
    c = client_for(make_user("a@test"))
    sid = _create(c)["id"]

    bad = simple_track(sid)
    bad["frames"]["t"][3] = bad["frames"]["t"][2]
    r = _put_signals(c, sid, data=bad)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "time_not_increasing"

    r = _put_signals(c, sid, data=simple_track("other-session"))
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "session_mismatch"


def test_gzip_bomb_is_413(client_for, make_user, monkeypatch):
    from visual_analysis import config

    monkeypatch.setattr(config, "MAX_DECOMPRESSED_BYTES", 256 * 1024)
    c = client_for(make_user("a@test"))
    sid = _create(c)["id"]

    bomb = gzip.compress(b"0" * (50 * 1024 * 1024), compresslevel=9)
    r = c.put(
        f"/v1/sessions/{sid}/visual-signals",
        content=bomb,
        headers={"Content-Encoding": "gzip", "Content-Type": "application/json"},
    )
    assert r.status_code == 413


def test_declared_oversize_is_413_before_reading(client_for, make_user):
    c = client_for(make_user("a@test"))
    sid = _create(c)["id"]
    r = c.put(
        f"/v1/sessions/{sid}/visual-signals",
        content=b"{}",
        headers={"Content-Length": str(3 * 1024 * 1024), "Content-Type": "application/json"},
    )
    assert r.status_code == 413


def test_start_uploaded_without_stored_track_is_409(client_for, make_user, fake_storage):
    user = make_user("a@test")
    c = client_for(user)
    sid = _create(c)["id"]
    fake_storage.sizes[f"users/{user.id}/sessions/{sid}/upload.webm"] = 1000

    r = c.post(f"/v1/sessions/{sid}/start", json={"video": {"status": "uploaded"}})
    assert r.status_code == 409


def test_start_unavailable_records_reason(client_for, make_user, fake_storage):
    user = make_user("a@test")
    c = client_for(user)
    sid = _create(c)["id"]
    fake_storage.sizes[f"users/{user.id}/sessions/{sid}/upload.webm"] = 1000

    r = c.post(f"/v1/sessions/{sid}/start", json={"video": {"status": "unavailable", "reason": "camera_denied"}})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["video_analysis_status"] == "unavailable"
    assert body["video_unavailable_reason"] == "camera_denied"


def test_start_unavailable_on_session_that_never_requested(client_for, make_user, fake_storage):
    """Old flow + a client that reports unavailable: recorded, not an error."""
    user = make_user("a@test")
    c = client_for(user)
    sid = _create(c, video="not_requested")["id"]
    fake_storage.sizes[f"users/{user.id}/sessions/{sid}/upload.webm"] = 1000

    r = c.post(f"/v1/sessions/{sid}/start", json={"video": {"status": "unavailable", "reason": "user_opted_out"}})
    assert r.status_code == 202
    assert r.json()["video_analysis_status"] == "unavailable"


# ---------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------

def test_start_without_body_behaves_as_before(client_for, make_user, fake_storage, fake_jobs):
    user = make_user("a@test")
    c = client_for(user)
    sid = _create(c, video="not_requested")["id"]
    fake_storage.sizes[f"users/{user.id}/sessions/{sid}/upload.webm"] = 1000

    r = c.post(f"/v1/sessions/{sid}/start")  # no body at all
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert body["video_analysis_status"] == "not_requested"
    assert body["video_unavailable_reason"] is None
    assert fake_jobs == [uuid.UUID(sid)]


def test_start_with_empty_json_body_behaves_as_before(client_for, make_user, fake_storage):
    user = make_user("a@test")
    c = client_for(user)
    sid = _create(c, video="not_requested")["id"]
    fake_storage.sizes[f"users/{user.id}/sessions/{sid}/upload.webm"] = 1000

    r = c.post(f"/v1/sessions/{sid}/start", json={})
    assert r.status_code == 202
    assert r.json()["video_analysis_status"] == "not_requested"


def test_create_without_video_field_is_not_requested(client_for, make_user):
    c = client_for(make_user("a@test"))
    r = c.post("/v1/sessions", json={"content_type": "audio/webm"})
    assert r.status_code == 201
    assert c.get(f"/v1/sessions/{r.json()['id']}").json()["video_analysis_status"] == "not_requested"


def test_list_carries_video_status(client_for, make_user):
    c = client_for(make_user("a@test"))
    a = _create(c)["id"]
    b = _create(c, video="not_requested")["id"]
    rows = {row["id"]: row for row in c.get("/v1/sessions").json()}
    assert rows[a]["video_analysis_status"] == "awaiting_upload"
    assert rows[b]["video_analysis_status"] == "not_requested"


# ---------------------------------------------------------------
# Flag off
# ---------------------------------------------------------------

def test_flag_off_ignores_request_and_hides_route(client_for, make_user, video_flag, fake_storage):
    video_flag(False)
    user = make_user("a@test")
    c = client_for(user)

    created = _create(c, video="requested")
    sid = created["id"]
    assert c.get(f"/v1/sessions/{sid}").json()["video_analysis_status"] == "not_requested"

    assert _put_signals(c, sid).status_code == 404

    fake_storage.sizes[f"users/{user.id}/sessions/{sid}/upload.webm"] = 1000
    r = c.post(f"/v1/sessions/{sid}/start", json={"video": {"status": "unavailable", "reason": "camera_denied"}})
    assert r.status_code == 202
    assert r.json()["video_analysis_status"] == "not_requested"


# ---------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------

def test_user_b_cannot_upload_to_or_read_user_a_session(client_for, make_user):
    a = make_user("a@test")
    b = make_user("b@test")

    sid = _create(client_for(a))["id"]

    cb = client_for(b)
    assert _put_signals(cb, sid).status_code == 404
    assert cb.get(f"/v1/sessions/{sid}").status_code == 404
    assert cb.get(f"/v1/sessions/{sid}/report").status_code == 404
    assert cb.post(f"/v1/sessions/{sid}/start", json={"video": {"status": "uploaded"}}).status_code == 404
    assert cb.delete(f"/v1/sessions/{sid}").status_code == 404


# ---------------------------------------------------------------
# Deletion cascades
# ---------------------------------------------------------------

def test_delete_removes_video_rows_and_storage_prefix(client_for, make_user, fake_storage, db):
    from app.models.video_analysis import SessionMetric, VideoAnalysis

    user = make_user("a@test")
    c = client_for(user)
    sid = _create(c)["id"]
    assert _put_signals(c, sid).status_code == 200

    db.add(
        SessionMetric(
            user_id=user.id, session_id=uuid.UUID(sid), metric_key="camera_facing_ratio",
            value=0.5, unit="ratio", definition_version="camera_facing@1",
            coverage=0.9, confidence="high", status="ok", platform="web",
        )
    )
    db.commit()

    r = c.delete(f"/v1/sessions/{sid}")
    assert r.status_code == 204
    db.expire_all()

    assert db.get(VideoAnalysis, uuid.UUID(sid)) is None
    assert db.query(SessionMetric).filter_by(session_id=uuid.UUID(sid)).count() == 0
    assert fake_storage.deleted_prefixes == [f"users/{user.id}/sessions/{sid}/"]
    assert not any(k.startswith(f"users/{user.id}/sessions/{sid}/") for k in fake_storage.blobs)


class _FakeCoachingResponse:
    def __init__(self, content: str):
        self.success = True
        self.content = content
        self.error = None


class _FakeCoachingClient:
    """A visual_feedback item with no moment_id -- correlation isn't
    the point of this test, only that a real feedback document gets
    written to a real key so deletion has three real artifacts (not
    one) to actually remove."""

    def generate(self, **kwargs):
        import json as _json

        return _FakeCoachingResponse(_json.dumps({
            "visual_feedback": [{
                "id": "vf_1", "category": "coverage", "polarity": "neutral",
                "moment_id": None, "metric_keys": [], "observation_ids": [],
                "coaching": "Visual delivery measurements were captured for this session.",
            }],
            "summary": "A short session with steady delivery.",
        }))


def test_delete_removes_all_three_artifacts_after_a_real_pipeline_run(client_for, make_user, fake_storage, db, tmp_path):
    """
    Runs both real pipeline hooks (not a hand-inserted row) so the
    signal track, video_analysis.json, and visual_feedback.json all
    genuinely exist under the session's storage prefix, plus a full
    set of 11 SessionMetric rows -- then deletes the session and
    checks fake_storage.blobs and the DB directly, rather than
    trusting that a prefix-based delete "should" catch files this
    test never actually created.
    """

    from app.models.session import DebateSession, SessionStatus
    from app.models.video_analysis import SessionMetric, VideoAnalysis
    from app.services import pipeline as pipeline_module

    user = make_user("cascade@test")
    c = client_for(user)
    sid = _create(c)["id"]
    assert _put_signals(c, sid, data=simple_track(sid, duration_s=6.0)).status_code == 200

    prefix = f"users/{user.id}/sessions/{sid}/"
    session_dir = tmp_path / sid
    session_dir.mkdir()
    (session_dir / "analysis.json").write_text(json.dumps({
        "total_duration": 6.0,
        "speech_segments": [{"start": 0.0, "end": 6.0, "duration": 6.0}],
    }), encoding="utf-8")
    (session_dir / "transcription.json").write_text(json.dumps({
        "segments": [{"start": 0.0, "end": 6.0, "text": "A short point.", "words": [
            {"word": w, "start": i * 0.4, "end": i * 0.4 + 0.3} for i, w in enumerate(["A", "short", "point."])
        ]}],
    }), encoding="utf-8")
    (session_dir / "raw_metrics.json").write_text(json.dumps({"fillers": {"instances": []}}), encoding="utf-8")
    (session_dir / "speech_content.json").write_text(json.dumps({
        "segments": [{"id": "au_01", "type": "conclusion", "start": 0.0, "end": 6.0, "segment_ids": ["s_000"], "summary": "Wraps up."}],
    }), encoding="utf-8")

    debate_session = db.query(DebateSession).filter_by(id=uuid.UUID(sid)).one()
    debate_session.status = SessionStatus.analyzing_speech
    db.commit()

    video_result = pipeline_module._run_video_analysis(
        db=db, debate_session=debate_session, session_directory=session_dir, user_id=user.id,
    )
    assert video_result is not None, "the pipeline hook must have actually run and produced a result"

    pipeline_module._run_visual_coaching(
        db=db, debate_session=debate_session, session_directory=session_dir, user_id=user.id,
        video_result=video_result, api_client=_FakeCoachingClient(), on_queued=None,
    )

    # Confirm all three artifacts and both row sets genuinely exist
    # before deleting -- otherwise the post-delete assertions below
    # would trivially pass with nothing to actually remove.
    video_row = db.get(VideoAnalysis, uuid.UUID(sid))
    assert video_row is not None
    assert video_row.result_key is not None
    assert video_row.feedback_key is not None
    assert f"{prefix}visual_signals.json.gz" in fake_storage.blobs
    assert video_row.result_key in fake_storage.blobs
    assert video_row.feedback_key in fake_storage.blobs
    assert db.query(SessionMetric).filter_by(session_id=uuid.UUID(sid)).count() == 11
    blobs_before = {k for k in fake_storage.blobs if k.startswith(prefix)}
    assert len(blobs_before) == 3

    r = c.delete(f"/v1/sessions/{sid}")
    assert r.status_code == 204
    db.expire_all()

    assert not any(k.startswith(prefix) for k in fake_storage.blobs)
    assert db.get(VideoAnalysis, uuid.UUID(sid)) is None
    assert db.query(SessionMetric).filter_by(session_id=uuid.UUID(sid)).count() == 0
