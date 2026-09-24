import subprocess

from pathlib import Path


TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1


class AudioConversionError(RuntimeError):
    """
    Raised when ffmpeg fails to normalize an uploaded audio file.
    """


def normalize_audio_to_wav(input_path, output_path) -> Path:
    """
    Convert an arbitrary uploaded audio file into 16kHz mono
    16-bit PCM WAV — the exact format audio/audio_analyzer.py's
    load_audio() strictly requires.

    Browser-recorded audio (e.g. via the MediaRecorder API)
    typically arrives as webm or ogg, not raw PCM WAV, so this
    conversion step is required before the rest of the existing
    pipeline can run unmodified.

    Requires ffmpeg to be installed and available on PATH.
    """

    input_path = Path(input_path)
    output_path = Path(output_path)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    command = [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-ar", str(TARGET_SAMPLE_RATE),
        "-ac", str(TARGET_CHANNELS),
        "-sample_fmt", "s16",
        "-f", "wav",
        str(output_path),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.returncode != 0:

        raise AudioConversionError(
            "ffmpeg failed to normalize uploaded audio:\n"
            + result.stderr.decode(
                "utf-8",
                errors="replace",
            )
        )

    return output_path