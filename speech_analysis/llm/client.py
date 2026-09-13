import json

from api.client import APIClient

from .schemas import SpeechAnalysisResponse
from .prompts import SYSTEM_PROMPT, build_analysis_prompt


class LLMClient:
    """
    Compatibility wrapper for speech analysis.

    The actual API key selection, rate limiting, reservation,
    provider selection, and usage tracking are handled by the
    centralized APIClient.

    This class remains here so the existing speech-analysis
    code does not need to change.
    """

    PROVIDER = "groq"
    MODEL = "openai/gpt-oss-120b"

    # Conservative estimate used by the scheduler.
    # Actual token usage is reconciled after the request.
    ESTIMATED_OUTPUT_TOKENS = 4000

    def __init__(self, api_client=None):
        """
        Initialize the speech-analysis LLM client.

        Args:
            api_client:
                Optional shared APIClient.

                The application should eventually create one
                APIClient and pass the same instance to all
                LLM clients.
        """

        self.api_client = api_client or APIClient()

    def analyze_speech(self, session_id, transcript):
        """
        Analyze a transcript and return a validated
        SpeechAnalysisResponse.
        """

        if not session_id:
            raise ValueError("session_id cannot be empty.")

        if not transcript or not transcript.strip():
            raise ValueError("transcript cannot be empty.")

        # -------------------------------------------------
        # Build prompt
        # -------------------------------------------------

        prompt = build_analysis_prompt(transcript)

        # -------------------------------------------------
        # Estimate tokens for the scheduler
        # -------------------------------------------------

        estimated_input_tokens = max(
            1,
            len(SYSTEM_PROMPT + prompt) // 4,
        )

        estimated_tokens = (
            estimated_input_tokens
            + self.ESTIMATED_OUTPUT_TOKENS
        )

        # -------------------------------------------------
        # Request through centralized APIClient
        # -------------------------------------------------

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
        )

        # -------------------------------------------------
        # Handle API failure
        # -------------------------------------------------

        if not response.success:
            raise RuntimeError(
                f"Speech analysis LLM request failed: "
                f"{response.error}"
            )

        if not response.content:
            raise RuntimeError(
                "LLM returned an empty response."
            )

        # -------------------------------------------------
        # Parse JSON
        # -------------------------------------------------

        try:
            data = json.loads(response.content)

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "LLM returned invalid JSON for speech analysis."
            ) from exc

        # -------------------------------------------------
        # Remove optional session_id if the model returns it
        # -------------------------------------------------

        if isinstance(data, dict):
            data.pop("session_id", None)

        # -------------------------------------------------
        # Validate against project schema
        # -------------------------------------------------

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