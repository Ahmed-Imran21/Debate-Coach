from typing import Callable, Optional

from api.client import APIClient


class LLMClient:
    """
    Compatibility wrapper for the coaching engine.
    """

    DEFAULT_PROVIDER = "groq"
    DEFAULT_MODEL = "openai/gpt-oss-120b"

    ESTIMATED_OUTPUT_TOKENS = 2500

    def __init__(
        self,
        api_client: Optional[APIClient] = None,
        model: str = DEFAULT_MODEL,
    ):
        self.api_client = api_client or APIClient()

        self.provider = self.DEFAULT_PROVIDER
        self.model = model

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict,
        temperature: float = 0.2,
        on_queued: Optional[Callable[[float], None]] = None,
    ) -> str:
        """
        Send a coaching request through the centralized
        API system.

        Args:
            on_queued:
                Optional callback invoked with the estimated
                wait time (seconds) if this request has to wait
                for API capacity. Forwarded to
                APIClient.generate().
        """

        if (
            not isinstance(system_prompt, str)
            or not system_prompt.strip()
        ):
            raise ValueError(
                "system_prompt cannot be empty."
            )

        if (
            not isinstance(user_prompt, str)
            or not user_prompt.strip()
        ):
            raise ValueError(
                "user_prompt cannot be empty."
            )

        if not isinstance(response_schema, dict):
            raise TypeError(
                "response_schema must be a dictionary."
            )

        estimated_input_tokens = max(
            1,
            len(system_prompt + user_prompt) // 4,
        )

        estimated_tokens = (
            estimated_input_tokens
            + self.ESTIMATED_OUTPUT_TOKENS
        )

        response = self.api_client.generate(
            task="coaching_analysis",
            estimated_tokens=estimated_tokens,
            provider=self.provider,
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            max_tokens=self.ESTIMATED_OUTPUT_TOKENS,
            temperature=temperature,
            on_queued=on_queued,
        )

        if not response.success:
            raise RuntimeError(
                f"Coaching LLM request failed: "
                f"{response.error}"
            )

        if not response.content:
            raise ValueError(
                "LLM returned an empty response."
            )

        return response.content.strip()