import json
from pathlib import Path

from typing import Callable, Optional

from api.client import APIClient
from audio.transcript_shape import CanonicalTranscript, to_canonical

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
    """
    Render the transcript for the model as one line per
    segment, each prefixed with its canonical id:

        [s_004] The problem with their argument is ...

    The model hands those ids back; it never writes
    timestamps. Accepts either the raw transcription dict or
    an already-built CanonicalTranscript.
    """

    canonical = (
        transcription
        if isinstance(transcription, CanonicalTranscript)
        else to_canonical(transcription)
    )

    transcript_parts = [
        f"[{segment.id}] {segment.text}"
        for segment in canonical.segments
        if segment.text
    ]

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

    canonical = to_canonical(transcription)

    transcript = prepare_transcript(
        canonical
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
        session_id,
        canonical,
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