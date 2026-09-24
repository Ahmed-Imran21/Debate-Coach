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
    def validate_labels_present(cls, value):
        """
        Only checks the unit named at least one label. Whether
        each individual label is one of VALID_LABELS is checked
        later, per unit, in response_parser.anchor_units() —
        dropping just the invented label (or the whole unit, if
        none of its labels turn out valid) rather than rejecting
        the entire LLM response over one bad word in one unit.

        Confirmed bug (2026-09-20): this validator used to also
        reject the whole response if ANY unit used a label outside
        the fixed 11, e.g. "warrant" (a real, common term in
        formal argumentation the model reached for unprompted on
        substantive content) — unlike an unrecognized segment_id,
        which was already tolerated at the anchor_units() level.
        Every session past a trivial one-sentence transcript was at
        risk of this. See anchor_units() for the actual filtering.
        """
        if not value:
            raise ValueError(
                "Every semantic segment must have at least one label."
            )
        return value

    # No cross-field validator for fallacy_type here anymore. An
    # inconsistent fallacy_type (present without "logical_fallacy"
    # in labels — possible after invalid-label filtering above, too)
    # is silently cleared to None in anchor_units(), same reasoning
    # as labels: one inconsistent field on one unit shouldn't fail
    # the whole response.


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
