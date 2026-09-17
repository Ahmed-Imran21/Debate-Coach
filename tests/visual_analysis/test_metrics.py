"""
§5.5: per-session metrics computed from PreparedSignals + events.

Fixtures reuse the same hand-derivable constructions as
test_events.py (a calibrated/uncalibrated 10s pitch drop, a single
straight-line gesture ramp, sustained face/second-person presence)
so the expected metric values can be worked out from the same
already-verified event boundaries, not just eyeballed. All fixtures
pad their last add_frames call's end_s by one extra step (+0.1) so
raw sampling reaches the final grid point exactly — without that,
the interpolation range cuts off one raw-frame early and the
smoothing window bleeds NaN back into the second-to-last grid point
too (see test_events.py's hands_still fixture for the same issue).
"""

import pytest

from visual_analysis import config
from visual_analysis.events import detect_events
from visual_analysis.metrics import compute_metrics
from visual_analysis.schema import VisualSignalTrack
from visual_analysis.signals import prepare_signals

from .synthetic import add_frames, base_track, speech_segments, still_hands


def _track(data: dict) -> VisualSignalTrack:
    return VisualSignalTrack.model_validate(data)


def _by_key(metrics: list[dict], key: str) -> dict:
    return next(m for m in metrics if m["key"] == key)


def _run(data: dict, duration_s: float) -> list[dict]:
    track = _track(data)
    p = prepare_signals(track, speech_segments((0.0, duration_s)))
    return compute_metrics(p, detect_events(p))


# ---------------------------------------------------------------
# Full coverage: face and hands visible for the whole track
# ---------------------------------------------------------------

def test_full_coverage_metrics_are_one_and_high_confidence():
    data = base_track(duration_s=10.0)
    lh, rh = still_hands()
    add_frames(data, end_s=10.1, yaw=0.0, pitch=0.0, lh=lh, rh=rh)
    metrics = _run(data, 10.0)

    for key in ("analysis_coverage", "face_visibility", "hand_visibility"):
        m = _by_key(metrics, key)
        assert m["available"] is True
        assert m["value"] == pytest.approx(1.0, abs=1e-6)
        assert m["confidence"] == "high"


# ---------------------------------------------------------------
# camera_facing_ratio / gaze_away_time_ratio / head_down_time_ratio
# ---------------------------------------------------------------
#
# Same [5.0, 15.0] pitch drop as test_events.py: smoothed head_down
# run is 5.1..14.9 (98 of 201 grid points), smoothed gaze_away run
# is 5.0..15.0 (101 of 201 points, since facing's 12deg threshold
# is looser than head_down's 15deg and still catches the two
# blended boundary points). face never drops out, so n_face_ok=201.

def _pitch_drop_data(duration_s: float, *, calibrated: bool) -> dict:
    data = base_track(duration_s=duration_s)
    lh, rh = still_hands()

    def pitch(t: float) -> float:
        return -20.0 if 5.0 <= t <= 15.0 else 0.0

    add_frames(data, end_s=duration_s + 0.1, pitch=pitch, lh=lh, rh=rh)
    if not calibrated:
        data["calibration"] = {
            "performed": False, "baseline": None, "samples": 0,
            "stability": 0.0, "right_hand_check": "skipped",
        }
    return data


def test_facing_and_head_down_ratios_calibrated():
    metrics = _run(_pitch_drop_data(20.0, calibrated=True), 20.0)

    facing = _by_key(metrics, "camera_facing_ratio")
    assert facing["value"] == pytest.approx(round(100 / 201, config.ROUND_RATIO), abs=1e-9)
    assert facing["confidence"] == "high"

    gaze_away = _by_key(metrics, "gaze_away_time_ratio")
    assert gaze_away["value"] == pytest.approx(round(101 / 201, config.ROUND_RATIO), abs=1e-9)
    assert gaze_away["confidence"] == "high"

    # [5.1, 14.9] inclusive at 0.1 spacing is 99 points, not 98 --
    # (14.9-5.1)/0.1 + 1, the "+1" for the inclusive endpoint.
    head_down = _by_key(metrics, "head_down_time_ratio")
    assert head_down["value"] == pytest.approx(round(99 / 201, config.ROUND_RATIO), abs=1e-9)
    assert head_down["confidence"] == "high"


