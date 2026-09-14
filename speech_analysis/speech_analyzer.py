import json
from pathlib import Path

from typing import Callable, Optional

from api.client import APIClient

from .llm.client import LLMClient
from .llm.response_parser import parse_and_validate


# ---------------------------------------------------------
# Transcript loading
# ---------------------------------------------------------

def load_transcription(transcription_path):
    transcription_path = Path(transcription_path)

    if not transcription_path.exists():
        raise FileNotFoundError(
            f"Transcription file not found: {transcription_path}"
        )

    with open(transcription_path, "r", encoding="utf-8") as file:
        transcription = json.load(file)

    if "segments" not in transcription:
        raise ValueError(
            "Transcription does not contain 'segments'."
        )

    return transcription


# ---------------------------------------------------------
# Prepare transcript for LLM
# ---------------------------------------------------------

def prepare_transcript(transcription):
    transcript_parts = []

    for segment in transcription["segments"]:

        start = segment.get("start")
        end = segment.get("end")
        text = segment.get("text", "").strip()

        if start is None or end is None:
            continue

        if not text:
            continue

        transcript_parts.append(
            f"[{start:.2f} - {end:.2f}] {text}"
        )

    if not transcript_parts:
        raise ValueError(
            "Transcription contains no usable speech segments."
        )

    return "\n".join(transcript_parts)


# ---------------------------------------------------------
# Save semantic analysis
# ---------------------------------------------------------

def save_speech_content(speech_content, output_path):
    output_path = Path(output_path)

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(
            speech_content.to_dict(),
            file,
            indent=4,
            ensure_ascii=False
        )

    return output_path


# ---------------------------------------------------------
# Main speech analysis function
# ---------------------------------------------------------

def analyze_speech(
    session_id,
    session_directory,
    api_client=None,
    on_queued: Optional[Callable[[float], None]] = None,
):
    """
    Perform semantic LLM analysis for a session.

    Args:
        on_queued:
            Optional callback invoked with the estimated wait
            time (seconds) if this request has to wait for API
            capacity. Forwarded down to APIClient.generate().
    """

    session_directory = Path(session_directory)

    transcription_path = (
        session_directory / "transcription.json"
    )

    output_path = (
        session_directory / "speech_content.json"
    )

    print("\nLoading transcription...")

    transcription = load_transcription(
        transcription_path
    )

    print("Preparing transcript...")

    transcript = prepare_transcript(
        transcription
    )

    print("Initializing LLM client...")

    client = LLMClient(
        api_client=api_client
    )

    print("Sending transcript to LLM...")

    response = client.analyze_speech(
        session_id=session_id,
        transcript=transcript,
        on_queued=on_queued,
    )

    print("Parsing LLM response...")

    speech_content = parse_and_validate(
        response,
        session_id
    )

    print("Saving semantic analysis...")

    save_speech_content(
        speech_content,
        output_path
    )

    print(
        f"Speech content saved to: {output_path}"
    )

    return output_path, speech_content