"""
Event detection over PreparedSignals (§5.4). Pure functions of a
PreparedSignals instance; no I/O.

Two interpretation calls, documented where they're made:
  - "camera-facing-derived events" (low confidence when uncalibrated
    or unstable) is read narrowly as gaze_away only, since facing
    is the only boolean events.py builds directly from the camera-
    facing cone. head_down shares the pitch baseline mechanically
    but is a different concept and is not covered by that rule.
  - For hand events (gesture, hands_still), "effective fps" is read
    as the hands effective fps (whether the hand model ran that
    tick), not the face effective fps, since that's what actually
    bounds how well a hand event was measured.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from . import config
from .signals import PreparedSignals, effective_fps_in_window


@dataclass
class Event:
    id: str
    type: str
    start: float
    end: float
    confidence: str
    attributes: dict

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "start": round(self.start, config.ROUND_SECONDS),
            "end": round(self.end, config.ROUND_SECONDS),
            "confidence": self.confidence,
            "attributes": self.attributes,
        }


@dataclass
class _Run:
    start_t: float
    end_t: float
    start_idx: int
    end_idx: int  # inclusive


def _find_runs(grid_t: np.ndarray, mask: np.ndarray) -> list[_Run]:
    """Maximal runs of True in mask. Run duration is grid_t[end] - grid_t[start]."""

    runs: list[_Run] = []
    n = mask.size
    i = 0
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and mask[j + 1]:
            j += 1
        runs.append(_Run(float(grid_t[i]), float(grid_t[j]), i, j))
        i = j + 1
    return runs


def _bridge_short_gaps(mask: np.ndarray, grid_t: np.ndarray, max_gap_s: float) -> np.ndarray:
    """
    Any maximal False-run strictly between two True values, whose
    own span (last False index's time minus first False index's
    time) is shorter than max_gap_s, is flipped to True. A False-
    run touching either edge of the array is left alone.

    Used for both "bridge a brief facing blip" (gaze_away) and
    "merge nearby gesture bursts" (gesture) — same mechanism, the
    doc names it separately for each.
    """

    out = mask.copy()
    n = out.size
    i = 0
    while i < n:
        if out[i]:
            i += 1
            continue
        j = i
        while j < n and not out[j]:
            j += 1
        # False run occupies [i, j-1]; j is the next True index, or n.
        if i > 0 and j < n:
            blip_duration = grid_t[j - 1] - grid_t[i]
            if blip_duration < max_gap_s:
                out[i:j] = True
        i = j
    return out


def _confidence(
    p: PreparedSignals,
    start: float,
    end: float,
    *,
    ran_mask: np.ndarray,
    camera_facing_derived: bool = False,
) -> str:
    if camera_facing_derived and (not p.calibration_performed or p.facing_confidence_low):
        return "low"

    fps = effective_fps_in_window(p.raw_t, ran_mask, start, end)
    return "high" if fps >= config.CONF_HIGH_FPS else "medium"


def _mean_over_run(x: np.ndarray, run: _Run) -> float:
    window = x[run.start_idx : run.end_idx + 1]
    finite = window[~np.isnan(window)]
    return float(np.mean(finite)) if finite.size else float("nan")


# ---------------------------------------------------------------
# gaze_away
# ---------------------------------------------------------------

def _gaze_away_events(p: PreparedSignals) -> list[Event]:
    not_facing = p.face_ok & ~p.facing
    bridged = _bridge_short_gaps(not_facing, p.grid_t, config.FACING_BRIDGE_S)

    events = []
    for run in _find_runs(p.grid_t, bridged):
        duration = run.end_t - run.start_t
        if duration < config.GAZE_AWAY_MIN_S:
            continue

        mean_yaw_delta = _mean_over_run(p.head_yaw, run) - p.baseline_yaw
        mean_pitch_delta = _mean_over_run(p.head_pitch, run) - p.baseline_pitch

        if abs(mean_pitch_delta) >= abs(mean_yaw_delta):
            direction = "down" if mean_pitch_delta < 0 else "up"
        else:
            direction = "right" if mean_yaw_delta > 0 else "left"

        events.append(
            Event(
                id="",
                type="gaze_away",
                start=run.start_t,
                end=run.end_t,
                confidence=_confidence(p, run.start_t, run.end_t, ran_mask=p.raw_face_ran, camera_facing_derived=True),
                attributes={
                    "direction": direction,
                    "mean_yaw_delta": round(mean_yaw_delta, config.ROUND_DEGREES),
                    "mean_pitch_delta": round(mean_pitch_delta, config.ROUND_DEGREES),
                },
            )
        )
    return events


# ---------------------------------------------------------------
# head_down
# ---------------------------------------------------------------

def _head_down_events(p: PreparedSignals) -> list[Event]:
    below = (p.head_pitch - p.baseline_pitch) <= config.HEAD_DOWN_PITCH_DEG

    events = []
    for run in _find_runs(p.grid_t, below):
        duration = run.end_t - run.start_t
        if duration < config.HEAD_DOWN_MIN_S:
            continue
        events.append(
            Event(
                id="",
                type="head_down",
                start=run.start_t,
                end=run.end_t,
                confidence=_confidence(p, run.start_t, run.end_t, ran_mask=p.raw_face_ran),
                attributes={},
            )
        )
    return events


# ---------------------------------------------------------------
# gesture
# ---------------------------------------------------------------

def _bounding_box_diagonal(cx: np.ndarray, cy_width_units: np.ndarray) -> float:
    finite = ~np.isnan(cx) & ~np.isnan(cy_width_units)
    if not finite.any():
        return 0.0
    xs, ys = cx[finite], cy_width_units[finite]
    return float(np.hypot(xs.max() - xs.min(), ys.max() - ys.min()))


def _gesture_events(p: PreparedSignals) -> list[Event]:
    # hand_speed is NaN wherever it's not measured; NaN > threshold
    # is already False in numpy, so above is False there too.
    above = p.hand_speed > config.GESTURE_SPEED_FS

    merged = _bridge_short_gaps(above, p.grid_t, config.GESTURE_MERGE_GAP_S)

    events = []
    for run in _find_runs(p.grid_t, merged):
        duration = run.end_t - run.start_t
        if duration < config.GESTURE_MIN_S:
            continue

        sl = slice(run.start_idx, run.end_idx + 1)
        lh_above = p.lh_speed[sl] > config.GESTURE_SPEED_FS
        rh_above = p.rh_speed[sl] > config.GESTURE_SPEED_FS
        n_points = run.end_idx - run.start_idx + 1

        left_took_part = (lh_above.sum() / n_points) >= config.GESTURE_HAND_SHARE_MIN
        right_took_part = (rh_above.sum() / n_points) >= config.GESTURE_HAND_SHARE_MIN

        if left_took_part and right_took_part:
            hands = "both"
        elif right_took_part:
            hands = "right"
        elif left_took_part:
            hands = "left"
        else:
            # The run qualified on max(lh_speed, rh_speed) but
            # neither hand individually cleared the share
            # threshold (e.g. the active hand alternated). Falls
            # back to whichever had the higher peak.
            hands = "right" if np.nanmax(p.rh_speed[sl], initial=-np.inf) >= np.nanmax(p.lh_speed[sl], initial=-np.inf) else "left"

        peak_speed = float(np.nanmax(p.hand_speed[sl]))

        # "The moving hand" for amplitude: whichever peaked higher.
        rh_peak = np.nanmax(p.rh_speed[sl], initial=-np.inf)
        lh_peak = np.nanmax(p.lh_speed[sl], initial=-np.inf)
        if rh_peak >= lh_peak:
            box_cx, box_cy = p.rh_cx[sl], p.rh_cy[sl]
        else:
            box_cx, box_cy = p.lh_cx[sl], p.lh_cy[sl]

        amplitude = _bounding_box_diagonal(box_cx, box_cy)
        if p.scale_ref and p.scale_ref > 0:
            amplitude = amplitude / p.scale_ref
        else:
            amplitude = 0.0

        events.append(
            Event(
                id="",
                type="gesture",
                start=run.start_t,
                end=run.end_t,
                confidence=_confidence(p, run.start_t, run.end_t, ran_mask=p.raw_hands_ran),
                attributes={
                    "hands": hands,
                    "peak_speed": round(peak_speed, config.ROUND_RATE),
                    "amplitude": round(amplitude, config.ROUND_AMPLITUDE),
                },
            )
        )
    return events


# ---------------------------------------------------------------
# hands_still
# ---------------------------------------------------------------

def _hands_still_events(p: PreparedSignals) -> list[Event]:
    still = p.hand_any_visible & (p.hand_speed < config.STILL_SPEED_FS)

    events = []
    for run in _find_runs(p.grid_t, still):
        duration = run.end_t - run.start_t
        if duration < config.STILL_MIN_S:
            continue
        events.append(
            Event(
                id="",
                type="hands_still",
                start=run.start_t,
                end=run.end_t,
                confidence=_confidence(p, run.start_t, run.end_t, ran_mask=p.raw_hands_ran),
                attributes={},
            )
        )
    return events


# ---------------------------------------------------------------
# face_lost
# ---------------------------------------------------------------

def _face_lost_events(p: PreparedSignals) -> list[Event]:
    lost = (~p.in_gap) & (np.isnan(p.face_count) | (p.face_count == 0))

    events = []
    for run in _find_runs(p.grid_t, lost):
        duration = run.end_t - run.start_t
        if duration < config.FACE_LOST_EVENT_MIN_S:
            continue
        events.append(
            Event(
                id="",
                type="face_lost",
                start=run.start_t,
                end=run.end_t,
                confidence=_confidence(p, run.start_t, run.end_t, ran_mask=p.raw_face_ran),
                attributes={},
            )
        )
    return events


# ---------------------------------------------------------------
# second_person
# ---------------------------------------------------------------

def _second_person_events(p: PreparedSignals) -> list[Event]:
    two = p.face_count == 2

    events = []
    for run in _find_runs(p.grid_t, two):
        duration = run.end_t - run.start_t
        if duration < config.SECOND_PERSON_EVENT_MIN_S:
            continue
        events.append(
            Event(
                id="",
                type="second_person",
                start=run.start_t,
                end=run.end_t,
                confidence=_confidence(p, run.start_t, run.end_t, ran_mask=p.raw_face_ran),
                attributes={},
            )
        )
    return events


# ---------------------------------------------------------------
# analysis_degraded
# ---------------------------------------------------------------

def _analysis_degraded_events(degradations: Sequence[Any]) -> list[Event]:
    events = []
    for d in degradations:
        events.append(
            Event(
                id="",
                type="analysis_degraded",
                start=float(d.t),
                end=float(d.t),
                confidence="medium",
                attributes={
                    "face_fps": round(float(d.face_fps), config.ROUND_RATE),
                    "hands_fps": round(float(d.hands_fps), config.ROUND_RATE),
                    "reason": d.reason,
                },
            )
        )
    return events


# ---------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------

def detect_events(p: PreparedSignals, degradations: Sequence[Any] = ()) -> list[dict]:
    """
    All event types, merged, sorted by start time, IDs assigned
    ve_0001... in that order.
    """

    all_events = (
        _gaze_away_events(p)
        + _head_down_events(p)
        + _gesture_events(p)
        + _hands_still_events(p)
        + _face_lost_events(p)
        + _second_person_events(p)
        + _analysis_degraded_events(degradations)
    )

    all_events.sort(key=lambda e: (e.start, e.end, e.type))

    for index, event in enumerate(all_events, start=1):
        event.id = f"ve_{index:04d}"

    return [e.to_dict() for e in all_events]
