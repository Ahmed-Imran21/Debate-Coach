import json

from typing import Callable, Optional

from api.client import APIClient

from .schemas import SpeechAnalysisResponse
from .prompts import SYSTEM_PROMPT, build_analysis_prompt


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
            raise RuntimeError(
                "LLM response failed speech-analysis "
                "schema validation."
            ) from exc

        return parsed_response