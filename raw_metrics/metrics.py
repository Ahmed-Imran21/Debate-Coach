import json
from pathlib import Path


def load_json(file_path):
    """
    Load and return JSON data from a file.
    """
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def calculate_word_count(transcription):
    """
    Calculate the total number of words using the word-level
    timestamps from transcription.json.
    """
    word_count = 0

    for segment in transcription.get("segments", []):
        word_count += len(segment.get("words", []))

    return word_count


def calculate_wpm(word_count, speech_duration):
    """
    Calculate words per minute based on actual speech duration.

    Returns 0 if speech duration is zero.
    """
    if speech_duration <= 0:
        return 0

    return round(word_count / (speech_duration / 60), 2)


def calculate_pause_metrics(pauses):
    """
    Calculate aggregate pause statistics.
    """
    if not pauses:
        return {
            "count": 0,
            "total_duration": 0,
            "average_duration": 0,
            "longest_duration": 0
        }

    durations = [
        pause.get("duration", 0)
        for pause in pauses
    ]

    total_duration = sum(durations)
    count = len(durations)

    return {
        "count": count,
        "total_duration": round(total_duration, 2),
        "average_duration": round(total_duration / count, 2),
        "longest_duration": round(max(durations), 2)
    }


def build_raw_metrics(
    session_id,
    transcription,
    audio_analysis,
    filler_results,
    stutter_results
):
    """
    Build the complete raw metrics structure.

    This function only deals with objective/raw speech metrics.
    It does not generate scores, feedback, strengths, weaknesses,
    or recommendations.
    """

    speech_duration = audio_analysis.get("speech_duration", 0)
    total_duration = audio_analysis.get("total_duration", 0)
    silence_duration = audio_analysis.get("silence_duration", 0)
    speech_percentage = audio_analysis.get("speech_percentage", 0)

    pauses = audio_analysis.get("pauses", [])

    word_count = calculate_word_count(transcription)
    words_per_minute = calculate_wpm(
        word_count,
        speech_duration
    )

    pause_metrics = calculate_pause_metrics(pauses)

    raw_metrics = {
        "session_id": session_id,

        "speech": {
            "total_duration": round(total_duration, 2),
            "speech_duration": round(speech_duration, 2),
            "silence_duration": round(silence_duration, 2),
            "speech_percentage": round(speech_percentage, 2),
            "word_count": word_count,
            "words_per_minute": words_per_minute
        },

        "pauses": pause_metrics,

        "fillers": {
            "count": filler_results.get("count", 0),
            "words": filler_results.get("words", {}),
            "instances": filler_results.get("instances", [])
        },

        "stutters": {
            "count": stutter_results.get("count", 0),
            "instances": stutter_results.get("instances", [])
        }
    }

    return raw_metrics


def analyze_metrics(session_id, session_directory):
    """
    Analyze a completed session and generate raw_metrics.json.

    Expected session directory structure:

        sessions/
        └── session_<id>/
            ├── recording.wav
            ├── transcription.json
            ├── analysis.json
            └── raw_metrics.json

    Returns:
        tuple:
            (output_path, raw_metrics)
    """

    session_directory = Path(session_directory)

    transcription_path = session_directory / "transcription.json"
    analysis_path = session_directory / "analysis.json"
    output_path = session_directory / "raw_metrics.json"

    # Validate required files
    if not transcription_path.exists():
        raise FileNotFoundError(
            f"Transcription file not found: {transcription_path}"
        )

    if not analysis_path.exists():
        raise FileNotFoundError(
            f"Audio analysis file not found: {analysis_path}"
        )

    # Load existing analysis data
    transcription = load_json(transcription_path)
    audio_analysis = load_json(analysis_path)

    # Import detectors here to keep responsibilities separated
    from .filler_detector import detect_fillers
    from .stutter_detector import detect_stutters

    # Detect fillers
    filler_results = detect_fillers(transcription)

    # Detect stutters
    stutter_results = detect_stutters(transcription)

    # Build final metrics
    raw_metrics = build_raw_metrics(
        session_id=session_id,
        transcription=transcription,
        audio_analysis=audio_analysis,
        filler_results=filler_results,
        stutter_results=stutter_results
    )

    # Save raw_metrics.json
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(
            raw_metrics,
            file,
            indent=4,
            ensure_ascii=False
        )

    return output_path, raw_metrics


if __name__ == "__main__":

    output_path, metrics = analyze_metrics(
        session_id,
        session_directory
    )

    print(f"Raw metrics saved to: {output_path}")
    print(json.dumps(metrics, indent=4, ensure_ascii=False))