from datetime import datetime
from typing import Optional

from .models import APIKey, APIReservation
from .key_registry import APIKeyRegistry
from .rate_limiter import RateLimiter


class UsageTracker:
    """
    Central component for recording and reconciling API usage.

    The scheduler deals with reservations.

    The usage tracker deals with what actually happened.
    """

    def __init__(
        self,
        registry: APIKeyRegistry,
        rate_limiter: RateLimiter,
    ):
        self.registry = registry
        self.rate_limiter = rate_limiter

    # ============================================================
    # SUCCESSFUL REQUEST
    # ============================================================

    def record_success(
        self,
        reservation: APIReservation,
        actual_tokens: Optional[int] = None,
    ) -> None:
        """
        Record a successfully completed API request.

        actual_tokens should contain the token usage reported
        by the provider when available.

        If actual_tokens is None, the original estimate is used.
        """

        key = self.registry.get_key(
            reservation.api_key_id
        )

        self.rate_limiter.commit(
            key,
            reservation,
            actual_tokens=actual_tokens,
        )

    # ============================================================
    # FAILED REQUEST
    # ============================================================

    def record_failure(
        self,
        reservation: APIReservation,
    ) -> None:
        """
        Release the reservation when the request failed before
        its usage should be committed.
        """

        key = self.registry.get_key(
            reservation.api_key_id
        )

        self.rate_limiter.release(
            key,
            reservation,
        )

    # ============================================================
    # RATE LIMIT ERROR
    # ============================================================

    def record_rate_limit(
        self,
        reservation: APIReservation,
        cooldown_seconds: int,
    ) -> None:
        """
        Handle a provider rate-limit response.

        The reservation is released and the key is temporarily
        placed into cooldown.
        """

        key = self.registry.get_key(
            reservation.api_key_id
        )

        self.rate_limiter.release(
            key,
            reservation,
        )

        self.rate_limiter.set_cooldown(
            key,
            cooldown_seconds,
        )

    # ============================================================
    # MANUAL COOLDOWN
    # ============================================================

    def cooldown_key(
        self,
        key_id: str,
        seconds: int,
    ) -> None:
        """
        Manually place a key into cooldown.
        """

        key = self.registry.get_key(key_id)

        self.rate_limiter.set_cooldown(
            key,
            seconds,
        )

    # ============================================================
    # CLEAR COOLDOWN
    # ============================================================

    def clear_cooldown(
        self,
        key_id: str,
    ) -> None:
        """
        Remove a key's cooldown.
        """

        key = self.registry.get_key(key_id)

        self.rate_limiter.clear_cooldown(
            key,
        )

    # ============================================================
    # PROVIDER USAGE RECONCILIATION
    # ============================================================

    def reconcile_tokens(
        self,
        reservation: APIReservation,
        actual_tokens: int,
    ) -> None:
        """
        Reconcile estimated token usage with actual provider
        usage.

        This should be called when the provider tells us exactly
        how many tokens were consumed.
        """

        key = self.registry.get_key(
            reservation.api_key_id
        )

        self.rate_limiter.commit(
            key,
            reservation,
            actual_tokens=actual_tokens,
        )

    # ============================================================
    # STATUS
    # ============================================================

    def get_key_status(
        self,
        key_id: str,
    ) -> dict:
        """
        Return the current usage/quota status for a key.
        """

        key = self.registry.get_key(key_id)

        return self.rate_limiter.get_status(key)

    # ============================================================
    # ALL KEYS STATUS
    # ============================================================

    def get_all_status(self) -> list:
        """
        Return the current usage/quota status for every key.
        """

        keys = self.registry.get_all_keys()

        return [
            self.rate_limiter.get_status(key)
            for key in keys
        ]