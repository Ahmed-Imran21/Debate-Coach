from audio.transcript_shape import CanonicalTranscript

from ..models.speech_content import (
    SpeechContent,
    SpeechSegment,
    unit_type_for,
)
from .schemas import SpeechAnalysisResponse


# ---------------------------------------------------------
# Anchor units to the transcript
# ---------------------------------------------------------

def anchor_units(response, canonical: CanonicalTranscript):
    """
    Turn the model's segment-id references into time-anchored
    units. Deterministic rules, in this order:

      - a segment id the transcript does not have is dropped
      - a segment id already used by an earlier unit is dropped
        (a transcript segment belongs to at most one unit)
      - a unit left with no valid ids is dropped
      - start = earliest start of its segments,
        end = latest end, text = their text joined in order
      - units are returned sorted by start, ids "au_000", ...

    Because transcript segments are disjoint and each is used
    once, the result is chronological and non-overlapping.
    """

    if not isinstance(response, SpeechAnalysisResponse):
        raise TypeError(
            "response must be a SpeechAnalysisResponse instance."
        )

    known = {seg.id: seg for seg in canonical.segments}
    used: set = set()
    anchored = []

    for unit in response.segments:

        ids = []
        for seg_id in unit.segment_ids:
            if seg_id in known and seg_id not in used:
                ids.append(seg_id)
                used.add(seg_id)

        if not ids:
            continue

        segs = sorted(
            (known[i] for i in ids),
            key=lambda s: s.start,
        )

        anchored.append(
            {
                "segment_ids": [s.id for s in segs],
                "start": segs[0].start,
                "end": max(s.end for s in segs),
                "text": " ".join(s.text for s in segs if s.text),
                "labels": list(unit.labels),
                "fallacy_type": unit.fallacy_type,
                "summary": (unit.summary or "").strip() or None,
            }
        )

    anchored.sort(key=lambda u: (u["start"], u["end"]))

    for index, unit in enumerate(anchored):
        unit["id"] = f"au_{index:03d}"
        unit["type"] = unit_type_for(unit["labels"])

    return anchored


# ---------------------------------------------------------
# Parse LLM response
# ---------------------------------------------------------

def parse_analysis_response(response, session_id, canonical: CanonicalTranscript):
    """
    Convert a validated LLM response into a SpeechContent
    object used by the rest of the application.
    """

    if not session_id:
        raise ValueError(
            "session_id cannot be empty."
        )

    speech_content = SpeechContent(
        session_id=session_id
    )

    for unit in anchor_units(response, canonical):

        segment = SpeechSegment(
            start=unit["start"],
            end=unit["end"],
            text=unit["text"],
            labels=unit["labels"],
            fallacy_type=unit["fallacy_type"],
            id=unit["id"],
            segment_ids=unit["segment_ids"],
            type=unit["type"],
            summary=unit["summary"],
        )

        speech_content.add_segment(segment)

    return speech_content


# ---------------------------------------------------------
# Validate segment ordering
# ---------------------------------------------------------

def validate_segment_order(speech_content):
    """
    Validate that semantic segments are ordered chronologically.
    Kept as a hard invariant even though anchor_units guarantees
    it, so any future change that breaks it fails loudly.
    """

    previous_end = 0.0

    for index, segment in enumerate(speech_content.segments):

        if segment.start < previous_end:
            raise ValueError(
                f"Segment {index} overlaps or is out of order. "
                f"Start: {segment.start}, "
                f"previous end: {previous_end}"
            )

        previous_end = segment.end


# ---------------------------------------------------------
# Parse and validate
# ---------------------------------------------------------

def parse_and_validate(response, session_id, canonical: CanonicalTranscript):
    """
    Convert the LLM response into SpeechContent and perform
    additional project-level validation.
    """

    speech_content = parse_analysis_response(
        response,
        session_id,
        canonical,
    )

    validate_segment_order(speech_content)

    return speech_content
