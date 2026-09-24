import json

from pathlib import Path
from typing import Optional


# ============================================================
# TRANSCRIPTION
# ============================================================

def transcribe_audio(
    audio_path,
    session_id,
    session_directory,
    whisper_client,
    language: Optional[str] = None,
    prompt: Optional[str] = None,
):
    """
    Transcribe one Debate Coach recording using the shared
    Groq WhisperClient.

    The WhisperClient is responsible for:

        - selecting a Whisper API key
        - queueing
        - rate-limit capacity
        - concurrency
        - cooldowns
        - calling Groq

    This function is responsible only for:

        - calling WhisperClient
        - converting its response into the existing
          transcription.json format
        - saving the result
    """

    audio_path = Path(audio_path)
    session_directory = Path(
        session_directory
    )

    session_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        session_directory
        / "transcription.json"
    )

    print()
    print(
        f"Transcribing session: "
        f"{session_id}"
    )

    print(
        f"Audio file: "
        f"{audio_path}"
    )

    # --------------------------------------------------------
    # Call shared Groq Whisper pool
    # --------------------------------------------------------

    result = whisper_client.transcribe(
        audio_path=audio_path,
        language=language,
        prompt=prompt,
        temperature=0.0,
    )

    # --------------------------------------------------------
    # Convert to the existing Debate Coach schema
    #
    # This is deliberately kept compatible with the old
    # faster-whisper output.
    # --------------------------------------------------------

    transcript = {
        "session_id": session_id,
        "audio_file": str(audio_path),
        "language": result.language,
        "language_probability": (
            result.language_probability
        ),
        "whisper_api_key_id": (
            result.api_key_id
        ),
        "segments": result.segments,
    }

    # --------------------------------------------------------
    # Save transcription
    # --------------------------------------------------------

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            transcript,
            file,
            indent=4,
            ensure_ascii=False,
        )

    print()
    print(
        f"Transcript saved to: "
        f"{output_path}"
    )

    return (
        output_path,
        transcript,
    )


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":

    from api.whisper import WhisperClient

    session_id = (
        "session_20260823_233450"
    )

    session_directory = Path(
        f"sessions/{session_id}"
    )

    audio_file = (
        session_directory
        / "recording.wav"
    )

    whisper_client = WhisperClient()

    try:

        transcribe_audio(
            audio_path=audio_file,
            session_id=session_id,
            session_directory=session_directory,
            whisper_client=whisper_client,
        )

    finally:

        whisper_client.shutdown()