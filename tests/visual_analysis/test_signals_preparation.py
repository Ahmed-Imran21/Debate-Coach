"""
§5.2-5.3: grid construction, interpolation gap-gating, nearest-
sample presence, gap masking, smoothing edge behaviour, and the
derived per-grid-point series (face_ok, facing, head_ang_speed,
hand_speed).
"""

import numpy as np
import pytest

from visual_analysis import config
from visual_analysis.schema import VisualSignalTrack
from visual_analysis.signals import (
    _build_grid,
    _interpolate_column,
    _nearest_column,
    _smooth,
    effective_fps_in_window,
    prepare_signals,
)

from .synthetic import add_frames, base_track, oscillating, speech_segments, still_hands, visual_strong


def _track(data: dict) -> VisualSignalTrack:
    return VisualSignalTrack.model_validate(data)


# ---------------------------------------------------------------
# Grid
# ---------------------------------------------------------------

def test_grid_spacing_and_count():
    grid = _build_grid(10.0, config.GRID_HZ)
    assert grid[0] == 0.0
    assert grid[-1] == pytest.approx(10.0)
    assert len(grid) == 101
    assert np.allclose(np.diff(grid), 1.0 / config.GRID_HZ)


def test_grid_single_point_for_zero_duration():
    grid = _build_grid(0.0, config.GRID_HZ)
    assert list(grid) == [0.0]


# ---------------------------------------------------------------
# Interpolation
# ---------------------------------------------------------------

def test_interpolate_fills_gaps_up_to_tolerance():
    grid = np.array([0.0, 1.0, 2.0])
    raw_t = np.array([0.0, 2.0])  # 2s gap, well over MAX_INTERP_GAP_S
    raw_v = np.array([0.0, 20.0])
    out = _interpolate_column(grid, raw_t, raw_v, max_gap_s=config.MAX_INTERP_GAP_S)
    assert np.isnan(out[1])  # gap too wide to bridge

    raw_t2 = np.array([0.0, 0.2])  # within MAX_INTERP_GAP_S (0.3)
    raw_v2 = np.array([0.0, 2.0])
    grid2 = np.array([0.0, 0.1, 0.2])
    out2 = _interpolate_column(grid2, raw_t2, raw_v2, max_gap_s=config.MAX_INTERP_GAP_S)
    assert out2[1] == pytest.approx(1.0)  # linear midpoint


def test_interpolate_nan_outside_data_range():
    raw_t = np.array([1.0, 2.0])
    raw_v = np.array([10.0, 20.0])
    grid = np.array([0.0, 1.5, 3.0])
    out = _interpolate_column(grid, raw_t, raw_v, max_gap_s=1.0)
    assert np.isnan(out[0])
    assert out[1] == pytest.approx(15.0)
    assert np.isnan(out[2])


def test_interpolate_empty_and_single_sample():
    grid = np.array([0.0, 1.0])
    assert np.all(np.isnan(_interpolate_column(grid, np.array([]), np.array([]), 1.0)))

    out = _interpolate_column(grid, np.array([0.0]), np.array([5.0]), 1.0)
    assert out[0] == 5.0
    assert np.isnan(out[1])


# ---------------------------------------------------------------
# Nearest-sample (presence columns)
# ---------------------------------------------------------------

def test_nearest_within_tolerance():
    raw_t = np.array([0.0, 1.0])
    raw_v = np.array([1.0, 0.0])
    grid = np.array([0.0, 0.1, 0.5, 0.9, 1.0])
    out = _nearest_column(grid, raw_t, raw_v, tolerance_s=config.PRESENCE_NEAREST_S)
    assert out[0] == 1.0    # exact match
    assert out[1] == 1.0    # 0.1s away, within 0.15
    assert np.isnan(out[2])  # 0.5s away from both, too far
    assert out[3] == 0.0    # 0.1s from raw_t[1]
    assert out[4] == 0.0


# ---------------------------------------------------------------
# Smoothing: NaN propagation and edge handling
# ---------------------------------------------------------------

def test_smooth_median_then_mean_of_constant_series():
    x = np.full(10, 5.0)
    assert np.allclose(_smooth(x), 5.0)


