"""
Schema + §3.3 validation: a valid synthetic track is accepted,
and every rejection rule fires individually with a stable code.
"""

import pytest

from visual_analysis import config
from visual_analysis.schema import VisualSignalTrack
from visual_analysis.signals import (
    SignalValidationError,
    check_duration,
    validate_track,
)

from .synthetic import clone, simple_track


def _parse(data: dict) -> VisualSignalTrack:
    return VisualSignalTrack.model_validate(data)


def _reject(data: dict, code: str, session_id: str = "s-test") -> None:
    with pytest.raises(SignalValidationError) as info:
        validate_track(_parse(data), session_id)
    assert info.value.code == code, info.value


def test_valid_track_is_accepted():
    data = simple_track()
    track = _parse(data)
    validate_track(track, "s-test")
    assert track.frame_count == 100
    assert track.schema_ == "debatecoach.visual_signals"


def test_extra_fields_are_rejected_by_schema():
    data = simple_track()
    data["frames"]["surprise"] = [1] * 100
    with pytest.raises(Exception):
        _parse(data)


def test_unsupported_schema_and_version():
    data = simple_track()
    data["schema"] = "other"
    _reject(data, "unsupported_schema")

    data = simple_track()
    data["schema_version"] = "0.9"
    _reject(data, "unsupported_schema_version")


def test_session_id_mismatch():
    _reject(simple_track("someone-else"), "session_mismatch")


def test_column_length_mismatch():
    data = simple_track()
    data["frames"]["head_yaw"].append(0.0)
    _reject(data, "column_length_mismatch")


def test_time_must_be_strictly_increasing_and_non_negative():
    data = simple_track()
    data["frames"]["t"][5] = data["frames"]["t"][4]
    _reject(data, "time_not_increasing")

    data = simple_track()
    data["frames"]["t"][0] = -0.1
    _reject(data, "negative_time")


def test_time_past_duration():
    data = simple_track(duration_s=10.0)
    data["frames"]["t"][-1] = 10.0 + config.T_PAST_DURATION_TOLERANCE_S + 0.01
    _reject(data, "time_past_duration")

    # exactly at the tolerance is fine
    data = simple_track(duration_s=10.0)
    data["frames"]["t"][-1] = 10.0 + config.T_PAST_DURATION_TOLERANCE_S
    validate_track(_parse(data), "s-test")


def test_too_many_frames(monkeypatch):
    monkeypatch.setattr(config, "MAX_FRAMES", 50)
    _reject(simple_track(), "too_many_frames")


@pytest.mark.parametrize(
    "column,bad",
    [
        ("head_yaw", 180.1),
        ("head_pitch", -180.1),
        ("head_roll", 999.0),
        ("iris_x", 1.51),
        ("iris_y", -1.51),
        ("face_scale", 1.01),
        ("face_cx", 1.11),
        ("face_cy", -0.11),
        ("lh_score", 1.01),
        ("rh_cx", 1.2),
        ("face_count", 3),
        ("lh_present", 2),
        ("rh_present", -1),
        ("infer_ms", -1.0),
    ],
)
def test_value_out_of_range(column, bad):
    data = simple_track()
    data["frames"][column][10] = bad
    _reject(data, "value_out_of_range")


def test_nulls_are_allowed_everywhere_except_t():
    data = simple_track()
    for key, col in data["frames"].items():
        if key != "t":
            col[3] = None
    validate_track(_parse(data), "s-test")


def test_gap_end_before_start():
    data = simple_track()
    data["gaps"] = [{"start": 5.0, "end": 4.0, "reason": "tab_hidden"}]
    _reject(data, "invalid_gap")


def test_duration_check_uses_max_of_abs_and_fraction():
    track = _parse(simple_track(duration_s=100.0))
    # tolerance = max(3.0, 2.0) = 3.0
    assert check_duration(track, 103.0) is None
    assert check_duration(track, 103.1) == "duration_mismatch"

    track = _parse(simple_track(duration_s=1000.0))
    # tolerance = max(3.0, 20.0) = 20.0
    assert check_duration(track, 1019.0) is None
    assert check_duration(track, 1021.0) == "duration_mismatch"

    assert check_duration(track, None) is None


def test_clone_does_not_share_state():
    a = simple_track()
    b = clone(a)
    b["frames"]["t"][0] = 99.0
    assert a["frames"]["t"][0] != 99.0
