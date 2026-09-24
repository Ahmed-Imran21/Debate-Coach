"""
Shared fixtures.

Everything here is generated in memory. No audio, no real
recordings, nothing read from the local sessions/ directories.
"""

import json
import os
from pathlib import Path

import pytest


# app.core.config instantiates Settings() at import time and
# requires these. Set them before any test module imports app.*.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("GCP_PROJECT_ID", "test-project")
os.environ.setdefault("GCP_STORAGE_BUCKET", "test-bucket")
# app.db.database builds its engine at import with Postgres pool
# arguments SQLite rejects. This URL is never connected to; API
# tests bind the ORM to their own SQLite engine instead.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@127.0.0.1:1/never")
os.environ.setdefault("VIDEO_ANALYSIS_ENABLED", "true")
# The per-client HTTP limiter is in-process and every TestClient
# request shares one client address, so route tests across files
# would otherwise 429 each other once the suite passes ~60 calls.
os.environ.setdefault("REQUEST_RATE_LIMIT_PER_MINUTE", "100000")
# Tests assert the production default (docs off); a developer's .env
# turning them on for local use must not leak in.
os.environ.setdefault("API_DOCS_ENABLED", "false")


def _word(text: str, start: float, end: float) -> dict:
    # Groq returns word text with a leading space and no
    # probability; mirror that exactly.
    return {
        "word": f" {text}",
        "start": start,
        "end": end,
        "probability": None,
    }


def build_transcription(session_id: str = "s-test") -> dict:
    """
    Three segments, ten seconds of speech, containing:
      - two single-word fillers ("um", "like")
      - one filler phrase ("you know")
      - one word repetition inside MAX_REPETITION_GAP ("this this")
    Word timings are monotonic and lie inside their segment.
    """

    seg_a = [
        _word("Um", 0.50, 0.70),
        _word("the", 0.75, 0.85),
        _word("motion", 0.90, 1.30),
        _word("is", 1.35, 1.45),
        _word("clearly", 1.50, 1.95),
        _word("justified.", 2.00, 2.60),
    ]

    seg_b = [
        _word("Like,", 3.10, 3.30),
        _word("this", 3.35, 3.55),
        _word("this", 3.60, 3.80),
        _word("evidence", 3.85, 4.30),
        _word("is", 4.35, 4.45),
        _word("overwhelming.", 4.50, 5.20),
    ]

    seg_c = [
        _word("You", 6.00, 6.15),
        _word("know,", 6.20, 6.45),
        _word("they", 6.50, 6.65),
        _word("never", 6.70, 6.95),
        _word("answered", 7.00, 7.40),
        _word("it.", 7.45, 7.70),
    ]

    def segment(words: list, text: str) -> dict:
        return {
            "start": words[0]["start"],
            "end": words[-1]["end"],
            "text": text,
            "words": words,
        }

    return {
        "session_id": session_id,
        "audio_file": "recording.wav",
        "language": "en",
        "language_probability": 0.99,
        "whisper_api_key_id": "groq_whisper_large_v3_1",
        "segments": [
            segment(seg_a, "Um the motion is clearly justified."),
            segment(seg_b, "Like, this this evidence is overwhelming."),
            segment(seg_c, "You know, they never answered it."),
        ],
    }


def build_audio_analysis(session_id: str = "s-test") -> dict:
    """
    VAD-style output matching audio/audio_analyzer.py. Three
    speech runs with two pauses between them.
    """

    speech_segments = [
        {"start": 0.45, "end": 2.65},
        {"start": 3.05, "end": 5.25},
        {"start": 5.95, "end": 7.75},
    ]

    for run in speech_segments:
        run["duration"] = round(run["end"] - run["start"], 3)

    pauses = []

    for previous, following in zip(speech_segments, speech_segments[1:]):
        pauses.append(
            {
                "start": previous["end"],
                "end": following["start"],
                "duration": round(following["start"] - previous["end"], 3),
            }
        )

    total_duration = 8.0
    speech_duration = round(sum(r["duration"] for r in speech_segments), 3)

    return {
        "session_id": session_id,
        "audio_file": "recording.wav",
        "sample_rate": 16000,
        "total_duration": total_duration,
        "speech_duration": speech_duration,
        "silence_duration": round(total_duration - speech_duration, 3),
        "speech_percentage": round(100 * speech_duration / total_duration, 2),
        "speech_segments": speech_segments,
        "pauses": pauses,
    }


@pytest.fixture
def transcription() -> dict:
    return build_transcription()


@pytest.fixture
def audio_analysis() -> dict:
    return build_audio_analysis()


@pytest.fixture
def session_dir(tmp_path: Path, transcription: dict, audio_analysis: dict) -> Path:
    """
    A session working directory laid out the way
    app/services/pipeline.py lays it out.
    """

    directory = tmp_path / "s-test"
    directory.mkdir()

    (directory / "transcription.json").write_text(
        json.dumps(transcription, indent=2), encoding="utf-8"
    )
    (directory / "analysis.json").write_text(
        json.dumps(audio_analysis, indent=2), encoding="utf-8"
    )

    return directory
