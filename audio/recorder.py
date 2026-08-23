import sounddevice as sd
import soundfile as sf
import numpy as np
from pathlib import Path


# -----------------------------
# Configuration
# -----------------------------

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "float32"


# -----------------------------
# Recording function
# -----------------------------

def record_audio(duration, output_path):
    """
    Record audio from the default microphone and save it as a WAV file.

    Parameters:
        duration (float): Recording duration in seconds.
        output_path (str or Path): Where the WAV file should be saved.

    Returns:
        Path: Path to the saved audio file.
    """

    print(f"Recording for {duration} seconds...")
    print("Speak now!")

    # Record audio from the microphone
    audio = sd.rec(
        int(duration * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE
    )

    # Wait until recording is completely finished
    sd.wait()

    print("Recording finished.")

    # Convert the NumPy array into a WAV file
    sf.write(
        output_path,
        audio,
        SAMPLE_RATE
    )

    print(f"Audio saved to: {output_path}")

    return Path(output_path)


# -----------------------------
# Test the recorder
# -----------------------------

if __name__ == "__main__":

    output_directory = Path("audio/recordings")
    output_directory.mkdir(parents=True, exist_ok=True)

    output_file = output_directory / "test_recording.wav"

    record_audio(
        duration=10,
        output_path=output_file
    )