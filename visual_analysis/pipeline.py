"""
Result assembly (§5.6): combine signal preparation, event detection
and metrics into one VideoAnalysisResult. Pure: no I/O, no storage,
no DB. app/services/visual_signals.py persists what this returns;
app/services/pipeline.py calls run_pipeline at the right point in
the session lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from . import config
from .events import detect_events
from .metrics import _mask_from_events, compute_metrics
from .schema import VisualSignalTrack
from .signals import prepare_signals


@dataclass
class VideoAnalysisResult:
    schema: str
    schema_version: str
    metrics_version: str
    session_id: str
    status: str
    quality: dict
    metrics: list
    events: list
    series: list
    duration_s: float

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "metrics_version": self.metrics_version,
            "session_id": self.session_id,
            "status": self.status,
            "quality": self.quality,
            "metrics": self.metrics,
            "events": self.events,
            "series": self.series,
            "duration_s": round(self.duration_s, config.ROUND_SECONDS),
        }


def _metrics_by_key(metrics: list[dict]) -> dict[str, dict]:
    return {m["key"]: m for m in metrics}


def _coverage_ok(metric: dict, min_coverage: float) -> bool:
    return metric["available"] and metric["value"] >= min_coverage


def _status_from_metrics(metrics: list[dict]) -> str:
    """
    processed: both modalities cleared their coverage gate.
    insufficient_data: neither did (nothing much was measurable).
    partial: one did and the other didn't (a mixed session -- e.g.
    a good face view but hands out of frame the whole time).

    Deliberately keyed off face_visibility/hand_visibility's own
    values against the same *_COVERAGE_MIN gates metrics.py applies
    per metric, not off individual metrics' unavailable_reason
    strings -- gesture_amplitude_avg being unavailable because
    nobody gestured (no_gesture_events) is a real finding, not a
    data-quality problem, and shouldn't downgrade the status.
    """

    by_key = _metrics_by_key(metrics)
    face_ok = _coverage_ok(by_key["face_visibility"], config.FACE_COVERAGE_MIN)
    hand_ok = _coverage_ok(by_key["hand_visibility"], config.HANDS_COVERAGE_MIN)

    if face_ok and hand_ok:
        return "processed"
    if not face_ok and not hand_ok:
        return "insufficient_data"
    return "partial"


def _build_quality(p, metrics: list[dict]) -> dict:
    by_key = _metrics_by_key(metrics)
    return {
        "frame_count": int(p.raw_t.size),
        "analysis_coverage": by_key["analysis_coverage"]["value"],
        "face_coverage": by_key["face_visibility"]["value"],
        "hand_coverage": by_key["hand_visibility"]["value"],
        "calibration_performed": p.calibration_performed,
        "calibration_stability": round(p.calibration_stability, config.ROUND_RATIO),
        "facing_confidence_low": p.facing_confidence_low,
        "scale_ref": round(p.scale_ref, config.ROUND_AMPLITUDE) if p.scale_ref is not None else None,
    }


def _build_series(p, events: list[dict]) -> list[dict]:
    """
    A SERIES_RESOLUTION_S-spaced (default 1Hz) downsample of the
    grid for report-UI charting -- the full GRID_HZ grid is finer
    than any chart needs and isn't sent to the client.
    """

    step = max(1, int(round(config.SERIES_RESOLUTION_S * p.grid_hz)))
    indices = np.arange(0, p.grid_t.size, step)

    gesture_mask = _mask_from_events(p.grid_t, events, "gesture")
    hands_still_mask = _mask_from_events(p.grid_t, events, "hands_still")

    series = []
    for i in indices:
        series.append({
            "t": round(float(p.grid_t[i]), config.ROUND_SECONDS),
            "facing": bool(p.facing[i]) if bool(p.face_ok[i]) else None,
            "gesture_active": bool(gesture_mask[i]),
            "hands_still": bool(hands_still_mask[i]),
            "speaking": bool(p.speaking[i]),
        })
    return series


def run_pipeline(track: VisualSignalTrack, speech_segments: Sequence[dict]) -> VideoAnalysisResult:
    p = prepare_signals(track, speech_segments)
    events = detect_events(p, track.degradations)
    metrics = compute_metrics(p, events)

    return VideoAnalysisResult(
        schema=config.RESULT_SCHEMA,
        schema_version=config.RESULT_SCHEMA_VERSION,
        metrics_version=config.METRICS_VERSION,
        session_id=track.session_id,
        status=_status_from_metrics(metrics),
        quality=_build_quality(p, metrics),
        metrics=metrics,
        events=events,
        series=_build_series(p, events),
        duration_s=p.duration_s,
    )
