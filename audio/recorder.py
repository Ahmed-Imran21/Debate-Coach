import sounddevice as sd
import soundfile as sf
import numpy as np

from pathlib import Path
from datetime import datetime
import threading


# -----------------------------
# Configuration
# -----------------------------

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "float32"


# -----------------------------
# Recording function
# -----------------------------

def record_audio(output_directory):
    """
    Record audio until the user presses Enter.

    Parameters:
        output_directory (str or Path):
            Directory where the WAV file should be saved.

    Returns:
        tuple:
            (session_id, audio_path)
    """

    # Generate a unique ID for this recording session
    session_id = datetime.now().strftime(
        "session_%Y%m%d_%H%M%S"
    )

    # Make sure the recordings directory exists
    output_directory = Path(output_directory)
    output_directory.mkdir(
        parents=True,
        exist_ok=True
    )

    # Create the filename using the session ID
    output_file = output_directory / f"{session_id}.wav"

    print()
    print("Press ENTER to start recording.")
    input()

    print()
    print("Recording started.")
    print("Speak now.")
    print("Press ENTER again to stop recording.")

    # This will contain chunks of audio
    audio_chunks = []

    # This event lets another thread tell the recording
    # loop when it should stop.
    stop_event = threading.Event()

    # Function that waits for the user to press Enter
    def wait_for_stop():
        input()
        stop_event.set()

    # Start the keyboard listener in another thread
    stop_thread = threading.Thread(
        target=wait_for_stop
    )

    stop_thread.start()

    # Start the microphone stream
    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype=DTYPE
    ) as stream:

        while not stop_event.is_set():

            # Read 100 milliseconds of audio
            data, overflowed = stream.read(
                int(SAMPLE_RATE * 0.1)
            )

            # Make a copy so the data remains safe
            audio_chunks.append(data.copy())

            # Warn us if the audio buffer overflowed
            if overflowed:
                print(
                    "Warning: audio buffer overflow detected."
                )

    # Make sure the keyboard thread has finished
    stop_thread.join()

    print()
    print("Recording stopped.")

    # Combine all recorded chunks into one NumPy array
    audio = np.concatenate(
        audio_chunks,
        axis=0
    )

    # Save the complete recording
    sf.write(
        output_file,
        audio,
        SAMPLE_RATE
    )

    print(f"Audio saved to: {output_file}")
    print(f"Session ID: {session_id}")

    return session_id, output_file


# -----------------------------
# Test the recorder
# -----------------------------

if __name__ == "__main__":

    recordings_directory = Path(
        "audio/recordings"
    )

    record_audio(
        output_directory=recordings_directory
    )