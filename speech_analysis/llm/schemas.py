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
# Semantic unit as the model returns it
# ---------------------------------------------------------

class SemanticSegment(BaseModel):
    """
    One unit of speech as classified by the LLM.

    The model identifies a unit only by the transcript segment
    ids it covers. It does not write timestamps or copy text:
    start, end and text are computed in code from the ids
    (see response_parser.anchor_units). start/end/text are
    accepted here for tolerance but ignored downstream.
    """

    segment_ids: List[str] = Field(
        description=(
            "Ids of the transcript segments this unit covers, "
            "e.g. [\"s_004\", \"s_005\"]."
        )
    )

    labels: List[str] = Field(
        description="Semantic labels assigned to this unit."
    )

    fallacy_type: Optional[str] = Field(
        default=None,
        description=(
            "Type of logical fallacy if the unit contains one."
        ),
    )

    summary: Optional[str] = Field(
        default=None,
        description="One short sentence describing the unit.",
    )

    # Tolerated, never trusted.
    id: Optional[str] = None
    start: Optional[float] = None
    end: Optional[float] = None
    text: Optional[str] = None

    @field_validator("segment_ids")
    @classmethod
    def validate_segment_ids(cls, value):
        cleaned = []
        for item in value or []:
            if isinstance(item, str) and item.strip():
                cleaned.append(item.strip())
        if not cleaned:
            raise ValueError(
                "Every semantic unit must reference at least one "
                "transcript segment id."
            )
        return cleaned

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
    Structured semantic analysis returned by the LLM.
    """

    segments: List[SemanticSegment] = Field(
        default_factory=list,
        description="Semantically classified speech units."
    )
