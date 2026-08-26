import json
from pathlib import Path

import torch
from silero_vad import load_silero_vad, get_speech_timestamps


# ---------------------------------
# Configuration
# ---------------------------------

SAMPLE_RATE = 16000

MIN_SPEECH_DURATION_MS = 250
MIN_SILENCE_DURATION_MS = 300


# ---------------------------------
# Load VAD model
# ---------------------------------

print("Loading Silero VAD model...")

vad_model = load_silero_vad()

print("Silero VAD model loaded.")


# ---------------------------------
# Analyze audio
# ---------------------------------

def analyze_audio(audio_path, session_id, session_directory):
    """
    Analyze an audio recording using Silero VAD.

    Parameters:
        audio_path (str or Path):
            Path to the WAV recording.

        session_id (str):
            Unique ID of the recording session.

        session_directory (str or Path):
            Directory belonging to the current debate session.

    Returns:
        tuple:
            (session_id, output_path, analysis)
    """

    audio_path = Path(audio_path)
    session_directory = Path(session_directory)

    # Make sure the session directory exists
    session_directory.mkdir(
        parents=True,
        exist_ok=True
    )

    # Analysis belongs to this session
    output_path = session_directory / "analysis.json"

    print()
    print(f"Analyzing session: {session_id}")
    print(f"Audio file: {audio_path}")

    # ---------------------------------
    # Load audio
    # ---------------------------------

    audio, sample_rate = load_audio(audio_path)

    print(f"Sample rate: {sample_rate} Hz")

    # ---------------------------------
    # Detect speech
    # ---------------------------------

    speech_timestamps = get_speech_timestamps(
        audio,
        vad_model,
        sampling_rate=sample_rate,
        min_speech_duration_ms=MIN_SPEECH_DURATION_MS,
        min_silence_duration_ms=MIN_SILENCE_DURATION_MS
    )

    # ---------------------------------
    # Convert sample positions to seconds
    # ---------------------------------

    speech_segments = []

    for segment in speech_timestamps:

        start_seconds = (
            segment["start"] / sample_rate
        )

        end_seconds = (
            segment["end"] / sample_rate
        )

        speech_segments.append(
            {
                "start": start_seconds,
                "end": end_seconds,
                "duration": end_seconds - start_seconds
            }
        )

    # ---------------------------------
    # Calculate total duration
    # ---------------------------------

    total_samples = audio.shape[-1]

    total_duration = (
        total_samples / sample_rate
    )

    # ---------------------------------
    # Calculate speech duration
    # ---------------------------------

    speech_duration = sum(
        segment["duration"]
        for segment in speech_segments
    )

    # ---------------------------------
    # Calculate silence duration
    # ---------------------------------

    silence_duration = (
        total_duration - speech_duration
    )

    # ---------------------------------
    # Calculate speech percentage
    # ---------------------------------

    if total_duration > 0:

        speech_percentage = (
            speech_duration / total_duration
        ) * 100

    else:

        speech_percentage = 0

    # ---------------------------------
    # Calculate pauses
    # ---------------------------------

    pauses = []

    for i in range(
        len(speech_segments) - 1
    ):

        current_segment = speech_segments[i]
        next_segment = speech_segments[i + 1]

        pause_start = current_segment["end"]
        pause_end = next_segment["start"]

        pause_duration = (
            pause_end - pause_start
        )

        pauses.append(
            {
                "start": pause_start,
                "end": pause_end,
                "duration": pause_duration
            }
        )

    # ---------------------------------
    # Create analysis result
    # ---------------------------------

    analysis = {
        "session_id": session_id,
        "audio_file": str(audio_path),
        "sample_rate": sample_rate,
        "total_duration": total_duration,
        "speech_duration": speech_duration,
        "silence_duration": silence_duration,
        "speech_percentage": speech_percentage,
        "speech_segments": speech_segments,
        "pauses": pauses
    }

    # ---------------------------------
    # Save analysis
    # ---------------------------------

    with open(
        output_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            analysis,
            file,
            indent=4
        )

    print()
    print(
        f"Audio analysis saved to: {output_path}"
    )

    return (
        session_id,
        output_path,
        analysis
    )


# ---------------------------------
# Audio loading
# ---------------------------------

def load_audio(audio_path):
    """
    Load a PCM WAV file and return:

        audio
        sample rate
    """

    import wave
    import numpy as np

    with wave.open(str(audio_path), "rb") as wav_file:

        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frame_count = wav_file.getnframes()

        audio_bytes = wav_file.readframes(frame_count)

    # Our recorder produces 16-bit PCM audio.
    if sample_width != 2:
        raise ValueError(
            f"Expected 16-bit WAV audio, "
            f"but found {sample_width * 8}-bit audio."
        )

    # Convert raw bytes → NumPy int16 array
    audio = np.frombuffer(
        audio_bytes,
        dtype=np.int16
    )

    # Convert int16 → float32
    audio = audio.astype(
        np.float32
    ) / 32768.0

    # Convert stereo → mono if necessary
    if channels > 1:

        audio = audio.reshape(
            -1,
            channels
        )

        audio = np.mean(
            audio,
            axis=1
        )

    # Convert NumPy → PyTorch tensor
    audio = torch.from_numpy(
        audio
    )

    # Our recorder already uses 16 kHz.
    # Keep this check so the analyzer knows
    # what format it received.
    if sample_rate != SAMPLE_RATE:

        raise ValueError(
            f"Expected {SAMPLE_RATE} Hz audio, "
            f"but found {sample_rate} Hz."
        )

    return audio, sample_rate


# ---------------------------------
# Test the analyzer
# ---------------------------------

if __name__ == "__main__":

    session_id = "session_20260823_233450"

    session_directory = Path(
        f"sessions/{session_id}"
    )

    audio_file = session_directory / "recording.wav"

    analyze_audio(
        audio_path=audio_file,
        session_id=session_id,
        session_directory=session_directory
    )