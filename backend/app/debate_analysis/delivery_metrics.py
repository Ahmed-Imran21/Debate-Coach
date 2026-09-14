"""
delivery_metrics.py — fully deterministic, no LLM or external API calls.

Input shape is intentionally provider-agnostic:

- `words`: list of {"word": str, "start": float, "end": float}
  This matches both your original local faster-whisper output AND
  Groq's verbose_json word-level output (see services/transcription.py),
  so this module works unchanged regardless of which transcription
  provider produced the data.

- `vad_segments` (optional): list of {"type": "speech" | "silence",
  "start": float, "end": float}, matching your Silero VAD analysis.json
  from the audio-analysis branch. If omitted, pause stats are derived
  from gaps between consecutive words instead (less precise, but keeps
  this module usable even without a VAD pass).

Nothing in this file talks to Groq, OpenAI, or any network. If you find
yourself wanting to add an API call here, it belongs in
semantic_analysis.py instead — this module is the "countable facts" half
of the architecture.
"""

import re
from collections import Counter
from typing import Any

# Common English filler/hedge words and short filler phrases. Extend as
# needed; keep this list plain-code data, not something an LLM decides.
FILLER_WORDS = {
    "um", "uh", "uhh", "umm", "er", "erm", "ah", "like", "actually",
    "basically", "literally", "so", "well", "right", "okay", "ok",
}
FILLER_PHRASES = ["you know", "i mean", "sort of", "kind of"]

PAUSE_THRESHOLD_SECONDS = 0.5  # gap >= this counts as a "pause"


def _normalize(word: str) -> str:
    return re.sub(r"[^\w']", "", word).lower()


def _duration_seconds(words: list[dict[str, Any]]) -> float:
    if not words:
        return 0.0
    return max(0.0, words[-1]["end"] - words[0]["start"])


def _filler_breakdown(words: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = [_normalize(w["word"]) for w in words]
    counts: Counter[str] = Counter()

    for token in normalized:
        if token in FILLER_WORDS:
            counts[token] += 1

    joined = " ".join(normalized)
    for phrase in FILLER_PHRASES:
        occurrences = joined.count(phrase)
        if occurrences:
            counts[phrase] += occurrences

    total = sum(counts.values())
    total_words = max(1, len(words))
    return {
        "total_fillers": total,
        "fillers_per_100_words": round(100 * total / total_words, 2),
        "breakdown": dict(counts.most_common()),
    }


def _repetitions(words: list[dict[str, Any]]) -> dict[str, Any]:
    """Flags immediate word-repeats (e.g. "the the", "I I think") — a cheap,
    deterministic proxy for disfluency. Not a semantic/argument-repetition
    detector; that judgment call belongs in semantic_analysis.py."""
    normalized = [_normalize(w["word"]) for w in words]
    repeats = []
    for i in range(1, len(normalized)):
        if normalized[i] and normalized[i] == normalized[i - 1]:
            repeats.append({"word": normalized[i], "index": i, "timestamp": words[i]["start"]})
    return {"count": len(repeats), "instances": repeats}


def _pause_stats_from_vad(vad_segments: list[dict[str, Any]]) -> dict[str, Any]:
    silences = [s for s in vad_segments if s.get("type") == "silence"]
    durations = [s["end"] - s["start"] for s in silences]
    pauses = [d for d in durations if d >= PAUSE_THRESHOLD_SECONDS]

    return {
        "source": "vad",
        "pause_count": len(pauses),
        "total_pause_seconds": round(sum(pauses), 2),
        "longest_pause_seconds": round(max(pauses), 2) if pauses else 0.0,
        "average_pause_seconds": round(sum(pauses) / len(pauses), 2) if pauses else 0.0,
    }


def _pause_stats_from_word_gaps(words: list[dict[str, Any]]) -> dict[str, Any]:
    gaps = [
        words[i]["start"] - words[i - 1]["end"]
        for i in range(1, len(words))
        if words[i]["start"] - words[i - 1]["end"] >= PAUSE_THRESHOLD_SECONDS
    ]
    return {
        "source": "word_gaps_fallback",
        "pause_count": len(gaps),
        "total_pause_seconds": round(sum(gaps), 2),
        "longest_pause_seconds": round(max(gaps), 2) if gaps else 0.0,
        "average_pause_seconds": round(sum(gaps) / len(gaps), 2) if gaps else 0.0,
    }


def compute_delivery_metrics(
    words: list[dict[str, Any]],
    vad_segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The single entry point for this module. Returns a plain JSON-
    serializable dict — this is what gets written to
    delivery_metrics.json."""
    duration = _duration_seconds(words)
    word_count = len(words)
    wpm = round((word_count / duration) * 60, 1) if duration > 0 else 0.0

    pause_stats = (
        _pause_stats_from_vad(vad_segments) if vad_segments else _pause_stats_from_word_gaps(words)
    )

    return {
        "word_count": word_count,
        "duration_seconds": round(duration, 2),
        "words_per_minute": wpm,
        "fillers": _filler_breakdown(words),
        "repetitions": _repetitions(words),
        "pauses": pause_stats,
    }
