from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock
from typing import Deque, Optional

from .models import APIKey, APIReservation


# ============================================================
# USAGE EVENTS
# ============================================================

@dataclass
class RequestEvent:
    """
    Represents one completed API request.
    """

    timestamp: datetime
    requests: int
    tokens: int


# ============================================================
# RATE LIMITER
# ============================================================

class RateLimiter:
    """
    Thread-safe rolling-window rate limiter.

    Tracks:

        RPM  -> requests in the last 60 seconds
        RPD  -> requests since the current UTC day started
        TPM  -> tokens in the last 60 seconds
        TPD  -> tokens since the current UTC day started

    Also tracks reservations so that concurrent requests cannot
    accidentally consume the same remaining capacity.

    Important:
        This is local accounting. Provider-reported usage and
        rate-limit headers should be used later to reconcile it.
    """

    MINUTE_WINDOW = timedelta(minutes=1)

    def __init__(self):
        self._lock = RLock()

        # --------------------------------------------------------
        # Usage history
        #
        # key_id -> deque of RequestEvent
        #
        # We keep events for the current day.
        # Old events are removed automatically.
        # --------------------------------------------------------

        self._events: dict[str, Deque[RequestEvent]] = {}

    # ============================================================
    # INTERNAL HELPERS
    # ============================================================

    def _get_events(
        self,
        api_key: APIKey,
    ) -> Deque[RequestEvent]:
        """
        Get or create the event history for a key.
        """

        if api_key.id not in self._events:
            self._events[api_key.id] = deque()

        return self._events[api_key.id]

    def _start_of_today(self) -> datetime:
        """
        Return today's UTC midnight.
        """

        now = datetime.utcnow()

        return datetime(
            year=now.year,
            month=now.month,
            day=now.day,
        )

    def _cleanup_events(
        self,
        api_key: APIKey,
    ) -> None:
        """
        Remove events that are older than the current UTC day.

        Events older than one day can never contribute to either
        the daily or minute rate limits.
        """

        events = self._get_events(api_key)

        day_start = self._start_of_today()

        while events and events[0].timestamp < day_start:
            events.popleft()

    def _get_minute_usage(
        self,
        api_key: APIKey,
    ) -> tuple[int, int]:
        """
        Return:

            (requests, tokens)

        used during the last 60 seconds.
        """

        events = self._get_events(api_key)

        now = datetime.utcnow()

        cutoff = now - self.MINUTE_WINDOW

        requests = 0
        tokens = 0

        for event in events:

            if event.timestamp > cutoff:
                requests += event.requests
                tokens += event.tokens

        return requests, tokens

    def _get_daily_usage(
        self,
        api_key: APIKey,
    ) -> tuple[int, int]:
        """
        Return:

            (requests, tokens)

        used since UTC midnight.
        """

        events = self._get_events(api_key)

        day_start = self._start_of_today()

        requests = 0
        tokens = 0

        for event in events:

            if event.timestamp >= day_start:
                requests += event.requests
                tokens += event.tokens

        return requests, tokens

    # ============================================================
    # REMAINING REQUESTS
    # ============================================================

    def remaining_requests_per_minute(
        self,
        api_key: APIKey,
    ) -> int:
        """
        Return requests still available in the current rolling
        60-second window.

        Reservations are included.
        """

        with self._lock:

            self._cleanup_events(api_key)

            requests_used, _ = self._get_minute_usage(api_key)

            remaining = (
                api_key.limits.rpm
                - requests_used
                - api_key.usage.active_requests
            )

            return max(0, remaining)

    def remaining_requests_per_day(
        self,
        api_key: APIKey,
    ) -> int:
        """
        Return requests still available today.
        """

        with self._lock:

            self._cleanup_events(api_key)

            requests_used, _ = self._get_daily_usage(api_key)

            remaining = (
                api_key.limits.rpd
                - requests_used
                - api_key.usage.active_requests
            )

            return max(0, remaining)

    # ============================================================
    # REMAINING TOKENS
    # ============================================================

    def remaining_tokens_per_minute(
        self,
        api_key: APIKey,
    ) -> int:
        """
        Return tokens still available in the rolling 60-second
        window.

        Reserved tokens are excluded from available capacity.
        """

        with self._lock:

            self._cleanup_events(api_key)

            _, tokens_used = self._get_minute_usage(api_key)

            remaining = (
                api_key.limits.tpm
                - tokens_used
                - api_key.usage.reserved_tokens
            )

            return max(0, remaining)

    def remaining_tokens_per_day(
        self,
        api_key: APIKey,
    ) -> int:
        """
        Return tokens still available today.
        """

        with self._lock:

            self._cleanup_events(api_key)

            _, tokens_used = self._get_daily_usage(api_key)

            remaining = (
                api_key.limits.tpd
                - tokens_used
                - api_key.usage.reserved_tokens
            )

            return max(0, remaining)

    # ============================================================
    # CAPACITY CHECK
    # ============================================================

    def can_handle(
        self,
        api_key: APIKey,
        estimated_tokens: int,
        estimated_requests: int = 1,
    ) -> bool:
        """
        Determine whether a key can currently handle a request.

        Checks:

            enabled
            cooldown
            RPM
            RPD
            TPM
            TPD
        """

        with self._lock:

            if estimated_tokens < 0:
                raise ValueError(
                    "estimated_tokens cannot be negative."
                )

            if estimated_requests <= 0:
                raise ValueError(
                    "estimated_requests must be greater than zero."
                )

            self._cleanup_events(api_key)

            now = datetime.utcnow()

            # ----------------------------------------------------
            # Enabled
            # ----------------------------------------------------

            if not api_key.enabled:
                return False

            # ----------------------------------------------------
            # Cooldown
            # ----------------------------------------------------

            if api_key.cooldown_until is not None:

                if now < api_key.cooldown_until:
                    return False

                # Cooldown has expired.
                api_key.cooldown_until = None

            # ----------------------------------------------------
            # Remaining capacity
            # ----------------------------------------------------

            remaining_rpm = (
                self.remaining_requests_per_minute(
                    api_key
                )
            )

            remaining_rpd = (
                self.remaining_requests_per_day(
                    api_key
                )
            )

            remaining_tpm = (
                self.remaining_tokens_per_minute(
                    api_key
                )
            )

            remaining_tpd = (
                self.remaining_tokens_per_day(
                    api_key
                )
            )

            return (
                remaining_rpm >= estimated_requests
                and remaining_rpd >= estimated_requests
                and remaining_tpm >= estimated_tokens
                and remaining_tpd >= estimated_tokens
            )

    # ============================================================
    # RESERVATION
    # ============================================================

    def reserve(
        self,
        api_key: APIKey,
        reservation: APIReservation,
    ) -> bool:
        """
        Atomically reserve capacity.

        This is critical for concurrent requests.

        Example:

            Key has 5,000 TPM remaining.

            User A reserves 3,000.

            User B now sees only 2,000 remaining and
            cannot reserve another 3,000.

        """

        with self._lock:

            if not self.can_handle(
                api_key,
                reservation.reserved_tokens,
                reservation.reserved_requests,
            ):
                return False

            api_key.usage.reserved_tokens += (
                reservation.reserved_tokens
            )

            api_key.usage.active_requests += (
                reservation.reserved_requests
            )

            return True

    # ============================================================
    # COMMIT
    # ============================================================

    def commit(
        self,
        api_key: APIKey,
        reservation: APIReservation,
        actual_tokens: Optional[int] = None,
    ) -> None:
        """
        Convert a reservation into actual usage.

        If actual_tokens is supplied, the provider's actual
        usage is recorded.

        Otherwise the original estimate is used.
        """

        with self._lock:

            self._cleanup_events(api_key)

            tokens_used = (
                actual_tokens
                if actual_tokens is not None
                else reservation.reserved_tokens
            )

            if tokens_used < 0:
                raise ValueError(
                    "actual_tokens cannot be negative."
                )

            # ----------------------------------------------------
            # Remove reservation
            # ----------------------------------------------------

            api_key.usage.reserved_tokens = max(
                0,
                api_key.usage.reserved_tokens
                - reservation.reserved_tokens,
            )

            api_key.usage.active_requests = max(
                0,
                api_key.usage.active_requests
                - reservation.reserved_requests,
            )

            # ----------------------------------------------------
            # Add actual usage event
            # ----------------------------------------------------

            event = RequestEvent(
                timestamp=datetime.utcnow(),
                requests=reservation.reserved_requests,
                tokens=tokens_used,
            )

            events = self._get_events(api_key)

            events.append(event)

    # ============================================================
    # RELEASE
    # ============================================================

    def release(
        self,
        api_key: APIKey,
        reservation: APIReservation,
    ) -> None:
        """
        Release a reservation without recording usage.

        Used when the API request never actually consumed
        provider capacity.
        """

        with self._lock:

            api_key.usage.reserved_tokens = max(
                0,
                api_key.usage.reserved_tokens
                - reservation.reserved_tokens,
            )

            api_key.usage.active_requests = max(
                0,
                api_key.usage.active_requests
                - reservation.reserved_requests,
            )

    # ============================================================
    # COOLDOWN
    # ============================================================

    def set_cooldown(
        self,
        api_key: APIKey,
        seconds: int,
    ) -> None:
        """
        Temporarily prevent a key from being selected.
        """

        if seconds < 0:
            raise ValueError(
                "Cooldown seconds cannot be negative."
            )

        with self._lock:

            api_key.cooldown_until = (
                datetime.utcnow()
                + timedelta(seconds=seconds)
            )

    def clear_cooldown(
        self,
        api_key: APIKey,
    ) -> None:
        """
        Remove the key's cooldown.
        """

        with self._lock:
            api_key.cooldown_until = None

    # ============================================================
    # USAGE SNAPSHOT
    # ============================================================

    def get_usage(
        self,
        api_key: APIKey,
    ) -> dict:
        """
        Return current usage for a key.
        """

        with self._lock:

            self._cleanup_events(api_key)

            minute_requests, minute_tokens = (
                self._get_minute_usage(api_key)
            )

            daily_requests, daily_tokens = (
                self._get_daily_usage(api_key)
            )

            return {
                "requests_this_minute": minute_requests,
                "requests_today": daily_requests,

                "tokens_this_minute": minute_tokens,
                "tokens_today": daily_tokens,

                "reserved_tokens": (
                    api_key.usage.reserved_tokens
                ),

                "active_requests": (
                    api_key.usage.active_requests
                ),
            }

    # ============================================================
    # FULL STATUS
    # ============================================================

    def get_status(
        self,
        api_key: APIKey,
    ) -> dict:
        """
        Return a complete quota/status snapshot.
        """

        with self._lock:

            usage = self.get_usage(api_key)

            now = datetime.utcnow()

            cooldown_active = (
                api_key.cooldown_until is not None
                and now < api_key.cooldown_until
            )

            return {
                "key_id": api_key.id,

                "provider": api_key.provider,

                "model": api_key.model,

                "enabled": api_key.enabled,

                "cooldown_active": cooldown_active,

                "cooldown_until": (
                    api_key.cooldown_until.isoformat()
                    if api_key.cooldown_until is not None
                    else None
                ),

                "rpm": {
                    "limit": api_key.limits.rpm,
                    "used": usage[
                        "requests_this_minute"
                    ],
                    "remaining": self.remaining_requests_per_minute(
                        api_key
                    ),
                },

                "rpd": {
                    "limit": api_key.limits.rpd,
                    "used": usage[
                        "requests_today"
                    ],
                    "remaining": self.remaining_requests_per_day(
                        api_key
                    ),
                },

                "tpm": {
                    "limit": api_key.limits.tpm,
                    "used": usage[
                        "tokens_this_minute"
                    ],
                    "reserved": usage[
                        "reserved_tokens"
                    ],
                    "remaining": self.remaining_tokens_per_minute(
                        api_key
                    ),
                },

                "tpd": {
                    "limit": api_key.limits.tpd,
                    "used": usage[
                        "tokens_today"
                    ],
                    "remaining": self.remaining_tokens_per_day(
                        api_key
                    ),
                },

                "active_requests": usage[
                    "active_requests"
                ],
            }

    # ============================================================
    # PROVIDER RECONCILIATION
    # ============================================================

    def reconcile_usage(
        self,
        api_key: APIKey,
        reservation: APIReservation,
        actual_tokens: int,
    ) -> None:
        """
        Record provider-reported actual token usage.

        This is essentially an explicit version of commit()
        intended for provider reconciliation.
        """

        self.commit(
            api_key,
            reservation,
            actual_tokens=actual_tokens,
        )