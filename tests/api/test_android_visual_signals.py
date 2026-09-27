"""
The Android app (android/) uploads the same VisualSignalTrack as the
website, with source.platform "android". The backend accepts it
unchanged and runs it through the same pipeline; nothing else about
the track differs.
"""

import gzip
import json
import uuid

import pytest

from visual_analysis.schema import VisualSignalTrack

from tests.visual_analysis.synthetic import simple_track


def android_track(session_id, **kwargs):
    data = simple_track(session_id, **kwargs)
    data["source"]["platform"] = "android"
    data["source"]["user_agent_family"] = "other"
    data["source"]["client_version"] = "android-1.0.0"
    return data


def test_the_schema_accepts_android_and_still_refuses_unknown_platforms():
    assert VisualSignalTrack.model_validate(android_track("s")).source.platform == "android"
    assert VisualSignalTrack.model_validate(simple_track("s")).source.platform == "web"
    for bad in ("ios", "Android", "", None):
        data = android_track("s")
        data["source"]["platform"] = bad
        with pytest.raises(Exception):
            VisualSignalTrack.model_validate(data)


def test_an_android_track_uploads_and_starts_like_a_web_one(client_for, make_user, fake_storage, fake_jobs, db):
    from app.models.video_analysis import VideoAnalysis

    user = make_user("a@test")
    c = client_for(user)
    r = c.post("/v1/sessions", json={"content_type": "audio/mp4", "title": "phone", "video_analysis": "requested"})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert r.json()["upload_headers"]["Content-Type"] == "audio/mp4"

    body = gzip.compress(json.dumps(android_track(sid)).encode())
    r = c.put(f"/v1/sessions/{sid}/visual-signals", content=body,
              headers={"Content-Type": "application/json", "Content-Encoding": "gzip"})
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "received", "frames": 100}

    row = db.query(VideoAnalysis).filter_by(session_id=uuid.UUID(sid)).one()
    assert row.platform == "android"

    fake_storage.sizes[f"users/{user.id}/sessions/{sid}/upload.m4a"] = 1000
    r = c.post(f"/v1/sessions/{sid}/start", json={"video": {"status": "uploaded"}})
    assert r.status_code == 202, r.text
    assert r.json()["video_analysis_status"] == "received"
