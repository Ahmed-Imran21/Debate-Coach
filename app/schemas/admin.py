import uuid

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


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    created_at: datetime
    last_seen_at: datetime | None
    session_count: int
    # In ADMIN_EMAILS. The admin force-delete refuses these; the page
    # uses it to show an "Admin" tag instead of a Delete button.
    is_admin: bool


class AdminUserPageOut(BaseModel):
    users: list[AdminUserOut]
    # Opaque; pass back as ?cursor= for the next page. Null on the last.
    next_cursor: str | None


class AdminDeleteUserRequest(BaseModel):
    # The calling admin's own password, re-checked before anything
    # else happens — not the target's, which the admin doesn't have.
    password: str
