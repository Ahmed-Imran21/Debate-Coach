import json
from pathlib import Path
from typing import Any, Dict

from ..models.session import CoachingSession


def load_json(file_path: Path) -> Dict[str, Any]:
    """
    Load a JSON file and return its contents as a dictionary.
    """

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not file_path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")

    try:
        with file_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON file: {file_path}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in: {file_path}")

    return data


def load_session(session_id: str, sessions_dir: str = "sessions") -> CoachingSession:
    """
    Load the raw metrics and speech content for a debate session.

    Expected session structure:

        sessions/
        └── <session_id>/
            ├── raw_metrics.json
            └── speech_content.json

    Returns:
        CoachingSession containing the session ID and both input files.
    """

    session_path = Path(sessions_dir) / session_id

    if not session_path.exists():
        raise FileNotFoundError(
            f"Session directory not found: {session_path}"
        )

    if not session_path.is_dir():
        raise ValueError(
            f"Session path is not a directory: {session_path}"
        )

    raw_metrics_path = session_path / "raw_metrics.json"
    speech_content_path = session_path / "speech_content.json"

    raw_metrics = load_json(raw_metrics_path)
    speech_content = load_json(speech_content_path)

    return CoachingSession(
        session_id=session_id,
        raw_metrics=raw_metrics,
        speech_content=speech_content,
    )