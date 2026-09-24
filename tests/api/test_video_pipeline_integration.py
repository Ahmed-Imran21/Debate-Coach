"""
§5.7: the pipeline hook (app/services/pipeline._run_video_analysis)
that turns an uploaded VisualSignalTrack into a stored
VideoAnalysisResult and SessionMetric rows, in the middle of the
existing session pipeline. Calls the hook function directly against
the fake-storage/SQLite harness in tests/api/conftest.py, rather
than going through the full audio pipeline (which needs real
Whisper/VAD calls) or a background job (which fake_jobs stubs out).

Every test takes app_module first among its fixtures (matching
conftest.py's own client_for fixture): it sets
GOOGLE_APPLICATION_CREDENTIALS before anything imports
app.services.storage, which constructs its client at import time.
A module-level `from app.services import pipeline import ...` would
run at collection time, before any fixture -- so those imports are
local to each test body instead, done only after app_module (and
fake_storage's monkeypatches) have already been resolved.
"""

import json

import pytest

from visual_analysis.schema import VisualSignalTrack

from tests.visual_analysis.synthetic import add_frames, base_track, still_hands


def _svc():
    from app.models.session import DebateSession, SessionStatus
    from app.models.video_analysis import SessionMetric, VideoAnalysis
    from app.services import pipeline as pipeline_module
    from app.services import visual_signals

    return DebateSession, SessionStatus, VideoAnalysis, SessionMetric, pipeline_module, visual_signals


def _make_session(db, user):
    DebateSession, SessionStatus, *_ = _svc()
    session = DebateSession(user_id=user.id, status=SessionStatus.analyzing_speech)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _write_analysis_json(tmp_path, session_id: str, *, total_duration: float, speech_segments: list[dict]):
    session_dir = tmp_path / session_id
    session_dir.mkdir()
    (session_dir / "analysis.json").write_text(
        json.dumps({"total_duration": total_duration, "speech_segments": speech_segments}),
        encoding="utf-8",
    )
    return session_dir


def _store_clean_track(user_id, session_id, duration_s: float = 6.0) -> str:
    _, _, _, _, _, visual_signals = _svc()
    data = base_track(session_id=str(session_id), duration_s=duration_s)
    lh, rh = still_hands()
    add_frames(data, end_s=duration_s + 0.1, yaw=0.0, pitch=0.0, lh=lh, rh=rh)
    track = VisualSignalTrack.model_validate(data)
    return visual_signals.store_track(user_id, session_id, track)


def test_happy_path_processes_and_stores_everything(app_module, db, fake_storage, video_flag, make_user, tmp_path):
    _, _, VideoAnalysis, SessionMetric, pipeline_module, _ = _svc()
    user = make_user("visual-pipeline@test.com")
    session = _make_session(db, user)

    key = _store_clean_track(user.id, session.id, duration_s=6.0)
    video_row = VideoAnalysis(session_id=session.id, user_id=user.id, status="received", signal_track_key=key)
    db.add(video_row)
    db.commit()

    session_dir = _write_analysis_json(
        tmp_path, str(session.id),
        total_duration=6.0,
        speech_segments=[{"start": 0.0, "end": 6.0, "duration": 6.0}],
    )

    pipeline_module._run_video_analysis(db=db, debate_session=session, session_directory=session_dir, user_id=user.id)

    db.refresh(video_row)
    assert video_row.status == "processed"
    assert video_row.processing_started_at is not None
    assert video_row.result_key is not None
    assert video_row.schema_version is not None
    assert video_row.metrics_version is not None
    assert video_row.platform == "web"
    assert video_row.quality["face_tracked_ratio"] == pytest.approx(1.0, abs=1e-6)

    stored = json.loads(fake_storage.blobs[video_row.result_key])
    assert stored["status"] == "complete"  # the result's own vocabulary, distinct from the DB row's "processed"
    assert len(stored["metrics"]) == 11

    metric_rows = db.query(SessionMetric).filter_by(session_id=session.id).all()
    assert len(metric_rows) == 11
    assert {r.metric_key for r in metric_rows} == set(stored["metrics"].keys())
    assert all(r.platform == "web" for r in metric_rows)
    face_tracked_row = next(r for r in metric_rows if r.metric_key == "face_tracked_ratio")
    assert face_tracked_row.status == "ok"
    assert face_tracked_row.value == pytest.approx(1.0, abs=1e-6)


