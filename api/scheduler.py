from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from .models import APIKey, APIRequest, APIReservation
from .key_registry import APIKeyRegistry
from .rate_limiter import RateLimiter


class APIScheduler:
    """
    Capacity-aware scheduler.

    Responsibilities:
    - find compatible API keys
    - rank them by available capacity
    - atomically reserve capacity
    - release/commit reservations

    It does NOT make API calls.
    """

    def __init__(
        self,
        registry: APIKeyRegistry,
        rate_limiter: RateLimiter,
    ):
        self.registry = registry
        self.rate_limiter = rate_limiter

    # -----------------------------------------------------
    # Acquire
    # -----------------------------------------------------

    def acquire(
        self,
        request: APIRequest,
    ) -> Optional[APIReservation]:

        candidates = self._get_candidates(request)

        if not candidates:
            return None

        # -------------------------------------------------
        # Rank candidates from best to worst
        # -------------------------------------------------

        candidates = sorted(
            candidates,
            key=lambda key: self._score_key(
                key,
                request,
            ),
            reverse=True,
        )

        # -------------------------------------------------
        # Try candidates one by one
        #
        # This is important for concurrency.
        # A key may become unavailable between the
        # capacity check and the actual reservation.
        # -------------------------------------------------

        for key in candidates:

            if not self.rate_limiter.can_handle(
                key,
                request.estimated_tokens,
                request.estimated_requests,
            ):
                continue

            reservation = APIReservation(
                reservation_id=str(uuid4()),
                request_id=request.request_id,
                api_key_id=key.id,
                reserved_tokens=request.estimated_tokens,
                reserved_requests=request.estimated_requests,
                created_at=datetime.utcnow(),
            )

            # -------------------------------------------------
            # reserve() performs the actual atomic check
            # -------------------------------------------------

            success = self.rate_limiter.reserve(
                key,
                reservation,
            )

            if success:
                return reservation

        # -------------------------------------------------
        # No key currently has enough capacity
        # -------------------------------------------------

        return None

    # -----------------------------------------------------
    # Candidate selection
    # -----------------------------------------------------

    def _get_candidates(
        self,
        request: APIRequest,
    ) -> List[APIKey]:

        keys = self.registry.get_enabled_keys()

        candidates = []

        for key in keys:

            # Provider restriction
            if (
                request.provider is not None
                and key.provider != request.provider
            ):
                continue

            # Model restriction
            if (
                request.model is not None
                and key.model != request.model
            ):
                continue

            candidates.append(key)

        return candidates

    # -----------------------------------------------------
    # Key scoring
    # -----------------------------------------------------

    def _score_key(
        self,
        key: APIKey,
        request: APIRequest,
    ) -> float:

        remaining_tpm = (
            self.rate_limiter
            .remaining_tokens_per_minute(key)
        )

        remaining_tpd = (
            self.rate_limiter
            .remaining_tokens_per_day(key)
        )

        remaining_rpm = (
            self.rate_limiter
            .remaining_requests_per_minute(key)
        )

        remaining_rpd = (
            self.rate_limiter
            .remaining_requests_per_day(key)
        )

        # -------------------------------------------------
        # Convert remaining capacity to ratios
        # -------------------------------------------------

        tpm_ratio = (
            remaining_tpm / key.limits.tpm
            if key.limits.tpm > 0
            else 0
        )

        tpd_ratio = (
            remaining_tpd / key.limits.tpd
            if key.limits.tpd > 0
            else 0
        )

        rpm_ratio = (
            remaining_rpm / key.limits.rpm
            if key.limits.rpm > 0
            else 0
        )

        rpd_ratio = (
            remaining_rpd / key.limits.rpd
            if key.limits.rpd > 0
            else 0
        )

        # -------------------------------------------------
        # Weighted capacity score
        #
        # TPM gets the highest weight because token
        # capacity is generally the most important
        # resource for LLM requests.
        # -------------------------------------------------

        score = (
            tpm_ratio * 0.50
            + tpd_ratio * 0.25
            + rpm_ratio * 0.15
            + rpd_ratio * 0.10
        )

        return score

    # -----------------------------------------------------
    # Release reservation
    # -----------------------------------------------------

    def release(
        self,
        reservation: APIReservation,
    ) -> None:

        key = self.registry.get_key(
            reservation.api_key_id
        )

        self.rate_limiter.release(
            key,
            reservation,
        )

    # -----------------------------------------------------
    # Commit successful request
    # -----------------------------------------------------

    def commit(
        self,
        reservation: APIReservation,
        actual_tokens: Optional[int] = None,
    ) -> None:

        key = self.registry.get_key(
            reservation.api_key_id
        )

        self.rate_limiter.commit(
            key,
            reservation,
            actual_tokens=actual_tokens,
        )

    # -----------------------------------------------------
    # Get reserved API key
    # -----------------------------------------------------

    def get_reserved_key(
        self,
        reservation: APIReservation,
    ) -> APIKey:

        return self.registry.get_key(
            reservation.api_key_id
        )