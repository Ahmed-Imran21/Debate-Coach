from ..models.speech_content import SpeechContent, SpeechSegment
from .schemas import SpeechAnalysisResponse


# ---------------------------------------------------------
# Parse LLM response
# ---------------------------------------------------------

def parse_analysis_response(response):
    """
    Convert a validated LLM response into a SpeechContent
    object used by the rest of the application.

    Parameters
    ----------
    response : SpeechAnalysisResponse
        Structured and validated response from the LLM.

    Returns
    -------
    SpeechContent
        Internal representation of the semantic analysis.
    """

    if not isinstance(response, SpeechAnalysisResponse):
        raise TypeError(
            "response must be a SpeechAnalysisResponse instance."
        )

    speech_content = SpeechContent(
        session_id=response.session_id
    )

    for semantic_segment in response.segments:

        segment = SpeechSegment(
            start=semantic_segment.start,
            end=semantic_segment.end,
            text=semantic_segment.text,
            labels=semantic_segment.labels,
            fallacy_type=semantic_segment.fallacy_type,
        )

        speech_content.add_segment(segment)

    return speech_content


# ---------------------------------------------------------
# Validate segment ordering
# ---------------------------------------------------------

def validate_segment_order(speech_content):
    """
    Validate that semantic segments are ordered chronologically.

    Parameters
    ----------
    speech_content : SpeechContent

    Raises
    ------
    ValueError
        If segments are out of chronological order.
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

def parse_and_validate(response):
    """
    Convert the LLM response into SpeechContent and perform
    additional project-level validation.

    Parameters
    ----------
    response : SpeechAnalysisResponse

    Returns
    -------
    SpeechContent
        Validated semantic analysis.
    """

    speech_content = parse_analysis_response(response)

    validate_segment_order(speech_content)

    return speech_content