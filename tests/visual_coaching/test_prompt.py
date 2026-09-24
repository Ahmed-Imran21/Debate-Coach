"""§7.2: deterministic prompt payload assembly -- no raw numbers out."""

import json

from visual_coaching.prompt import (
    _duration_bucket,
    _observation_description,
    build_argument_summary,
    build_input_payload,
    build_metrics_payload,
    build_moments_payload,
    build_quality_payload,
)


def _video_analysis(**overrides) -> dict:
    base = {
        "quality": {
            "face_tracked_ratio": 0.9,
            "hands_visible_ratio": {"any": 0.8},
            "warnings": [],
            "context": {"setting": "camera_audience", "uses_notes": False},
        },
        "metrics": {
            "face_tracked_ratio": {"status": "ok", "confidence": "high"},
            "camera_facing_ratio": {"status": "ok", "confidence": "medium"},
            "gaze_away_events_per_min": {"status": "insufficient_coverage"},
            "hands_visible_ratio": {"status": "ok", "confidence": "high"},
        },
    }
    base.update(overrides)
    return base


def test_ok_metrics_get_plain_and_level_never_a_value():
    payload = build_metrics_payload(_video_analysis())
    by_key = {m["key"]: m for m in payload}

    facing = by_key["camera_facing_ratio"]
    assert facing["status"] == "ok"
    assert facing["confidence"] == "medium"
    assert "plain" in facing and isinstance(facing["plain"], str)
    assert "level" in facing
    assert "value" not in facing


def test_non_ok_metrics_send_status_only():
    payload = build_metrics_payload(_video_analysis())
    by_key = {m["key"]: m for m in payload}

    gaze = by_key["gaze_away_events_per_min"]
    assert gaze == {"key": "gaze_away_events_per_min", "status": "insufficient_coverage"}


def test_in_room_practice_omits_camera_facing_metrics_entirely():
    va = _video_analysis()
    va["quality"]["context"]["setting"] = "in_room_practice"
    payload = build_metrics_payload(va)
    keys = {m["key"] for m in payload}

    assert "camera_facing_ratio" not in keys
    assert "gaze_away_events_per_min" not in keys
    assert "face_tracked_ratio" in keys  # not a camera-facing-cone metric


def test_quality_payload_buckets_coverage_and_flags_disabled_tier():
    payload = build_quality_payload(_video_analysis())
    assert payload["face_tracked"] == "high"  # 0.9 >= CONF_HIGH_COVERAGE (0.85)
    assert payload["hands_visible"] == "medium"  # 0.8 is >= CONF_MEDIUM_COVERAGE (0.60) but < 0.85

    va = _video_analysis()
    va["metrics"]["hands_visible_ratio"] = {"status": "disabled_by_tier"}
    assert build_quality_payload(va)["hands_visible"] == "not_available"


def test_duration_bucket_boundaries():
    assert _duration_bucket(1.9) == "brief"
    assert _duration_bucket(2.0) == "sustained"
    assert _duration_bucket(5.0) == "sustained"
    assert _duration_bucket(5.1) == "long"


def test_gaze_away_observation_matches_the_spec_example_phrasing():
    obs = {"id": "o_01a", "kind": "event", "event_ref": "ve_0088", "type": "gaze_away", "duration_s": 4.2, "direction": "down"}
    assert _observation_description(obs) == "looked down for a sustained stretch"


def test_metric_observations_produce_nonempty_descriptions():
    for obs in (
        {"kind": "metric", "metric": "camera_facing_ratio", "unit_value": 0.2, "session_value": 0.8},
        {"kind": "metric", "metric": "head_down_fraction", "unit_value": 0.7, "session_value": None},
        {"kind": "metric", "metric": "hands_still_fraction", "unit_value": 0.9, "session_value": None},
        {"kind": "metric", "metric": "hand_activity_ratio", "unit_value": 2.5, "session_value": 1.0},
    ):
        description = _observation_description(obs)
        assert isinstance(description, str) and description


def test_moments_payload_formats_time_and_maps_observations():
    moments = [{
        "id": "m_01", "rule_id": "long_gaze_away_in_key_unit@1", "polarity": "improve",
        "anchor": {"argument_unit_id": "au_07", "type": "conclusion"},
        "start": 272.4, "end": 289.0,
        "excerpt_text": "hello world",
        "observations": [{"id": "o_01a", "kind": "event", "event_ref": "ve_0088", "type": "gaze_away", "duration_s": 4.2, "direction": "down"}],
    }]
    payload = build_moments_payload(moments)
    assert payload[0]["time"] == "04:32-04:49"
    assert payload[0]["unit_type"] == "conclusion"
    assert payload[0]["excerpt"] == "hello world"
    assert payload[0]["observations"] == [{"id": "o_01a", "description": "looked down for a sustained stretch"}]


def test_argument_summary_only_includes_referenced_units_and_dedupes():
    moments = [
        {"anchor": {"argument_unit_id": "au_01", "type": "claim"}},
        {"anchor": {"argument_unit_id": "au_01", "type": "claim"}},  # same unit twice
        {"anchor": {"argument_unit_id": "au_02", "type": "rebuttal"}},
    ]
    segments = [
        {"id": "au_01", "type": "claim", "summary": "First point."},
        {"id": "au_02", "type": "rebuttal", "summary": "Second point."},
        {"id": "au_03", "type": "conclusion", "summary": "Never referenced."},
    ]
    summary = build_argument_summary(moments, segments)
    assert {s["id"] for s in summary} == {"au_01", "au_02"}


def test_build_input_payload_is_json_serializable_and_includes_speech_duration():
    payload = build_input_payload(_video_analysis(), [], [], speech_duration_s=391.2)
    assert payload["context"]["speech_duration_s"] == 391.2
    json.dumps(payload)  # must not raise
