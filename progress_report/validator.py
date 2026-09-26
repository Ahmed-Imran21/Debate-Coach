"""
Checks the LLM's progress report and enforces its limits in Python,
whatever the prompt said: at most MAX_BULLETS bullets, each a
non-empty plain sentence of sane length, no duplicates, and no
digits. The model is never sent a number (prompt.py), so a digit in
the output was invented.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .prompt import MAX_BULLETS

MAX_BULLET_CHARS = 400

_LEADING_MARKER = re.compile(r"^\s*(?:[-*•]+|\(?[a-z]\)|[a-z]\.)\s+", re.IGNORECASE)
_DIGIT = re.compile(r"\d")
_EM_DASH = re.compile(r"\s*—\s*")


@dataclass
class ValidationOutcome:
    bullets: list[str]
    dropped: int


class InvalidReport(ValueError):
    """The response has no usable bullets at all."""


def _clean(text: str) -> str:
    text = " ".join(text.split())
    text = _LEADING_MARKER.sub("", text)
    text = _EM_DASH.sub(", ", text).replace("–", "-")
    return text.strip()


def validate(raw: Any) -> ValidationOutcome:
    """
    raw: the model's response, a JSON string or already-parsed dict.
    Returns the kept bullets (at most MAX_BULLETS) and how many were
    dropped. Raises InvalidReport if none are usable.
    """

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InvalidReport("response is not valid JSON") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("bullets"), list):
        raise InvalidReport("response has no 'bullets' list")

    kept: list[str] = []
    seen: set[str] = set()
    dropped = 0

    for item in raw["bullets"]:
        if not isinstance(item, str):
            dropped += 1
            continue
        text = _clean(item)
        key = text.lower()
        if not text or len(text) > MAX_BULLET_CHARS or _DIGIT.search(text) or key in seen:
            dropped += 1
            continue
        seen.add(key)
        kept.append(text)

    dropped += max(0, len(kept) - MAX_BULLETS)
    kept = kept[:MAX_BULLETS]

    if not kept:
        raise InvalidReport("no usable bullets")

    return ValidationOutcome(bullets=kept, dropped=dropped)
