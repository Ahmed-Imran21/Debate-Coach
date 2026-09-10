import os
from typing import Optional

from dotenv import load_dotenv
from groq import Groq


load_dotenv()


class LLMClient:
    """
    Handles communication with the Groq language model.

    This class is responsible only for:
        - connecting to Groq
        - sending prompts
        - requesting structured JSON output
        - returning the model response

    Prompt construction and response parsing are handled elsewhere.
    """

    DEFAULT_MODEL = "openai/gpt-oss-120b"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
    ):
        """
        Initialize the Groq client.

        Args:
            api_key:
                Optional Groq API key. If not provided, the
                GROQ_API_KEY environment variable is used.

            model:
                Groq model identifier.
        """

        api_key = api_key or os.getenv("GROQ_API_KEY")

        if not api_key:
            raise ValueError(
                "GROQ_API_KEY was not found. "
                "Set it in the environment or pass it explicitly."
            )

        self.client = Groq(api_key=api_key)
        self.model = model

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict,
        temperature: float = 0.2,
    ) -> str:
        """
        Send a prompt to Groq and return a structured JSON response.

        Args:
            system_prompt:
                Instructions defining the model's role and behavior.

            user_prompt:
                The actual analysis request.

            response_schema:
                JSON Schema that the model must follow.

            temperature:
                Controls randomness. A low value is preferred for
                consistent analytical feedback.

        Returns:
            The model's response as a JSON string.
        """

        if not system_prompt.strip():
            raise ValueError(
                "system_prompt cannot be empty."
            )

        if not user_prompt.strip():
            raise ValueError(
                "user_prompt cannot be empty."
            )

        if not isinstance(response_schema, dict):
            raise TypeError(
                "response_schema must be a dictionary."
            )

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=temperature,
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
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "debate_coaching_feedback",
                    "strict": True,
                    "schema": response_schema,
                },
            },
        )

        if not response.choices:
            raise ValueError(
                "Groq returned no response choices."
            )

        content = response.choices[0].message.content

        if content is None:
            raise ValueError(
                "Groq returned an empty response."
            )

        return content.strip()