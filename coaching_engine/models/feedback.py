from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FeedbackItem:
    """
    Represents a single coaching observation or recommendation.
    """

    category: str
    title: str
    issue: str
    severity: str
    evidence: List[str] = field(default_factory=list)
    explanation: Optional[str] = None
    recommendation: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)