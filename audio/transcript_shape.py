"""
One canonical transcript shape for everything downstream of
transcription that is new on this branch (argument-unit time
anchoring, the session timeline, video correlation).

The stored transcription.json and the raw_metrics consumers keep
the provider's nested shape untouched; this module is a pure,
in-memory view over it. Convert once, at the point transcription
output enters analysis, and pass the result along. Do not scatter
shape conversions.

Canonical shape (see docs/video-analysis/PHASE0_REPORT.md):

    words:    [{i, start, end, text, segment_id}]   flat, global index
    segments: [{id, start, end, text, word_range}]  word_range = [lo, hi)

All times are seconds from audio start. Segment ids are
"s_000", "s_001", ... in transcript order, so a prompt can show
them and the model can hand them back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional


def segment_id_for(index: int) -> str:
    return f"s_{index:03d}"


@dataclass(frozen=True)
class CanonicalWord:
    i: int
    start: float
    end: float
    text: str
    segment_id: str

    def to_dict(self) -> dict:
        return {
            "i": self.i,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "segment_id": self.segment_id,
        }


@dataclass(frozen=True)
class CanonicalSegment:
    id: str
    start: float
    end: float
    text: str
    word_range: tuple[int, int]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "word_range": list(self.word_range),
        }


@dataclass(frozen=True)
class CanonicalTranscript:
    words: tuple[CanonicalWord, ...]
    segments: tuple[CanonicalSegment, ...]

    def to_dict(self) -> dict:
        return {
            "words": [w.to_dict() for w in self.words],
            "segments": [s.to_dict() for s in self.segments],
        }

    def segment(self, segment_id: str) -> Optional[CanonicalSegment]:
        for seg in self.segments:
            if seg.id == segment_id:
                return seg
        return None

    def span(self, segment_ids: Iterable[str]) -> Optional[tuple[float, float]]:
        """Earliest start and latest end across the given segments."""
        found = [s for s in (self.segment(i) for i in segment_ids) if s is not None]
        if not found:
            return None
        return (min(s.start for s in found), max(s.end for s in found))

    def excerpt(self, word_range: tuple[int, int], max_words: int = 40) -> str:
        lo, hi = word_range
        lo = max(0, lo)
        hi = min(len(self.words), hi, lo + max_words)
        return " ".join(w.text for w in self.words[lo:hi])

    def word_range_for(self, segment_ids: Iterable[str]) -> Optional[tuple[int, int]]:
        found = [s for s in (self.segment(i) for i in segment_ids) if s is not None]
        if not found:
            return None
        return (
            min(s.word_range[0] for s in found),
            max(s.word_range[1] for s in found),
        )


def _num(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return (value or "").strip() if isinstance(value, str) else ""


def _raw_words_for_segment(
    segment: dict,
    loose_words: list[dict],
    seg_start: Optional[float],
    seg_end: Optional[float],
) -> list[dict]:
    """
    Prefer words nested in the segment (the shape audio/transcriber.py
    writes). Fall back to a flat top-level list, placed by start time,
    so a provider that returns words unnested still normalises.
    """
    nested = segment.get("words")
    if isinstance(nested, list) and nested:
        return nested

    if not loose_words or seg_start is None or seg_end is None:
        return []

    return [
        w
        for w in loose_words
        if _num(w.get("start")) is not None
        and seg_start <= _num(w.get("start")) <= seg_end
    ]


def to_canonical(transcription: dict) -> CanonicalTranscript:
    """
    Build the canonical shape from whatever the transcription
    chain produced. Words without both timestamps or without text
    are dropped; they cannot be placed on a timeline. Segments
    without a usable start/end take them from their words, and a
    segment with neither is dropped.
    """

    raw_segments = transcription.get("segments") or []
    loose_words = transcription.get("words") or []
    if not isinstance(loose_words, list):
        loose_words = []

    words: list[CanonicalWord] = []
    segments: list[CanonicalSegment] = []

    for index, raw_seg in enumerate(raw_segments):
        if not isinstance(raw_seg, dict):
            continue

        seg_id = segment_id_for(index)
        seg_start = _num(raw_seg.get("start"))
        seg_end = _num(raw_seg.get("end"))

        lo = len(words)
        for raw_word in _raw_words_for_segment(raw_seg, loose_words, seg_start, seg_end):
            if not isinstance(raw_word, dict):
                continue
            w_start = _num(raw_word.get("start"))
            w_end = _num(raw_word.get("end"))
            w_text = _text(raw_word.get("word"))
            if w_start is None or w_end is None or not w_text:
                continue
            words.append(
                CanonicalWord(
                    i=len(words),
                    start=w_start,
                    end=w_end,
                    text=w_text,
                    segment_id=seg_id,
                )
            )
        hi = len(words)

        if seg_start is None or seg_end is None:
            if hi == lo:
                continue
            seg_start = words[lo].start if seg_start is None else seg_start
            seg_end = words[hi - 1].end if seg_end is None else seg_end

        seg_text = _text(raw_seg.get("text"))
        if not seg_text and hi > lo:
            seg_text = " ".join(w.text for w in words[lo:hi])

        segments.append(
            CanonicalSegment(
                id=seg_id,
                start=seg_start,
                end=seg_end,
                text=seg_text,
                word_range=(lo, hi),
            )
        )

    return CanonicalTranscript(words=tuple(words), segments=tuple(segments))
