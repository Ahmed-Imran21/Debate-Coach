from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class CategoryScores:
    """
    Scores for the individual coaching categories, 0 to 100.

    rebuttal is None when the speech had nothing to rebut (e.g. an
    opening speech): "not scored", which is different from scoring 0,
    and it's left out of the overall score.
    """

    quantitative: float = 0.0
    argumentation: float = 0.0
    rebuttal: Optional[float] = 0.0
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

    def as_dict(self) -> Dict[str, Optional[float]]:
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
