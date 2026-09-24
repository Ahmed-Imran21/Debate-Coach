"""
Visual coaching prompt assembly (§7.2, §7.3). Every number is
converted to a status, a confidence, or a deterministically-bucketed
plain-English description before it reaches the LLM -- no raw value,
ratio, count, or duration is ever sent. That's what makes an
invented number in the output impossible to confuse with a real one,
not just something the validator happens to catch afterward.
"""

from __future__ import annotations

import json
from typing import Optional

from visual_analysis import config as visual_config


SYSTEM_PROMPT = """You are a debate delivery coach. You receive measurements already computed by software. Do not measure, estimate, or state any numbers, percentages, counts, or durations. Refer to evidence only by the provided IDs.

Describe observable behaviour only. Never describe or guess emotions, feelings, personality, or mental state. Forbidden examples: nervous, anxious, confident, insecure, dishonest, scared, bored, stressed.

Looking away is not inherently a problem; comment on it only when it is tied to a provided moment.

Do not comment on a metric whose status is not ok, except to note briefly that it could not be assessed (category coverage), at most once.

Interpretation must be framed as its effect on the audience and paired with a concrete, practical suggestion.

Balance: include at least one strength if any moment has polarity strength or any metric supports one.

Maximum 6 items. Each coaching field: 1 to 3 sentences, plain English, no em dashes, no emojis.

Output only JSON matching the schema."""


# Metrics built from the camera-facing cone (§5.3's `facing`) --
# omitted from the payload entirely in in_room_practice context,
# where facing the camera isn't a meaningful thing to coach on. Same
# set as visual_analysis/metrics.py's _CALIBRATION_SENSITIVE_KEYS,
# which represents the same underlying concept.
_CAMERA_FACING_METRIC_KEYS = frozenset({
    "camera_facing_ratio", "gaze_away_events_per_min", "longest_gaze_away_s",
})

# (plain description, level) per metric. "level" is a coaching-
# relevant direction hint, not shown to the user -- it's the closest
# thing to a value the model gets, and it's a category, never a
# number. Not given verbatim in the spec beyond camera_facing_ratio's
# own example; the rest are written to match that example's style.
_METRIC_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "face_tracked_ratio": ("share of speaking time your face was visible to the camera", "coverage_only"),
    "camera_facing_ratio": ("share of speaking time facing the camera", "higher_is_usually_better"),
    "gaze_away_events_per_min": ("how often you looked away from the camera, per minute of speaking", "lower_is_usually_better"),
    "longest_gaze_away_s": ("the longest single stretch you looked away from the camera", "lower_is_usually_better"),
    "head_down_ratio": ("share of speaking time your head was tilted down", "lower_is_usually_better"),
    "head_motion_median_deg_s": ("your typical head movement speed", "context_dependent"),
    "hands_visible_ratio": ("share of speaking time your hands were visible on camera", "coverage_only"),
    "gesture_rate_per_min": ("how often you made a hand gesture, per minute of speaking", "context_dependent"),
    "gesture_amplitude_median": ("the typical size of your hand gestures", "context_dependent"),
    "hands_still_longest_s": ("the longest stretch your hands stayed still", "lower_is_usually_better"),
    "hands_still_ratio": ("share of speaking time your hands stayed still", "lower_is_usually_better"),
}


def _coverage_level(ratio: Optional[float]) -> str:
    if ratio is None:
        return "not_available"
    if ratio >= visual_config.CONF_HIGH_COVERAGE:
        return "high"
    if ratio >= visual_config.CONF_MEDIUM_COVERAGE:
        return "medium"
    return "low"


def build_quality_payload(video_analysis: dict) -> dict:
    quality = video_analysis.get("quality", {})
    metrics = video_analysis.get("metrics", {})

    hands_status = metrics.get("hands_visible_ratio", {}).get("status")
    if hands_status == "disabled_by_tier":
        hands_level = "not_available"
    else:
        hands_level = _coverage_level(quality.get("hands_visible_ratio", {}).get("any"))

    return {
        "face_tracked": _coverage_level(quality.get("face_tracked_ratio")),
        "hands_visible": hands_level,
        "warnings": list(quality.get("warnings", [])),
    }


