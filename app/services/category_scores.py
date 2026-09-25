"""
Per-category coaching scores as session columns.

The single map from a coaching category to its column on
DebateSession, shared by the pipeline (which writes the columns when
coaching completes), scripts/backfill_category_scores.py (which fills
them for older sessions from feedback.json) and the progress
endpoint (which reads them).
"""

import math
from typing import Any, Optional

CATEGORY_COLUMNS: dict[str, str] = {
    "argumentation": "score_argumentation",
    "rebuttal": "score_rebuttal",
    "structure": "score_structure",
    "persuasion": "score_persuasion",
    "logic": "score_logic",
}

# Only rebuttal can legitimately be absent: None means the speech had
# nothing to rebut ("not scored"), which is not the same as zero.
NULLABLE_CATEGORIES = {"rebuttal"}


def parse_category_scores(scores: Any) -> dict[str, Optional[float]]:
    """
    Validate the "scores" block of a stored feedback.json and return
    {column: value}. Raises ValueError on anything that isn't a
    complete, in-range set of category scores. The caller logs and
    skips; nothing is ever guessed.
    """

    if not isinstance(scores, dict):
        raise ValueError("scores is not an object")

    columns: dict[str, Optional[float]] = {}

    for category, column in CATEGORY_COLUMNS.items():
        if category not in scores:
            raise ValueError(f"scores is missing {category!r}")

        value = scores[category]

        if value is None:
            if category not in NULLABLE_CATEGORIES:
                raise ValueError(f"{category} is null")
            columns[column] = None
            continue

        # bool is an int subclass: reject it explicitly.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{category} is not a number: {value!r}")

        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError(f"{category} is out of range: {value!r}")

        columns[column] = float(value)

    return columns
