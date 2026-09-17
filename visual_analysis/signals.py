"""
Validation the Pydantic schema cannot express, plus (later)
cleaning and resampling. Pure: no I/O, no logging of arrays.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

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
