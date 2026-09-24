"""
§5.5: the 11-row metrics table. Fixtures reuse the same
hand-derivable constructions as test_events.py (a calibrated/
uncalibrated 10s pitch drop, a single straight-line gesture ramp,
sustained second-person presence) so expected values come from
already-verified event boundaries, not eyeballing. Every fixture
pads its last add_frames call's end_s by one extra step (+0.1) so
raw sampling reaches the final grid point exactly -- see
test_events.py's hands_still fixture for why that matters.
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


def _run(data: dict, duration_s: float, device_tier: str = "full") -> dict:
    track = _track(data)
    p = prepare_signals(track, speech_segments((0.0, duration_s)))
    return compute_metrics(p, detect_events(p, track.degradations), device_tier)


# ---------------------------------------------------------------
# Full coverage: face and hands visible for the whole track
# ---------------------------------------------------------------

def test_full_coverage_is_complete_and_high_confidence():
    data = base_track(duration_s=10.0)
    lh, rh = still_hands()
    add_frames(data, end_s=10.1, yaw=0.0, pitch=0.0, lh=lh, rh=rh)
    metrics = _run(data, 10.0)

    assert metrics["face_tracked_ratio"]["value"] == pytest.approx(1.0, abs=1e-6)
    assert metrics["face_tracked_ratio"]["status"] == "ok"
    assert metrics["face_tracked_ratio"]["confidence"] == "high"

    assert metrics["camera_facing_ratio"]["value"] == pytest.approx(1.0, abs=1e-6)
    assert metrics["camera_facing_ratio"]["coverage"] == pytest.approx(1.0, abs=1e-6)
    assert metrics["camera_facing_ratio"]["confidence"] == "high"

    assert metrics["gaze_away_events_per_min"]["value"] == pytest.approx(0.0, abs=1e-6)
    assert metrics["longest_gaze_away_s"]["value"] == pytest.approx(0.0, abs=1e-6)
    assert metrics["head_down_ratio"]["value"] == pytest.approx(0.0, abs=1e-6)
    assert metrics["head_motion_median_deg_s"]["value"] == pytest.approx(0.0, abs=1e-6)

    assert metrics["hands_visible_ratio"]["value"] == pytest.approx(1.0, abs=1e-6)
    assert metrics["gesture_rate_per_min"]["value"] == pytest.approx(0.0, abs=1e-6)

    amplitude = metrics["gesture_amplitude_median"]
    assert amplitude["status"] == "ok"
    assert amplitude["value"] is None
    assert amplitude["note"] == "no_gestures"

    # still hands from t=0.1 (index 0's speed is always NaN) to t=10.0.
    assert metrics["hands_still_longest_s"]["value"] == pytest.approx(9.9, abs=1e-6)
    assert metrics["hands_still_ratio"]["value"] == pytest.approx(round(100 / 101, config.ROUND_RATIO), abs=1e-9)

    for key in ("face_tracked_ratio", "camera_facing_ratio", "hands_visible_ratio", "hands_still_ratio"):
        assert metrics[key]["status"] == "ok"


# ---------------------------------------------------------------
# camera_facing_ratio / gaze_away_* / head_down_ratio
# ---------------------------------------------------------------
#
# Same [5.0, 15.0] pitch drop as test_events.py: the smoothed
# head_down run is 5.1..14.9 (99 of 201 grid points), the smoothed
# gaze_away run is 5.0..15.0 (101 of 201 points, since facing's
# 12deg threshold is looser than head_down's 15deg and still catches
# the two blended boundary points ~-13.33deg). face never drops out.

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


def test_facing_and_head_down_metrics_calibrated():
    metrics = _run(_pitch_drop_data(20.0, calibrated=True), 20.0)

    facing = metrics["camera_facing_ratio"]
    assert facing["value"] == pytest.approx(round(100 / 201, config.ROUND_RATIO), abs=1e-9)
    assert facing["confidence"] == "high"

    rate = metrics["gaze_away_events_per_min"]
    speaking_minutes = 201 / config.GRID_HZ / 60.0
    assert rate["value"] == pytest.approx(round(1 / speaking_minutes, config.ROUND_RATE), abs=1e-6)
    assert rate["confidence"] == "high"

    longest = metrics["longest_gaze_away_s"]
    assert longest["value"] == pytest.approx(10.0, abs=1e-6)

    # [5.1, 14.9] inclusive at 0.1 spacing is 99 points, not 98 --
    # (14.9-5.1)/0.1 + 1, the "+1" for the inclusive endpoint.
    head_down = metrics["head_down_ratio"]
    assert head_down["value"] == pytest.approx(round(99 / 201, config.ROUND_RATIO), abs=1e-9)
    assert head_down["confidence"] == "high"

    assert metrics["head_motion_median_deg_s"]["value"] == pytest.approx(0.0, abs=1e-6)


def test_facing_derived_confidence_drops_to_medium_when_uncalibrated_head_down_unaffected():
    # Same [5,15] drop in a 40s track (a minority of the session),
    # so the uncalibrated median-pitch fallback baseline still lands
    # on exactly 0.0 -- same underlying event boundaries as the
    # calibrated case, only confidence differs.
    metrics = _run(_pitch_drop_data(40.0, calibrated=False), 40.0)

    # Coverage and fps are still excellent, so the compound "high"
    # condition's calibration clause is the only thing failing --
    # that drops it to "medium" (coverage >= CONF_MEDIUM_COVERAGE),
    # not all the way to "low".
    assert metrics["camera_facing_ratio"]["confidence"] == "medium"
    assert metrics["gaze_away_events_per_min"]["confidence"] == "medium"
    assert metrics["longest_gaze_away_s"]["confidence"] == "medium"

    # head_down isn't built from the facing cone, so it's unaffected.
    assert metrics["head_down_ratio"]["confidence"] == "high"


def test_face_gated_metrics_insufficient_coverage_below_face_coverage_min():
    data = base_track(duration_s=10.0)
    lh, rh = still_hands()
    add_frames(data, start_s=0.0, end_s=2.0, face=True, lh=lh, rh=rh)
    add_frames(data, start_s=2.0, end_s=10.1, face=False, lh=lh, rh=rh)
    metrics = _run(data, 10.0)

    assert metrics["face_tracked_ratio"]["value"] < config.FACE_COVERAGE_MIN
    assert metrics["face_tracked_ratio"]["status"] == "ok"  # ungated -- it IS the coverage figure

    for key in ("camera_facing_ratio", "gaze_away_events_per_min", "longest_gaze_away_s", "head_down_ratio", "head_motion_median_deg_s"):
        m = metrics[key]
        assert m["status"] == "insufficient_coverage"
        assert m["value"] is None
        assert m["confidence"] is None


# ---------------------------------------------------------------
# gesture_rate_per_min / gesture_amplitude_median
# ---------------------------------------------------------------
#
# Same straight-line ramp as test_events.py's gesture test: one
# gesture event, peak_speed ~3.33 fs/s, amplitude ~2.89.

def _gesture_data(duration_s: float = 6.0) -> dict:
    data = base_track(duration_s=duration_s)
    lh_fn = lambda t: (0.35, 0.75)  # noqa: E731

    def rh_fn(t: float):
        if t < 2.0:
            return (0.35, 0.7)
        if t <= 3.0:
            return (0.35 + 0.3 * (t - 2.0), 0.7)
        return (0.65, 0.7)

    add_frames(data, end_s=duration_s + 0.1, lh=lh_fn, rh=rh_fn)
    return data


def test_gesture_metrics_exact():
    metrics = _run(_gesture_data(6.0), 6.0)

    # speaking mask is inclusive of both segment endpoints, so a
    # (0.0, 6.0) segment covers 61 grid points, all hand-visible.
    speaking_hands_minutes = 61 / config.GRID_HZ / 60.0
    rate = metrics["gesture_rate_per_min"]
    assert rate["value"] == pytest.approx(round(1 / speaking_hands_minutes, config.ROUND_RATE), abs=1e-2)
    assert rate["confidence"] == "high"

    amplitude = metrics["gesture_amplitude_median"]
    assert amplitude["status"] == "ok"
    assert amplitude["value"] == pytest.approx(2.89, abs=0.02)
    assert "note" not in amplitude or amplitude.get("note") is None


def test_hand_gated_metrics_insufficient_coverage_below_hands_coverage_min():
    data = base_track(duration_s=10.0)
    add_frames(data, start_s=0.0, end_s=1.0, hands_ran=True, lh=lambda t: (0.35, 0.7), rh=lambda t: (0.65, 0.7))
    add_frames(data, start_s=1.0, end_s=10.1, hands_ran=False)
    metrics = _run(data, 10.0)

    assert metrics["hands_visible_ratio"]["value"] < config.HANDS_COVERAGE_MIN
    for key in ("gesture_rate_per_min", "gesture_amplitude_median", "hands_still_longest_s", "hands_still_ratio"):
        m = metrics[key]
        assert m["status"] == "insufficient_coverage"
        assert m["value"] is None


def test_hand_behavior_metrics_not_measured_without_a_usable_scale_ref():
    # Hands clear the coverage gate (visible the whole time) but the
    # face -- needed for scale_ref -- never appears, so gesture/
    # hands_still can't be converted to face_scale units at all.
    data = base_track(duration_s=6.0)
    lh, rh = still_hands()
    add_frames(data, end_s=6.1, face=False, lh=lh, rh=rh)
    metrics = _run(data, 6.0)

    assert metrics["hands_visible_ratio"]["value"] == pytest.approx(1.0, abs=1e-6)
    assert metrics["hands_visible_ratio"]["status"] == "ok"

    for key in ("gesture_rate_per_min", "gesture_amplitude_median", "hands_still_longest_s", "hands_still_ratio"):
        m = metrics[key]
        assert m["status"] == "not_measured"
        assert m["value"] is None


def test_hand_metrics_disabled_by_tier_for_face_only_device():
    data = _gesture_data(6.0)  # would otherwise show real gesture activity
    metrics = _run(data, 6.0, device_tier="face_only")

    assert metrics["hands_visible_ratio"]["status"] == "disabled_by_tier"
    for key in ("gesture_rate_per_min", "gesture_amplitude_median", "hands_still_longest_s", "hands_still_ratio"):
        m = metrics[key]
        assert m["status"] == "disabled_by_tier"
        assert m["value"] is None
        assert m["confidence"] is None

    # Face metrics are untouched by a hand-side tier restriction.
    assert metrics["face_tracked_ratio"]["status"] == "ok"


# ---------------------------------------------------------------
# Second-person confidence cap (applies to every metric, not a
# second_person metric of its own -- there isn't one in this table)
# ---------------------------------------------------------------

def test_second_person_caps_every_confidence_at_low():
    data = base_track(duration_s=10.0)
    lh, rh = still_hands()
    add_frames(data, start_s=0.0, end_s=2.0, face_count=2, lh=lh, rh=rh)
    add_frames(data, start_s=2.0, end_s=10.1, face_count=1, lh=lh, rh=rh)
    metrics = _run(data, 10.0)

    # Second person for 2.0 of 10.0s speaking = 20%, well over
    # SECOND_PERSON_LOW_CONF_RATIO (10%).
    for key, m in metrics.items():
        if m["confidence"] is not None:
            assert m["confidence"] == "low", key


# ---------------------------------------------------------------
# Zero speaking time
# ---------------------------------------------------------------

def test_zero_speaking_time_metrics_not_measured():
    data = base_track(duration_s=5.0)
    lh, rh = still_hands()
    add_frames(data, end_s=5.1, lh=lh, rh=rh)
    track = _track(data)
    p = prepare_signals(track, [])  # no speech segments at all
    metrics = compute_metrics(p, detect_events(p, track.degradations), "full")

    assert metrics["face_tracked_ratio"]["status"] == "not_measured"
    assert metrics["hands_visible_ratio"]["status"] == "not_measured"
