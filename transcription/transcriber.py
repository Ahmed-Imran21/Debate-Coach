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

def transcribe_audio(audio_path, output_path):
    """
    Transcribe an audio file using faster-whisper.

    Parameters:
        audio_path (str or Path): Path to the input WAV file.
        output_path (str or Path): Path where the transcript JSON
                                   should be saved.

    Returns:
        dict: Structured transcript data.
    """

    audio_path = Path(audio_path)
    output_path = Path(output_path)

    print(f"Transcribing: {audio_path}")

    # Run Whisper
    segments, info = model.transcribe(
        str(audio_path),
        word_timestamps=True
    )

    # Convert Whisper's generator into a list
    segments = list(segments)

    # Store the complete transcript
    transcript = {
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

        # Store individual words
        if segment.words is not None:

            for word in segment.words:

                word_data = {
                    "word": word.word,
                    "start": word.start,
                    "end": word.end,
                    "probability": word.probability
                }

                segment_data["words"].append(word_data)

        transcript["segments"].append(segment_data)

    # Make sure the output directory exists
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # Save transcript as JSON
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

    print(f"Transcript saved to: {output_path}")

    return transcript


# --------------------------------------------------
# Test the transcriber
# --------------------------------------------------

if __name__ == "__main__":

    audio_file = Path(
        "audio/recordings/test_recording.wav"
    )

    transcript_file = Path(
        "transcription/transcripts/test_transcript.json"
    )

    transcribe_audio(
        audio_path=audio_file,
        output_path=transcript_file
    )