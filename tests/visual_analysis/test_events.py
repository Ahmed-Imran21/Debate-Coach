"""
§5.4: event detection over PreparedSignals.

Several fixtures below are built so their expected event boundaries
can be derived by hand (not just eyeballed), the same way
test_signals_preparation.py works through grid/interpolation math
exactly. Two mechanisms matter for that derivation:

  - head_pitch/head_yaw/hand positions go through smoothing
    (median-3 then mean-3) before events.py ever sees them. For a
    step function (still -> dropped -> still), the median pass is a
    no-op (the transition isn't a single-point outlier) but the mean
    pass blends the single grid point at each edge toward the other
    side, in effect shrinking a threshold-crossing run by one grid
    point (0.1s) at each end relative to the raw step. For a
    continuous piecewise-linear ramp (gesture test), the same mean
    pass blends only the two kink points, not the interior.
  - face_count/lh_present/rh_present are nearest-sampled, never
    smoothed, so runs built from them (face_lost, second_person)
    match the raw step exactly with no edge shrinkage.
"""

import pytest

from visual_analysis import config
from visual_analysis.events import detect_events
from visual_analysis.schema import Degradation, VisualSignalTrack
from visual_analysis.signals import prepare_signals

from .synthetic import add_frames, base_track, speech_segments, still_hands, visual_strong


def _track(data: dict) -> VisualSignalTrack:
    return VisualSignalTrack.model_validate(data)


def _by_type(events: list[dict], type_: str) -> list[dict]:
    return [e for e in events if e["type"] == type_]


# ---------------------------------------------------------------
# head_down / gaze_away: a single 10s pitch drop, calibrated
# ---------------------------------------------------------------
#
# duration 20s, pitch -20 (delta -20 from a baseline of 0) for
# t in [5.0, 15.0] inclusive, else 0. See module docstring for why
# the smoothed head_down run ends up 5.1..14.9 (9.8s) while the
# smoothed gaze_away run (threshold 12, not 15) ends up 5.0..15.0
# (10.0s exactly): the two blended boundary points (~-13.33) clear
# the looser facing-cone threshold but not the stricter head-down
# one.

def _pitch_drop_track(duration_s: float) -> dict:
    data = base_track(duration_s=duration_s)
    lh, rh = still_hands()

    def pitch(t: float) -> float:
        return -20.0 if 5.0 <= t <= 15.0 else 0.0

    add_frames(data, pitch=pitch, lh=lh, rh=rh)
    return data


def test_head_down_and_gaze_away_exact_boundaries_calibrated():
    track = _track(_pitch_drop_track(20.0))
    p = prepare_signals(track, speech_segments((0.0, 20.0)))
    events = detect_events(p)

    head_down = _by_type(events, "head_down")
    assert len(head_down) == 1
    assert head_down[0]["start"] == pytest.approx(5.1, abs=1e-6)
    assert head_down[0]["end"] == pytest.approx(14.9, abs=1e-6)
    assert head_down[0]["confidence"] == "high"

    gaze_away = _by_type(events, "gaze_away")
    assert len(gaze_away) == 1
    assert gaze_away[0]["start"] == pytest.approx(5.0, abs=1e-6)
    assert gaze_away[0]["end"] == pytest.approx(15.0, abs=1e-6)
    assert gaze_away[0]["confidence"] == "high"
    assert gaze_away[0]["attributes"]["direction"] == "down"

    # gaze_away starts earlier (5.0 vs 5.1) -> gets the lower id,
    # regardless of what other event types (e.g. hands_still, which
    # also fires over this whole still-handed fixture) sort before it.
    ordered = [e for e in events if e["type"] in ("gaze_away", "head_down")]
    assert ordered[0]["type"] == "gaze_away"
    assert ordered[1]["type"] == "head_down"
    assert int(ordered[0]["id"].split("_")[1]) < int(ordered[1]["id"].split("_")[1])

    # ids are sequential across *all* detected events, not just these two.
    assert [e["id"] for e in events] == [f"ve_{i:04d}" for i in range(1, len(events) + 1)]


