"""
Validation the Pydantic schema cannot express, plus cleaning and
resampling onto a uniform grid (§5.2-5.3). Pure: no I/O, no
logging of arrays.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from . import config
from .schema import FRAME_COLUMNS, VisualSignalTrack


@dataclass(frozen=True)
class SignalValidationError(ValueError):
    """A rejected track. `code` is stable and machine-readable."""

    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


_RANGES: dict[str, tuple[float, float]] = {
    "head_yaw": config.ANGLE_RANGE,
    "head_pitch": config.ANGLE_RANGE,
    "head_roll": config.ANGLE_RANGE,
    "iris_x": config.IRIS_RANGE,
    "iris_y": config.IRIS_RANGE,
    "face_scale": config.UNIT_RANGE,
    "face_cx": config.COORD_RANGE,
    "face_cy": config.COORD_RANGE,
    "lh_score": config.UNIT_RANGE,
    "lh_cx": config.COORD_RANGE,
    "lh_cy": config.COORD_RANGE,
    "rh_score": config.UNIT_RANGE,
    "rh_cx": config.COORD_RANGE,
    "rh_cy": config.COORD_RANGE,
}

_PRESENCE_VALUES = {0, 1}
_FACE_COUNT_VALUES = {0, 1, 2}


def validate_track(track: VisualSignalTrack, expected_session_id: str) -> None:
    """
    Raise SignalValidationError for anything in §3.3 that does
    not need the audio duration. Duration agreement is checked
    separately at analysis time (see check_duration).
    """

    if track.schema_ != config.SIGNAL_SCHEMA:
        raise SignalValidationError("unsupported_schema", f"schema {track.schema_!r} is not supported")

    if track.schema_version not in config.SUPPORTED_SIGNAL_SCHEMA_VERSIONS:
        raise SignalValidationError(
            "unsupported_schema_version",
            f"schema_version {track.schema_version!r} is not supported",
        )

    if track.session_id != expected_session_id:
        raise SignalValidationError("session_mismatch", "session_id does not match the session in the route")

    t = track.frames.t
    n = len(t)

    if n > config.MAX_FRAMES:
        raise SignalValidationError("too_many_frames", f"{n} rows exceeds the limit of {config.MAX_FRAMES}")

    for name in FRAME_COLUMNS:
        column = getattr(track.frames, name)
        if len(column) != n:
            raise SignalValidationError(
                "column_length_mismatch",
                f"frames.{name} has {len(column)} rows but frames.t has {n}",
            )

    for i, value in enumerate(t):
        if value < 0:
            raise SignalValidationError("negative_time", f"frames.t[{i}] is negative")
        if i > 0 and value <= t[i - 1]:
            raise SignalValidationError("time_not_increasing", f"frames.t[{i}] is not greater than frames.t[{i - 1}]")

    if n and t[-1] > track.clock.duration_s + config.T_PAST_DURATION_TOLERANCE_S:
        raise SignalValidationError(
            "time_past_duration",
            f"frames.t ends at {t[-1]} but clock.duration_s is {track.clock.duration_s}",
        )

    for name, (lo, hi) in _RANGES.items():
        for i, value in enumerate(getattr(track.frames, name)):
            if value is not None and not (lo <= value <= hi):
                raise SignalValidationError("value_out_of_range", f"frames.{name}[{i}] = {value} is outside [{lo}, {hi}]")

    for i, value in enumerate(track.frames.face_count):
        if value is not None and value not in _FACE_COUNT_VALUES:
            raise SignalValidationError("value_out_of_range", f"frames.face_count[{i}] = {value} is not 0, 1 or 2")

    for name in ("lh_present", "rh_present"):
        for i, value in enumerate(getattr(track.frames, name)):
            if value is not None and value not in _PRESENCE_VALUES:
                raise SignalValidationError("value_out_of_range", f"frames.{name}[{i}] = {value} is not 0, 1 or null")

    for i, value in enumerate(track.frames.infer_ms):
        if value is not None and value < 0:
            raise SignalValidationError("value_out_of_range", f"frames.infer_ms[{i}] is negative")

    for i, gap in enumerate(track.gaps):
        if gap.end < gap.start:
            raise SignalValidationError("invalid_gap", f"gaps[{i}] ends before it starts")


def duration_tolerance_s(audio_duration_s: float) -> float:
    return max(config.DURATION_MISMATCH_ABS_S, config.DURATION_MISMATCH_FRACTION * audio_duration_s)


def check_duration(track: VisualSignalTrack, audio_duration_s: Optional[float]) -> Optional[str]:
    """
    Return a reason string if clock.duration_s disagrees with the
    audio by more than the tolerance, else None. Called at analysis
    time; a mismatch fails the video analysis, never the session.
    """

    if audio_duration_s is None:
        return None

    if abs(track.clock.duration_s - audio_duration_s) > duration_tolerance_s(audio_duration_s):
        return "duration_mismatch"

    return None


# ================================================================
# Signal preparation (§5.2, §5.3)
# ================================================================

# Columns interpolated as continuous numbers (linear, gap-gated).
_INTERP_COLUMNS = (
    "head_yaw", "head_pitch", "head_roll", "iris_x", "iris_y",
    "face_scale", "face_cx", "face_cy",
    "lh_cx", "lh_cy", "lh_score", "rh_cx", "rh_cy", "rh_score",
)

# Columns resampled as nearest-sample-within-tolerance (§5.2.2):
# discrete/presence-like, where "the value 0.7s ago, smeared
# forward" would be actively misleading.
_NEAREST_COLUMNS = ("face_count", "lh_present", "rh_present")


def _to_float_array(values: Sequence[Optional[float]]) -> np.ndarray:
    return np.array([np.nan if v is None else float(v) for v in values], dtype=float)


def _build_grid(duration_s: float, hz: int) -> np.ndarray:
    n_points = int(np.floor(duration_s * hz)) + 1
    n_points = max(n_points, 1)
    return np.arange(n_points, dtype=float) / hz


def _interpolate_column(
    grid_t: np.ndarray,
    raw_t: np.ndarray,
    raw_v: np.ndarray,
    max_gap_s: float,
) -> np.ndarray:
    """
    Linear interpolation, NaN outside [raw_t[0], raw_t[-1]] and
    NaN across any bracketing gap wider than max_gap_s. raw_t/raw_v
    must already have NaN rows dropped (non-null samples only) and
    be sorted ascending.
    """

    out = np.full(grid_t.shape, np.nan)

    if raw_t.size == 0:
        return out

    if raw_t.size == 1:
        out[grid_t == raw_t[0]] = raw_v[0]
        return out

    idx = np.searchsorted(raw_t, grid_t, side="right") - 1
    idx = np.clip(idx, 0, raw_t.size - 2)

    left_t, right_t = raw_t[idx], raw_t[idx + 1]
    left_v, right_v = raw_v[idx], raw_v[idx + 1]

    gap = right_t - left_t
    safe_gap = np.where(gap > 0, gap, 1.0)
    frac = (grid_t - left_t) / safe_gap
    interpolated = left_v + frac * (right_v - left_v)

    within_range = (grid_t >= raw_t[0]) & (grid_t <= raw_t[-1])
    within_gap = gap <= max_gap_s

    valid = within_range & within_gap
    out[valid] = interpolated[valid]
    return out


def _nearest_column(
    grid_t: np.ndarray,
    raw_t: np.ndarray,
    raw_v: np.ndarray,
    tolerance_s: float,
) -> np.ndarray:
    """Nearest raw sample within tolerance_s, else NaN."""

    out = np.full(grid_t.shape, np.nan)

    if raw_t.size == 0:
        return out

    idx = np.searchsorted(raw_t, grid_t, side="left")
    idx_left = np.clip(idx - 1, 0, raw_t.size - 1)
    idx_right = np.clip(idx, 0, raw_t.size - 1)

    dist_left = np.abs(grid_t - raw_t[idx_left])
    dist_right = np.abs(grid_t - raw_t[idx_right])
    use_right = dist_right < dist_left

    nearest_idx = np.where(use_right, idx_right, idx_left)
    nearest_dist = np.where(use_right, dist_right, dist_left)

    within = nearest_dist <= tolerance_s
    out[within] = raw_v[nearest_idx[within]]
    return out


def _grid_in_gap(grid_t: np.ndarray, gaps: Sequence) -> np.ndarray:
    out = np.zeros(grid_t.shape, dtype=bool)
    for gap in gaps:
        out |= (grid_t >= gap.start) & (grid_t <= gap.end)
    return out


def _mask_gaps(grid_t: np.ndarray, columns: dict[str, np.ndarray], gaps: Sequence) -> None:
    """In place: NaN every column within any gap interval."""

    inside_any = _grid_in_gap(grid_t, gaps)
    if not inside_any.any():
        return
    for arr in columns.values():
        arr[inside_any] = np.nan


def _rolling_stat_3(x: np.ndarray, stat) -> np.ndarray:
    """
    Centered window of up to 3 points (2 at the sequence edges,
    where there is no third neighbour to include — not padded
    with a synthetic NaN neighbour, which would permanently null
    the first/last grid point regardless of data quality). NaN if
    any point actually inside that window is NaN.
    """

    n = x.size
    out = np.full(n, np.nan)
    for i in range(n):
        lo = max(0, i - 1)
        hi = min(n, i + 2)
        window = x[lo:hi]
        if np.any(np.isnan(window)):
            continue
        out[i] = stat(window)
    return out


def _smooth(x: np.ndarray) -> np.ndarray:
    return _rolling_stat_3(_rolling_stat_3(x, np.median), np.mean)


@dataclass
class PreparedSignals:
    """
    Everything metrics.py/events.py need, already resampled onto a
    uniform GRID_HZ grid, smoothed, and gap-masked. Raw (ungridded)
    timestamps are kept alongside for effective-fps calculations,
    which need real tick density, not a resampled view of it.
    """

    grid_t: np.ndarray
    grid_hz: int

    face_ok: np.ndarray          # bool
    face_count: np.ndarray       # float (nearest-sampled int, NaN = undetermined)
    head_yaw: np.ndarray
    head_pitch: np.ndarray
    head_roll: np.ndarray
    head_ang_speed: np.ndarray   # deg/s
    iris_x: np.ndarray
    iris_y: np.ndarray
    face_scale: np.ndarray
    facing: np.ndarray           # bool, only meaningful where face_ok
    facing_confidence_low: bool  # calibration missing or unstable
    baseline_yaw: float
    baseline_pitch: float
    baseline_iris_x: float
    baseline_iris_y: float

    in_gap: np.ndarray           # bool, grid points inside a recorded gap

    lh_present: np.ndarray       # float 0/1/NaN
    rh_present: np.ndarray
    lh_cx: np.ndarray
    lh_cy: np.ndarray            # width-unit-converted, see _hand_speed's aspect conversion
    rh_cx: np.ndarray
    rh_cy: np.ndarray            # width-unit-converted
    lh_speed: np.ndarray         # fs/s
    rh_speed: np.ndarray
    hand_any_visible: np.ndarray  # bool
    hand_speed: np.ndarray        # max(lh_speed, rh_speed), NaN-aware

    speaking: np.ndarray          # bool

    scale_ref: Optional[float]
    calibration_performed: bool
    calibration_stability: float
    context_in_room: bool
    uses_notes: bool

    duration_s: float

    raw_t: np.ndarray
    raw_face_ran: np.ndarray      # bool: this raw tick is not inside a gap (face always runs)
    raw_hands_ran: np.ndarray     # bool: lh_present or rh_present non-null at this raw tick

    gaps: Sequence = field(default_factory=list)


def _speaking_mask(grid_t: np.ndarray, speech_segments: Sequence[dict]) -> np.ndarray:
    mask = np.zeros(grid_t.shape, dtype=bool)
    for seg in speech_segments:
        mask |= (grid_t >= seg["start"]) & (grid_t <= seg["end"])
    return mask


def prepare_signals(
    track: VisualSignalTrack,
    speech_segments: Sequence[dict],
) -> PreparedSignals:
    """
    §5.2-5.3. speech_segments: the canonical VAD speech segments
    (audio/audio_analyzer.py's analysis.json speech_segments, or a
    words-derived fallback merging gaps < SPEECH_GAP_MERGE_S — that
    derivation is the caller's responsibility, since it depends on
    the audio pipeline's own artifacts, not on anything visual).
    """

    duration_s = track.clock.duration_s
    grid_t = _build_grid(duration_s, config.GRID_HZ)

    raw_t = np.array(track.frames.t, dtype=float)

    interp: dict[str, np.ndarray] = {}
    for name in _INTERP_COLUMNS:
        raw_v = _to_float_array(getattr(track.frames, name))
        present = ~np.isnan(raw_v)
        interp[name] = _interpolate_column(grid_t, raw_t[present], raw_v[present], config.MAX_INTERP_GAP_S)

    nearest: dict[str, np.ndarray] = {}
    for name in _NEAREST_COLUMNS:
        raw_v = _to_float_array(getattr(track.frames, name))
        present = ~np.isnan(raw_v)
        nearest[name] = _nearest_column(grid_t, raw_t[present], raw_v[present], config.PRESENCE_NEAREST_S)

    all_columns = {**interp, **nearest}
    _mask_gaps(grid_t, all_columns, track.gaps)

    for name in _INTERP_COLUMNS:
        interp[name] = _smooth(interp[name])
    # Nearest-sample (presence-like) columns are not smoothed: a
    # median/mean of 0/1/2 values would invent a face_count of 1.5,
    # which has no meaning.

    face_count = nearest["face_count"]
    face_ok = (~np.isnan(face_count)) & (face_count >= 1) & ~np.isnan(interp["head_yaw"]) & ~np.isnan(interp["head_pitch"])

    calibration_performed = track.calibration.performed
    calibration_stability = track.calibration.stability
    baseline = track.calibration.baseline

    if calibration_performed and baseline is not None:
        b_yaw, b_pitch, b_ix, b_iy = baseline.head_yaw, baseline.head_pitch, baseline.iris_x, baseline.iris_y
        facing_confidence_low = calibration_stability < config.CALIBRATION_STABILITY_MIN
    else:
        # §5.3: no calibration -> baseline yaw 0, pitch = median
        # pitch over the whole session, iris 0; confidence capped
        # low for camera-facing metrics by the caller.
        b_yaw, b_ix, b_iy = 0.0, 0.0, 0.0
        finite_pitch = interp["head_pitch"][~np.isnan(interp["head_pitch"])]
        b_pitch = float(np.median(finite_pitch)) if finite_pitch.size else 0.0
        facing_confidence_low = True

    d_yaw = np.abs(interp["head_yaw"] - b_yaw) <= config.FACING_YAW_DEG
    d_pitch = np.abs(interp["head_pitch"] - b_pitch) <= config.FACING_PITCH_DEG

    iris_x_known = ~np.isnan(interp["iris_x"])
    iris_y_known = ~np.isnan(interp["iris_y"])
    d_iris_x = np.where(iris_x_known, np.abs(interp["iris_x"] - b_ix) <= config.FACING_IRIS_X, True)
    d_iris_y = np.where(iris_y_known, np.abs(interp["iris_y"] - b_iy) <= config.FACING_IRIS_Y, True)

    facing = face_ok & d_yaw & d_pitch & d_iris_x.astype(bool) & d_iris_y.astype(bool)

    dt = 1.0 / config.GRID_HZ
    d_yaw_step = np.diff(interp["head_yaw"], prepend=np.nan)
    d_pitch_step = np.diff(interp["head_pitch"], prepend=np.nan)
    d_roll_step = np.diff(interp["head_roll"], prepend=np.nan)
    head_ang_speed = np.sqrt(d_yaw_step**2 + d_pitch_step**2 + d_roll_step**2) / dt
    head_ang_speed[0] = np.nan  # no previous point to diff against

    speaking = _speaking_mask(grid_t, speech_segments)
    scale_ref_samples = interp["face_scale"][speaking & ~np.isnan(interp["face_scale"])]
    scale_ref = float(np.median(scale_ref_samples)) if scale_ref_samples.size else None

    def _hand_speed(cx: np.ndarray, cy: np.ndarray, present: np.ndarray) -> np.ndarray:
        # cy is normalized by frame height, cx by width; convert cy
        # to width units before measuring distance (§5.3).
        aspect = track.capture.frame_height / track.capture.frame_width
        cy_w = cy * aspect
        d_cx = np.diff(cx, prepend=np.nan)
        d_cy = np.diff(cy_w, prepend=np.nan)
        dist = np.sqrt(d_cx**2 + d_cy**2)
        present_now = present == 1
        present_prev = np.concatenate(([False], present_now[:-1]))
        speed = np.full(cx.shape, np.nan)
        if scale_ref and scale_ref > 0:
            valid = present_now & present_prev
            speed[valid] = (dist[valid] / dt) / scale_ref
        return speed

    lh_speed = _hand_speed(interp["lh_cx"], interp["lh_cy"], nearest["lh_present"])
    rh_speed = _hand_speed(interp["rh_cx"], interp["rh_cy"], nearest["rh_present"])
    hand_any_visible = (nearest["lh_present"] == 1) | (nearest["rh_present"] == 1)

    hand_aspect = track.capture.frame_height / track.capture.frame_width
    lh_cy_w = interp["lh_cy"] * hand_aspect
    rh_cy_w = interp["rh_cy"] * hand_aspect

    both_nan = np.isnan(lh_speed) & np.isnan(rh_speed)
    hand_speed = np.nanmax(
        np.stack([np.nan_to_num(lh_speed, nan=-np.inf), np.nan_to_num(rh_speed, nan=-np.inf)]),
        axis=0,
    )
    hand_speed[both_nan] = np.nan

    raw_inside_gap = np.zeros(raw_t.shape, dtype=bool)
    for gap in track.gaps:
        raw_inside_gap |= (raw_t >= gap.start) & (raw_t <= gap.end)
    raw_face_ran = ~raw_inside_gap

    raw_lh_present = _to_float_array(track.frames.lh_present)
    raw_rh_present = _to_float_array(track.frames.rh_present)
    raw_hands_ran = (~np.isnan(raw_lh_present) | ~np.isnan(raw_rh_present)) & raw_face_ran

    return PreparedSignals(
        grid_t=grid_t,
        grid_hz=config.GRID_HZ,
        face_ok=face_ok,
        face_count=face_count,
        head_yaw=interp["head_yaw"],
        head_pitch=interp["head_pitch"],
        head_roll=interp["head_roll"],
        head_ang_speed=head_ang_speed,
        iris_x=interp["iris_x"],
        iris_y=interp["iris_y"],
        face_scale=interp["face_scale"],
        facing=facing,
        facing_confidence_low=facing_confidence_low,
        baseline_yaw=b_yaw,
        baseline_pitch=b_pitch,
        baseline_iris_x=b_ix,
        baseline_iris_y=b_iy,
        in_gap=_grid_in_gap(grid_t, track.gaps),
        lh_present=nearest["lh_present"],
        rh_present=nearest["rh_present"],
        lh_cx=interp["lh_cx"],
        lh_cy=lh_cy_w,
        rh_cx=interp["rh_cx"],
        rh_cy=rh_cy_w,
        lh_speed=lh_speed,
        rh_speed=rh_speed,
        hand_any_visible=hand_any_visible,
        hand_speed=hand_speed,
        speaking=speaking,
        scale_ref=scale_ref,
        calibration_performed=calibration_performed,
        calibration_stability=calibration_stability,
        context_in_room=track.context.setting == "in_room_practice",
        uses_notes=track.context.uses_notes,
        duration_s=duration_s,
        raw_t=raw_t,
        raw_face_ran=raw_face_ran,
        raw_hands_ran=raw_hands_ran,
        gaps=track.gaps,
    )


def effective_fps_in_window(raw_t: np.ndarray, ran_mask: np.ndarray, start: float, end: float) -> float:
    """
    Median ticks-per-second within [start, end], counting only
    ticks where ran_mask is True. §5.4/§5.6 define this as "median
    effective fps ... across seconds"; for a window shorter than a
    second (a short gesture, for instance) there is no full second
    to bin, so this falls back to a simple rate over the window.
    """

    in_window = (raw_t >= start) & (raw_t <= end) & ran_mask
    count = int(in_window.sum())
    span = end - start

    if span <= 0:
        return 0.0

    if span < 1.0:
        return count / span

    bin_starts = np.arange(start, end, 1.0)
    bin_counts = []
    for bin_start in bin_starts:
        bin_end = min(bin_start + 1.0, end)
        bin_counts.append(int(((raw_t >= bin_start) & (raw_t < bin_end) & ran_mask).sum()))

    return float(np.median(bin_counts)) if bin_counts else 0.0
