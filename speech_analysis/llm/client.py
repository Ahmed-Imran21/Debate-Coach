import os

from dotenv import load_dotenv
from openai import OpenAI

from .schemas import SpeechAnalysisResponse
from .prompts import SYSTEM_PROMPT, build_analysis_prompt


load_dotenv()

MODEL_NAME = os.getenv(
    "DEBATE_COACH_MODEL",
    "openai/gpt-oss-120b"
)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class LLMClient:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")

        if not api_key:
            raise ValueError(
                "GROQ_API_KEY environment variable is not set."
            )

        self.client = OpenAI(
            api_key=api_key,
            base_url=GROQ_BASE_URL
        )

        self.model = MODEL_NAME

    def analyze_speech(self, session_id, transcript):
        if not session_id:
            raise ValueError("session_id cannot be empty.")

        if not transcript or not transcript.strip():
            raise ValueError("transcript cannot be empty.")

        prompt = build_analysis_prompt(transcript)

        try:
            response = self.client.responses.parse(
                model=self.model,
                input=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                text_format=SpeechAnalysisResponse,
            )

        except Exception as e:
            raise RuntimeError(
                f"LLM request failed: {e}"
            ) from e

        if response.output_parsed is None:
            raise RuntimeError(
                "LLM returned no structured response."
            )

        result = response.output_parsed

        if result.session_id != session_id:
            raise ValueError(
                "LLM returned an incorrect session_id. "
                f"Expected '{session_id}', "
                f"got '{result.session_id}'."
            )

        return result