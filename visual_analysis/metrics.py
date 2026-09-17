"""
Per-session metrics over PreparedSignals + detected events (§5.5).

RECONSTRUCTION NOTE: the task document's own §5.5 table is no longer
available to derive this from verbatim (it was only ever pasted
inline in chat, not saved to the repo, and has since scrolled out of
context). Every threshold used below (FACE_COVERAGE_MIN,
HANDS_COVERAGE_MIN, CONF_HIGH_COVERAGE, CONF_MEDIUM_COVERAGE,
SECOND_PERSON_LOW_CONF_RATIO, the rounding constants) *is* verbatim
from that document — they were transcribed into config.py during
Phase 1, while it was still open. The 11 metrics below, their exact
formulas, and how those thresholds combine into gates/confidence
tiers are a reconstruction from that config plus the events.py
output, not a re-read of the source table. Sanity-check this file
against the original document if it turns up, before tuning
thresholds against real data per THRESHOLD_TUNING.md.

Every metric is one of:
  - a coverage ratio (face_visibility, hand_visibility, analysis_coverage):
    always available, confidence "high" unconditionally (it's a
    direct count over the raw grid, not a derived quantity with its
    own extra uncertainty).
  - a face- or hand-gated quantity (everything else except
    second_person_time_ratio and face_lost_count): unavailable below
    that modality's *_COVERAGE_MIN; otherwise "high"/"medium"/"low"
    confidence from where the relevant coverage ratio falls relative
    to CONF_HIGH_COVERAGE / CONF_MEDIUM_COVERAGE.
  - second_person_time_ratio: always available (it doesn't depend on
    the primary face passing face_ok), "low" confidence only for a
    small-but-nonzero ratio (< SECOND_PERSON_LOW_CONF_RATIO), which
    is as likely to be a misdetection as a real second person.
  - face_lost_count: always available, "high" confidence (an exact
    count of a directly-observed condition).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from . import config
from .signals import PreparedSignals


@dataclass
class Metric:
    key: str
    value: Optional[float]
    unit: str
    confidence: Optional[str]
    available: bool
    unavailable_reason: Optional[str]

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "unit": self.unit,
            "confidence": self.confidence,
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
            "definition_version": config.METRICS_VERSION,
        }


def _coverage_confidence(coverage: float) -> str:
    if coverage >= config.CONF_HIGH_COVERAGE:
        return "high"
    if coverage >= config.CONF_MEDIUM_COVERAGE:
        return "medium"
    return "low"


def _unavailable(key: str, unit: str, reason: str) -> Metric:
    return Metric(key=key, value=None, unit=unit, confidence=None, available=False, unavailable_reason=reason)


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


def _ratio_metric(
    key: str,
    unit: str,
    *,
    numerator: int,
    denominator: int,
    coverage_for_confidence: float,
    coverage_min: float,
    coverage_reason: str,
    round_to: int = config.ROUND_RATIO,
) -> Metric:
    if coverage_for_confidence < coverage_min:
        return _unavailable(key, unit, coverage_reason)
    if denominator <= 0:
        return _unavailable(key, unit, "no_data")

    value = round(numerator / denominator, round_to)
    return Metric(
        key=key,
        value=value,
        unit=unit,
        confidence=_coverage_confidence(coverage_for_confidence),
        available=True,
        unavailable_reason=None,
    )


def compute_metrics(p: PreparedSignals, events: list[dict]) -> list[dict]:
    n_total = p.grid_t.size
    n_analyzed = int((~p.in_gap).sum())

    # --- coverage metrics: always available -------------------------------

    analysis_coverage = Metric(
        key="analysis_coverage",
        value=round(n_analyzed / n_total, config.ROUND_RATIO) if n_total else None,
        unit="ratio",
        confidence="high" if n_total else None,
        available=n_total > 0,
        unavailable_reason=None if n_total else "no_data",
    )

    n_face_ok = int(p.face_ok.sum())
    face_coverage = (n_face_ok / n_analyzed) if n_analyzed else 0.0
    face_visibility = Metric(
        key="face_visibility",
        value=round(face_coverage, config.ROUND_RATIO) if n_analyzed else None,
        unit="ratio",
        confidence="high" if n_analyzed else None,
        available=n_analyzed > 0,
        unavailable_reason=None if n_analyzed else "no_data",
    )

    n_hands_visible = int(p.hand_any_visible.sum())
    hand_coverage = (n_hands_visible / n_analyzed) if n_analyzed else 0.0
    hand_visibility = Metric(
        key="hand_visibility",
        value=round(hand_coverage, config.ROUND_RATIO) if n_analyzed else None,
        unit="ratio",
        confidence="high" if n_analyzed else None,
        available=n_analyzed > 0,
        unavailable_reason=None if n_analyzed else "no_data",
    )

    # --- face-gated metrics -------------------------------------------------

    def _downgrade_if_uncalibrated(metric: Metric) -> Metric:
        # Same narrow scoping as events.py's gaze_away confidence: any
        # metric built from the camera-facing cone is only as good as
        # the calibration baseline it's measured against.
        if metric.available and p.facing_confidence_low:
            metric.confidence = "low"
        return metric

    camera_facing_ratio = _downgrade_if_uncalibrated(_ratio_metric(
        "camera_facing_ratio", "ratio",
        numerator=int((p.face_ok & p.facing).sum()),
        denominator=n_face_ok,
        coverage_for_confidence=face_coverage,
        coverage_min=config.FACE_COVERAGE_MIN,
        coverage_reason="low_face_coverage",
    ))

    gaze_away_mask = _mask_from_events(p.grid_t, events, "gaze_away") & p.face_ok
    gaze_away_time_ratio = _downgrade_if_uncalibrated(_ratio_metric(
        "gaze_away_time_ratio", "ratio",
        numerator=int(gaze_away_mask.sum()),
        denominator=n_face_ok,
        coverage_for_confidence=face_coverage,
        coverage_min=config.FACE_COVERAGE_MIN,
        coverage_reason="low_face_coverage",
    ))

    head_down_mask = _mask_from_events(p.grid_t, events, "head_down") & p.face_ok
    head_down_time_ratio = _ratio_metric(
        "head_down_time_ratio", "ratio",
        numerator=int(head_down_mask.sum()),
        denominator=n_face_ok,
        coverage_for_confidence=face_coverage,
        coverage_min=config.FACE_COVERAGE_MIN,
        coverage_reason="low_face_coverage",
    )

    # --- hand-gated metrics --------------------------------------------------

    speaking_s = float(p.speaking.sum()) / p.grid_hz
    gesture_events = [e for e in events if e["type"] == "gesture"]

    if hand_coverage < config.HANDS_COVERAGE_MIN:
        gesture_rate = _unavailable("gesture_rate", "per_min", "low_hand_coverage")
    elif speaking_s <= 0:
        gesture_rate = _unavailable("gesture_rate", "per_min", "no_speaking_time")
    else:
        gesture_rate = Metric(
            key="gesture_rate",
            value=round(len(gesture_events) / (speaking_s / 60.0), config.ROUND_RATE),
            unit="per_min",
            confidence=_coverage_confidence(hand_coverage),
            available=True,
            unavailable_reason=None,
        )

    if hand_coverage < config.HANDS_COVERAGE_MIN:
        gesture_amplitude_avg = _unavailable("gesture_amplitude_avg", "amplitude", "low_hand_coverage")
    elif not gesture_events:
        gesture_amplitude_avg = _unavailable("gesture_amplitude_avg", "amplitude", "no_gesture_events")
    else:
        mean_amplitude = float(np.mean([e["attributes"]["amplitude"] for e in gesture_events]))
        gesture_amplitude_avg = Metric(
            key="gesture_amplitude_avg",
            value=round(mean_amplitude, config.ROUND_AMPLITUDE),
            unit="amplitude",
            confidence=_coverage_confidence(hand_coverage),
            available=True,
            unavailable_reason=None,
        )

    hands_still_mask = _mask_from_events(p.grid_t, events, "hands_still") & p.hand_any_visible
    hands_still_time_ratio = _ratio_metric(
        "hands_still_time_ratio", "ratio",
        numerator=int(hands_still_mask.sum()),
        denominator=n_hands_visible,
        coverage_for_confidence=hand_coverage,
        coverage_min=config.HANDS_COVERAGE_MIN,
        coverage_reason="low_hand_coverage",
    )

    # --- ungated metrics -------------------------------------------------

    n_second_person = int((p.face_count == 2).sum())
    second_person_ratio = (n_second_person / n_analyzed) if n_analyzed else 0.0
    if n_analyzed == 0:
        second_person_time_ratio = _unavailable("second_person_time_ratio", "ratio", "no_data")
    else:
        if 0.0 < second_person_ratio < config.SECOND_PERSON_LOW_CONF_RATIO:
            sp_confidence = "low"
        else:
            sp_confidence = "high"
        second_person_time_ratio = Metric(
            key="second_person_time_ratio",
            value=round(second_person_ratio, config.ROUND_RATIO),
            unit="ratio",
            confidence=sp_confidence,
            available=True,
            unavailable_reason=None,
        )

    face_lost_count = Metric(
        key="face_lost_count",
        value=float(len([e for e in events if e["type"] == "face_lost"])),
        unit="count",
        confidence="high",
        available=True,
        unavailable_reason=None,
    )

    return [
        m.to_dict()
        for m in (
            analysis_coverage,
            face_visibility,
            hand_visibility,
            camera_facing_ratio,
            gaze_away_time_ratio,
            head_down_time_ratio,
            gesture_rate,
            gesture_amplitude_avg,
            hands_still_time_ratio,
            second_person_time_ratio,
            face_lost_count,
        )
    ]
