import os
import queue

from faster_whisper import WhisperModel
from pathlib import Path
import json


# --------------------------------------------------
# Configuration
# --------------------------------------------------

MODEL_SIZE = "small"
DEVICE = "cpu"
COMPUTE_TYPE = "int8"

# Number of Whisper model instances kept warm and ready.
#
# faster-whisper / ctranslate2 model objects are not guaranteed
# safe for unsynchronized concurrent inference calls from
# multiple threads. Serializing every transcription behind a
# single lock would erase concurrency for a multi-user server,
# so instead we keep a small, fixed pool of independent model
# instances: up to POOL_SIZE transcriptions can run truly in
# parallel, and additional concurrent calls simply block until
# an instance frees up rather than spawning unbounded instances
# (which would exhaust memory/CPU under load).
POOL_SIZE = int(os.environ.get("WHISPER_POOL_SIZE", "2"))


# --------------------------------------------------
# Model pool
# --------------------------------------------------

class _WhisperModelPool:
    """
    Thread-safe pool of preloaded Whisper model instances.
    """

    def __init__(self, size: int):

        if size < 1:
            raise ValueError(
                "WHISPER_POOL_SIZE must be at least 1."
            )

        self._pool: "queue.Queue[WhisperModel]" = queue.Queue()

        print(f"Loading {size} Whisper model instance(s)...")

        for _ in range(size):

            self._pool.put(
                WhisperModel(
                    MODEL_SIZE,
                    device=DEVICE,
                    compute_type=COMPUTE_TYPE,
                )
            )

        print("Whisper model pool ready.")

    def acquire(self) -> WhisperModel:
        """
        Block until a model instance is available, then return it.
        """

        return self._pool.get()

    def release(self, model: WhisperModel) -> None:
        """
        Return a model instance to the pool.
        """

        self._pool.put(model)


_model_pool = _WhisperModelPool(POOL_SIZE)


# --------------------------------------------------
# Transcription function
# --------------------------------------------------

def transcribe_audio(audio_path, session_id, session_directory):
    """
    Transcribe an audio file using faster-whisper.

    Parameters:
        audio_path (str or Path):
            Path to the input WAV file.

        session_id (str):
            Unique ID belonging to this recording session.

        session_directory (str or Path):
            Directory belonging to the current debate session.

    Returns:
        tuple:
            (transcript_path, transcript)
    """

    audio_path = Path(audio_path)
    session_directory = Path(session_directory)

    session_directory.mkdir(
        parents=True,
        exist_ok=True
    )

    output_path = session_directory / "transcription.json"

    print()
    print(f"Transcribing session: {session_id}")
    print(f"Audio file: {audio_path}")

    model = _model_pool.acquire()

    try:

        segments, info = model.transcribe(
            str(audio_path),
            word_timestamps=True
        )

        segments = list(segments)

        transcript = {
            "session_id": session_id,
            "audio_file": str(audio_path),
            "language": info.language,
            "language_probability": info.language_probability,
            "segments": []
        }

        for segment in segments:

            segment_data = {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip(),
                "words": []
            }

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

    finally:

        # Always return the model to the pool, even if
        # transcription raised.
        _model_pool.release(model)

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

    return output_path, transcript


# --------------------------------------------------
# Test the transcriber
# --------------------------------------------------

if __name__ == "__main__":

    session_id = "session_20260823_233450"

    session_directory = Path(
        f"sessions/{session_id}"
    )

    audio_file = session_directory / "recording.wav"

    transcribe_audio(
        audio_path=audio_file,
        session_id=session_id,
        session_directory=session_directory
    )