from faster_whisper import WhisperModel
from pathlib import Path
import json


# --------------------------------------------------
# Configuration
# --------------------------------------------------

MODEL_SIZE = "small"
DEVICE = "cpu"
COMPUTE_TYPE = "int8"


# --------------------------------------------------
# Load Whisper model
# --------------------------------------------------


model = WhisperModel(
    MODEL_SIZE,
    device=DEVICE,
    compute_type=COMPUTE_TYPE
)


# --------------------------------------------------
# Transcription function
# --------------------------------------------------

def transcribe_audio(audio_path, session_id, output_directory):
    """
    Transcribe an audio file using faster-whisper.

    Parameters:
        audio_path (str or Path):
            Path to the input WAV file.

        session_id (str):
            Unique ID belonging to this recording session.

        output_directory (str or Path):
            Directory where the transcript JSON should be saved.

    Returns:
        tuple:
            (session_id, transcript_path, transcript)
    """

    audio_path = Path(audio_path)
    output_directory = Path(output_directory)

    # Create the transcript directory if necessary
    output_directory.mkdir(
        parents=True,
        exist_ok=True
    )

    # Create transcript filename using the session ID
    output_path = output_directory / f"{session_id}.json"

    print()
    print(f"Transcribing session: {session_id}")
    print(f"Audio file: {audio_path}")

    # Run Whisper
    segments, info = model.transcribe(
        str(audio_path),
        word_timestamps=True
    )

    # Convert Whisper's generator into a list
    segments = list(segments)

    # Create our structured transcript
    transcript = {
        "session_id": session_id,
        "audio_file": str(audio_path),
        "language": info.language,
        "language_probability": info.language_probability,
        "segments": []
    }

    # Process every segment
    for segment in segments:

        segment_data = {
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip(),
            "words": []
        }

        # Process individual words
        if segment.words is not None:

            for word in segment.words:

                word_data = {
                    "word": word.word,
                    "start": word.start,
                    "end": word.end,
                    "probability": word.probability
                }

                segment_data["words"].append(
                    word_data
                )

        transcript["segments"].append(
            segment_data
        )

    # Save transcript
    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            transcript,
            file,
            indent=4,
            ensure_ascii=False
        )

    print()
    print(f"Transcript saved to: {output_path}")

    return session_id, output_path, transcript


# --------------------------------------------------
# Test the transcriber
# --------------------------------------------------

if __name__ == "__main__":

    session_id = "session_20260823_233450"

    audio_file = Path(
        f"audio/recordings/{session_id}.wav"
    )

    transcript_directory = Path(
        "transcription/transcripts"
    )

    transcribe_audio(
        audio_path=audio_file,
        session_id=session_id,
        output_directory=transcript_directory
    )