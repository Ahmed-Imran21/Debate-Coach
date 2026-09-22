from datetime import datetime

from pydantic import BaseModel


class KeyUsageOut(BaseModel):
    key_id: str
    label: str
    provider: str

    requests_used: int
    requests_limit: int
    requests_remaining: int

    prompt_tokens: int
    completion_tokens: int
    tokens_used: int
    tokens_limit: int
    tokens_remaining: int

    window_reset_at: datetime | None

    # Supplementary only — see app/services/key_usage.py. Null for
    # most Gemini keys; Gemini doesn't return these the way Groq
    # does.
    last_rate_limit_headers: dict[str, str] | None


class StorageUsageOut(BaseModel):
    used_bytes: int
    used_gb: float
    quota_gb: float
    remaining_gb: float


class AdminStatsOut(BaseModel):
    active_users: int
    total_signups: int
    keys: list[KeyUsageOut]
    storage: StorageUsageOut


class AdminWhoAmIOut(BaseModel):
    email: str
    is_admin: bool