def test_facing_derived_ratios_low_confidence_when_uncalibrated_head_down_unaffected():
    # A 40s track (10s drop is a minority of the session) so the
    # uncalibrated median-pitch fallback baseline still lands on
    # 0.0, same as test_events.py's equivalent confidence test.
    metrics = _run(_pitch_drop_data(40.0, calibrated=False), 40.0)

    assert _by_key(metrics, "camera_facing_ratio")["confidence"] == "low"
    assert _by_key(metrics, "gaze_away_time_ratio")["confidence"] == "low"
    assert _by_key(metrics, "head_down_time_ratio")["confidence"] != "low"


def test_face_gated_ratios_unavailable_below_face_coverage_min():
    data = base_track(duration_s=10.0)
    lh, rh = still_hands()
    add_frames(data, start_s=0.0, end_s=2.0, face=True, lh=lh, rh=rh)
    add_frames(data, start_s=2.0, end_s=10.1, face=False, lh=lh, rh=rh)
    metrics = _run(data, 10.0)

    assert _by_key(metrics, "face_visibility")["value"] < config.FACE_COVERAGE_MIN
    assert _by_key(metrics, "face_visibility")["available"] is True

    for key in ("camera_facing_ratio", "gaze_away_time_ratio", "head_down_time_ratio"):
        m = _by_key(metrics, key)
        assert m["available"] is False
        assert m["unavailable_reason"] == "low_face_coverage"
        assert m["value"] is None


# ---------------------------------------------------------------
# gesture_rate / gesture_amplitude_avg
# ---------------------------------------------------------------
#
# Same straight-line ramp as test_events.py's gesture test: one
# gesture event, peak_speed ~3.33 fs/s, amplitude ~2.89.

def test_gesture_rate_and_amplitude_exact():
    data = base_track(duration_s=6.0)
    lh_fn = lambda t: (0.35, 0.75)  # noqa: E731

    def rh_fn(t: float):
        if t < 2.0:
            return (0.35, 0.7)
        if t <= 3.0:
            return (0.35 + 0.3 * (t - 2.0), 0.7)
        return (0.65, 0.7)

    add_frames(data, end_s=6.1, lh=lh_fn, rh=rh_fn)
    metrics = _run(data, 6.0)

    # speaking mask is inclusive of both segment endpoints, so a
    # (0.0, 6.0) segment covers 61 grid points = 6.1s, not 6.0s.
    expected_rate = 1 / (6.1 / 60.0)
    rate = _by_key(metrics, "gesture_rate")
    assert rate["available"] is True
    assert rate["value"] == pytest.approx(expected_rate, abs=0.01)
    assert rate["confidence"] == "high"

    amplitude = _by_key(metrics, "gesture_amplitude_avg")
    assert amplitude["available"] is True
    assert amplitude["value"] == pytest.approx(2.89, abs=0.02)


def test_gesture_rate_zero_but_amplitude_unavailable_for_still_hands():
    data = base_track(duration_s=6.0)
    lh, rh = still_hands()
    add_frames(data, end_s=6.1, lh=lh, rh=rh)
    metrics = _run(data, 6.0)

    rate = _by_key(metrics, "gesture_rate")
    assert rate["available"] is True
    assert rate["value"] == pytest.approx(0.0, abs=1e-9)

    amplitude = _by_key(metrics, "gesture_amplitude_avg")
    assert amplitude["available"] is False
    assert amplitude["unavailable_reason"] == "no_gesture_events"


