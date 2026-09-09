from typing import Any, Dict, Optional

from openai import OpenAI


class LLMClient:
    """
    Handles communication with the language model.

    This class is responsible only for sending prompts to the LLM
    and returning the model's response.

    Prompt construction and response parsing are handled elsewhere.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
    ):
        """
        Initialize the LLM client.

        Args:
            api_key:
                OpenAI API key. If None, the OpenAI client will attempt
                to obtain the key from the environment.
            model:
                Name of the model to use.
        """

        if api_key:
            self.client = OpenAI(api_key=api_key)
        else:
            self.client = OpenAI()

        self.model = model

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> str:
        """
        Send a prompt to the language model and return its response.

        Args:
            system_prompt:
                Instructions defining the role and behavior of the model.

            user_prompt:
                The actual content to be analyzed.

            temperature:
                Controls response randomness. A low value is preferred
                for consistent coaching analysis.

        Returns:
            The model's response as a string.
        """

        if not system_prompt.strip():
            raise ValueError("system_prompt cannot be empty.")

        if not user_prompt.strip():
            raise ValueError("user_prompt cannot be empty.")

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
        )

        content = response.choices[0].message.content

        if content is None:
            raise ValueError("LLM returned an empty response.")

        return content.strip()