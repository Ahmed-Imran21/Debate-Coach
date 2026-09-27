"""
Share links: the owner's management responses, and the PUBLIC report
payload served at GET /v1/shared/{token}.

The public payload is a whitelist by construction. Every model below
declares only the fields that may leave the server, and pydantic
drops any other key (extra="ignore") at every level of nesting. The
stored documents carry things that must never be exposed: the
session's real id (inside video_analysis), device details
(source_summary), internal anchor ids, audio and object keys. None
of those are declared here, so none can get through. The exact key
set is pinned by tests/api/test_shares.py.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ShareStatusOut(BaseModel):
    sharing: bool
    created_at: datetime | None


class ShareCreatedOut(BaseModel):
    # Shown to the owner once. Only its hash is stored, so it can't
    # be shown again; "Create new link" issues a fresh one.
    token: str
    created_at: datetime


# ------------------------------------------------------------
# Public payload
# ------------------------------------------------------------


class _Whitelist(BaseModel):
    model_config = ConfigDict(extra="ignore")


class SharedMotion(_Whitelist):
    title: str
    description: str


class SharedFeedbackItem(_Whitelist):
    category: str
    title: str
    issue: str
    severity: str
    evidence: list[str] = []
    explanation: str | None = None
    recommendation: str | None = None


class SharedDelivery(_Whitelist):
    words_per_minute: float | None = None
    speech_duration: float | None = None
    filler_count: int | None = None
    pause_count: int | None = None
    stutter_count: int | None = None


class SharedVisualContext(_Whitelist):
    setting: str | None = None


class SharedVisualQuality(_Whitelist):
    context: SharedVisualContext = SharedVisualContext()
    warnings: list[str] = []


class SharedVisualMetric(_Whitelist):
    status: str
    value: float | None = None
    confidence: str | None = None


class SharedVideoAnalysis(_Whitelist):
    quality: SharedVisualQuality = SharedVisualQuality()
    metrics: dict[str, SharedVisualMetric] = {}


class SharedMomentAnchor(_Whitelist):
    type: str


class SharedMomentObservation(_Whitelist):
    id: str
    kind: str
    type: str | None = None
    duration_s: float | None = None
    direction: str | None = None
    metric: str | None = None
    unit_value: float | None = None
    session_value: float | None = None


class SharedMoment(_Whitelist):
    id: str
    polarity: str
    anchor: SharedMomentAnchor
    start: float
    end: float
    excerpt_text: str = ""
    observations: list[SharedMomentObservation] = []
    # Ranks the moments when coaching produced none (KeyMomentsList).
    salience: float = 0.0


class SharedVisualFeedbackItem(_Whitelist):
    id: str
    category: str
    polarity: str
    moment_id: str | None = None
    coaching: str


class SharedVisualFeedback(_Whitelist):
    visual_feedback: list[SharedVisualFeedbackItem] = []


class SharedReportOut(_Whitelist):
    title: str | None
    recorded_at: datetime
    motion: SharedMotion | None
    # A motion was set but coaching fell back and couldn't use it.
    motion_not_applied: bool = False
    scores: dict[str, float | None]
    feedback: list[SharedFeedbackItem]
    delivery: SharedDelivery

    # Visual delivery, named and shaped as the owner's report names
    # them so the same components render both, but with every nested
    # object cut down to the fields those components display.
    video_analysis_status: str = "not_requested"
    video_unavailable_reason: str | None = None
    visual_coaching_status: str = "not_requested"
    video_analysis: SharedVideoAnalysis | None = None
    correlated_moments: list[SharedMoment] | None = None
    visual_feedback: SharedVisualFeedback | None = None