def test_skips_when_flag_disabled(app_module, db, fake_storage, video_flag, make_user, tmp_path):
    _, _, VideoAnalysis, _, pipeline_module, _ = _svc()
    video_flag(False)
    user = make_user("flag-off@test.com")
    session = _make_session(db, user)
    key = _store_clean_track(user.id, session.id)
    video_row = VideoAnalysis(session_id=session.id, user_id=user.id, status="received", signal_track_key=key)
    db.add(video_row)
    db.commit()

    session_dir = _write_analysis_json(tmp_path, str(session.id), total_duration=6.0, speech_segments=[])
    pipeline_module._run_video_analysis(db=db, debate_session=session, session_directory=session_dir, user_id=user.id)

    db.refresh(video_row)
    assert video_row.status == "received"
    assert video_row.result_key is None


def test_skips_when_no_video_row(app_module, db, fake_storage, video_flag, make_user, tmp_path):
    _, _, VideoAnalysis, _, pipeline_module, _ = _svc()
    user = make_user("no-row@test.com")
    session = _make_session(db, user)
    session_dir = _write_analysis_json(tmp_path, str(session.id), total_duration=6.0, speech_segments=[])

    # Must not raise for a session with no video_analyses row at all.
    pipeline_module._run_video_analysis(db=db, debate_session=session, session_directory=session_dir, user_id=user.id)

    assert db.query(VideoAnalysis).filter_by(session_id=session.id).first() is None


def test_skips_when_status_is_not_received(app_module, db, fake_storage, video_flag, make_user, tmp_path):
    _, _, VideoAnalysis, _, pipeline_module, _ = _svc()
    user = make_user("awaiting@test.com")
    session = _make_session(db, user)
    video_row = VideoAnalysis(session_id=session.id, user_id=user.id, status="awaiting_upload")
    db.add(video_row)
    db.commit()

    session_dir = _write_analysis_json(tmp_path, str(session.id), total_duration=6.0, speech_segments=[])
    pipeline_module._run_video_analysis(db=db, debate_session=session, session_directory=session_dir, user_id=user.id)

    db.refresh(video_row)
    assert video_row.status == "awaiting_upload"


def test_duration_mismatch_marks_unavailable(app_module, db, fake_storage, video_flag, make_user, tmp_path):
    _, _, VideoAnalysis, SessionMetric, pipeline_module, _ = _svc()
    user = make_user("mismatch@test.com")
    session = _make_session(db, user)
    key = _store_clean_track(user.id, session.id, duration_s=6.0)  # track clock says 6.0s
    video_row = VideoAnalysis(session_id=session.id, user_id=user.id, status="received", signal_track_key=key)
    db.add(video_row)
    db.commit()

    # Audio says 60s -- far outside the duration tolerance.
    session_dir = _write_analysis_json(
        tmp_path, str(session.id),
        total_duration=60.0,
        speech_segments=[{"start": 0.0, "end": 60.0, "duration": 60.0}],
    )
    pipeline_module._run_video_analysis(db=db, debate_session=session, session_directory=session_dir, user_id=user.id)

    db.refresh(video_row)
    assert video_row.status == "unavailable"
    assert video_row.unavailable_reason == "duration_mismatch"
    assert video_row.result_key is None
    assert db.query(SessionMetric).filter_by(session_id=session.id).count() == 0


def test_exception_marks_failed_without_raising(app_module, db, fake_storage, video_flag, make_user, tmp_path):
    _, _, VideoAnalysis, _, pipeline_module, _ = _svc()
    user = make_user("broken@test.com")
    session = _make_session(db, user)
    # Points at a key nothing was ever stored under.
    video_row = VideoAnalysis(session_id=session.id, user_id=user.id, status="received", signal_track_key="does/not/exist.json.gz")
    db.add(video_row)
    db.commit()

    session_dir = _write_analysis_json(tmp_path, str(session.id), total_duration=6.0, speech_segments=[])

    # Must not raise -- visual analysis is best-effort.
    pipeline_module._run_video_analysis(db=db, debate_session=session, session_directory=session_dir, user_id=user.id)

    db.refresh(video_row)
    assert video_row.status == "failed"
