from typing import Any, Dict, List, Optional

from groq import Groq

from ..models import APIKey


class GroqProvider:
    """
    Thin adapter around the Groq API.

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
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:

        client = Groq(api_key=api_key.key)

        request_kwargs: Dict[str, Any] = {
            "model": api_key.model,
            "messages": messages,
        }

        if max_tokens is not None:
            request_kwargs["max_tokens"] = max_tokens

        if temperature is not None:
            request_kwargs["temperature"] = temperature

        response = client.chat.completions.create(
            **request_kwargs
        )

        # -------------------------------------------------
        # Content
        # -------------------------------------------------

        content = ""

        if response.choices:
            content = response.choices[0].message.content or ""

        # -------------------------------------------------
        # Token usage
        # -------------------------------------------------

        actual_tokens = None

        usage = getattr(response, "usage", None)

        if usage is not None:

            total_tokens = getattr(
                usage,
                "total_tokens",
                None,
            )

            prompt_tokens = getattr(
                usage,
                "prompt_tokens",
                0,
            ) or 0

            completion_tokens = getattr(
                usage,
                "completion_tokens",
                0,
            ) or 0

            if total_tokens is not None:
                actual_tokens = total_tokens
            else:
                actual_tokens = (
                    prompt_tokens
                    + completion_tokens
                )

        # -------------------------------------------------
        # Finish reason
        # -------------------------------------------------

        finish_reason = None

        if response.choices:
            finish_reason = (
                response.choices[0].finish_reason
            )

        # -------------------------------------------------
        # Rate-limit headers
        # -------------------------------------------------

        rate_limit_headers = {}

        raw_response = getattr(
            response,
            "_response",
            None,
        )

        if raw_response is not None:

            headers = getattr(
                raw_response,
                "headers",
                None,
            )

            if headers is not None:

                rate_limit_headers = {
                    key.lower(): value
                    for key, value in headers.items()
                    if (
                        key.lower().startswith(
                            "x-ratelimit"
                        )
                        or key.lower() == "retry-after"
                    )
                }

        # -------------------------------------------------
        # Return normalized result
        # -------------------------------------------------

        return {
            "content": content,
            "actual_tokens": actual_tokens,
            "finish_reason": finish_reason,
            "usage": usage,
            "rate_limit_headers": rate_limit_headers,
            "raw_response": response,
        }