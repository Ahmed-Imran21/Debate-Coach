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

from .whisper import WhisperClient


class APIClient:
    """
    Central API gateway for the entire Debate Coach.

    This object owns TWO independent resource systems:

        1. LLM API system
           ----------------
           Groq/Gemini LLM keys
           token/request rate limiting
           LLM request queue

        2. Whisper API system
           ------------------
           Groq Whisper keys
           audio-second/request rate limiting
           Whisper request queue
           circular Whisper key pool

    Both are process-wide and shared by all sessions.
    """

    def __init__(self):

        # =====================================================
        # LLM API INFRASTRUCTURE
        # =====================================================

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

        self.request_queue = RequestQueue()

        self.queue_worker = QueueWorker(
            self
        )

        self.queue_worker.start()

        # =====================================================
        # LLM PROVIDERS
        # =====================================================

        self.providers = {
            "groq": GroqProvider(),
            "gemini": GeminiProvider(),
        }

        # =====================================================
        # WHISPER API INFRASTRUCTURE
        #
        # This is a SINGLE process-wide WhisperClient.
        #
        # Every session therefore shares the same Whisper
        # key pool and Whisper queue.
        # =====================================================

        self.whisper_client = WhisperClient()

    # =========================================================
    # SHUTDOWN
    # =========================================================

    def shutdown(self) -> None:
        """
        Shut down both API systems cleanly.
        """

        # -----------------------------------------------------
        # Stop LLM queue
        # -----------------------------------------------------

        self.queue_worker.stop()

        while True:

            queued_request = (
                self.request_queue.get_nowait()
            )

            if queued_request is None:
                break

            queued_request.response = APIResponse(
                request_id=(
                    queued_request
                    .request
                    .request_id
                ),
                api_key_id="",
                success=False,
                queued=True,
                estimated_wait_seconds=(
                    queued_request
                    .estimated_wait_seconds
                ),
                error=(
                    "APIClient is shutting down; "
                    "queued request was cancelled."
                ),
            )

            queued_request.event.set()

        # -----------------------------------------------------
        # Stop Whisper queue
        # -----------------------------------------------------

        self.whisper_client.shutdown()

    # =========================================================
    # LLM GENERATE
    # =========================================================

    def generate(
        self,
        task: str,
        estimated_tokens: int,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        messages: Optional[
            List[Dict[str, str]]
        ] = None,
        prompt: Optional[str] = None,
        system_instruction: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        wait_if_queued: bool = True,
        max_wait_seconds: Optional[float] = None,
        on_queued: Optional[
            Callable[[float], None]
        ] = None,
    ) -> APIResponse:

        if estimated_tokens < 0:
            raise ValueError(
                "estimated_tokens cannot be negative."
            )

        request_id = str(uuid4())

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
            "system_instruction": (
                system_instruction
            ),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        # -----------------------------------------------------
        # Immediate reservation
        # -----------------------------------------------------

        reservation = (
            self.scheduler.acquire(
                request
            )
        )

        if reservation is not None:

            api_key = (
                self.scheduler
                .get_reserved_key(
                    reservation
                )
            )

            return self._execute_request(
                request=request,
                reservation=reservation,
                api_key=api_key,
                call_kwargs=call_kwargs,
            )

        # -----------------------------------------------------
        # Queue
        # -----------------------------------------------------

        estimated_wait = (
            self.scheduler.estimate_wait(
                request
            )
        )

        if on_queued is not None:
            on_queued(
                estimated_wait
            )

        if not wait_if_queued:

            return APIResponse(
                request_id=request_id,
                api_key_id="",
                success=False,
                queued=True,
                estimated_wait_seconds=(
                    estimated_wait
                ),
                error=(
                    "No API key currently has enough "
                    "available capacity. Request has "
                    "been queued."
                ),
            )

        queued_request = QueuedRequest(
            request=request,
            call_kwargs=call_kwargs,
            estimated_wait_seconds=(
                estimated_wait
            ),
        )

        self.request_queue.put(
            queued_request
        )

        completed = (
            queued_request.event.wait(
                timeout=max_wait_seconds
            )
        )

        if not completed:

            return APIResponse(
                request_id=request_id,
                api_key_id="",
                success=False,
                queued=True,
                estimated_wait_seconds=(
                    estimated_wait
                ),
                error=(
                    "Timed out waiting for available "
                    "API capacity."
                ),
            )

        return queued_request.response

    # =========================================================
    # LLM EXECUTION
    # =========================================================

    def _execute_request(
        self,
        request: APIRequest,
        reservation: APIReservation,
        api_key: APIKey,
        call_kwargs: Dict[str, Any],
    ) -> APIResponse:

        provider_adapter = (
            self.providers.get(
                api_key.provider
            )
        )

        if provider_adapter is None:

            self.usage_tracker.record_failure(
                reservation
            )

            return APIResponse(
                request_id=(
                    request.request_id
                ),
                api_key_id=api_key.id,
                success=False,
                error=(
                    f"Unsupported provider: "
                    f"{api_key.provider}"
                ),
            )

        messages = call_kwargs.get(
            "messages"
        )

        prompt = call_kwargs.get(
            "prompt"
        )

        system_instruction = (
            call_kwargs.get(
                "system_instruction"
            )
        )

        max_tokens = call_kwargs.get(
            "max_tokens"
        )

        temperature = call_kwargs.get(
            "temperature"
        )

        try:

            if api_key.provider == "groq":

                if messages is None:

                    raise ValueError(
                        "messages are required "
                        "when using Groq."
                    )

                result = (
                    provider_adapter.generate(
                        api_key=api_key,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                )

            elif api_key.provider == "gemini":

                if prompt is None:

                    raise ValueError(
                        "prompt is required "
                        "when using Gemini."
                    )

                result = (
                    provider_adapter.generate(
                        api_key=api_key,
                        prompt=prompt,
                        system_instruction=(
                            system_instruction
                        ),
                        max_output_tokens=(
                            max_tokens
                        ),
                        temperature=(
                            temperature
                        ),
                    )
                )

            else:

                raise ValueError(
                    f"Unsupported provider: "
                    f"{api_key.provider}"
                )

            actual_tokens = result.get(
                "actual_tokens"
            )

            self.usage_tracker.record_success(
                reservation=reservation,
                actual_tokens=actual_tokens,
            )

            return APIResponse(
                request_id=(
                    request.request_id
                ),
                api_key_id=api_key.id,
                success=True,
                content=result.get(
                    "content"
                ),
                actual_tokens=(
                    actual_tokens
                ),
            )

        except Exception as error:

            error_message = str(error)

            if self._is_rate_limit_error(
                error
            ):

                cooldown_seconds = (
                    self._get_retry_after(
                        error
                    )
                )

                self.usage_tracker.record_rate_limit(
                    reservation=reservation,
                    cooldown_seconds=(
                        cooldown_seconds
                    ),
                )

                return APIResponse(
                    request_id=(
                        request.request_id
                    ),
                    api_key_id=api_key.id,
                    success=False,
                    error=(
                        f"Rate limit reached "
                        f"for key "
                        f"{api_key.id}: "
                        f"{error_message}"
                    ),
                    status_code=429,
                )

            self.usage_tracker.record_failure(
                reservation
            )

            return APIResponse(
                request_id=(
                    request.request_id
                ),
                api_key_id=api_key.id,
                success=False,
                error=error_message,
            )

    # =========================================================
    # RATE LIMIT DETECTION
    # =========================================================

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

        error_text = str(
            error
        ).lower()

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

    # =========================================================
    # RETRY AFTER
    # =========================================================

    @staticmethod
    def _get_retry_after(
        error: Exception,
    ) -> float:

        retry_after = getattr(
            error,
            "retry_after",
            None,
        )

        if retry_after is not None:

            try:

                return float(
                    retry_after
                )

            except (
                TypeError,
                ValueError,
            ):
                pass

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

                        return float(
                            value
                        )

                    except (
                        TypeError,
                        ValueError,
                    ):
                        pass

        return 60.0

    # =========================================================
    # LLM STATUS
    # =========================================================

    def get_status(
        self,
    ) -> List[Dict[str, Any]]:

        return (
            self.usage_tracker
            .get_all_status()
        )

    # =========================================================
    # LLM KEYS
    # =========================================================

    def get_keys(self):

        return (
            self.registry
            .get_all_keys()
        )

    # =========================================================
    # LLM QUEUE
    # =========================================================

    def get_queue_size(
        self,
    ) -> int:

        return (
            self.request_queue
            .size()
        )

    # =========================================================
    # WHISPER QUEUE
    # =========================================================

    def get_whisper_queue_size(
        self,
    ) -> int:

        return (
            self.whisper_client
            .get_queue_size()
        )

    # =========================================================
    # WHISPER STATUS
    # =========================================================

    def get_whisper_status(
        self,
    ):

        return (
            self.whisper_client
            .get_status()
        )