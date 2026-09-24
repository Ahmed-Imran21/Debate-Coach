import json
import logging

from typing import Callable, Optional

from api.client import APIClient

from .schemas import SpeechAnalysisResponse
from .prompts import SYSTEM_PROMPT, build_analysis_prompt


logger = logging.getLogger(__name__)


class SpeechAnalysisValidationError(RuntimeError):
    """
    Raised when the LLM's response for speech analysis fails
    schema validation. Carries the raw response text (always
    valid JSON at this point — a JSONDecodeError is raised
    separately, before this can happen) so a caller with access
    to object storage can persist it as a failure artifact.

    speech_analysis/ deliberately has no dependency on app/ or
    any storage backend (see app/core/config.py's layering note,
    and grep speech_analysis/audio/api/visual_analysis for "from
    app" — there isn't one), so this class only carries data; it
    does not attempt to persist itself. app/services/pipeline.py,
    which already imports both this package and storage.py, does
    that in its outer exception handler.

    Confirmed bug (2026-09-20): the transcript that triggered the
    validation error this class now preserves was gone by the time
    anyone could look at it — never uploaded (the pipeline only
    uploads artifacts after every stage succeeds), and deleted from
    local disk by the pipeline's own `finally: shutil.rmtree(...)`
    the moment the run failed. Diagnosing it required re-running
    Whisper against the original audio from scratch.
    """

    def __init__(self, message: str, raw_response: str):
        super().__init__(message)
        self.raw_response = raw_response


class LLMClient:
    """
    Compatibility wrapper for speech analysis.

    The actual API key selection, rate limiting, reservation,
    provider selection, usage tracking, and waiting queue are
    handled by the centralized APIClient.
    """

    PROVIDER = "groq"
    MODEL = "openai/gpt-oss-120b"

    ESTIMATED_OUTPUT_TOKENS = 4000

    def __init__(self, api_client=None):
        """
        Initialize the speech-analysis LLM client.

        Args:
            api_client:
                Optional shared APIClient.
        """

        self.api_client = api_client or APIClient()

    def analyze_speech(
        self,
        session_id,
        transcript,
        on_queued: Optional[Callable[[float], None]] = None,
    ):
        """
        Analyze a transcript and return a validated
        SpeechAnalysisResponse.

        Args:
            on_queued:
                Optional callback invoked with the estimated
                wait time (seconds) if this request has to wait
                for API capacity. Forwarded to
                APIClient.generate().
        """

        if not session_id:
            raise ValueError("session_id cannot be empty.")

        if not transcript or not transcript.strip():
            raise ValueError("transcript cannot be empty.")

        prompt = build_analysis_prompt(transcript)

        estimated_input_tokens = max(
            1,
            len(SYSTEM_PROMPT + prompt) // 4,
        )

        estimated_tokens = (
            estimated_input_tokens
            + self.ESTIMATED_OUTPUT_TOKENS
        )

        response = self.api_client.generate(
            task="speech_analysis",
            estimated_tokens=estimated_tokens,
            provider=self.PROVIDER,
            model=self.MODEL,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            max_tokens=self.ESTIMATED_OUTPUT_TOKENS,
            temperature=0.0,
            on_queued=on_queued,
            # Native JSON mode. The prompt says "JSON", which
            # Groq requires for this to be accepted.
            response_format="json",
        )

        if not response.success:
            raise RuntimeError(
                f"Speech analysis LLM request failed: "
                f"{response.error}"
            )

        if not response.content:
            raise RuntimeError(
                "LLM returned an empty response."
            )

        try:
            data = json.loads(response.content)

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "LLM returned invalid JSON for speech analysis."
            ) from exc

        if isinstance(data, dict):
            data.pop("session_id", None)

        try:
            parsed_response = (
                SpeechAnalysisResponse.model_validate(data)
            )

        except Exception as exc:
            # This is the only place the raw text is available at
            # all — response.content is not stored anywhere, and
            # data/exc are locals that vanish the moment this
            # function returns. Logged at ERROR level regardless of
            # whether the caller goes on to persist it (see
            # SpeechAnalysisValidationError's docstring): app's own
            # logging currently goes to the terminal only, not a
            # file (logging.basicConfig in app/main.py has no
            # FileHandler) — a real, separate gap, since this log
            # line is otherwise exactly as unrecoverable as the
            # working directory was.
            logger.error(
                "Speech analysis LLM response failed schema "
                "validation for session %s: %s\nRaw response:\n%s",
                session_id,
                exc,
                response.content,
            )
            raise SpeechAnalysisValidationError(
                "LLM response failed speech-analysis "
                "schema validation.",
                raw_response=response.content,
            ) from exc

        return parsed_response