def test_gaze_away_and_head_down_low_confidence_only_for_gaze_away_when_uncalibrated():
    # Same [5,15] drop, but embedded in a 40s track so the drop is
    # a small minority of the session: the uncalibrated fallback
    # baseline (median pitch over the whole session) still lands on
    # exactly 0.0, so the boundary math above holds unchanged here.
    data = _pitch_drop_track(40.0)
    data["calibration"] = {"performed": False, "baseline": None, "samples": 0, "stability": 0.0, "right_hand_check": "skipped"}
    track = _track(data)
    p = prepare_signals(track, speech_segments((0.0, 40.0)))
    assert p.baseline_pitch == pytest.approx(0.0, abs=1e-6)
    assert p.facing_confidence_low is True

    events = detect_events(p)

    gaze_away = _by_type(events, "gaze_away")
    assert len(gaze_away) == 1
    assert gaze_away[0]["confidence"] == "low"

    head_down = _by_type(events, "head_down")
    assert len(head_down) == 1
    assert head_down[0]["confidence"] != "low"  # head_down is not camera-facing-derived


def test_gaze_away_below_minimum_duration_does_not_fire():
    data = base_track(duration_s=10.0)
    lh, rh = still_hands()

    def pitch(t: float) -> float:
        return -20.0 if 5.0 <= t <= 5.5 else 0.0  # ~0.5s raw, well under GAZE_AWAY_MIN_S

    add_frames(data, pitch=pitch, lh=lh, rh=rh)
    track = _track(data)
    p = prepare_signals(track, speech_segments((0.0, 10.0)))
    assert _by_type(detect_events(p), "gaze_away") == []


def test_gaze_away_bridges_a_short_facing_blip_but_not_a_long_one():
    # Two 1.0s not-facing stretches (each below GAZE_AWAY_MIN_S on
    # its own) with a brief facing blip between them.
    def make(blip_s: float) -> dict:
        data = base_track(duration_s=10.0)
        lh, rh = still_hands()

        def pitch(t: float) -> float:
            if 2.0 <= t < 3.0:
                return -20.0
            if 3.0 <= t < 3.0 + blip_s:
                return 0.0
            if 3.0 + blip_s <= t < 4.0 + blip_s:
                return -20.0
            return 0.0

        add_frames(data, pitch=pitch, lh=lh, rh=rh)
        return data

    bridged = _track(make(0.1))  # < FACING_BRIDGE_S (0.3)
    p_bridged = prepare_signals(bridged, speech_segments((0.0, 10.0)))
    assert len(_by_type(detect_events(p_bridged), "gaze_away")) == 1

    not_bridged = _track(make(0.5))  # > FACING_BRIDGE_S
    p_not_bridged = prepare_signals(not_bridged, speech_segments((0.0, 10.0)))
    assert _by_type(detect_events(p_not_bridged), "gaze_away") == []


# ---------------------------------------------------------------
# gesture
# ---------------------------------------------------------------
#
# rh moves in a straight line 0.35 -> 0.65 (cx) over exactly 1.0s
# [2.0, 3.0], held still before/after; lh stays still throughout.
# A linear ramp is unaffected by the median-3 pass anywhere, and by
# the mean-3 pass everywhere except its two kink points (t=2.0 and
# t=3.0), which get blended toward the flat side. That shrinks the
# above-threshold run to grid points 2.1..3.0 (see inline numbers).

def _gesture_track() -> dict:
    data = base_track(duration_s=6.0)
    lh_fn = lambda t: (0.35, 0.75)  # noqa: E731

    def rh_fn(t: float):
        if t < 2.0:
            return (0.35, 0.7)
        if t <= 3.0:
            return (0.35 + 0.3 * (t - 2.0), 0.7)
        return (0.65, 0.7)

    add_frames(data, lh=lh_fn, rh=rh_fn)
    return data


def test_gesture_exact_single_ramp():
    track = _track(_gesture_track())
    p = prepare_signals(track, speech_segments((0.0, 6.0)))
    events = detect_events(p)

    gesture = _by_type(events, "gesture")
    assert len(gesture) == 1
    ev = gesture[0]
    assert ev["start"] == pytest.approx(2.1, abs=1e-6)
    assert ev["end"] == pytest.approx(3.0, abs=1e-6)
    assert ev["attributes"]["hands"] == "right"
    assert ev["attributes"]["peak_speed"] == pytest.approx(3.33, abs=0.02)
    assert ev["attributes"]["amplitude"] == pytest.approx(2.89, abs=0.02)
    assert ev["confidence"] == "high"


