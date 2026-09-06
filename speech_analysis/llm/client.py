import os

from dotenv import load_dotenv
from openai import OpenAI

from .schemas import SpeechAnalysisResponse
from .prompts import SYSTEM_PROMPT, build_analysis_prompt


# ---------------------------------------------------------
# Load environment variables
# ---------------------------------------------------------

load_dotenv()


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

MODEL_NAME = os.getenv(
    "DEBATE_COACH_MODEL",
    "gpt-4o-mini"
)

# ---------------------------------------------------------
# LLM Client
# ---------------------------------------------------------

class LLMClient:
    """
    Handles communication with the LLM API.
    """

    def __init__(self):
        """
        Initialize the LLM client.

        The API key is read from the OPENAI_API_KEY
        environment variable.
        """

        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is not set."
            )

        self.client = OpenAI(api_key=api_key)
        self.model = MODEL_NAME

    # -----------------------------------------------------
    # Semantic analysis
    # -----------------------------------------------------

    def analyze_speech(self, session_id, transcript):
        """
        Analyze a transcript using the LLM.

        Parameters
        ----------
        session_id : str
            ID of the current debate session.

        transcript : str
            Transcript to analyze.

        Returns
        -------
        SpeechAnalysisResponse
            Validated semantic analysis.
        """

        if not session_id:
            raise ValueError(
                "session_id cannot be empty."
            )

        if not transcript or not transcript.strip():
            raise ValueError(
                "transcript cannot be empty."
            )

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

        # -------------------------------------------------
        # Verify session ID
        # -------------------------------------------------

        if result.session_id != session_id:
            raise ValueError(
                "LLM returned an incorrect session_id. "
                f"Expected '{session_id}', "
                f"got '{result.session_id}'."
            )

        return result