def test_hand_gated_metrics_unavailable_below_hands_coverage_min():
    data = base_track(duration_s=10.0)
    add_frames(data, start_s=0.0, end_s=1.0, hands_ran=True, lh=lambda t: (0.35, 0.7), rh=lambda t: (0.65, 0.7))
    add_frames(data, start_s=1.0, end_s=10.1, hands_ran=False)
    metrics = _run(data, 10.0)

    assert _by_key(metrics, "hand_visibility")["value"] < config.HANDS_COVERAGE_MIN
    for key in ("gesture_rate", "gesture_amplitude_avg", "hands_still_time_ratio"):
        m = _by_key(metrics, key)
        assert m["available"] is False
        assert m["unavailable_reason"] == "low_hand_coverage"


# ---------------------------------------------------------------
# face_lost_count
# ---------------------------------------------------------------

def test_face_lost_count_exact():
    data = base_track(duration_s=8.0)
    lh, rh = still_hands()
    add_frames(data, start_s=0.0, end_s=3.0, face=True, lh=lh, rh=rh)
    add_frames(data, start_s=3.0, end_s=6.0, face=False, lh=lh, rh=rh)
    add_frames(data, start_s=6.0, end_s=8.1, face=True, lh=lh, rh=rh)
    metrics = _run(data, 8.0)

    count = _by_key(metrics, "face_lost_count")
    assert count["value"] == 1.0
    assert count["confidence"] == "high"
    assert count["available"] is True


# ---------------------------------------------------------------
# second_person_time_ratio
# ---------------------------------------------------------------

def test_second_person_ratio_high_confidence_for_a_substantial_presence():
    data = base_track(duration_s=5.0)
    lh, rh = still_hands()
    add_frames(data, start_s=0.0, end_s=2.0, face_count=1, lh=lh, rh=rh)
    add_frames(data, start_s=2.0, end_s=3.5, face_count=2, lh=lh, rh=rh)
    add_frames(data, start_s=3.5, end_s=5.1, face_count=1, lh=lh, rh=rh)
    metrics = _run(data, 5.0)

    ratio = _by_key(metrics, "second_person_time_ratio")
    assert ratio["value"] == pytest.approx(round(15 / 51, config.ROUND_RATIO), abs=1e-9)
    assert ratio["confidence"] == "high"


def test_second_person_ratio_low_confidence_for_a_small_blip():
    # Below SECOND_PERSON_EVENT_MIN_S, so this never becomes an
    # event at all -- but the metric counts raw face_count==2 grid
    # points regardless of whether they formed a qualifying event.
    data = base_track(duration_s=5.0)
    lh, rh = still_hands()
    add_frames(data, start_s=0.0, end_s=2.0, face_count=1, lh=lh, rh=rh)
    add_frames(data, start_s=2.0, end_s=2.3, face_count=2, lh=lh, rh=rh)
    add_frames(data, start_s=2.3, end_s=5.1, face_count=1, lh=lh, rh=rh)
    metrics = _run(data, 5.0)

    ratio = _by_key(metrics, "second_person_time_ratio")
    assert 0.0 < ratio["value"] < config.SECOND_PERSON_LOW_CONF_RATIO
    assert ratio["confidence"] == "low"


# ---------------------------------------------------------------
# Degenerate: nothing analyzed at all
# ---------------------------------------------------------------

def test_fully_gapped_track():
    data = base_track(duration_s=5.0)
    lh, rh = still_hands()
    add_frames(data, end_s=5.1, lh=lh, rh=rh)
    data["gaps"] = [{"start": 0.0, "end": 5.0, "reason": "camera_interrupted"}]
    metrics = _run(data, 5.0)

    coverage = _by_key(metrics, "analysis_coverage")
    assert coverage["available"] is True
    assert coverage["value"] == pytest.approx(0.0, abs=1e-6)

    for key in ("face_visibility", "hand_visibility"):
        m = _by_key(metrics, key)
        assert m["available"] is False
        assert m["unavailable_reason"] == "no_data"
