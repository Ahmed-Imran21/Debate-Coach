from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from .config import build_registry
from .models import (
    APIKey,
    APIRequest,
    APIReservation,
    APIResponse,
    QueuedRequest,
)
from .rate_limiter import RateLimiter
from .scheduler import APIScheduler
from .usage_tracker import UsageTracker
from .request_queue import RequestQueue
from .queue_worker import QueueWorker

from .providers.groq import GroqProvider
from .providers.gemini import GeminiProvider


class APIClient:
    """
    Central API gateway for the entire Debate Coach.

    Responsibilities:
        - maintain the API key registry
        - schedule requests
        - reserve rate-limit capacity
        - select the appropriate provider
        - execute the request
        - record actual usage
        - handle provider failures
        - handle rate-limit errors
        - queue requests when no key currently has capacity, and
          service them in the background as capacity frees up

    The application should create ONE APIClient and share
    that instance with all components that need an LLM. This
    is what makes concurrent multi-user usage safe: every
    session's requests compete for capacity through the same
    registry/rate limiter/scheduler/queue, instead of each
    session tracking its own (incorrect) view of quota.
    """

    def __init__(self):
        # -------------------------------------------------
        # Central API infrastructure
        # -------------------------------------------------

        self.registry = build_registry()

        self.rate_limiter = RateLimiter()

        self.scheduler = APIScheduler(
            registry=self.registry,
            rate_limiter=self.rate_limiter,
        )

        self.usage_tracker = UsageTracker(
            registry=self.registry,
            rate_limiter=self.rate_limiter,
        )

        # -------------------------------------------------
        # Waiting queue for requests with no available capacity
        # -------------------------------------------------

        self.request_queue = RequestQueue()

        self.queue_worker = QueueWorker(self)
        self.queue_worker.start()

        # -------------------------------------------------
        # Provider adapters
        # -------------------------------------------------

        self.providers = {
            "groq": GroqProvider(),
            "gemini": GeminiProvider(),
        }

    # -----------------------------------------------------
    # Shutdown
    # -----------------------------------------------------

    def shutdown(self) -> None:
        """
        Stop the background queue worker.

        Call this when the application (or server) is exiting
        so the worker thread does not linger.
        """

        self.queue_worker.stop()

    # -----------------------------------------------------
    # Generate
    # -----------------------------------------------------

    def generate(
        self,
        task: str,
        estimated_tokens: int,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        prompt: Optional[str] = None,
        system_instruction: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        wait_if_queued: bool = True,
        max_wait_seconds: Optional[float] = None,
        on_queued: Optional[Callable[[float], None]] = None,
    ) -> APIResponse:
        """
        Execute one LLM request through the centralized
        scheduler.

        The scheduler decides which API key should be used,
        honoring `provider`/`model` as a preference when given,
        or considering every enabled key when not.

        If no key currently has enough capacity, the request is
        placed on a waiting queue instead of failing outright.

        Args:
            wait_if_queued:
                If True (default), this call blocks until the
                queued request completes or max_wait_seconds
                elapses, then returns the final APIResponse.

                If False, the call returns immediately with
                success=False, queued=True, and
                estimated_wait_seconds set, without blocking.
                Use this from an async server that wants to
                notify the user of an ETA and poll or receive
                a callback separately, rather than holding a
                request thread open.

            max_wait_seconds:
                Maximum time to block waiting for a queued
                request when wait_if_queued=True. None means
                wait indefinitely.

            on_queued:
                Optional callback invoked with the estimated
                wait time in seconds, the moment a request is
                queued (before any blocking happens). Useful
                for surfacing an ETA to the user immediately.

        Returns:
            An APIResponse. When the request was queued, check
            `.queued` and `.estimated_wait_seconds` in addition
            to `.success`.
        """

        if estimated_tokens < 0:
            raise ValueError(
                "estimated_tokens cannot be negative."
            )

        request_id = str(uuid4())

        # -------------------------------------------------
        # Create scheduling request
        # -------------------------------------------------

        request = APIRequest(
            request_id=request_id,
            task=task,
            estimated_tokens=estimated_tokens,
            provider=provider,
            model=model,
            estimated_requests=1,
        )

        call_kwargs: Dict[str, Any] = {
            "messages": messages,
            "prompt": prompt,
            "system_instruction": system_instruction,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        # -------------------------------------------------
        # Try to reserve capacity immediately
        # -------------------------------------------------

        reservation = self.scheduler.acquire(request)

        if reservation is not None:

            api_key = self.scheduler.get_reserved_key(
                reservation
            )

            return self._execute_request(
                request=request,
                reservation=reservation,
                api_key=api_key,
                call_kwargs=call_kwargs,
            )

        # -------------------------------------------------
        # No key currently has capacity.
        # Queue instead of failing outright.
        # -------------------------------------------------

        estimated_wait = self.scheduler.estimate_wait(request)

        if on_queued is not None:
            on_queued(estimated_wait)

        if not wait_if_queued:

            return APIResponse(
                request_id=request_id,
                api_key_id="",
                success=False,
                queued=True,
                estimated_wait_seconds=estimated_wait,
                error=(
                    "No API key currently has enough available "
                    "capacity. Request has been queued."
                ),
            )

        queued_request = QueuedRequest(
            request=request,
            call_kwargs=call_kwargs,
            estimated_wait_seconds=estimated_wait,
        )

        self.request_queue.put(queued_request)

        completed = queued_request.event.wait(
            timeout=max_wait_seconds
        )

        if not completed:

            return APIResponse(
                request_id=request_id,
                api_key_id="",
                success=False,
                queued=True,
                estimated_wait_seconds=estimated_wait,
                error=(
                    "Timed out waiting for available API "
                    "capacity."
                ),
            )

        return queued_request.response

    # -----------------------------------------------------
    # Execute a reserved request against its provider
    #
    # Extracted so both the immediate path above and
    # QueueWorker (for requests that had to wait) can share
    # the exact same execution + bookkeeping logic.
    # -----------------------------------------------------

    def _execute_request(
        self,
        request: APIRequest,
        reservation: APIReservation,
        api_key: APIKey,
        call_kwargs: Dict[str, Any],
    ) -> APIResponse:

        provider_adapter = self.providers.get(
            api_key.provider
        )

        if provider_adapter is None:

            self.usage_tracker.record_failure(
                reservation
            )

            return APIResponse(
                request_id=request.request_id,
                api_key_id=api_key.id,
                success=False,
                error=(
                    f"Unsupported provider: "
                    f"{api_key.provider}"
                ),
            )

        messages = call_kwargs.get("messages")
        prompt = call_kwargs.get("prompt")
        system_instruction = call_kwargs.get(
            "system_instruction"
        )
        max_tokens = call_kwargs.get("max_tokens")
        temperature = call_kwargs.get("temperature")

        try:

            if api_key.provider == "groq":

                if messages is None:
                    raise ValueError(
                        "messages are required when "
                        "using Groq."
                    )

                result = provider_adapter.generate(
                    api_key=api_key,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

            elif api_key.provider == "gemini":

                if prompt is None:
                    raise ValueError(
                        "prompt is required when "
                        "using Gemini."
                    )

                result = provider_adapter.generate(
                    api_key=api_key,
                    prompt=prompt,
                    system_instruction=system_instruction,
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                )

            else:
                raise ValueError(
                    f"Unsupported provider: "
                    f"{api_key.provider}"
                )

            # -------------------------------------------------
            # Successful request
            # -------------------------------------------------

            actual_tokens = result.get(
                "actual_tokens"
            )

            self.usage_tracker.record_success(
                reservation=reservation,
                actual_tokens=actual_tokens,
            )

            return APIResponse(
                request_id=request.request_id,
                api_key_id=api_key.id,
                success=True,
                content=result.get("content"),
                actual_tokens=actual_tokens,
            )

        except Exception as error:

            error_message = str(error)

            # -------------------------------------------------
            # Rate-limit error
            # -------------------------------------------------

            if self._is_rate_limit_error(error):

                cooldown_seconds = (
                    self._get_retry_after(error)
                )

                self.usage_tracker.record_rate_limit(
                    reservation=reservation,
                    cooldown_seconds=cooldown_seconds,
                )

                return APIResponse(
                    request_id=request.request_id,
                    api_key_id=api_key.id,
                    success=False,
                    error=(
                        f"Rate limit reached for key "
                        f"{api_key.id}: "
                        f"{error_message}"
                    ),
                    status_code=429,
                )

            # -------------------------------------------------
            # Normal failure
            # -------------------------------------------------

            self.usage_tracker.record_failure(
                reservation
            )

            return APIResponse(
                request_id=request.request_id,
                api_key_id=api_key.id,
                success=False,
                error=error_message,
            )

    # -----------------------------------------------------
    # Rate-limit detection
    # -----------------------------------------------------

    @staticmethod
    def _is_rate_limit_error(
        error: Exception,
    ) -> bool:

        status_code = getattr(
            error,
            "status_code",
            None,
        )

        if status_code == 429:
            return True

        response = getattr(
            error,
            "response",
            None,
        )

        if response is not None:

            response_status = getattr(
                response,
                "status_code",
                None,
            )

            if response_status == 429:
                return True

        error_text = str(error).lower()

        rate_limit_phrases = [
            "rate limit",
            "rate_limit",
            "too many requests",
            "429",
            "quota exceeded",
            "resource exhausted",
        ]

        return any(
            phrase in error_text
            for phrase in rate_limit_phrases
        )

    # -----------------------------------------------------
    # Retry-after extraction
    # -----------------------------------------------------

    @staticmethod
    def _get_retry_after(
        error: Exception,
    ) -> float:

        # -------------------------------------------------
        # Direct retry_after attribute
        # -------------------------------------------------

        retry_after = getattr(
            error,
            "retry_after",
            None,
        )

        if retry_after is not None:

            try:
                return float(retry_after)

            except (
                TypeError,
                ValueError,
            ):
                pass

        # -------------------------------------------------
        # Response headers
        # -------------------------------------------------

        response = getattr(
            error,
            "response",
            None,
        )

        if response is not None:

            headers = getattr(
                response,
                "headers",
                None,
            )

            if headers:

                value = headers.get(
                    "retry-after"
                )

                if value is not None:

                    try:
                        return float(value)

                    except (
                        TypeError,
                        ValueError,
                    ):
                        pass

        # -------------------------------------------------
        # Safe fallback
        # -------------------------------------------------

        return 60.0

    # -----------------------------------------------------
    # API status
    # -----------------------------------------------------

    def get_status(
        self,
    ) -> List[Dict[str, Any]]:
        """
        Return the current status of every API key.
        """

        return self.usage_tracker.get_all_status()

    # -----------------------------------------------------
    # API keys
    # -----------------------------------------------------

    def get_keys(self):
        """
        Return all registered APIKey objects.
        """

        return self.registry.get_all_keys()

    # -----------------------------------------------------
    # Queue status
    # -----------------------------------------------------

    def get_queue_size(self) -> int:
        """
        Return the number of requests currently waiting for
        capacity to free up.
        """

        return self.request_queue.size()