def build_metrics_payload(video_analysis: dict) -> list[dict]:
    metrics = video_analysis.get("metrics", {})
    in_room = video_analysis.get("quality", {}).get("context", {}).get("setting") == "in_room_practice"

    payload = []
    for key, m in metrics.items():
        if in_room and key in _CAMERA_FACING_METRIC_KEYS:
            continue

        if m.get("status") != "ok":
            payload.append({"key": key, "status": m.get("status")})
            continue

        plain, level = _METRIC_DESCRIPTIONS.get(key, (key, "context_dependent"))
        payload.append({
            "key": key,
            "status": "ok",
            "confidence": m.get("confidence"),
            "plain": plain,
            "level": level,
        })
    return payload


def _duration_bucket(seconds: float) -> str:
    if seconds < 2.0:
        return "brief"
    if seconds <= 5.0:
        return "sustained"
    return "long"


def _facing_delta_phrase(unit_value: float, session_value: Optional[float]) -> str:
    if session_value is None:
        return "facing the camera"
    delta = session_value - unit_value
    if delta >= 0.35:
        return "facing the camera well below your usual level for this part of the session"
    if delta >= 0.15:
        return "facing the camera below your usual level for this part of the session"
    if delta > -0.15:
        return "facing the camera close to your usual level for this part of the session"
    return "facing the camera above your usual level for this part of the session"


def _fraction_phrase(fraction: float) -> str:
    if fraction < 0.6:
        return "part of"
    if fraction < 0.85:
        return "most of"
    return "nearly all of"


def _activity_phrase(ratio: float) -> str:
    return "noticeably more animated than your typical pace" if ratio >= 2.0 else "more animated than your typical pace"


def _observation_description(obs: dict) -> str:
    if obs["kind"] == "event" and obs.get("type") == "gaze_away":
        bucket = _duration_bucket(obs["duration_s"])
        direction = obs.get("direction") or "away"
        return f"looked {direction} for a {bucket} stretch"

    metric = obs.get("metric")
    if metric == "camera_facing_ratio":
        return _facing_delta_phrase(obs["unit_value"], obs.get("session_value"))
    if metric == "head_down_fraction":
        return f"head tilted down for {_fraction_phrase(obs['unit_value'])} this part of the speech"
    if metric == "hands_still_fraction":
        return f"hands stayed still for {_fraction_phrase(obs['unit_value'])} this part of the speech"
    if metric == "hand_activity_ratio":
        return f"hand movement was {_activity_phrase(obs['unit_value'])}"

    return "an observed change in delivery"


def _format_time_range(start: float, end: float) -> str:
    def fmt(t: float) -> str:
        total = int(round(t))
        return f"{total // 60:02d}:{total % 60:02d}"
    return f"{fmt(start)}-{fmt(end)}"


def build_moments_payload(moments: list[dict]) -> list[dict]:
    payload = []
    for m in moments:
        payload.append({
            "id": m["id"],
            "rule_id": m["rule_id"],
            "polarity": m["polarity"],
            "unit_type": m["anchor"]["type"],
            "time": _format_time_range(m["start"], m["end"]),
            "excerpt": m.get("excerpt_text", ""),
            "observations": [
                {"id": o["id"], "description": _observation_description(o)}
                for o in m["observations"]
            ],
        })
    return payload


def build_argument_summary(moments: list[dict], speech_content_segments: list[dict]) -> list[dict]:
    """Summaries only for units a selected moment actually anchors to."""

    unit_ids = {m["anchor"]["argument_unit_id"] for m in moments}
    by_id = {seg["id"]: seg for seg in speech_content_segments if seg.get("id")}

    summary = []
    for unit_id in unit_ids:
        seg = by_id.get(unit_id)
        if seg is None:
            continue
        summary.append({"id": unit_id, "type": seg.get("type"), "summary": seg.get("summary", "")})
    return summary


def build_input_payload(
    video_analysis: dict,
    moments: list[dict],
    speech_content_segments: list[dict],
    speech_duration_s: float,
) -> dict:
    quality = video_analysis.get("quality", {})
    context = quality.get("context", {})

    return {
        # speech_duration_s is sent per §7.2's own shown example
        # payload -- it's session-level context for the model, not a
        # delivery measurement about the speaker's own behavior, so
        # it isn't covered by "do not send numeric metric values".
        "context": {
            "setting": context.get("setting"),
            "uses_notes": context.get("uses_notes"),
            "speech_duration_s": round(speech_duration_s, 1),
        },
        "quality": build_quality_payload(video_analysis),
        "metrics": build_metrics_payload(video_analysis),
        "moments": build_moments_payload(moments),
        "argument_summary": build_argument_summary(moments, speech_content_segments),
    }


def build_user_prompt(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
