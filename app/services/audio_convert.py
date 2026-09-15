"""
Normalize arbitrary uploaded audio into the exact WAV format
audio/audio_analyzer.py's load_audio() requires.

Moved here from server/audio_convert.py. Browser recordings
arrive as webm/opus or mp4/aac depending on the platform, and
Silero VAD needs 16 kHz mono 16-bit PCM, so this conversion is
mandatory before the rest of the pipeline can run unmodified.

Requires ffmpeg on PATH. The Dockerfile installs it.
"""

import shutil
import subprocess

from pathlib import Path


TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1

# A speech longer than this is almost certainly a mistake, and
# transcription cost scales with length. Debate speeches top out
# around eight minutes; this leaves generous headroom.
MAX_DURATION_SECONDS = 1800


class AudioConversionError(RuntimeError):
    """
    Raised when ffmpeg cannot read or convert the upload.
    """


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def normalize_audio_to_wav(
    input_path,
    output_path,
) -> Path:

    input_path = Path(input_path)
    output_path = Path(output_path)

    if not ffmpeg_available():
        raise AudioConversionError(
            "ffmpeg is not installed on this server."
        )

    if not input_path.exists():
        raise AudioConversionError(
            f"Audio file not found: {input_path}"
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    command = [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-t", str(MAX_DURATION_SECONDS),
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

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise AudioConversionError(
            "Conversion produced an empty audio file."
        )

    return output_path
