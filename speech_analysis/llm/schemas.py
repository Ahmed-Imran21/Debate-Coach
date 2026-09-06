from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


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
# Semantic segment
# ---------------------------------------------------------

class SemanticSegment(BaseModel):
    """
    Represents one portion of speech classified by the LLM.
    """

    start: float = Field(
        description="Start timestamp of the segment in seconds."
    )

    end: float = Field(
        description="End timestamp of the segment in seconds."
    )

    text: str = Field(
        description="Exact transcript text belonging to this segment."
    )

    labels: List[str] = Field(
        description="Semantic labels assigned to this segment."
    )

    fallacy_type: Optional[str] = Field(
        default=None,
        description=(
            "Type of logical fallacy if the segment contains "
            "a logical fallacy."
        )
    )

    @field_validator("start", "end")
    @classmethod
    def validate_timestamp(cls, value):
        if value < 0:
            raise ValueError("Timestamp cannot be negative.")

        return value

    @field_validator("end")
    @classmethod
    def validate_end(cls, value, info):
        start = info.data.get("start")

        if start is not None and value < start:
            raise ValueError(
                "End timestamp cannot be earlier than start timestamp."
            )

        return value

    @field_validator("text")
    @classmethod
    def validate_text(cls, value):
        if not value.strip():
            raise ValueError("Segment text cannot be empty.")

        return value

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, value):

        if not value:
            raise ValueError(
                "Every semantic segment must have at least one label."
            )

        invalid_labels = [
            label
            for label in value
            if label not in VALID_LABELS
        ]

        if invalid_labels:
            raise ValueError(
                f"Invalid labels: {invalid_labels}. "
                f"Valid labels are: {sorted(VALID_LABELS)}"
            )

        return value

    @field_validator("fallacy_type")
    @classmethod
    def validate_fallacy_type(cls, value, info):

        if value is not None:
            labels = info.data.get("labels", [])

            if "logical_fallacy" not in labels:
                raise ValueError(
                    "fallacy_type can only be provided when "
                    "'logical_fallacy' is one of the labels."
                )

        return value


# ---------------------------------------------------------
# Complete LLM response
# ---------------------------------------------------------

class SpeechAnalysisResponse(BaseModel):
    """
    Complete structured response returned by the LLM.
    """

    session_id: str = Field(
        description="ID of the session being analyzed."
    )

    segments: List[SemanticSegment] = Field(
        default_factory=list,
        description="Semantically classified speech segments."
    )