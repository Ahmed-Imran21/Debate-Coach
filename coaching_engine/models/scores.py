from dataclasses import dataclass, field
from typing import Dict


@dataclass
class CategoryScores:
    """
    Scores for the individual coaching categories.
    Values should normally be between 0 and 100.
    """

    quantitative: float = 0.0
    argumentation: float = 0.0
    rebuttal: float = 0.0
    structure: float = 0.0
    persuasion: float = 0.0
    logic: float = 0.0


@dataclass
class CoachingScores:
    """
    Complete scoring result for a debate session.
    """

    categories: CategoryScores = field(default_factory=CategoryScores)
    overall: float = 0.0

    def as_dict(self) -> Dict[str, float]:
        """
        Return scores in a JSON-friendly format.
        """

        return {
            "quantitative": self.categories.quantitative,
            "argumentation": self.categories.argumentation,
            "rebuttal": self.categories.rebuttal,
            "structure": self.categories.structure,
            "persuasion": self.categories.persuasion,
            "logic": self.categories.logic,
            "overall": self.overall,
        }