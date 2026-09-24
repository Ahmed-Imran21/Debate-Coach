"""§5.6: result assembly (visual_analysis/pipeline.py)."""

import json

import pytest

from visual_analysis import config
from visual_analysis.pipeline import run_pipeline
from visual_analysis.schema import VisualSignalTrack

from .synthetic import add_frames, base_track, speech_segments, still_hands


def _track(data: dict) -> VisualSignalTrack:
    return VisualSignalTrack.model_validate(data)


def _full_coverage_data(duration_s: float = 10.0) -> dict:
    data = base_track(duration_s=duration_s)
    lh, rh = still_hands()
    add_frames(data, end_s=duration_s + 0.1, yaw=0.0, pitch=0.0, lh=lh, rh=rh)
    return data


def test_full_coverage_is_complete_and_json_serializable():
    result = run_pipeline(_track(_full_coverage_data(10.0)), speech_segments((0.0, 10.0)))

    assert result.status == "complete"
    assert result.unavailable_reason is None
    assert result.schema == config.RESULT_SCHEMA
    assert result.schema_version == config.RESULT_SCHEMA_VERSION
    assert result.metrics_version == config.METRICS_VERSION
    assert result.session_id == "s-test"
    assert len(result.metrics) == 11
    assert isinstance(result.metrics, dict)

    d = result.to_dict()
    assert "duration_s" not in d  # internal-only field, not part of the wire shape
    encoded = json.dumps(d)
    decoded = json.loads(encoded)
    assert decoded["status"] == "complete"


def test_source_summary_reflects_the_track():
    result = run_pipeline(_track(_full_coverage_data(10.0)), speech_segments((0.0, 10.0)))
    assert result.source_summary == {
        "platform": "web",
        "runtime_version": "1.0.1",
        "delegate": "GPU",
        "device_tier": "full",
    }


def test_quality_summary_fields():
    result = run_pipeline(_track(_full_coverage_data(10.0)), speech_segments((0.0, 10.0)))
    q = result.quality

    assert q["analyzed_duration_s"] == pytest.approx(10.1, abs=1e-6)  # inclusive-both-ends grid, same as speaking below
    assert q["speaking_duration_s"] == pytest.approx(10.1, abs=1e-6)  # inclusive-both-ends speaking mask
    assert q["face_tracked_ratio"] == pytest.approx(1.0, abs=1e-6)
    assert q["hands_visible_ratio"] == {"any": pytest.approx(1.0), "left": pytest.approx(1.0), "right": pytest.approx(1.0)}
    assert q["effective_fps"]["face_median"] > 8.0
    assert q["effective_fps"]["hands_median"] > 8.0
    assert q["second_person_ratio"] == pytest.approx(0.0, abs=1e-6)
    assert q["calibration"] == {"performed": True, "stability": pytest.approx(0.91), "right_hand_check": "passed"}
    assert q["context"] == {"setting": "camera_audience", "uses_notes": False}
    assert q["clock_uncertainty_ms"] == 150
    assert q["warnings"] == []


def test_partial_when_only_one_modality_clears_its_gate():
    data = base_track(duration_s=10.0)
    add_frames(data, start_s=0.0, end_s=10.1, face=True, hands_ran=False, yaw=0.0, pitch=0.0)
    result = run_pipeline(_track(data), speech_segments((0.0, 10.0)))
    assert result.status == "partial"


def test_fully_gapped_track_is_partial_not_insufficient():
    # face_tracked_ratio/hands_visible_ratio are ungated and compute
    # to a real 0.0 here (a measured fact -- audio speech timing is
    # independent of a video gap), so they're "ok" even though every
    # gated metric downstream is "insufficient_coverage". Per the
    # literal spec rule ("insufficient_data if none are ok"), that
    # makes this "partial", not "insufficient_data".
    data = _full_coverage_data(5.0)
    data["gaps"] = [{"start": 0.0, "end": 5.0, "reason": "camera_interrupted"}]
    result = run_pipeline(_track(data), speech_segments((0.0, 5.0)))
    assert result.status == "partial"
    assert result.metrics["face_tracked_ratio"]["value"] == pytest.approx(0.0, abs=1e-6)
    assert result.metrics["camera_facing_ratio"]["status"] == "insufficient_coverage"