def test_smooth_single_nan_spreads_to_neighbours_but_not_further():
    # index 4 is NaN; median pass nulls 3,4,5 (any window touching
    # index 4); mean pass then nulls one point further each side.
    x = np.array([1.0, 1.0, 1.0, 1.0, np.nan, 1.0, 1.0, 1.0, 1.0])
    out = _smooth(x)
    nan_positions = set(np.where(np.isnan(out))[0].tolist())
    assert nan_positions == {2, 3, 4, 5, 6}
    assert out[0] == pytest.approx(1.0)
    assert out[1] == pytest.approx(1.0)
    assert out[7] == pytest.approx(1.0)
    assert out[8] == pytest.approx(1.0)


def test_smooth_edge_points_use_a_real_2point_window_not_padding():
    # No NaN anywhere; edges must NOT be forced NaN by a phantom
    # out-of-bounds neighbour.
    x = np.array([2.0, 4.0, 6.0, 8.0])
    out = _smooth(x)
    assert not np.any(np.isnan(out))


def test_smooth_rejects_a_single_outlier_via_the_median_pass():
    x = np.array([1.0, 1.0, 1.0, 9.0, 1.0, 1.0, 1.0])
    out = _smooth(x)
    # median(1,9,1) = 1 at the spike's own position -> no NaN, and
    # the spike should not visibly propagate into neighbours.
    assert out[3] == pytest.approx(1.0)
    assert np.allclose(out, 1.0)


# ---------------------------------------------------------------
# prepare_signals: face_ok / facing
# ---------------------------------------------------------------

def test_face_ok_true_when_face_and_head_pose_present():
    track = _track(visual_strong(duration_s=5.0))
    p = prepare_signals(track, speech_segments((0.0, 5.0)))
    # allow the documented edge-of-data NaN at the very first/last grid point
    assert p.face_ok[5:-5].all()


def test_face_ok_false_without_a_face():
    data = base_track(duration_s=5.0)
    add_frames(data, face=False, hands_ran=False)
    track = _track(data)
    p = prepare_signals(track, speech_segments((0.0, 5.0)))
    assert not p.face_ok.any()


def test_facing_true_within_cone_false_outside_it():
    data = base_track(duration_s=5.0)
    lh, rh = still_hands()
    add_frames(data, yaw=config.FACING_YAW_DEG + 5.0, pitch=0.0, lh=lh, rh=rh)
    track = _track(data)
    p = prepare_signals(track, speech_segments((0.0, 5.0)))
    assert p.face_ok[10:-10].all()
    assert not p.facing[10:-10].any()


def test_facing_uses_calibration_baseline_not_zero():
    data = base_track(duration_s=5.0)
    data["calibration"] = {
        "performed": True,
        "baseline": {"head_yaw": 20.0, "head_pitch": 0.0, "iris_x": 0.0, "iris_y": 0.0},
        "samples": 20,
        "stability": 0.9,
        "right_hand_check": "passed",
    }
    lh, rh = still_hands()
    add_frames(data, yaw=20.0, pitch=0.0, lh=lh, rh=rh)  # at baseline, not at 0
    track = _track(data)
    p = prepare_signals(track, speech_segments((0.0, 5.0)))
    assert p.facing[10:-10].all()


def test_no_calibration_uses_median_pitch_as_baseline():
    data = base_track(duration_s=5.0)
    data["calibration"] = {
        "performed": False, "baseline": None, "samples": 0, "stability": 0.0, "right_hand_check": "skipped",
    }
    lh, rh = still_hands()
    add_frames(data, yaw=0.0, pitch=-8.0, lh=lh, rh=rh)  # constant pitch, becomes its own baseline
    track = _track(data)
    p = prepare_signals(track, speech_segments((0.0, 5.0)))
    assert p.facing_confidence_low is True
    assert p.facing[10:-10].all()  # every point equals the median, so within FACING_PITCH_DEG of it


# ---------------------------------------------------------------
# head_ang_speed
# ---------------------------------------------------------------

def test_head_ang_speed_of_a_constant_ramp():
    data = base_track(duration_s=5.0)
    lh, rh = still_hands()
    rate_deg_per_s = 30.0
    add_frames(data, yaw=lambda t: rate_deg_per_s * t, pitch=0.0, lh=lh, rh=rh)
    track = _track(data)
    p = prepare_signals(track, speech_segments((0.0, 5.0)))
    # away from both data edges and smoothing edges
    mid = slice(15, -15)
    assert np.nanmean(p.head_ang_speed[mid]) == pytest.approx(rate_deg_per_s, rel=0.05)


def test_head_ang_speed_zero_when_still():
    track = _track(visual_strong(duration_s=5.0))
    p = prepare_signals(track, speech_segments((0.0, 5.0)))
    assert np.nanmax(np.abs(p.head_ang_speed[5:-5])) < 1e-6


