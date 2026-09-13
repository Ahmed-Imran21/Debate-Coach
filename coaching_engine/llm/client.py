from typing import Optional

from api.client import APIClient


class LLMClient:
    """
    Compatibility wrapper for the coaching engine.

    The actual API key selection, rate limiting, reservation,
    provider selection, and usage tracking are handled by the
    centralized APIClient.

    Prompt construction and response parsing remain in the
    coaching_engine package.
    """

    DEFAULT_PROVIDER = "groq"
    DEFAULT_MODEL = "openai/gpt-oss-120b"

    # Conservative scheduler estimate.
    ESTIMATED_OUTPUT_TOKENS = 2500

    def __init__(
        self,
        api_client: Optional[APIClient] = None,
        model: str = DEFAULT_MODEL,
    ):
        """
        Initialize the coaching LLM client.

        Args:
            api_client:
                Optional shared APIClient.

            model:
                Model to request from the scheduler.
        """

        self.api_client = api_client or APIClient()

        self.provider = self.DEFAULT_PROVIDER
        self.model = model

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict,
        temperature: float = 0.2,
    ) -> str:
        """
        Send a coaching request through the centralized
        API system.

        Args:
            system_prompt:
                Instructions defining the model's role.

            user_prompt:
                The actual coaching analysis request.

            response_schema:
                Project response schema.

                Response validation remains in the existing
                coaching-engine parser.

            temperature:
                Controls response randomness.

        Returns:
            Raw JSON response string.
        """

        # -------------------------------------------------
        # Validate inputs
        # -------------------------------------------------

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

        # -------------------------------------------------
        # Estimate input tokens
        # -------------------------------------------------

        estimated_input_tokens = max(
            1,
            len(system_prompt + user_prompt) // 4,
        )

        estimated_tokens = (
            estimated_input_tokens
            + self.ESTIMATED_OUTPUT_TOKENS
        )

        # -------------------------------------------------
        # Request through centralized APIClient
        # -------------------------------------------------

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
        )

        # -------------------------------------------------
        # Handle API failure
        # -------------------------------------------------

        if not response.success:
            raise RuntimeError(
                f"Coaching LLM request failed: "
                f"{response.error}"
            )

        if not response.content:
            raise ValueError(
                "LLM returned an empty response."
            )

        # -------------------------------------------------
        # Return raw JSON string
        #
        # The existing coaching-engine parser will handle
        # validation and conversion.
        # -------------------------------------------------

        return response.content.strip()