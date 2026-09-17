"""
Characterization tests for raw_metrics.

These pin the CURRENT numbers produced from the nested-word
transcript shape. They are the "existing tests must pass"
gate for the canonical-transcript work: raw_metrics is not
supposed to change at all, and these prove it did not.
"""

import json
from pathlib import Path

from raw_metrics.filler_detector import detect_fillers
from raw_metrics.metrics import analyze_metrics, calculate_word_count
from raw_metrics.stutter_detector import detect_stutters


def test_word_count_reads_nested_words(transcription):
    assert calculate_word_count(transcription) == 18


def test_fillers_from_nested_words(transcription):
    result = detect_fillers(transcription)

    assert result["count"] == 3
    assert result["words"] == {"um": 1, "like": 1, "you know": 1}

    # Single-word instances keep the transcript's original casing
    # and punctuation; only the phrase instance is normalised.
    instances = result["instances"]
    assert [i.get("word") or i.get("phrase") for i in instances] == [
        "Um",
        "Like,",
        "you know",
    ]
    # Chronological, and the phrase spans both of its words.
    assert [round(i["start"], 2) for i in instances] == [0.50, 3.10, 6.00]
    assert round(instances[2]["end"], 2) == 6.45


def test_stutters_from_nested_words(transcription):
    result = detect_stutters(transcription)

    assert result["count"] == 1
    instance = result["instances"][0]
    assert instance["type"] == "word_repetition"
    assert round(instance["start"], 2) == 3.35
    assert round(instance["end"], 2) == 3.80


def test_analyze_metrics_end_to_end(session_dir: Path):
    output_path, raw_metrics = analyze_metrics("s-test", session_dir)

    assert output_path == session_dir / "raw_metrics.json"
    assert json.loads(output_path.read_text(encoding="utf-8")) == raw_metrics

    assert raw_metrics["session_id"] == "s-test"

    speech = raw_metrics["speech"]
    assert speech["total_duration"] == 8.0
    assert speech["speech_duration"] == 6.2
    assert speech["silence_duration"] == 1.8
    assert speech["speech_percentage"] == 77.5
    assert speech["word_count"] == 18
    assert speech["words_per_minute"] == 174.19

    pauses = raw_metrics["pauses"]
    assert pauses == {
        "count": 2,
        "total_duration": 1.1,
        "average_duration": 0.55,
        "longest_duration": 0.7,
    }

    assert raw_metrics["fillers"]["count"] == 3
    assert raw_metrics["stutters"]["count"] == 1
