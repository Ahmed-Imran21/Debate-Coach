"""
Per-session metrics (§5.5): the 11-row metrics table. Each row is a
dict with value/unit/basis/coverage/confidence/status/
definition_version, computed from PreparedSignals + the event list
detected by events.py. Pure: no I/O.

Two coverage figures gate everything else:
  - face_tracked_ratio: speaking & face_ok / speaking. Gates the six
    face metrics (itself excluded -- it has no gate of its own).
  - hands_visible_ratio: speaking & hand_any_visible / speaking.
    Gates the other four hand metrics (itself excluded, but it does
    carry its own disabled_by_tier when device_tier == "face_only").

"coverage" on every gated row is that modality's own ratio value,
not a per-row recomputation -- the spec is explicit ("coverage = the
gate's ratio"), so it's computed once and reused.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from . import config
from .signals import PreparedSignals, effective_fps_in_window


FACE_METRIC_KEYS = (
    "face_tracked_ratio",
    "camera_facing_ratio",
    "gaze_away_events_per_min",
    "longest_gaze_away_s",
    "head_down_ratio",
    "head_motion_median_deg_s",
)

HAND_METRIC_KEYS = (
    "hands_visible_ratio",
    "gesture_rate_per_min",
    "gesture_amplitude_median",
    "hands_still_longest_s",
    "hands_still_ratio",
)

# Metrics whose confidence additionally needs a calibrated, stable
# baseline to ever reach "high" -- the ones built directly from the
# facing cone. head_down/head_motion use pitch/angular-speed
# directly, not the cone, so they're not included.
_CALIBRATION_SENSITIVE_KEYS = frozenset({
    "camera_facing_ratio", "gaze_away_events_per_min", "longest_gaze_away_s",
})


def _mask_from_events(grid_t: np.ndarray, events: list[dict], event_type: str) -> np.ndarray:
    """
    Rebuild a grid-aligned boolean mask from already-rounded event
    dicts. Exact, not approximate: ROUND_SECONDS is 1 decimal place
    and grid_t is always an exact multiple of 1/GRID_HZ = 0.1, so
    every event boundary is already bit-exact to its grid point.
    """

    mask = np.zeros(grid_t.shape, dtype=bool)
    for e in events:
        if e["type"] == event_type:
            mask |= (grid_t >= e["start"]) & (grid_t <= e["end"])
    return mask


def _count(mask: np.ndarray) -> int:
    return int(mask.sum())


def _safe_ratio(numerator: int, denominator: int) -> Optional[float]:
    if denominator <= 0:
        return None
    return numerator / denominator


def _midpoint_in_speech(event: dict, grid_t: np.ndarray, speaking: np.ndarray) -> bool:
    mid = (event["start"] + event["end"]) / 2.0
    idx = int(np.argmin(np.abs(grid_t - mid)))
    return bool(speaking[idx])


def _overlaps_speech(event: dict, grid_t: np.ndarray, speaking: np.ndarray) -> bool:
    in_span = (grid_t >= event["start"]) & (grid_t <= event["end"])
    return bool((speaking & in_span).any())


def _confidence(coverage: Optional[float], effective_fps: float, *, calibration_ok: bool) -> str:
    if coverage is None:
        return "low"
    if coverage >= config.CONF_HIGH_COVERAGE and effective_fps >= config.CONF_HIGH_FPS and calibration_ok:
        return "high"
    if coverage >= config.CONF_MEDIUM_COVERAGE:
        return "medium"
    return "low"


def _coverage_gate(value: Optional[float], min_coverage: float) -> str:
    if value is None:
        return "not_measured"
    if value < min_coverage:
        return "insufficient_coverage"
    return "ok"


def _hand_gate(value: Optional[float], device_tier: str) -> str:
    if device_tier == "face_only":
        return "disabled_by_tier"
    return _coverage_gate(value, config.HANDS_COVERAGE_MIN)


def _hand_behavior_status(hand_gate_status: str, scale_ref: Optional[float]) -> str:
    """
    The four metrics built from hand *speed* (not just presence)
    need scale_ref to convert distance to face_scale units at all
    -- a face that was never tracked during speech (scale_ref is
    None) is a distinct, more specific problem than low hand
    coverage, so it's checked after the shared hand gate passes.
    """

    if hand_gate_status != "ok":
        return hand_gate_status
    if scale_ref is None:
        return "not_measured"
    return "ok"


def _finalize(
    key: str, unit: str, basis: str, definition_version: str,
    *, value: Optional[float], coverage: Optional[float], confidence: str,
    status: str, round_to: int, note: Optional[str] = None,
) -> dict:
    if status != "ok":
        value, confidence = None, None
    elif value is not None:
        value = round(value, round_to)

    d = {
        "key": key,
        "value": value,
        "unit": unit,
        "basis": basis,
        "coverage": round(coverage, config.ROUND_RATIO) if coverage is not None else None,
        "confidence": confidence,
        "status": status,
        "definition_version": definition_version,
    }
    if note is not None:
        d["note"] = note
    return d


def compute_metrics(p: PreparedSignals, events: list[dict], device_tier: str) -> dict[str, dict]:
    speaking = p.speaking
    n_speaking = _count(speaking)

    n_speaking_face_ok = _count(speaking & p.face_ok)
    n_speaking_face_ok_facing = _count(speaking & p.face_ok & p.facing)
    n_speaking_hands_visible = _count(speaking & p.hand_any_visible)
    n_speaking_head_down = _count(speaking & _mask_from_events(p.grid_t, events, "head_down") & p.face_ok)
    n_speaking_hands_still = _count(speaking & _mask_from_events(p.grid_t, events, "hands_still") & p.hand_any_visible)

    face_tracked_value = _safe_ratio(n_speaking_face_ok, n_speaking)
    hands_visible_value = _safe_ratio(n_speaking_hands_visible, n_speaking)

    face_gate_status = _coverage_gate(face_tracked_value, config.FACE_COVERAGE_MIN)
    hand_gate_status = _hand_gate(hands_visible_value, device_tier)

    face_effective_fps = effective_fps_in_window(p.raw_t, p.raw_face_ran, 0.0, p.duration_s)
    hands_effective_fps = effective_fps_in_window(p.raw_t, p.raw_hands_ran, 0.0, p.duration_s)
    calibration_ok = not p.facing_confidence_low

    def face_confidence(key: str) -> str:
        return _confidence(face_tracked_value, face_effective_fps, calibration_ok=calibration_ok if key in _CALIBRATION_SENSITIVE_KEYS else True)

    hand_confidence = _confidence(hands_visible_value, hands_effective_fps, calibration_ok=True)

    speaking_minutes = n_speaking / p.grid_hz / 60.0
    speaking_hands_minutes = n_speaking_hands_visible / p.grid_hz / 60.0

    gaze_away_events = [e for e in events if e["type"] == "gaze_away"]
    gaze_away_events_in_speech = [e for e in gaze_away_events if _midpoint_in_speech(e, p.grid_t, speaking)]

    gesture_events = [e for e in events if e["type"] == "gesture"]
    gesture_events_in_speech = [e for e in gesture_events if _midpoint_in_speech(e, p.grid_t, speaking)]

    hands_still_events = [e for e in events if e["type"] == "hands_still"]
    hands_still_events_in_speech = [e for e in hands_still_events if _overlaps_speech(e, p.grid_t, speaking)]

    metrics: dict[str, dict] = {}

    # 1. face_tracked_ratio -- no gate.
    metrics["face_tracked_ratio"] = _finalize(
        "face_tracked_ratio", "ratio", "speaking_time", "face_tracked@1",
        value=face_tracked_value, coverage=face_tracked_value,
        confidence=face_confidence("face_tracked_ratio"),
        status="ok" if face_tracked_value is not None else "not_measured",
        round_to=config.ROUND_RATIO,
    )

    # 2. camera_facing_ratio
    metrics["camera_facing_ratio"] = _finalize(
        "camera_facing_ratio", "ratio", "face_tracked_speaking_time", "camera_facing@1",
        value=_safe_ratio(n_speaking_face_ok_facing, n_speaking_face_ok), coverage=face_tracked_value,
        confidence=face_confidence("camera_facing_ratio"), status=face_gate_status,
        round_to=config.ROUND_RATIO,
    )

    # 3. gaze_away_events_per_min
    metrics["gaze_away_events_per_min"] = _finalize(
        "gaze_away_events_per_min", "per_min", "speaking_minutes", "gaze_away@1",
        value=(len(gaze_away_events_in_speech) / speaking_minutes) if speaking_minutes > 0 else None,
        coverage=face_tracked_value, confidence=face_confidence("gaze_away_events_per_min"),
        status=face_gate_status if speaking_minutes > 0 else "not_measured",
        round_to=config.ROUND_RATE,
    )

    # 4. longest_gaze_away_s -- all gaze_away events, not speech-filtered.
    metrics["longest_gaze_away_s"] = _finalize(
        "longest_gaze_away_s", "s", "all_gaze_away_events", "gaze_away@1",
        value=max((e["end"] - e["start"] for e in gaze_away_events), default=0.0),
        coverage=face_tracked_value, confidence=face_confidence("longest_gaze_away_s"),
        status=face_gate_status, round_to=config.ROUND_SECONDS,
    )

    # 5. head_down_ratio
    metrics["head_down_ratio"] = _finalize(
        "head_down_ratio", "ratio", "face_tracked_speaking_time", "head_down@1",
        value=_safe_ratio(n_speaking_head_down, n_speaking_face_ok), coverage=face_tracked_value,
        confidence=face_confidence("head_down_ratio"), status=face_gate_status,
        round_to=config.ROUND_RATIO,
    )

    # 6. head_motion_median_deg_s
    head_motion_pool = p.head_ang_speed[speaking & p.face_ok]
    head_motion_pool = head_motion_pool[~np.isnan(head_motion_pool)]
    metrics["head_motion_median_deg_s"] = _finalize(
        "head_motion_median_deg_s", "deg_per_s", "face_tracked_speaking_time", "head_motion@1",
        value=float(np.median(head_motion_pool)) if head_motion_pool.size else None,
        coverage=face_tracked_value, confidence=face_confidence("head_motion_median_deg_s"),
        status=face_gate_status if head_motion_pool.size else "not_measured",
        round_to=config.ROUND_DEGREES,
    )

    # 7. hands_visible_ratio -- no coverage gate, but disabled_by_tier applies.
    hands_visible_status = "disabled_by_tier" if device_tier == "face_only" else ("ok" if hands_visible_value is not None else "not_measured")
    metrics["hands_visible_ratio"] = _finalize(
        "hands_visible_ratio", "ratio", "speaking_time", "hands_visible@1",
        value=hands_visible_value, coverage=hands_visible_value,
        confidence=hand_confidence, status=hands_visible_status,
        round_to=config.ROUND_RATIO,
    )

    # 8. gesture_rate_per_min
    gesture_status = _hand_behavior_status(hand_gate_status, p.scale_ref) if speaking_hands_minutes > 0 else "not_measured"
    metrics["gesture_rate_per_min"] = _finalize(
        "gesture_rate_per_min", "per_min", "hand_tracked_speaking_minutes", "gesture_burst@1",
        value=(len(gesture_events_in_speech) / speaking_hands_minutes) if speaking_hands_minutes > 0 else None,
        coverage=hands_visible_value, confidence=hand_confidence, status=gesture_status,
        round_to=config.ROUND_RATE,
    )

    # 9. gesture_amplitude_median -- zero events is "ok" with a null
    # value and a note, per spec: never report a fabricated zero.
    if gesture_status != "ok":
        amp_value, amp_note = None, None
    elif not gesture_events_in_speech:
        amp_value, amp_note = None, "no_gestures"
    else:
        amp_value = float(np.median([e["attributes"]["amplitude"] for e in gesture_events_in_speech]))
        amp_note = None
    metrics["gesture_amplitude_median"] = _finalize(
        "gesture_amplitude_median", "face_scale", "gesture_events_in_speech", "gesture_burst@1",
        value=amp_value, coverage=hands_visible_value, confidence=hand_confidence,
        status=gesture_status, round_to=config.ROUND_AMPLITUDE, note=amp_note,
    )

    # 10. hands_still_longest_s -- events overlapping speech, not speech-filtered by midpoint.
    still_status = _hand_behavior_status(hand_gate_status, p.scale_ref)
    metrics["hands_still_longest_s"] = _finalize(
        "hands_still_longest_s", "s", "hands_still_events_overlapping_speech", "hands_still@1",
        value=max((e["end"] - e["start"] for e in hands_still_events_in_speech), default=0.0),
        coverage=hands_visible_value, confidence=hand_confidence, status=still_status,
        round_to=config.ROUND_SECONDS,
    )

    # 11. hands_still_ratio
    metrics["hands_still_ratio"] = _finalize(
        "hands_still_ratio", "ratio", "hand_tracked_speaking_time", "hands_still@1",
        value=_safe_ratio(n_speaking_hands_still, n_speaking_hands_visible),
        coverage=hands_visible_value, confidence=hand_confidence, status=still_status,
        round_to=config.ROUND_RATIO,
    )

    # Global cap: a session with a substantial second-person presence
    # makes every measurement here less trustworthy (whose face/hands
    # are actually being tracked is ambiguous), not just second-person
    # detection itself -- which isn't a metric in this table at all.
    second_person_ratio = _safe_ratio(_count(speaking & (p.face_count == 2)), n_speaking)
    if second_person_ratio is not None and second_person_ratio > config.SECOND_PERSON_LOW_CONF_RATIO:
        for m in metrics.values():
            if m["confidence"] is not None:
                m["confidence"] = "low"

    return metrics
