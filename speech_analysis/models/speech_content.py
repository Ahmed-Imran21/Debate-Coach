from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------
# Allowed semantic labels
# ---------------------------------------------------------

VALID_LABELS = {
    "claim",
    "argument",
    "evidence",
    "example",
    "reasoning",
    "rebuttal",
    "counterargument",
    "concession",
    "logical_fallacy",
    "conclusion",
    "question",
}


# ---------------------------------------------------------
# Speech segment
# ---------------------------------------------------------

@dataclass
class SpeechSegment:
    """
    Represents a portion of the speaker's speech that has
    been semantically classified by the LLM.
    """

    start: float
    end: float
    text: str

    labels: List[str] = field(default_factory=list)

    fallacy_type: Optional[str] = None

    def __post_init__(self):
        """
        Validate the segment after creation.
        """

        if self.start < 0:
            raise ValueError("Start timestamp cannot be negative.")

        if self.end < self.start:
            raise ValueError(
                "End timestamp cannot be earlier than start timestamp."
            )

        if not self.text.strip():
            raise ValueError(
                "Speech segment text cannot be empty."
            )

        # Validate labels
        invalid_labels = [
            label
            for label in self.labels
            if label not in VALID_LABELS
        ]

        if invalid_labels:
            raise ValueError(
                f"Invalid labels: {invalid_labels}. "
                f"Valid labels are: {sorted(VALID_LABELS)}"
            )

        # A fallacy type only makes sense when the segment
        # has been classified as a logical fallacy.
        if self.fallacy_type is not None:
            if "logical_fallacy" not in self.labels:
                raise ValueError(
                    "fallacy_type can only be provided when "
                    "'logical_fallacy' is one of the labels."
                )

    def to_dict(self):
        """
        Convert the segment into a JSON-compatible dictionary.
        """

        data = {
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "labels": self.labels,
        }

        if self.fallacy_type is not None:
            data["fallacy_type"] = self.fallacy_type

        return data


# ---------------------------------------------------------
# Speech content
# ---------------------------------------------------------

@dataclass
class SpeechContent:
    """
    Represents the complete semantic analysis of a session.
    """

    session_id: str

    segments: List[SpeechSegment] = field(default_factory=list)

    def add_segment(self, segment: SpeechSegment):
        """
        Add a classified speech segment.
        """

        if not isinstance(segment, SpeechSegment):
            raise TypeError(
                "segment must be a SpeechSegment instance."
            )

        self.segments.append(segment)

    def to_dict(self):
        """
        Convert the complete analysis into a JSON-compatible
        dictionary.
        """

        return {
            "session_id": self.session_id,
            "segments": [
                segment.to_dict()
                for segment in self.segments
            ],
        }