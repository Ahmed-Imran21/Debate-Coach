"""
Argument analysis: the output structure every consumer reads
(coaching_engine validators require {start, end, text, labels};
the report reads fallacy_type) plus the segment-id anchoring
rules from Prerequisite B. The LLM is mocked throughout.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pytest

from audio.transcript_shape import to_canonical
from speech_analysis.llm.response_parser import (
    anchor_units,
    validate_segment_order,
)
from speech_analysis.llm.schemas import SpeechAnalysisResponse
from speech_analysis.models.speech_content import SpeechContent, SpeechSegment
from speech_analysis.speech_analyzer import analyze_speech, prepare_transcript


@dataclass
class FakeResponse:
    success: bool = True
    content: Optional[str] = None
    error: Optional[str] = None


@dataclass
class FakeAPIClient:
    reply: dict
    calls: list = field(default_factory=list)

    def generate(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        return FakeResponse(content=json.dumps(self.reply))


def _reply(units: list[dict]) -> dict:
    return {"session_id": "s-test", "segments": units}


GOOD_UNITS = [
    {"segment_ids": ["s_000"], "labels": ["claim"], "fallacy_type": None},
    {
        "segment_ids": ["s_001"],
        "labels": ["evidence", "logical_fallacy"],
        "fallacy_type": "hasty_generalization",
        "summary": "Generalises from one case.",
    },
    {"segment_ids": ["s_002"], "labels": ["rebuttal"], "fallacy_type": None},
]


# ---------------------------------------------------------------
# Consumer-facing structure (unchanged contract)
# ---------------------------------------------------------------

def test_output_structure(session_dir: Path):
    client = FakeAPIClient(reply=_reply(GOOD_UNITS))

    output_path, content = analyze_speech("s-test", session_dir, api_client=client)

    assert output_path == session_dir / "speech_content.json"
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved == content.to_dict()
    assert saved["session_id"] == "s-test"
    assert len(saved["segments"]) == 3

    for seg in saved["segments"]:
        assert {"start", "end", "text", "labels"} <= set(seg)
        assert isinstance(seg["labels"], list) and seg["labels"]

    assert "fallacy_type" not in saved["segments"][0]
    assert saved["segments"][1]["fallacy_type"] == "hasty_generalization"
    assert saved["segments"][1]["labels"] == ["evidence", "logical_fallacy"]


def test_times_and_text_are_computed_from_the_transcript(session_dir: Path, transcription):
    """LLM-written start/end/text must be ignored."""
    units = [dict(u) for u in GOOD_UNITS]
    units[0].update({"start": 99.0, "end": 100.0, "text": "made up"})
    client = FakeAPIClient(reply=_reply(units))

    _, content = analyze_speech("s-test", session_dir, api_client=client)
    seg0 = content.segments[0]

    assert (seg0.start, seg0.end) == (0.50, 2.60)
    assert seg0.text == transcription["segments"][0]["text"]
    assert seg0.id == "au_000"
    assert seg0.segment_ids == ["s_000"]
    assert seg0.type == "claim"

    assert content.segments[1].type == "evidence"
    assert content.segments[1].summary == "Generalises from one case."
    assert content.segments[2].type == "rebuttal"


def test_llm_receives_segment_ids_not_timestamps(session_dir: Path):
    client = FakeAPIClient(reply=_reply(GOOD_UNITS))
    analyze_speech("s-test", session_dir, api_client=client)

    call = client.calls[0]
    assert call["provider"] == "groq"
    assert call["model"] == "openai/gpt-oss-120b"
    assert call["temperature"] == 0.0
    assert call["response_format"] == "json"

    user_msg = call["messages"][1]["content"]
    assert "[s_000] Um the motion is clearly justified." in user_msg
    assert "[s_001] Like, this this evidence is overwhelming." in user_msg
    assert "[s_002] You know, they never answered it." in user_msg
    assert "[0.50 - 2.60]" not in user_msg
    assert "JSON" in user_msg  # Groq's JSON mode requires it


def test_prepare_transcript_rejects_empty(transcription):
    with pytest.raises(ValueError, match="no usable speech segments"):
        prepare_transcript({"segments": []})


# ---------------------------------------------------------------
# Anchoring rules
# ---------------------------------------------------------------

def _anchor(units: list[dict], transcription: dict) -> list[dict]:
    response = SpeechAnalysisResponse.model_validate({"segments": units})
    return anchor_units(response, to_canonical(transcription))


def test_multi_segment_unit_spans_its_segments(transcription):
    out = _anchor([{"segment_ids": ["s_001", "s_002"], "labels": ["conclusion"]}], transcription)

    assert len(out) == 1
    assert out[0]["segment_ids"] == ["s_001", "s_002"]
    assert (out[0]["start"], out[0]["end"]) == (3.10, 7.70)
    assert out[0]["text"] == (
        "Like, this this evidence is overwhelming. You know, they never answered it."
    )
    assert out[0]["type"] == "conclusion"


def test_unknown_ids_dropped_and_empty_unit_dropped(transcription):
    out = _anchor(
        [
            {"segment_ids": ["s_999"], "labels": ["claim"]},
            {"segment_ids": ["s_998", "s_000"], "labels": ["claim"]},
        ],
        transcription,
    )
    assert [u["segment_ids"] for u in out] == [["s_000"]]
    assert out[0]["id"] == "au_000"


def test_segment_used_by_earlier_unit_is_dropped_from_later(transcription):
    out = _anchor(
        [
            {"segment_ids": ["s_000", "s_001"], "labels": ["claim"]},
            {"segment_ids": ["s_001", "s_002"], "labels": ["rebuttal"]},
        ],
        transcription,
    )
    assert [u["segment_ids"] for u in out] == [["s_000", "s_001"], ["s_002"]]
    # and therefore never overlaps
    content = SpeechContent(session_id="x")
    for u in out:
        content.add_segment(
            SpeechSegment(start=u["start"], end=u["end"], text=u["text"], labels=u["labels"])
        )
    validate_segment_order(content)


def test_units_are_sorted_by_time_and_ids_follow(transcription):
    out = _anchor(
        [
            {"segment_ids": ["s_002"], "labels": ["conclusion"]},
            {"segment_ids": ["s_000"], "labels": ["claim"]},
        ],
        transcription,
    )
    assert [u["segment_ids"][0] for u in out] == ["s_000", "s_002"]
    assert [u["id"] for u in out] == ["au_000", "au_001"]


def test_type_mapping_precedence(transcription):
    cases = {
        ("conclusion", "rebuttal", "claim"): "conclusion",
        ("rebuttal", "claim"): "rebuttal",
        ("counterargument",): "rebuttal",
        ("argument", "reasoning"): "claim",
        ("example",): "evidence",
        ("concession",): "other",
        ("question",): "other",
        ("logical_fallacy",): "other",
    }
    for labels, expected in cases.items():
        out = _anchor([{"segment_ids": ["s_000"], "labels": list(labels)}], transcription)
        assert out[0]["type"] == expected, labels


def test_invalid_label_is_dropped_from_an_otherwise_valid_unit(transcription):
    """
    Confirmed bug (2026-09-20): a label outside VALID_LABELS (e.g.
    the model reaching for "warrant", a real argumentation term
    this app's fixed 11-label taxonomy doesn't include) used to
    fail the ENTIRE response via a Pydantic field_validator, not
    just the one unit — unlike an unrecognized segment_id, which
    anchor_units() already tolerated. This is exactly the gap that
    let a real, non-trivial transcript fail in production
    undetected until it happened.
    """
    out = _anchor(
        [{"segment_ids": ["s_000"], "labels": ["claim", "warrant"]}],
        transcription,
    )
    assert len(out) == 1
    assert out[0]["labels"] == ["claim"]  # "warrant" dropped, "claim" kept


def test_unit_whose_only_label_is_invalid_is_dropped_not_the_response(transcription):
    out = _anchor(
        [
            {"segment_ids": ["s_000"], "labels": ["warrant"]},  # only label is invalid
            {"segment_ids": ["s_001"], "labels": ["rebuttal"]},  # unaffected
        ],
        transcription,
    )
    assert [u["segment_ids"] for u in out] == [["s_001"]]


def test_invalid_label_via_analyze_speech_end_to_end(session_dir: Path):
    """Same as above two, through the real entry point: no longer raises."""
    units = [dict(GOOD_UNITS[0], labels=["not_a_label"])]
    client = FakeAPIClient(reply=_reply(units))

    _, content = analyze_speech("s-test", session_dir, api_client=client)

    assert content.segments == []  # the unit's only label was invalid


def test_fallacy_type_without_logical_fallacy_label_is_cleared_not_rejected(transcription):
    """
    Same class of problem as invalid labels, same fix shape: a
    fallacy_type present without "logical_fallacy" among the
    unit's labels used to reject the whole response (schemas.py's
    old validate_fallacy_type). It's now silently cleared to None
    for that unit instead — the unit itself is still meaningful
    (it has a valid label), only the one inconsistent field is
    wrong.
    """
    out = _anchor(
        [{"segment_ids": ["s_000"], "labels": ["claim"], "fallacy_type": "straw_man"}],
        transcription,
    )
    assert len(out) == 1
    assert out[0]["labels"] == ["claim"]
    assert out[0]["fallacy_type"] is None


def test_unit_without_ids_is_rejected_by_schema(session_dir: Path):
    client = FakeAPIClient(reply=_reply([{"segment_ids": [], "labels": ["claim"]}]))

    with pytest.raises(RuntimeError, match="schema validation"):
        analyze_speech("s-test", session_dir, api_client=client)


def test_validate_segment_order_still_guards():
    content = SpeechContent(session_id="x")
    content.add_segment(SpeechSegment(start=5.0, end=6.0, text="b", labels=["claim"]))
    content.add_segment(SpeechSegment(start=1.0, end=2.0, text="a", labels=["claim"]))
    with pytest.raises(ValueError, match="overlaps or is out of order"):
        validate_segment_order(content)
