"""
preprocessing.py — reshapes the raw transcript into compact input for the
LLM call in semantic_analysis.py. No LLM/API calls happen here either;
this is plain text transformation, kept separate from delivery_metrics.py
because its job is "prepare for judgment," not "count things."
"""

import re
from typing import Any

from app.debate_analysis.delivery_metrics import FILLER_PHRASES, FILLER_WORDS, _normalize

MAX_INPUT_CHARS = 12_000  # keep the LLM prompt small; truncate long sessions


def _strip_fillers(words: list[dict[str, Any]]) -> list[str]:
    kept = []
    joined_lower = " ".join(_normalize(w["word"]) for w in words)

    skip_indices: set[int] = set()
    for phrase in FILLER_PHRASES:
        # crude but sufficient: mark word-index spans matching filler phrases
        phrase_words = phrase.split()
        normalized = [_normalize(w["word"]) for w in words]
        for i in range(len(normalized) - len(phrase_words) + 1):
            if normalized[i : i + len(phrase_words)] == phrase_words:
                skip_indices.update(range(i, i + len(phrase_words)))

    for i, w in enumerate(words):
        if i in skip_indices:
            continue
        if _normalize(w["word"]) in FILLER_WORDS:
            continue
        kept.append(w["word"])

    return kept


def build_llm_input(words: list[dict[str, Any]], raw_text: str | None = None) -> dict[str, Any]:
    """Produces the payload semantic_analysis.py sends to the LLM.

    Deliberately strips filler words/phrases before sending to the model —
    delivery_metrics.py already captured how many fillers there were and
    where; the semantic layer only needs the substance of what was argued.
    """
    cleaned_words = _strip_fillers(words)
    cleaned_text = " ".join(cleaned_words)
    cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()

    truncated = False
    if len(cleaned_text) > MAX_INPUT_CHARS:
        cleaned_text = cleaned_text[:MAX_INPUT_CHARS]
        truncated = True

    return {
        "cleaned_transcript": cleaned_text,
        "original_word_count": len(words),
        "cleaned_word_count": len(cleaned_words),
        "truncated": truncated,
    }