def test_no_gesture_events_for_still_hands():
    track = _track(visual_strong(duration_s=6.0))
    p = prepare_signals(track, speech_segments((0.0, 6.0)))
    assert _by_type(detect_events(p), "gesture") == []


def _piecewise_linear(breakpoints: list[tuple[float, float]]):
    """Flat before the first point and after the last; linear between
    consecutive points in between. Avoids hand-rolled conditionals
    that are easy to get subtly wrong at the resting values."""

    def fn(t: float) -> float:
        if t <= breakpoints[0][0]:
            return breakpoints[0][1]
        if t >= breakpoints[-1][0]:
            return breakpoints[-1][1]
        for (t0, v0), (t1, v1) in zip(breakpoints, breakpoints[1:]):
            if t0 <= t <= t1:
                return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
        return breakpoints[-1][1]

    return fn


def test_gesture_bridges_a_short_gap_between_two_bursts_but_not_a_long_one():
    def make(gap_s: float) -> dict:
        data = base_track(duration_s=8.0)
        lh_fn = lambda t: (0.35, 0.75)  # noqa: E731
        burst_len = 0.3
        b1_start, b1_end = 2.0, 2.0 + burst_len
        b2_start = b1_end + gap_s
        b2_end = b2_start + burst_len

        cx = _piecewise_linear([
            (b1_start, 0.35),
            (b1_end, 0.35 + 0.5 * burst_len),
            (b2_start, 0.35 + 0.5 * burst_len),
            (b2_end, 0.35 + 1.0 * burst_len),
        ])
        rh_fn = lambda t: (cx(t), 0.7)  # noqa: E731

        add_frames(data, lh=lh_fn, rh=rh_fn)
        return data

    bridged = _track(make(0.1))  # < GESTURE_MERGE_GAP_S (0.20)
    p_bridged = prepare_signals(bridged, speech_segments((0.0, 8.0)))
    assert len(_by_type(detect_events(p_bridged), "gesture")) == 1

    not_bridged = _track(make(0.6))  # > GESTURE_MERGE_GAP_S
    p_not_bridged = prepare_signals(not_bridged, speech_segments((0.0, 8.0)))
    assert len(_by_type(detect_events(p_not_bridged), "gesture")) == 2


# ---------------------------------------------------------------
# hands_still
# ---------------------------------------------------------------

def test_hands_still_exact_boundaries():
    data = base_track(duration_s=10.0)
    lh, rh = still_hands()
    add_frames(data, end_s=10.1, yaw=0.0, pitch=0.0, lh=lh, rh=rh)  # +1 step so raw t reaches 10.0
    track = _track(data)
    p = prepare_signals(track, speech_segments((0.0, 10.0)))
    events = detect_events(p)

    still = _by_type(events, "hands_still")
    assert len(still) == 1
    # index 0's speed is always NaN (no previous sample to diff
    # against), so the run starts one grid point in.
    assert still[0]["start"] == pytest.approx(0.1, abs=1e-6)
    assert still[0]["end"] == pytest.approx(10.0, abs=1e-6)
    assert still[0]["confidence"] == "high"


def test_hands_still_low_fps_confidence_medium():
    data = base_track(duration_s=5.0)
    lh, rh = still_hands()
    add_frames(data, fps=4.0, lh=lh, rh=rh)
    track = _track(data)
    p = prepare_signals(track, speech_segments((0.0, 5.0)))
    events = detect_events(p)

    still = _by_type(events, "hands_still")
    assert len(still) == 1
    assert still[0]["confidence"] == "medium"


def test_hands_still_below_minimum_duration_does_not_fire():
    track = _track(visual_strong(duration_s=1.0))
    p = prepare_signals(track, speech_segments((0.0, 1.0)))
    assert _by_type(detect_events(p), "hands_still") == []


# ---------------------------------------------------------------
# face_lost
# ---------------------------------------------------------------

def test_face_lost_exact_boundaries():
    data = base_track(duration_s=8.0)
    lh, rh = still_hands()
    add_frames(data, start_s=0.0, end_s=3.0, face=True, lh=lh, rh=rh)
    add_frames(data, start_s=3.0, end_s=6.0, face=False, lh=lh, rh=rh)
    add_frames(data, start_s=6.0, end_s=8.1, face=True, lh=lh, rh=rh)
    track = _track(data)
    p = prepare_signals(track, speech_segments((0.0, 8.0)))
    events = detect_events(p)

    lost = _by_type(events, "face_lost")
    assert len(lost) == 1
    assert lost[0]["start"] == pytest.approx(3.0, abs=1e-6)
    assert lost[0]["end"] == pytest.approx(5.9, abs=1e-6)


