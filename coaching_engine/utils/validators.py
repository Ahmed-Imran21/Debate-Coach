from typing import Any, Dict

from ..models.session import CoachingSession


REQUIRED_RAW_METRIC_SECTIONS = {
    "speech",
    "pauses",
    "fillers",
    "stutters",
}


def validate_raw_metrics(
    raw_metrics: Dict[str, Any],
) -> None:
    """
    Validate the basic structure of raw_metrics.json.
    """

    if not isinstance(raw_metrics, dict):
        raise ValueError(
            "raw_metrics must be a dictionary."
        )

    missing_sections = (
        REQUIRED_RAW_METRIC_SECTIONS
        - raw_metrics.keys()
    )

    if missing_sections:
        raise ValueError(
            "raw_metrics is missing required sections: "
            f"{sorted(missing_sections)}"
        )


def validate_speech_content(
    speech_content: Dict[str, Any],
) -> None:
    """
    Validate the basic structure of speech_content.json.
    """

    if not isinstance(speech_content, dict):
        raise ValueError(
            "speech_content must be a dictionary."
        )

    if "session_id" not in speech_content:
        raise ValueError(
            "speech_content is missing session_id."
        )

    if "segments" not in speech_content:
        raise ValueError(
            "speech_content is missing segments."
        )

    if not isinstance(
        speech_content["segments"],
        list,
    ):
        raise ValueError(
            "speech_content segments must be a list."
        )

    for index, segment in enumerate(
        speech_content["segments"]
    ):
        if not isinstance(segment, dict):
            raise ValueError(
                f"Speech segment {index} must be a dictionary."
            )

        required_fields = {
            "start",
            "end",
            "text",
            "labels",
        }

        missing = required_fields - segment.keys()

        if missing:
            raise ValueError(
                f"Speech segment {index} is missing: "
                f"{sorted(missing)}"
            )

        if not isinstance(segment["labels"], list):
            raise ValueError(
                f"Speech segment {index} labels must be a list."
            )


def validate_session(
    session: CoachingSession,
) -> None:
    """
    Validate a CoachingSession before analysis.
    """

    if not isinstance(session, CoachingSession):
        raise TypeError(
            "session must be a CoachingSession instance."
        )

    if not session.session_id.strip():
        raise ValueError(
            "session_id cannot be empty."
        )

    validate_raw_metrics(
        session.raw_metrics
    )

    validate_speech_content(
        session.speech_content
    )