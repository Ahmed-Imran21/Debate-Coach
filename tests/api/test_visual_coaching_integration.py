"""
§7.1: the pipeline hook (app/services/pipeline._run_visual_coaching)
that runs after the existing coaching stage. Chains it with
_run_video_analysis (§5.7, already covered end-to-end in
test_video_pipeline_integration.py) for a realistic sequence, using
a fake LLM client passed directly as the api_client argument rather
than monkeypatching anything network-shaped.

Same app_module-first fixture ordering and lazy-import pattern as
test_video_pipeline_integration.py -- see that file's module
docstring for why.
"""

import json

from visual_analysis.schema import VisualSignalTrack

from tests.visual_analysis.synthetic import add_frames, base_track, still_hands


def _svc():
    from app.models.session import DebateSession, SessionStatus
    from app.models.video_analysis import VideoAnalysis
    from app.services import pipeline as pipeline_module
    from app.services import visual_signals

    return DebateSession, SessionStatus, VideoAnalysis, pipeline_module, visual_signals


def _make_session(db, user):
    DebateSession, SessionStatus, *_ = _svc()
    session = DebateSession(user_id=user.id, status=SessionStatus.analyzing_speech)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _store_clean_track(user_id, session_id, duration_s: float = 6.0) -> str:
    _, _, _, _, visual_signals = _svc()
    data = base_track(session_id=str(session_id), duration_s=duration_s)
    lh, rh = still_hands()
    add_frames(data, end_s=duration_s + 0.1, yaw=0.0, pitch=0.0, lh=lh, rh=rh)
    track = VisualSignalTrack.model_validate(data)
    return visual_signals.store_track(user_id, session_id, track)


def _write_session_files(tmp_path, session_id: str, *, total_duration: float = 6.0):
    session_dir = tmp_path / session_id
    session_dir.mkdir()

    (session_dir / "analysis.json").write_text(json.dumps({
        "total_duration": total_duration,
        "speech_segments": [{"start": 0.0, "end": total_duration, "duration": total_duration}],
    }), encoding="utf-8")

    (session_dir / "transcription.json").write_text(json.dumps({
        "segments": [{
            "start": 0.0, "end": total_duration, "text": "This is my point.",
            "words": [{"word": w, "start": i * 0.5, "end": i * 0.5 + 0.4} for i, w in enumerate(["This", "is", "my", "point."])],
        }],
    }), encoding="utf-8")

    (session_dir / "raw_metrics.json").write_text(json.dumps({"fillers": {"instances": []}}), encoding="utf-8")

    (session_dir / "speech_content.json").write_text(json.dumps({
        "segments": [{"id": "au_01", "type": "conclusion", "start": 0.0, "end": total_duration, "segment_ids": ["s_000"], "summary": "Wraps up the point."}],
    }), encoding="utf-8")

    return session_dir


class _FakeResponse:
    def __init__(self, content: str):
        self.success = True
        self.content = content
        self.error = None


class FakeAPIClient:
    VALID_ITEM = {
        "id": "vf_1", "category": "gaze", "polarity": "improve",
        "moment_id": None, "metric_keys": [], "observation_ids": [],
        "coaching": "Try to look at the lens a bit more while you speak.",
    }

    def generate(self, **kwargs):
        return _FakeResponse(json.dumps({"visual_feedback": [self.VALID_ITEM], "summary": "Solid effort with room to grow."}))


def test_full_chain_video_analysis_then_visual_coaching(app_module, db, fake_storage, video_flag, make_user, tmp_path):
    _, _, VideoAnalysis, pipeline_module, _ = _svc()
    user = make_user("chain@test.com")
    session = _make_session(db, user)

    key = _store_clean_track(user.id, session.id, duration_s=6.0)
    video_row = VideoAnalysis(session_id=session.id, user_id=user.id, status="received", signal_track_key=key)
    db.add(video_row)
    db.commit()

    session_dir = _write_session_files(tmp_path, str(session.id), total_duration=6.0)

    video_result = pipeline_module._run_video_analysis(db=db, debate_session=session, session_directory=session_dir, user_id=user.id)
    assert video_result is not None
    db.refresh(video_row)
    assert video_row.status == "processed"

    pipeline_module._run_visual_coaching(
        db=db, debate_session=session, session_directory=session_dir, user_id=user.id,
        video_result=video_result, api_client=FakeAPIClient(), on_queued=None,
    )

    db.refresh(video_row)
    assert video_row.coaching_status == "completed"
    assert video_row.feedback_key is not None

    stored = json.loads(fake_storage.blobs[video_row.feedback_key])
    assert stored["visual_feedback"][0]["id"] == "vf_1"
    assert stored["summary"] == "Solid effort with room to grow."
    assert stored["validation"] == {"retried": False, "dropped_items": 0}


def test_skips_when_video_result_is_none(app_module, db, fake_storage, video_flag, make_user, tmp_path):
    _, _, VideoAnalysis, pipeline_module, _ = _svc()
    user = make_user("no-result@test.com")
    session = _make_session(db, user)
    video_row = VideoAnalysis(session_id=session.id, user_id=user.id, status="processed")
    db.add(video_row)
    db.commit()

    session_dir = _write_session_files(tmp_path, str(session.id))
    pipeline_module._run_visual_coaching(
        db=db, debate_session=session, session_directory=session_dir, user_id=user.id,
        video_result=None, api_client=FakeAPIClient(), on_queued=None,
    )

    db.refresh(video_row)
    assert video_row.coaching_status == "not_requested"  # untouched


def test_skips_when_status_is_not_processed_or_partial(app_module, db, fake_storage, video_flag, make_user, tmp_path):
    _, _, VideoAnalysis, pipeline_module, _ = _svc()
    user = make_user("insufficient@test.com")
    session = _make_session(db, user)
    video_row = VideoAnalysis(session_id=session.id, user_id=user.id, status="insufficient_data")
    db.add(video_row)
    db.commit()

    session_dir = _write_session_files(tmp_path, str(session.id))
    pipeline_module._run_visual_coaching(
        db=db, debate_session=session, session_directory=session_dir, user_id=user.id,
        video_result={"status": "insufficient_data"}, api_client=FakeAPIClient(), on_queued=None,
    )

    db.refresh(video_row)
    assert video_row.coaching_status == "not_requested"


def test_missing_local_artifact_marks_failed_without_raising(app_module, db, fake_storage, video_flag, make_user, tmp_path):
    _, _, VideoAnalysis, pipeline_module, _ = _svc()
    user = make_user("broken-files@test.com")
    session = _make_session(db, user)
    video_row = VideoAnalysis(session_id=session.id, user_id=user.id, status="processed")
    db.add(video_row)
    db.commit()

    session_dir = tmp_path / str(session.id)
    session_dir.mkdir()  # no artifact files written at all

    pipeline_module._run_visual_coaching(
        db=db, debate_session=session, session_directory=session_dir, user_id=user.id,
        video_result={"status": "processed"}, api_client=FakeAPIClient(), on_queued=None,
    )

    db.refresh(video_row)
    assert video_row.coaching_status == "failed"
    assert video_row.feedback_key is None