def test_insufficient_data_for_zero_speaking_time():
    result = run_pipeline(_track(_full_coverage_data(5.0)), [])
    assert result.status == "insufficient_data"


def test_series_uniform_for_a_clean_still_session():
    result = run_pipeline(_track(_full_coverage_data(10.0)), speech_segments((0.0, 10.0)))
    series = result.series

    assert series["resolution_s"] == config.SERIES_RESOLUTION_S
    expected_bins = 10  # arange(0, 10.0, 1.0)
    assert len(series["camera_facing"]) == expected_bins
    assert len(series["hand_activity"]) == expected_bins
    assert len(series["head_motion"]) == expected_bins

    assert all(v == pytest.approx(1.0, abs=1e-6) for v in series["camera_facing"])
    assert all(v == pytest.approx(0.0, abs=1e-6) for v in series["hand_activity"])
    assert all(v == pytest.approx(0.0, abs=1e-6) for v in series["head_motion"])


def test_series_null_when_no_face_in_a_bin():
    data = base_track(duration_s=5.0)
    add_frames(data, start_s=0.0, end_s=5.1, face=False, hands_ran=False)
    result = run_pipeline(_track(data), speech_segments((0.0, 5.0)))
    assert all(v is None for v in result.series["camera_facing"])
    assert all(v is None for v in result.series["hand_activity"])
    assert all(v is None for v in result.series["head_motion"])


def test_warnings_face_often_out_of_frame_not_hands():
    data = base_track(duration_s=10.0)
    lh, rh = still_hands()
    add_frames(data, start_s=0.0, end_s=2.0, face=True, lh=lh, rh=rh)
    add_frames(data, start_s=2.0, end_s=10.1, face=False, lh=lh, rh=rh)
    result = run_pipeline(_track(data), speech_segments((0.0, 10.0)))
    assert "face_often_out_of_frame" in result.quality["warnings"]
    assert "hands_mostly_out_of_frame" not in result.quality["warnings"]


def test_warnings_calibration_skipped_vs_unstable():
    skipped_data = _full_coverage_data(5.0)
    skipped_data["calibration"] = {
        "performed": False, "baseline": None, "samples": 0,
        "stability": 0.0, "right_hand_check": "skipped",
    }
    skipped = run_pipeline(_track(skipped_data), speech_segments((0.0, 5.0)))
    assert "calibration_skipped" in skipped.quality["warnings"]
    assert "calibration_unstable" not in skipped.quality["warnings"]

    unstable_data = _full_coverage_data(5.0)
    unstable_data["calibration"]["stability"] = 0.2
    unstable = run_pipeline(_track(unstable_data), speech_segments((0.0, 5.0)))
    assert "calibration_unstable" in unstable.quality["warnings"]
    assert "calibration_skipped" not in unstable.quality["warnings"]


def test_warnings_context_degradation_and_clock_uncertainty():
    data = _full_coverage_data(5.0)
    data["context"] = {"setting": "in_room_practice", "uses_notes": True}
    data["clock"]["uncertainty_ms"] = 500
    data["degradations"] = [{"t": 1.0, "face_fps": 3.0, "hands_fps": 0.0, "reason": "manual"}]
    result = run_pipeline(_track(data), speech_segments((0.0, 5.0)))

    assert "in_room_context" in result.quality["warnings"]
    assert "high_clock_uncertainty" in result.quality["warnings"]
    assert "analysis_degraded" in result.quality["warnings"]


def test_warnings_second_person_detected():
    data = base_track(duration_s=10.0)
    lh, rh = still_hands()
    add_frames(data, start_s=0.0, end_s=2.0, face_count=2, lh=lh, rh=rh)
    add_frames(data, start_s=2.0, end_s=10.1, face_count=1, lh=lh, rh=rh)
    result = run_pipeline(_track(data), speech_segments((0.0, 10.0)))
    assert "second_person_detected" in result.quality["warnings"]
