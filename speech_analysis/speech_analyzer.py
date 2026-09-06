import json
from pathlib import Path

from .llm.client import LLMClient
from .llm.response_parser import parse_and_validate


# ---------------------------------------------------------
# Transcript loading
# ---------------------------------------------------------

def load_transcription(transcription_path):
    """
    Load transcription.json from disk.

    Parameters
    ----------
    transcription_path : str or Path
        Path to transcription.json.

    Returns
    -------
    dict
        Loaded transcription data.
    """

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
    Convert transcription.json into a timestamped text format
    suitable for the LLM.

    Parameters
    ----------
    transcription : dict
        Loaded transcription data.

    Returns
    -------
    str
        Timestamped transcript.
    """

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
    """
    Save SpeechContent as speech_content.json.

    Parameters
    ----------
    speech_content : SpeechContent
        Parsed semantic analysis.

    output_path : str or Path
        Destination path.
    """

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

def analyze_speech(session_id, session_directory):
    """
    Perform semantic LLM analysis for a session.

    Pipeline:

        transcription.json
              ↓
        prepare transcript
              ↓
            LLM
              ↓
        structured response
              ↓
        parse + validate
              ↓
        speech_content.json

    Parameters
    ----------
    session_id : str
        ID of the current session.

    session_directory : str or Path
        Directory containing the session files.

    Returns
    -------
    tuple
        (output_path, speech_content)
    """

    session_directory = Path(session_directory)

    transcription_path = (
        session_directory / "transcription.json"
    )

    output_path = (
        session_directory / "speech_content.json"
    )

    # -----------------------------------------------------
    # Load transcription
    # -----------------------------------------------------

    print("\nLoading transcription...")

    transcription = load_transcription(
        transcription_path
    )

    # -----------------------------------------------------
    # Prepare transcript
    # -----------------------------------------------------

    print("Preparing transcript...")

    transcript = prepare_transcript(
        transcription
    )

    # -----------------------------------------------------
    # Create LLM client
    # -----------------------------------------------------

    print("Initializing LLM client...")

    client = LLMClient()

    # -----------------------------------------------------
    # Analyze speech
    # -----------------------------------------------------

    print("Sending transcript to LLM...")

    response = client.analyze_speech(
        session_id=session_id,
        transcript=transcript
    )

    # -----------------------------------------------------
    # Parse and validate
    # -----------------------------------------------------

    print("Parsing LLM response...")

    speech_content = parse_and_validate(
        response
    )

    # -----------------------------------------------------
    # Save result
    # -----------------------------------------------------

    print("Saving semantic analysis...")

    save_speech_content(
        speech_content,
        output_path
    )

    print(
        f"Speech content saved to: {output_path}"
    )

    return output_path, speech_content