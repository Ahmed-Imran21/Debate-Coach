from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class CoachingSession:
    """
    Represents the input data required by the coaching engine
    for a single debate session.
    """

    session_id: str
    raw_metrics: Dict[str, Any]
    speech_content: Dict[str, Any]