def test_face_lost_inside_a_recorded_gap_is_not_an_event():
    data = base_track(duration_s=8.0)
    lh, rh = still_hands()
    add_frames(data, start_s=0.0, end_s=3.0, face=True, lh=lh, rh=rh)
    add_frames(data, start_s=3.0, end_s=6.0, face=False, lh=lh, rh=rh)
    add_frames(data, start_s=6.0, end_s=8.1, face=True, lh=lh, rh=rh)
    data["gaps"] = [{"start": 3.0, "end": 5.9, "reason": "tab_hidden"}]
    track = _track(data)
    p = prepare_signals(track, speech_segments((0.0, 8.0)))
    assert _by_type(detect_events(p), "face_lost") == []


# ---------------------------------------------------------------
# second_person
# ---------------------------------------------------------------

def test_second_person_exact_boundaries():
    data = base_track(duration_s=5.0)
    lh, rh = still_hands()
    add_frames(data, start_s=0.0, end_s=2.0, face_count=1, lh=lh, rh=rh)
    add_frames(data, start_s=2.0, end_s=3.5, face_count=2, lh=lh, rh=rh)
    add_frames(data, start_s=3.5, end_s=5.1, face_count=1, lh=lh, rh=rh)
    track = _track(data)
    p = prepare_signals(track, speech_segments((0.0, 5.0)))
    events = detect_events(p)

    two = _by_type(events, "second_person")
    assert len(two) == 1
    assert two[0]["start"] == pytest.approx(2.0, abs=1e-6)
    assert two[0]["end"] == pytest.approx(3.4, abs=1e-6)


def test_second_person_below_minimum_duration_does_not_fire():
    data = base_track(duration_s=5.0)
    lh, rh = still_hands()
    add_frames(data, start_s=0.0, end_s=2.0, face_count=1, lh=lh, rh=rh)
    add_frames(data, start_s=2.0, end_s=2.3, face_count=2, lh=lh, rh=rh)
    add_frames(data, start_s=2.3, end_s=5.1, face_count=1, lh=lh, rh=rh)
    track = _track(data)
    p = prepare_signals(track, speech_segments((0.0, 5.0)))
    assert _by_type(detect_events(p), "second_person") == []


# ---------------------------------------------------------------
# analysis_degraded
# ---------------------------------------------------------------

def test_analysis_degraded_passthrough():
    track = _track(visual_strong(duration_s=5.0))
    p = prepare_signals(track, speech_segments((0.0, 5.0)))
    degradations = [
        Degradation(t=2.0, face_fps=3.0, hands_fps=0.0, reason="p90_latency"),
        Degradation(t=4.0, face_fps=1.0, hands_fps=0.0, reason="thermal_suspected"),
    ]
    events = detect_events(p, degradations)

    degraded = _by_type(events, "analysis_degraded")
    assert len(degraded) == 2
    assert degraded[0]["start"] == degraded[0]["end"] == pytest.approx(2.0)
    assert degraded[0]["attributes"] == {"face_fps": 3.0, "hands_fps": 0.0, "reason": "p90_latency"}
    assert degraded[1]["attributes"]["reason"] == "thermal_suspected"
    assert all(e["confidence"] == "medium" for e in degraded)


# ---------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------

def test_detect_events_empty_when_nothing_qualifies():
    track = _track(visual_strong(duration_s=3.0))  # too short for any MIN_S threshold
    p = prepare_signals(track, speech_segments((0.0, 3.0)))
    assert detect_events(p) == []


def test_event_ids_are_sequential_and_start_ordered_across_types():
    data = _pitch_drop_track(20.0)
    track = _track(data)
    p = prepare_signals(track, speech_segments((0.0, 20.0)))
    events = detect_events(p, [Degradation(t=1.0, face_fps=5.0, hands_fps=5.0, reason="manual")])

    assert [e["id"] for e in events] == [f"ve_{i:04d}" for i in range(1, len(events) + 1)]
    starts = [e["start"] for e in events]
    assert starts == sorted(starts)
