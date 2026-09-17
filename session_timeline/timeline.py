"""
SessionTimeline (§6.1): a read-only view assembled from already-
stored artifacts, not itself stored. Pure: takes already-loaded
dicts, does no I/O -- the caller (visual_coaching/service.py) reads
transcription.json, analysis.json, raw_metrics.json, speech_content.
json and video_analysis.json and passes their parsed contents in.

Source mapping (§6.1 says "map them, don't recompute them"):
  - words: audio/transcript_shape.to_canonical(transcription) --
    the one canonical shape everything downstream already uses.
  - speech_segments, pauses: analysis.json (audio_analyzer.py's own
    output). raw_metrics.json's "pauses" key is an aggregate summary
    (count/total/average/longest), not a list of timed pauses, so it
    can't serve a timeline -- analysis.json is the only artifact
    that actually has per-pause {start, end, duration} objects.
  - fillers: raw_metrics.json's fillers.instances, which -- unlike
    pauses -- already is a per-occurrence list with start/end.
  - argument_units: speech_content.json's segments, each already
    carrying id/type/segment_ids/start/end from Prerequisite B's
    anchor_units().
  - visual_events: video_analysis.json's events list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from audio.transcript_shape import CanonicalTranscript, to_canonical


@dataclass
class SessionTimeline:
    session_id: str
    canonical: CanonicalTranscript
    speech_segments: list[dict]
    pauses: list[dict]
    fillers: list[dict]
    argument_units: list[dict]
    visual_events: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "tracks": {
                "words": [w.to_dict() for w in self.canonical.words],
                "speech_segments": self.speech_segments,
                "pauses": self.pauses,
                "fillers": self.fillers,
                "argument_units": self.argument_units,
                "visual_events": self.visual_events,
            },
        }


def _argument_unit_view(segment: dict) -> Optional[dict]:
    if not segment.get("id") or not segment.get("segment_ids"):
        return None
    return {
        "id": segment["id"],
        "type": segment.get("type"),
        "start": segment.get("start"),
        "end": segment.get("end"),
        "segment_ids": list(segment["segment_ids"]),
    }


def build_timeline(
    session_id: str,
    transcription: dict,
    audio_analysis: dict,
    raw_metrics: dict,
    speech_content: dict,
    video_analysis: Optional[dict] = None,
) -> SessionTimeline:
    canonical = to_canonical(transcription)

    argument_units = [
        view for view in (
            _argument_unit_view(seg) for seg in speech_content.get("segments", [])
        )
        if view is not None
    ]

    return SessionTimeline(
        session_id=session_id,
        canonical=canonical,
        speech_segments=list(audio_analysis.get("speech_segments", [])),
        pauses=list(audio_analysis.get("pauses", [])),
        fillers=list(raw_metrics.get("fillers", {}).get("instances", [])),
        argument_units=argument_units,
        visual_events=list(video_analysis["events"]) if video_analysis else [],
    )
