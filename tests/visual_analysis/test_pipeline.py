"""§5.6: result assembly (visual_analysis/pipeline.py)."""

import json

import pytest

from visual_analysis import config
from visual_analysis.pipeline import run_pipeline
from visual_analysis.schema import VisualSignalTrack

from .synthetic import add_frames, base_track, speech_segments, still_hands


def _track(data: dict) -> VisualSignalTrack:
    return VisualSignalTrack.model_validate(data)


def test_full_coverage_is_processed_and_json_serializable():
    data = base_track(duration_s=10.0)
    lh, rh = still_hands()
    add_frames(data, end_s=10.1, yaw=0.0, pitch=0.0, lh=lh, rh=rh)
    result = run_pipeline(_track(data), speech_segments((0.0, 10.0)))

    assert result.status == "processed"
    assert result.schema == config.RESULT_SCHEMA
    assert result.schema_version == config.RESULT_SCHEMA_VERSION
    assert result.metrics_version == config.METRICS_VERSION
    assert result.session_id == "s-test"
    assert len(result.metrics) == 11
    assert result.duration_s == pytest.approx(10.0, abs=1e-6)

    # round-trips cleanly through JSON -- no stray numpy scalar types.
    encoded = json.dumps(result.to_dict())
    decoded = json.loads(encoded)
    assert decoded["status"] == "processed"


def test_quality_summary_reflects_calibration_and_coverage():
    data = base_track(duration_s=10.0)
    lh, rh = still_hands()
    add_frames(data, end_s=10.1, yaw=0.0, pitch=0.0, lh=lh, rh=rh)
    result = run_pipeline(_track(data), speech_segments((0.0, 10.0)))

    q = result.quality
    assert q["calibration_performed"] is True
    assert q["facing_confidence_low"] is False
    assert q["face_coverage"] == pytest.approx(1.0, abs=1e-6)
    assert q["hand_coverage"] == pytest.approx(1.0, abs=1e-6)
    assert q["scale_ref"] == pytest.approx(0.09, abs=1e-6)
    assert q["frame_count"] == len(data["frames"]["t"])


def test_partial_when_only_one_modality_has_coverage():
    data = base_track(duration_s=10.0)
    add_frames(data, start_s=0.0, end_s=10.1, face=True, hands_ran=False, yaw=0.0, pitch=0.0)
    result = run_pipeline(_track(data), speech_segments((0.0, 10.0)))
    assert result.status == "partial"


def test_insufficient_data_for_a_fully_gapped_track():
    data = base_track(duration_s=5.0)
    lh, rh = still_hands()
    add_frames(data, end_s=5.1, lh=lh, rh=rh)
    data["gaps"] = [{"start": 0.0, "end": 5.0, "reason": "camera_interrupted"}]
    result = run_pipeline(_track(data), speech_segments((0.0, 5.0)))
    assert result.status == "insufficient_data"


def test_series_is_downsampled_to_series_resolution():
    data = base_track(duration_s=10.0)
    lh, rh = still_hands()
    add_frames(data, end_s=10.1, yaw=0.0, pitch=0.0, lh=lh, rh=rh)
    result = run_pipeline(_track(data), speech_segments((0.0, 10.0)))

    # 10s of session at SERIES_RESOLUTION_S=1.0 -> 11 points (0..10 inclusive).
    expected_points = int(10.0 / config.SERIES_RESOLUTION_S) + 1
    assert len(result.series) == expected_points
    assert [p["t"] for p in result.series] == [pytest.approx(float(i)) for i in range(expected_points)]
    assert all(p["speaking"] is True for p in result.series)
    assert all(p["facing"] is True for p in result.series)


def test_series_marks_facing_null_when_face_not_visible():
    data = base_track(duration_s=5.0)
    add_frames(data, start_s=0.0, end_s=5.1, face=False, hands_ran=False)
    result = run_pipeline(_track(data), speech_segments((0.0, 5.0)))
    assert all(p["facing"] is None for p in result.series)
