"""§6.1: SessionTimeline assembly from already-loaded artifact dicts."""

from session_timeline.timeline import build_timeline


def _transcription() -> dict:
    return {
        "segments": [
            {
                "start": 0.0, "end": 2.0, "text": "Hello there",
                "words": [
                    {"word": "Hello", "start": 0.0, "end": 0.5},
                    {"word": "there", "start": 0.6, "end": 1.0},
                ],
            },
        ],
    }


def test_build_timeline_maps_every_source_correctly():
    transcription = _transcription()
    audio_analysis = {
        "speech_segments": [{"start": 0.0, "end": 2.0, "duration": 2.0}],
        "pauses": [{"start": 2.0, "end": 2.5, "duration": 0.5}],
    }
    raw_metrics = {"fillers": {"instances": [{"word": "um", "start": 1.0, "end": 1.2, "probability": 0.9}]}}
    speech_content = {
        "session_id": "s-1",
        "segments": [
            {"id": "au_01", "type": "claim", "start": 0.0, "end": 2.0, "segment_ids": ["s_000"], "text": "…", "labels": ["claim"]},
            # missing segment_ids -- must be dropped, not crash.
            {"start": 2.0, "end": 3.0, "text": "…", "labels": []},
        ],
    }
    video_analysis = {"events": [{"id": "ve_0001", "type": "gaze_away", "start": 1.0, "end": 2.0, "confidence": "high", "attributes": {}}]}

    timeline = build_timeline("s-1", transcription, audio_analysis, raw_metrics, speech_content, video_analysis)

    assert timeline.session_id == "s-1"
    assert [w.text for w in timeline.canonical.words] == ["Hello", "there"]
    assert timeline.speech_segments == [{"start": 0.0, "end": 2.0, "duration": 2.0}]
    assert timeline.pauses == [{"start": 2.0, "end": 2.5, "duration": 0.5}]
    assert timeline.fillers == [{"word": "um", "start": 1.0, "end": 1.2, "probability": 0.9}]
    assert timeline.argument_units == [{"id": "au_01", "type": "claim", "start": 0.0, "end": 2.0, "segment_ids": ["s_000"]}]
    assert timeline.visual_events == video_analysis["events"]


def test_build_timeline_without_video_analysis_has_empty_visual_events():
    timeline = build_timeline("s-1", _transcription(), {"speech_segments": [], "pauses": []}, {}, {"segments": []}, None)
    assert timeline.visual_events == []


def test_to_dict_matches_the_tracks_shape():
    timeline = build_timeline(
        "s-1", _transcription(),
        {"speech_segments": [], "pauses": []},
        {},
        {"segments": []},
        None,
    )
    d = timeline.to_dict()
    assert d["session_id"] == "s-1"
    assert set(d["tracks"].keys()) == {"words", "speech_segments", "pauses", "fillers", "argument_units", "visual_events"}
    assert d["tracks"]["words"][0]["text"] == "Hello"
