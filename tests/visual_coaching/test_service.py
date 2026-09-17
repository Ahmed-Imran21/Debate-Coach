"""
§7.1/§7.5: visual_coaching/service.py's orchestration -- the LLM call
itself is faked (FakeAPIClient), so these tests exercise the retry-
once-then-drop flow and document assembly without a network call.
"""

import json

import pytest

from api.models import APIResponse
from visual_coaching.service import MODEL, generate_visual_coaching


class FakeAPIClient:
    def __init__(self, responses: list[dict | Exception]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return APIResponse(request_id="r", api_key_id="k", success=True, content=json.dumps(item))


def _video_analysis(**overrides) -> dict:
    base = {
        "status": "complete",
        "metrics_version": "visual-metrics-1.0",
        "metrics": {
            "camera_facing_ratio": {"status": "ok", "confidence": "high"},
        },
        "quality": {
            "clock_uncertainty_ms": 150,
            "context": {"setting": "camera_audience", "uses_notes": False},
            "face_tracked_ratio": 0.9,
            "hands_visible_ratio": {"any": 0.8},
            "warnings": [],
        },
        "series": {"resolution_s": 1.0, "camera_facing": [], "hand_activity": [], "head_motion": []},
        "events": [],
    }
    base.update(overrides)
    return base


def _transcription() -> dict:
    return {"segments": [{"start": 0.0, "end": 1.0, "text": "Hi", "words": [{"word": "Hi", "start": 0.0, "end": 0.5}]}]}


def _run(fake_client, video_analysis=None):
    return generate_visual_coaching(
        session_id="s-1",
        transcription=_transcription(),
        audio_analysis={"speech_duration": 60.0, "speech_segments": [], "pauses": []},
        raw_metrics={"fillers": {"instances": []}},
        speech_content={"segments": []},
        video_analysis=video_analysis or _video_analysis(),
        api_client=fake_client,
        on_queued=None,
    )


VALID_RESPONSE = {
    "visual_feedback": [{
        "id": "vf_1", "category": "gaze", "polarity": "improve",
        "moment_id": None, "metric_keys": ["camera_facing_ratio"], "observation_ids": [],
        "coaching": "Try to look at the lens a bit more while you speak.",
    }],
    "summary": "Solid overall delivery with room to grow.",
}

INVALID_RESPONSE = {
    "visual_feedback": [{
        "id": "vf_1", "category": "gaze", "polarity": "improve",
        "moment_id": None, "metric_keys": ["camera_facing_ratio"], "observation_ids": [],
        "coaching": "You paused for about 4 seconds there.",  # number content -- violates rule 4
    }],
    "summary": "s",
}


def test_happy_path_completes_without_retry():
    client = FakeAPIClient([VALID_RESPONSE])
    outcome = _run(client)

    assert outcome.status == "completed"
    assert len(client.calls) == 1
    assert outcome.document["visual_feedback"][0]["id"] == "vf_1"
    assert outcome.document["summary"] == "Solid overall delivery with room to grow."
    assert outcome.document["validation"] == {"retried": False, "dropped_items": 0}
    assert outcome.document["model"] == MODEL
    assert outcome.document["correlated_moments"] == []


def test_retries_once_on_violation_and_succeeds():
    client = FakeAPIClient([INVALID_RESPONSE, VALID_RESPONSE])
    outcome = _run(client)

    assert outcome.status == "completed"
    assert len(client.calls) == 2
    assert outcome.document["validation"]["retried"] is True
    # the retry message lists rule names, never the offending text.
    retry_messages = [m["content"] for m in client.calls[1]["messages"] if "violated" in m["content"]]
    assert retry_messages
    assert "number_content" in retry_messages[0]
    assert "4 seconds" not in retry_messages[0]


def test_still_invalid_after_retry_drops_items_and_fails():
    client = FakeAPIClient([INVALID_RESPONSE, INVALID_RESPONSE])
    outcome = _run(client)

    assert len(client.calls) == 2
    assert outcome.status == "failed"
    assert outcome.document["visual_feedback"] == []
    assert outcome.document["validation"]["retried"] is True
    assert outcome.document["validation"]["dropped_items"] == 1


def test_llm_failure_produces_failed_status_but_keeps_moments():
    client = FakeAPIClient([RuntimeError("network down")])
    outcome = _run(client)

    assert outcome.status == "failed"
    assert outcome.document["visual_feedback"] == []
    assert outcome.document["correlated_moments"] == []  # still present, just empty here
    assert "correlated_moments" in outcome.document


def test_calls_llm_with_json_mode_and_expected_provider():
    client = FakeAPIClient([VALID_RESPONSE])
    _run(client)

    call = client.calls[0]
    assert call["response_format"] == "json"
    assert call["task"] == "visual_coaching"
    assert call["provider"] == "groq"
    assert call["model"] == MODEL
    assert call["messages"][0]["role"] == "system"


def test_in_room_practice_omits_camera_facing_from_sent_metrics():
    # A response that doesn't cite camera_facing_ratio -- in_room_practice
    # means it's never sent, so citing it here would (correctly) fail
    # validation and trigger an unrelated retry this test isn't about.
    response = {**VALID_RESPONSE, "visual_feedback": [{**VALID_RESPONSE["visual_feedback"][0], "metric_keys": []}]}
    client = FakeAPIClient([response])
    va = _video_analysis()
    va["quality"]["context"]["setting"] = "in_room_practice"
    _run(client, video_analysis=va)

    user_message = client.calls[0]["messages"][1]["content"]
    payload = json.loads(user_message)
    keys = {m["key"] for m in payload["metrics"]}
    assert "camera_facing_ratio" not in keys
