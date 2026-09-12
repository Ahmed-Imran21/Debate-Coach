from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


# ============================================================
# API KEY LIMITS
# ============================================================

@dataclass
class APILimits:
    """
    Static rate limits for an API key.

    All limits are expressed per the provider's documented
    limits for that particular key/account.
    """

    rpm: int
    rpd: int
    tpm: int
    tpd: int


# ============================================================
# API KEY USAGE
# ============================================================

@dataclass
class APIUsage:
    """
    Runtime usage information for an API key.

    The scheduler/rate limiter updates this object as requests
    are made and tokens are consumed.
    """

    requests_this_minute: int = 0
    requests_today: int = 0

    tokens_this_minute: int = 0
    tokens_today: int = 0

    # Tokens that have been reserved for requests that have
    # been assigned a key but have not completed yet.
    reserved_tokens: int = 0

    # Requests currently using this key.
    active_requests: int = 0

    # Timestamp of the beginning of the current minute window.
    minute_window_start: Optional[datetime] = None

    # Date associated with the current daily usage window.
    day: Optional[str] = None


# ============================================================
# API KEY
# ============================================================

@dataclass
class APIKey:
    """
    Represents one API key and everything the scheduler needs
    to know about it.
    """

    id: str

    provider: str

    model: str

    key: str

    limits: APILimits

    usage: APIUsage = field(default_factory=APIUsage)

    # If a provider temporarily rejects the key (for example
    # with a rate-limit response), the scheduler can place the
    # key into cooldown until this timestamp.
    cooldown_until: Optional[datetime] = None

    # Whether this key is currently available to the scheduler.
    enabled: bool = True


# ============================================================
# API REQUEST
# ============================================================

@dataclass
class APIRequest:
    """
    Represents one request that needs to be sent to an API.

    The scheduler receives this object and decides which API
    key should execute it.
    """

    request_id: str

    task: str

    estimated_tokens: int

    # Optional restrictions.
    # If None, the scheduler can consider any compatible key.
    provider: Optional[str] = None

    model: Optional[str] = None

    # Number of API requests this operation will consume.
    # Normally 1, but keeping this configurable makes the
    # scheduler more flexible.
    estimated_requests: int = 1


# ============================================================
# API RESERVATION
# ============================================================

@dataclass
class APIReservation:
    """
    Represents capacity reserved by a request before the
    actual API call is made.

    Reservations prevent two simultaneous users from seeing
    the same remaining capacity and both selecting the same key.
    """

    reservation_id: str

    request_id: str

    api_key_id: str

    reserved_tokens: int

    reserved_requests: int

    created_at: datetime = field(default_factory=datetime.utcnow)


# ============================================================
# API RESPONSE
# ============================================================

@dataclass
class APIResponse:
    """
    Standardized response returned by the API layer.

    Provider-specific response formats should be converted
    into this structure so the rest of the application does
    not need to know whether the request went through Groq,
    Gemini, etc.
    """

    request_id: str

    api_key_id: str

    success: bool

    content: Optional[str] = None

    actual_tokens: Optional[int] = None

    error: Optional[str] = None

    status_code: Optional[int] = None

    completed_at: datetime = field(default_factory=datetime.utcnow)