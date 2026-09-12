from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from .models import APIKey, APIRequest, APIReservation
from .key_registry import APIKeyRegistry
from .rate_limiter import RateLimiter


class APIScheduler:
    """
    Central API-key scheduler.

    Responsible for:

        1. Finding keys compatible with a request.
        2. Checking their available capacity.
        3. Selecting the best key.
        4. Reserving capacity before returning the key.

    The scheduler does NOT make API calls itself.
    """

    def __init__(
        self,
        registry: APIKeyRegistry,
        rate_limiter: RateLimiter,
    ):
        self.registry = registry
        self.rate_limiter = rate_limiter

    # ============================================================
    # PUBLIC API
    # ============================================================

    def acquire(
        self,
        request: APIRequest,
    ) -> Optional[APIReservation]:
        """
        Find and reserve the best API key for a request.

        Returns:
            APIReservation if a suitable key exists.
            None if no key currently has enough capacity.
        """

        candidates = self._get_candidates(request)

        if not candidates:
            return None

        candidates = [
            key
            for key in candidates
            if self.rate_limiter.can_handle(
                key,
                request.estimated_tokens,
                request.estimated_requests,
            )
        ]

        if not candidates:
            return None

        selected_key = self._select_best_key(
            candidates,
            request,
        )

        reservation = APIReservation(
            reservation_id=str(uuid4()),
            request_id=request.request_id,
            api_key_id=selected_key.id,
            reserved_tokens=request.estimated_tokens,
            reserved_requests=request.estimated_requests,
            created_at=datetime.utcnow(),
        )

        success = self.rate_limiter.reserve(
            selected_key,
            reservation,
        )

        if not success:
            return None

        return reservation

    # ============================================================
    # FIND CANDIDATES
    # ============================================================

    def _get_candidates(
        self,
        request: APIRequest,
    ) -> List[APIKey]:
        """
        Find keys that are compatible with the request.
        """

        keys = self.registry.get_enabled_keys()

        candidates = []

        for key in keys:

            # ----------------------------------------------------
            # Provider restriction
            # ----------------------------------------------------

            if (
                request.provider is not None
                and key.provider != request.provider
            ):
                continue

            # ----------------------------------------------------
            # Model restriction
            # ----------------------------------------------------

            if (
                request.model is not None
                and key.model != request.model
            ):
                continue

            candidates.append(key)

        return candidates

    # ============================================================
    # SELECT BEST KEY
    # ============================================================

    def _select_best_key(
        self,
        candidates: List[APIKey],
        request: APIRequest,
    ) -> APIKey:
        """
        Select the key with the greatest remaining capacity.

        This is intentionally NOT simple round-robin.

        A key with 7,000 TPM remaining is more useful for a
        3,000-token request than a key with only 3,500 TPM remaining.

        We score keys based on their remaining TPM percentage.
        """

        def score(key: APIKey):

            remaining_tpm = (
                self.rate_limiter.remaining_tokens_per_minute(
                    key
                )
            )

            remaining_tpd = (
                self.rate_limiter.remaining_tokens_per_day(
                    key
                )
            )

            remaining_rpm = (
                self.rate_limiter.remaining_requests_per_minute(
                    key
                )
            )

            remaining_rpd = (
                self.rate_limiter.remaining_requests_per_day(
                    key
                )
            )

            # ----------------------------------------------------
            # Normalize capacity
            # ----------------------------------------------------

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

            # TPM gets the highest weight because token capacity
            # will generally be the important throughput constraint.
            return (
                tpm_ratio * 0.50
                + tpd_ratio * 0.25
                + rpm_ratio * 0.15
                + rpd_ratio * 0.10
            )

        return max(
            candidates,
            key=score,
        )

    # ============================================================
    # RELEASE
    # ============================================================

    def release(
        self,
        reservation: APIReservation,
    ) -> None:
        """
        Release a reservation when the request did not execute.

        This is useful when a worker fails before making the
        provider request.
        """

        key = self.registry.get_key(
            reservation.api_key_id
        )

        self.rate_limiter.release(
            key,
            reservation,
        )

    # ============================================================
    # COMMIT
    # ============================================================

    def commit(
        self,
        reservation: APIReservation,
        actual_tokens: Optional[int] = None,
    ) -> None:
        """
        Convert a reservation into actual usage after a request
        completes.
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
    # GET KEY
    # ============================================================

    def get_reserved_key(
        self,
        reservation: APIReservation,
    ) -> APIKey:
        """
        Return the API key associated with a reservation.
        """

        return self.registry.get_key(
            reservation.api_key_id
        )