from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class SessionCreatedResponse(BaseModel):
    session_id: str
    status: str


class SessionStatusResponse(BaseModel):
    session_id: str
    status: str
    created_at: str
    updated_at: str
    error: Optional[str] = None
    estimated_wait_seconds: Optional[float] = None


class ScoreBreakdown(BaseModel):
    quantitative: float
    argumentation: float
    rebuttal: float
    structure: float
    persuasion: float
    logic: float
    overall: float


class FeedbackItemResponse(BaseModel):
    severity: str
    title: str
    category: str
    issue: str
    evidence: List[str] = []
    explanation: Optional[str] = None
    recommendation: Optional[str] = None


class SessionResultsResponse(BaseModel):
    session_id: str
    status: str
    scores: Optional[ScoreBreakdown] = None
    feedback: List[FeedbackItemResponse] = []


class ApiKeyStatusResponse(BaseModel):
    key_id: str
    provider: str
    model: str
    enabled: bool
    cooldown_active: bool
    rpm: Dict[str, Any]
    rpd: Dict[str, Any]
    tpm: Dict[str, Any]
    tpd: Dict[str, Any]
    active_requests: int


class SystemStatusResponse(BaseModel):
    queue_size: int
    keys: List[ApiKeyStatusResponse]