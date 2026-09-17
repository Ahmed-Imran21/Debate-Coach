"""
Correlated moments (§6.2): pure rule-based pairing of visual events
with "key" argument units (claim, rebuttal, conclusion), each a
candidate coaching moment with a deterministically-computed
salience. No LLM here -- visual_coaching/service.py sends the
selected moments to the LLM afterward; this module only selects and
describes them from data.

Two things are computed once per key unit and shared across every
rule that needs them, rather than each rule re-deriving them:
  - unit_facing / unit_face_cov: mean / coverage of the "camera_facing"
    series bins overlapping the unit's span.
  - unit_hand_cov / unit_hand_activity: same, for "hand_activity".
The series (§5.6) is 1Hz-resolution and already stored in
video_analysis.json, so this reuses it rather than needing raw
per-grid-point signals, which aren't available at this stage (this
module runs against stored artifacts, not the in-memory
PreparedSignals from visual_analysis.pipeline).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from speech_analysis.models.speech_content import KEY_UNIT_TYPES
from visual_analysis import config

from .timeline import SessionTimeline


MIN_UNIT_DURATION_S = 3.0
MAX_MOMENTS = 8
MAX_PER_RULE = 3

TYPE_WEIGHT = {"conclusion": 0.4, "rebuttal": 0.35, "claim": 0.3}

# Rules 1-4 flag something to work on; rule 5 is the one positive
# (strength) rule -- see the module docstring in the spec excerpt
# this was built from (§6.2's table has no explicit polarity column,
# but its own "keep one of each polarity per unit" selection rule
# only makes sense if each rule has a fixed polarity, and
# physical_emphasis_in_key_unit@1 is the only one whose salience
# formula is parenthetically marked "(polarity strength)").
_POLARITY = {
    "long_gaze_away_in_key_unit@1": "improve",
    "low_camera_facing_in_key_unit@1": "improve",
    "head_down_in_key_unit@1": "improve",
    "hands_still_in_key_unit@1": "improve",
    "physical_emphasis_in_key_unit@1": "strength",
}


@dataclass
class _UnitContext:
    unit: dict
    duration: float
    unit_facing: Optional[float]
    unit_face_cov: float
    unit_hand_cov: float
    unit_hand_activity: Optional[float]


def _overlap_duration(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def _bin_range(start: float, end: float, resolution: float, n_bins: int) -> range:
    lo = max(0, int(start // resolution))
    hi = min(n_bins, int(math.ceil(end / resolution)))
    return range(lo, hi)


def _series_stats(series: list, start: float, end: float, resolution: float) -> tuple[Optional[float], float]:
    """(mean of non-null bins overlapping [start, end], coverage = fraction non-null)."""

    indices = list(_bin_range(start, end, resolution, len(series)))
    if not indices:
        return None, 0.0
    values = [series[i] for i in indices if series[i] is not None]
    coverage = len(values) / len(indices)
    mean = sum(values) / len(values) if values else None
    return mean, coverage


def _event_time_fraction(events: list[dict], event_type: str, unit_start: float, unit_end: float) -> float:
    duration = unit_end - unit_start
    if duration <= 0:
        return 0.0
    total = sum(
        _overlap_duration(e["start"], e["end"], unit_start, unit_end)
        for e in events if e["type"] == event_type
    )
    return total / duration


def _median(values: list[float]) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def _unit_context(unit: dict, series: dict) -> _UnitContext:
    start, end = unit["start"], unit["end"]
    resolution = series["resolution_s"]
    facing_mean, face_cov = _series_stats(series["camera_facing"], start, end, resolution)
    hand_mean, hand_cov = _series_stats(series["hand_activity"], start, end, resolution)
    return _UnitContext(
        unit=unit, duration=end - start,
        unit_facing=facing_mean, unit_face_cov=face_cov,
        unit_hand_cov=hand_cov, unit_hand_activity=hand_mean,
    )


def _observation(kind: str, **fields) -> dict:
    return {"kind": kind, **fields}


def _candidate(rule_id: str, ctx: _UnitContext, salience: float, observations: list[dict]) -> dict:
    return {
        "rule_id": rule_id,
        "polarity": _POLARITY[rule_id],
        "anchor": {"argument_unit_id": ctx.unit["id"], "type": ctx.unit["type"]},
        "segment_ids": list(ctx.unit.get("segment_ids", [])),
        "start": ctx.unit["start"],
        "end": ctx.unit["end"],
        "salience": min(1.0, salience),
        "_observations": observations,
    }


# ---------------------------------------------------------------
# The 5 rules
# ---------------------------------------------------------------

def _rule_long_gaze_away(ctx: _UnitContext, events: list[dict], session_facing: Optional[float], camera_audience: bool) -> Optional[dict]:
    if not camera_audience:
        return None
    best = None
    for e in events:
        if e["type"] != "gaze_away":
            continue
        duration = e["end"] - e["start"]
        if duration < 3.0:
            continue
        overlap = _overlap_duration(e["start"], e["end"], ctx.unit["start"], ctx.unit["end"])
        if overlap / duration < 0.5:
            continue
        if best is None or duration > (best["end"] - best["start"]):
            best = e
    if best is None:
        return None

    duration = best["end"] - best["start"]
    salience = min(1.0, duration / 8.0) * 0.6 + TYPE_WEIGHT[ctx.unit["type"]]
    observations = [
        _observation("event", event_ref=best["id"], type="gaze_away", duration_s=round(duration, 1), direction=best["attributes"].get("direction")),
    ]
    if session_facing is not None and ctx.unit_facing is not None:
        observations.append(_observation("metric", metric="camera_facing_ratio", unit_value=round(ctx.unit_facing, 3), session_value=round(session_facing, 3)))
    return _candidate("long_gaze_away_in_key_unit@1", ctx, salience, observations)


def _rule_low_camera_facing(ctx: _UnitContext, session_facing: Optional[float], camera_audience: bool) -> Optional[dict]:
    if not camera_audience or session_facing is None or ctx.unit_facing is None:
        return None
    if ctx.unit_face_cov < 0.6:
        return None
    if ctx.unit_facing > session_facing - 0.25:
        return None

    salience = min(1.0, (session_facing - ctx.unit_facing) / 0.5) * 0.6 + TYPE_WEIGHT[ctx.unit["type"]]
    observations = [
        _observation("metric", metric="camera_facing_ratio", unit_value=round(ctx.unit_facing, 3), session_value=round(session_facing, 3)),
    ]
    return _candidate("low_camera_facing_in_key_unit@1", ctx, salience, observations)


def _rule_head_down(ctx: _UnitContext, events: list[dict], uses_notes: bool) -> Optional[dict]:
    if uses_notes and ctx.unit["type"] == "claim":
        return None
    fraction = _event_time_fraction(events, "head_down", ctx.unit["start"], ctx.unit["end"])
    if fraction < 0.5:
        return None

    salience = fraction * 0.6 + TYPE_WEIGHT[ctx.unit["type"]]
    observations = [_observation("metric", metric="head_down_fraction", unit_value=round(fraction, 3), session_value=None)]
    return _candidate("head_down_in_key_unit@1", ctx, salience, observations)


def _rule_hands_still(ctx: _UnitContext, events: list[dict]) -> Optional[dict]:
    if ctx.unit_hand_cov < 0.5:
        return None
    fraction = _event_time_fraction(events, "hands_still", ctx.unit["start"], ctx.unit["end"])
    if fraction < 0.6:
        return None

    salience = fraction * 0.5 + TYPE_WEIGHT[ctx.unit["type"]]
    observations = [_observation("metric", metric="hands_still_fraction", unit_value=round(fraction, 3), session_value=None)]
    return _candidate("hands_still_in_key_unit@1", ctx, salience, observations)


def _rule_physical_emphasis(ctx: _UnitContext, session_facing: Optional[float], session_hand_activity_median: Optional[float], in_room_practice: bool) -> Optional[dict]:
    if ctx.unit["type"] not in ("rebuttal", "conclusion"):
        return None
    if ctx.unit_hand_cov < 0.5 or ctx.unit_hand_activity is None:
        return None
    if not session_hand_activity_median or session_hand_activity_median <= 0:
        return None
    if ctx.unit_hand_activity < 1.5 * session_hand_activity_median:
        return None
    if not (in_room_practice or (session_facing is not None and ctx.unit_facing is not None and ctx.unit_facing >= session_facing)):
        return None

    activity_ratio = ctx.unit_hand_activity / session_hand_activity_median
    salience = min(1.0, activity_ratio / 3.0) * 0.5 + TYPE_WEIGHT[ctx.unit["type"]]
    observations = [
        _observation("metric", metric="hand_activity_ratio", unit_value=round(activity_ratio, 3), session_value=1.0),
    ]
    if ctx.unit_facing is not None:
        observations.append(_observation("metric", metric="camera_facing_ratio", unit_value=round(ctx.unit_facing, 3), session_value=round(session_facing, 3) if session_facing is not None else None))
    return _candidate("physical_emphasis_in_key_unit@1", ctx, salience, observations)


# ---------------------------------------------------------------
# Selection (§6.2)
# ---------------------------------------------------------------

def _dedup_by_unit_and_polarity(candidates: list[dict]) -> list[dict]:
    best: dict[tuple[str, str], dict] = {}
    for c in candidates:
        key = (c["anchor"]["argument_unit_id"], c["polarity"])
        if key not in best or c["salience"] > best[key]["salience"]:
            best[key] = c
    return list(best.values())


def _cap_per_rule(candidates: list[dict], max_per_rule: int) -> list[dict]:
    by_rule: dict[str, list[dict]] = {}
    for c in candidates:
        by_rule.setdefault(c["rule_id"], []).append(c)
    kept: list[dict] = []
    for rule_candidates in by_rule.values():
        rule_candidates.sort(key=lambda c: c["salience"], reverse=True)
        kept.extend(rule_candidates[:max_per_rule])
    return kept


def _finalize_moments(candidates: list[dict], canonical) -> list[dict]:
    moments = []
    for index, c in enumerate(candidates, start=1):
        moment_id = f"m_{index:02d}"
        word_range = canonical.word_range_for(c["segment_ids"])

        observations = []
        for obs_index, obs in enumerate(c["_observations"]):
            suffix = chr(ord("a") + obs_index)
            observations.append({"id": f"o_{index:02d}{suffix}", **obs})

        moment = {
            "id": moment_id,
            "rule_id": c["rule_id"],
            "polarity": c["polarity"],
            "anchor": {"argument_unit_id": c["anchor"]["argument_unit_id"], "type": c["anchor"]["type"]},
            "start": round(c["start"], 1),
            "end": round(c["end"], 1),
            "excerpt_word_range": list(word_range) if word_range else None,
            "excerpt_text": canonical.excerpt(word_range) if word_range else "",
            "observations": observations,
            "salience": round(c["salience"], 3),
        }
        moments.append(moment)
    return moments


def build_correlated_moments(timeline: SessionTimeline, video_analysis: dict) -> list[dict]:
    if video_analysis.get("status") not in ("complete", "partial"):
        return []

    quality = video_analysis.get("quality", {})
    if quality.get("clock_uncertainty_ms", 0) > config.CLOCK_UNCERTAINTY_MAX_MS_FOR_MOMENTS:
        return []

    series = video_analysis.get("series")
    if not series:
        return []

    context = quality.get("context", {})
    camera_audience = context.get("setting") == "camera_audience"
    in_room_practice = context.get("setting") == "in_room_practice"
    uses_notes = bool(context.get("uses_notes"))

    metrics = video_analysis.get("metrics", {})
    facing_metric = metrics.get("camera_facing_ratio", {})
    session_facing = facing_metric.get("value") if facing_metric.get("status") == "ok" else None

    hand_bins = [v for v in series.get("hand_activity", []) if v is not None]
    session_hand_activity_median = _median(hand_bins)

    events = timeline.visual_events

    key_units = [
        u for u in timeline.argument_units
        if u.get("type") in KEY_UNIT_TYPES and u.get("start") is not None and u.get("end") is not None
        and (u["end"] - u["start"]) >= MIN_UNIT_DURATION_S
    ]

    candidates: list[dict] = []
    for unit in key_units:
        ctx = _unit_context(unit, series)

        for candidate in (
            _rule_long_gaze_away(ctx, events, session_facing, camera_audience),
            _rule_low_camera_facing(ctx, session_facing, camera_audience),
            _rule_head_down(ctx, events, uses_notes),
            _rule_hands_still(ctx, events),
            _rule_physical_emphasis(ctx, session_facing, session_hand_activity_median, in_room_practice),
        ):
            if candidate is not None:
                candidates.append(candidate)

    candidates = _dedup_by_unit_and_polarity(candidates)
    candidates = _cap_per_rule(candidates, MAX_PER_RULE)
    candidates.sort(key=lambda c: c["salience"], reverse=True)
    candidates = candidates[:MAX_MOMENTS]

    return _finalize_moments(candidates, timeline.canonical)
