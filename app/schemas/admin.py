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


class WhisperKeyUsageOut(BaseModel):
    """
    One Whisper (transcription) key, in its own units: requests and
    seconds of audio, never tokens. Rolling windows, as Groq enforces
    them. Requests count every attempt; audio counts successful
    transcriptions only. The key id only, never the key.
    """

    key_id: str
    label: str

    requests_last_minute: int
    requests_last_hour: int
    requests_last_24h: int
    requests_per_minute_limit: int
    requests_per_day_limit: int

    audio_seconds_last_hour: float
    audio_seconds_last_24h: float
    audio_seconds_per_hour_limit: int
    audio_seconds_per_day_limit: int

    failed_last_24h: int
    rate_limited_last_24h: int
    last_used_at: datetime | None


class AdminStatsOut(BaseModel):
    active_users: int
    total_signups: int
    keys: list[KeyUsageOut]
    # Transcription keys, separate from the LLM keys above (which are
    # unchanged).
    whisper_keys: list[WhisperKeyUsageOut] = []
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
