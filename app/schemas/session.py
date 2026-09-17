import uuid

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.session import SessionStatus


# Formats a browser MediaRecorder actually produces, plus the
# common file types someone might upload from a phone.
ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/aac": ".aac",
    "audio/flac": ".flac",
}


class SessionCreateRequest(BaseModel):
    content_type: str = Field(
        description=(
            "MIME type of the audio you are about to upload. "
            "Must be sent verbatim as the Content-Type header "
            "on the PUT to upload_url."
        )
    )

    title: str | None = Field(
        default=None,
        max_length=200,
    )

    # Opt in to visual analysis for this session. Ignored (treated
    # as not_requested) when VIDEO_ANALYSIS_ENABLED is false.
    video_analysis: Literal["requested", "not_requested"] = "not_requested"


class VideoFinalize(BaseModel):
    """
    How the client's video track ended up, sent with POST /start.
    "uploaded" requires the signal track to already be stored.
    """

    status: Literal["uploaded", "unavailable"]
    reason: (
        Literal[
            "camera_denied",
            "unsupported",
            "model_load_failed",
            "device_too_slow",
            "user_opted_out",
            "upload_failed",
            "face_not_found",
        ]
        | None
    ) = None


class SessionStartRequest(BaseModel):
    """
    Optional body for POST /start. An absent body, or an absent
    `video` field, means exactly what a bodyless call meant before
    this field existed.
    """

    video: VideoFinalize | None = None


class SessionCreateResponse(BaseModel):
    id: uuid.UUID
    status: SessionStatus
    upload_url: str
    upload_headers: dict[str, str]
    expires_in_seconds: int


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    status: SessionStatus
    progress: float

    queue_wait_seconds: float | None

    overall_score: float | None
    duration_seconds: float | None
    words_per_minute: float | None
    feedback_count: int | None

    error_message: str | None

    created_at: datetime
    updated_at: datetime

    # Video track. Always present; "not_requested" when the
    # session never asked for it or the feature is off.
    video_analysis_status: str = "not_requested"
    video_unavailable_reason: str | None = None
    visual_coaching_status: str = "not_requested"


class FeedbackItemOut(BaseModel):
    category: str
    title: str
    issue: str
    severity: str
    evidence: list[str]
    explanation: str | None
    recommendation: str | None
    metadata: dict[str, Any]


class SessionReportOut(BaseModel):
    """
    Everything the results page needs, in one response.

    Returned inline rather than as a set of presigned download
    links: these are small JSON documents and a single round
    trip is simpler for every client to consume.
    """

    id: uuid.UUID
    title: str | None
    status: SessionStatus
    created_at: datetime

    scores: dict[str, float]
    feedback: list[FeedbackItemOut]

    raw_metrics: dict[str, Any]
    speech_content: dict[str, Any]

    # The Silero VAD output. Carries the per-pause list, which
    # raw_metrics only summarises, so the client can place each
    # pause on the time axis rather than just count them.
    analysis: dict[str, Any]

    # Short-lived link to the normalized recording, so the
    # client can play back what was analyzed.
    audio_url: str | None

    # Video track (additive; all null/"not_requested" when the
    # feature is off or the session did not request it).
    video_analysis_status: str = "not_requested"
    video_unavailable_reason: str | None = None
    visual_coaching_status: str = "not_requested"
    video_analysis: dict[str, Any] | None = None
    correlated_moments: list[dict[str, Any]] | None = None
    visual_feedback: dict[str, Any] | None = None