# ---------------------------------------------------------------
# hand_speed
# ---------------------------------------------------------------

def test_hand_speed_zero_for_still_hands():
    track = _track(visual_strong(duration_s=5.0))
    p = prepare_signals(track, speech_segments((0.0, 5.0)))
    assert np.nanmax(p.hand_speed[5:-5]) < 1e-6


def test_hand_speed_positive_for_moving_hand_and_uses_max_of_both():
    data = base_track(duration_s=4.0)
    moving_rh = oscillating(center=(0.65, 0.7), amplitude=0.05, hz=1.0)
    still_lh = lambda t: (0.35, 0.7)  # noqa: E731
    add_frames(data, lh=still_lh, rh=moving_rh)
    track = _track(data)
    p = prepare_signals(track, speech_segments((0.0, 4.0)))

    mid = slice(10, -10)
    assert np.nanmean(p.rh_speed[mid]) > 0.5
    assert np.nanmean(p.lh_speed[mid]) < 1e-6
    # hand_speed is the max of the two -> tracks the moving hand
    assert np.allclose(
        np.nan_to_num(p.hand_speed[mid]),
        np.nan_to_num(p.rh_speed[mid]),
        atol=1e-9,
    )


def test_hand_speed_nan_without_a_usable_scale_ref():
    data = base_track(duration_s=3.0)
    add_frames(data, face=False, hands_ran=False)  # no face at all -> no scale_ref
    track = _track(data)
    p = prepare_signals(track, speech_segments((0.0, 3.0)))
    assert p.scale_ref is None
    assert np.all(np.isnan(p.hand_speed))


# ---------------------------------------------------------------
# Gaps mask everything, including otherwise-valid interpolation
# ---------------------------------------------------------------

def test_gap_masks_values_that_would_otherwise_interpolate():
    data = base_track(duration_s=5.0)
    lh, rh = still_hands()
    add_frames(data, yaw=0.0, pitch=0.0, lh=lh, rh=rh)
    data["gaps"] = [{"start": 2.0, "end": 3.0, "reason": "tab_hidden"}]
    track = _track(data)
    p = prepare_signals(track, speech_segments((0.0, 5.0)))

    inside = (p.grid_t >= 2.0) & (p.grid_t <= 3.0)
    assert np.all(np.isnan(p.head_yaw[inside]))
    assert not p.face_ok[inside].any()


# ---------------------------------------------------------------
# scale_ref: median during speech only
# ---------------------------------------------------------------

def test_scale_ref_uses_only_speaking_time():
    data = base_track(duration_s=6.0)
    lh, rh = still_hands()

    def scale(t: float) -> float:
        return 0.20 if t < 3.0 else 0.08  # first half "too close", second half normal

    f = data["frames"]
    add_frames(data, end_s=3.0, yaw=0.0, pitch=0.0, face_scale=0.20, lh=lh, rh=rh)
    add_frames(data, start_s=3.0, end_s=6.0, yaw=0.0, pitch=0.0, face_scale=0.08, lh=lh, rh=rh)
    track = _track(data)

    # Speaking only in the second half -> scale_ref should reflect
    # only the 0.08 samples, not the 0.20 ones.
    p = prepare_signals(track, speech_segments((3.0, 6.0)))
    assert p.scale_ref == pytest.approx(0.08, abs=1e-6)


# ---------------------------------------------------------------
# effective_fps_in_window
# ---------------------------------------------------------------

def test_effective_fps_in_window_matches_a_steady_rate():
    raw_t = np.arange(0, 10, 0.1)  # 10 fps
    ran = np.ones_like(raw_t, dtype=bool)
    fps = effective_fps_in_window(raw_t, ran, 2.0, 8.0)
    assert fps == pytest.approx(10.0, abs=1.0)


def test_effective_fps_in_window_sub_second_uses_rate_fallback():
    raw_t = np.array([0.0, 0.05, 0.10, 0.15])
    ran = np.ones_like(raw_t, dtype=bool)
    fps = effective_fps_in_window(raw_t, ran, 0.0, 0.2)
    assert fps == pytest.approx(4 / 0.2)


def test_effective_fps_in_window_respects_ran_mask():
    raw_t = np.arange(0, 5, 0.1)
    ran = np.zeros_like(raw_t, dtype=bool)
    ran[::2] = True  # half the ticks "ran"
    fps = effective_fps_in_window(raw_t, ran, 0.0, 4.0)
    assert fps == pytest.approx(5.0, abs=1.0)
