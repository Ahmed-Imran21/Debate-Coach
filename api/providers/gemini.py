from typing import Any, Dict, Optional

from google import genai

from ..models import APIKey


class GeminiProvider:
    """
    Thin adapter around the Gemini API.

    This class does NOT:
    - choose API keys
    - perform rate limiting
    - manage reservations
    - retry requests

    The scheduler/client layer handles those responsibilities.
    """

    def generate(
        self,
        api_key: APIKey,
        prompt: str,
        system_instruction: Optional[str] = None,
        max_output_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:

        client = genai.Client(
            api_key=api_key.key
        )

        # -------------------------------------------------
        # Build generation configuration
        # -------------------------------------------------

        config: Dict[str, Any] = {}

        if system_instruction is not None:
            config["system_instruction"] = (
                system_instruction
            )

        if max_output_tokens is not None:
            config["max_output_tokens"] = (
                max_output_tokens
            )

        if temperature is not None:
            config["temperature"] = temperature

        # -------------------------------------------------
        # Generate response
        # -------------------------------------------------

        response = client.models.generate_content(
            model=api_key.model,
            contents=prompt,
            config=config if config else None,
        )

        # -------------------------------------------------
        # Content
        # -------------------------------------------------

        content = getattr(
            response,
            "text",
            None,
        ) or ""

        # -------------------------------------------------
        # Token usage
        # -------------------------------------------------

        actual_tokens = None

        usage_metadata = getattr(
            response,
            "usage_metadata",
            None,
        )

        if usage_metadata is not None:

            total_tokens = getattr(
                usage_metadata,
                "total_token_count",
                None,
            )

            if total_tokens is not None:
                actual_tokens = total_tokens

        # -------------------------------------------------
        # Return normalized result
        # -------------------------------------------------

        return {
            "content": content,
            "actual_tokens": actual_tokens,
            "usage": usage_metadata,
            "raw_response": response,
        }