"""
Result assembly (§5.6): combine signal preparation, event detection
and metrics into one VideoAnalysisResult. Pure: no I/O, no storage,
no DB. app/services/visual_signals.py persists what this returns;
app/services/pipeline.py calls run_pipeline at the right point in
the session lifecycle and translates "complete" to the DB's
"processed" status (see §5.7 -- the result's own status vocabulary
and the video_analyses.status column's vocabulary are deliberately
different: "processed | partial | insufficient_data" there vs
"complete | partial | insufficient_data | unavailable | failed"
here, with "unavailable"/"failed" only ever set by the caller, never
by run_pipeline itself).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence

import numpy as np

from . import config
from .events import detect_events
from .metrics import FACE_METRIC_KEYS, HAND_METRIC_KEYS, compute_metrics
from .schema import VisualSignalTrack
from .signals import PreparedSignals, effective_fps_in_window, prepare_signals


@dataclass
class VideoAnalysisResult:
    schema: str
    schema_version: str
    metrics_version: str
    session_id: str
    computed_at: str
    source_summary: dict
    status: str
    unavailable_reason: Optional[str]
    quality: dict
    metrics: dict
    events: list
    series: dict
    duration_s: float  # internal convenience; not part of the wire shape

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "metrics_version": self.metrics_version,
            "session_id": self.session_id,
            "computed_at": self.computed_at,
            "source_summary": self.source_summary,
            "status": self.status,
            "unavailable_reason": self.unavailable_reason,
            "quality": self.quality,
            "metrics": self.metrics,
            "events": self.events,
            "series": self.series,
        }


def _status_from_metrics(metrics: dict[str, dict]) -> str:
    face_ok = all(metrics[k]["status"] == "ok" for k in FACE_METRIC_KEYS)
    hand_ok = all(metrics[k]["status"] in ("ok", "disabled_by_tier") for k in HAND_METRIC_KEYS)
    any_ok = any(m["status"] == "ok" for m in metrics.values())

    if face_ok and hand_ok:
        return "complete"
    if not any_ok:
        return "insufficient_data"
    return "partial"


def _build_source_summary(track: VisualSignalTrack) -> dict:
    return {
        "platform": track.source.platform,
        "runtime_version": track.source.runtime.version,
        "delegate": track.source.runtime.delegate,
        "device_tier": track.source.device_tier,
    }


def _hand_visibility_breakdown(p: PreparedSignals) -> dict:
    speaking = p.speaking
    n_speaking = int(speaking.sum())

    def ratio(present: np.ndarray) -> Optional[float]:
        if n_speaking <= 0:
            return None
        return round(int((speaking & (present == 1)).sum()) / n_speaking, config.ROUND_RATIO)

    return {
        "any": ratio(np.where((p.lh_present == 1) | (p.rh_present == 1), 1.0, 0.0)),
        "left": ratio(p.lh_present),
        "right": ratio(p.rh_present),
    }


def _warnings(track: VisualSignalTrack, p: PreparedSignals, face_tracked: Optional[float], hands_visible: Optional[float], second_person_ratio: Optional[float]) -> list[str]:
    warnings: list[str] = []

    if face_tracked is not None and face_tracked < config.FACE_COVERAGE_MIN:
        warnings.append("face_often_out_of_frame")
    if hands_visible is not None and hands_visible < config.HANDS_COVERAGE_MIN:
        warnings.append("hands_mostly_out_of_frame")
    if not track.calibration.performed:
        warnings.append("calibration_skipped")
    elif track.calibration.stability < config.CALIBRATION_STABILITY_MIN:
        warnings.append("calibration_unstable")
    if second_person_ratio is not None and second_person_ratio > config.SECOND_PERSON_LOW_CONF_RATIO:
        warnings.append("second_person_detected")
    if track.degradations:
        warnings.append("analysis_degraded")
    if track.clock.uncertainty_ms > config.CLOCK_UNCERTAINTY_MAX_MS_FOR_MOMENTS:
        warnings.append("high_clock_uncertainty")
    if track.context.setting == "in_room_practice":
        warnings.append("in_room_context")

    return warnings


def _build_quality(track: VisualSignalTrack, p: PreparedSignals, metrics: dict) -> dict:
    n_analyzed = int((~p.in_gap).sum())
    n_speaking = int(p.speaking.sum())

    face_tracked = metrics["face_tracked_ratio"]["coverage"]
    hands_visible = metrics["hands_visible_ratio"]["coverage"]

    n_second_person = int((p.speaking & (p.face_count == 2)).sum())
    second_person_ratio = round(n_second_person / n_speaking, config.ROUND_RATIO) if n_speaking > 0 else None

    return {
        "analyzed_duration_s": round(n_analyzed / p.grid_hz, config.ROUND_SECONDS),
        "speaking_duration_s": round(n_speaking / p.grid_hz, config.ROUND_SECONDS),
        "face_tracked_ratio": face_tracked,
        "hands_visible_ratio": _hand_visibility_breakdown(p),
        "effective_fps": {
            "face_median": round(effective_fps_in_window(p.raw_t, p.raw_face_ran, 0.0, p.duration_s), config.ROUND_RATE),
            "hands_median": round(effective_fps_in_window(p.raw_t, p.raw_hands_ran, 0.0, p.duration_s), config.ROUND_RATE),
        },
        "second_person_ratio": second_person_ratio,
        "calibration": {
            "performed": track.calibration.performed,
            "stability": track.calibration.stability,
            "right_hand_check": track.calibration.right_hand_check,
        },
        "context": {
            "setting": track.context.setting,
            "uses_notes": track.context.uses_notes,
        },
        "clock_uncertainty_ms": track.clock.uncertainty_ms,
        "warnings": _warnings(track, p, face_tracked, hands_visible, second_person_ratio),
    }


def _build_series(p: PreparedSignals) -> dict:
    """
    A SERIES_RESOLUTION_S-wide (default 1s) aggregation of the grid
    for report-UI charting: per second, the fraction of face_ok
    points that were facing, the mean hand speed, and the mean head
    angular speed -- null wherever that second has no qualifying
    points, never 0 (0 would mean "measured and definitely not
    facing/moving", which is a different claim).
    """

    resolution = config.SERIES_RESOLUTION_S
    duration = p.duration_s
    bin_starts = np.arange(0.0, max(duration, resolution), resolution)

    camera_facing: list[Optional[float]] = []
    hand_activity: list[Optional[float]] = []
    head_motion: list[Optional[float]] = []

    for bin_start in bin_starts:
        bin_end = min(bin_start + resolution, duration) if duration > 0 else bin_start + resolution
        in_bin = (p.grid_t >= bin_start) & (p.grid_t < bin_end)

        face_ok_in_bin = in_bin & p.face_ok
        n_face_ok = int(face_ok_in_bin.sum())
        camera_facing.append(
            round(int((face_ok_in_bin & p.facing).sum()) / n_face_ok, config.ROUND_RATIO) if n_face_ok else None
        )

        hand_speed_in_bin = p.hand_speed[in_bin]
        hand_speed_in_bin = hand_speed_in_bin[~np.isnan(hand_speed_in_bin)]
        hand_activity.append(round(float(np.mean(hand_speed_in_bin)), config.ROUND_RATE) if hand_speed_in_bin.size else None)

        motion_in_bin = p.head_ang_speed[in_bin]
        motion_in_bin = motion_in_bin[~np.isnan(motion_in_bin)]
        head_motion.append(round(float(np.mean(motion_in_bin)), config.ROUND_DEGREES) if motion_in_bin.size else None)

    return {
        "resolution_s": resolution,
        "camera_facing": camera_facing,
        "hand_activity": hand_activity,
        "head_motion": head_motion,
    }


def run_pipeline(track: VisualSignalTrack, speech_segments: Sequence[dict]) -> VideoAnalysisResult:
    p = prepare_signals(track, speech_segments)
    events = detect_events(p, track.degradations)
    metrics = compute_metrics(p, events, track.source.device_tier)

    speaking_seconds = float(p.speaking.sum()) / p.grid_hz
    status = "insufficient_data" if speaking_seconds <= 0 else _status_from_metrics(metrics)

    return VideoAnalysisResult(
        schema=config.RESULT_SCHEMA,
        schema_version=config.RESULT_SCHEMA_VERSION,
        metrics_version=config.METRICS_VERSION,
        session_id=track.session_id,
        computed_at=datetime.now(timezone.utc).isoformat(),
        source_summary=_build_source_summary(track),
        status=status,
        unavailable_reason=None,
        quality=_build_quality(track, p, metrics),
        metrics=metrics,
        events=events,
        series=_build_series(p),
        duration_s=p.duration_s,
    )
