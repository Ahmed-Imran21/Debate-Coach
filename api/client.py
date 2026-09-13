from typing import Any, Dict, List, Optional
from uuid import uuid4

from .config import build_registry
from .models import APIRequest, APIResponse
from .rate_limiter import RateLimiter
from .scheduler import APIScheduler
from .usage_tracker import UsageTracker

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

    The application should create ONE APIClient and share
    that instance with all components that need an LLM.
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
        # Provider adapters
        # -------------------------------------------------

        self.providers = {
            "groq": GroqProvider(),
            "gemini": GeminiProvider(),
        }

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
    ) -> APIResponse:
        """
        Execute one LLM request through the centralized
        scheduler.

        The scheduler decides which API key should be used.
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

        # -------------------------------------------------
        # Reserve capacity
        # -------------------------------------------------

        reservation = self.scheduler.acquire(
            request
        )

        if reservation is None:
            return APIResponse(
                request_id=request_id,
                api_key_id="",
                success=False,
                error=(
                    "No API key currently has enough "
                    "available capacity."
                ),
            )

        # -------------------------------------------------
        # Get selected key
        # -------------------------------------------------

        api_key = (
            self.scheduler.get_reserved_key(
                reservation
            )
        )

        # -------------------------------------------------
        # Find provider adapter
        # -------------------------------------------------

        provider_adapter = self.providers.get(
            api_key.provider
        )

        if provider_adapter is None:

            self.usage_tracker.record_failure(
                reservation
            )

            return APIResponse(
                request_id=request_id,
                api_key_id=api_key.id,
                success=False,
                error=(
                    f"Unsupported provider: "
                    f"{api_key.provider}"
                ),
            )

        # -------------------------------------------------
        # Execute provider request
        # -------------------------------------------------

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
                request_id=request_id,
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
                    request_id=request_id,
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
                request_id=request_id,
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