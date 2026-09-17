"""
Deterministic validation of the visual-coaching LLM response (§7.5).
Applied in order, rules 1-2 reject the whole response (structural:
bad JSON, missing keys, an out-of-range category/polarity -- all
naturally expressed as a Pydantic schema, so a schema failure IS a
rule 1/2 failure); rules 3-5 are checked per item and drop only the
offending item; rule 6 (em dash, emoji) never fails anything -- an
em dash is rewritten to a comma, per the spec's own instruction, and
an emoji is folded into a content violation instead since the spec
gives no separate rewrite for it; rule 7 caps the survivors at 6.

service.py is the only caller: it does the retry-once-then-drop
orchestration described in §7.5 ("If any item fails rules 3-5: retry
the whole call once... If items still fail, drop the failing items
and keep the rest"), using violated_rules from this module to build
the retry message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

CATEGORIES = ("gaze", "gestures", "head", "integration", "coverage")
POLARITIES = ("strength", "improve", "neutral")

# §7.5 rule 4, verbatim.
NUMBER_WORDS = frozenset({
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "half", "twice", "percent", "percentage", "seconds", "minutes",
})

# §7.5 rule 5, verbatim -- kept in one constant as instructed.
AFFECT_WORDS = frozenset({
    "nervous", "nervousness", "anxious", "anxiety", "confident", "confidence",
    "insecure", "insecurity", "dishonest", "dishonesty", "scared", "afraid",
    "fear", "fearful", "bored", "boredom", "uneasy", "uncomfortable", "comfortable",
    "tense", "relaxed", "emotional", "emotion", "emotions", "feel", "feeling", "feelings",
    "shy", "timid", "arrogant", "passionate", "enthusiastic", "frustrated", "angry", "happy", "sad",
})

MAX_ITEMS = 6
EM_DASH = "—"

_DIGIT_RE = re.compile(r"\d")
_WORD_RE = re.compile(r"[A-Za-z']+")
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000026FF"
    "\U00002700-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U00002B00-\U00002BFF"
    "]"
)


# ---------------------------------------------------------------
# Structural schema (§7.5 rules 1-2)
# ---------------------------------------------------------------

class VisualFeedbackItem(BaseModel):
    id: str
    category: Literal["gaze", "gestures", "head", "integration", "coverage"]
    polarity: Literal["strength", "improve", "neutral"]
    moment_id: Optional[str] = None
    metric_keys: list[str] = Field(default_factory=list)
    observation_ids: list[str] = Field(default_factory=list)
    coaching: str

    model_config = ConfigDict(extra="forbid")


class VisualFeedbackResponse(BaseModel):
    visual_feedback: list[VisualFeedbackItem]
    summary: str

    model_config = ConfigDict(extra="forbid")


def parse_response(data: dict) -> VisualFeedbackResponse:
    """Raises pydantic.ValidationError -- rules 1-2, a whole-response failure."""
    return VisualFeedbackResponse.model_validate(data)


# ---------------------------------------------------------------
# Content checks (§7.5 rules 4-6)
# ---------------------------------------------------------------

def normalize_em_dashes(text: str) -> str:
    return text.replace(EM_DASH, ",")


def contains_forbidden_number_content(text: str) -> bool:
    if _DIGIT_RE.search(text) or "%" in text:
        return True
    words = {w.lower() for w in _WORD_RE.findall(text)}
    return not words.isdisjoint(NUMBER_WORDS)


def contains_affect_word(text: str) -> bool:
    words = {w.lower() for w in _WORD_RE.findall(text)}
    return not words.isdisjoint(AFFECT_WORDS)


def contains_emoji(text: str) -> bool:
    return bool(_EMOJI_RE.search(text))


# ---------------------------------------------------------------
# Per-item + whole-response validation (§7.5 rules 3-7)
# ---------------------------------------------------------------

@dataclass
class ValidationOutcome:
    items: list[dict]
    summary: str
    violated_rules: list[str] = field(default_factory=list)
    dropped_count: int = 0


def _item_violations(item: VisualFeedbackItem, input_payload: dict) -> list[str]:
    moments_by_id = {m["id"]: m for m in input_payload.get("moments", [])}
    ok_metric_keys = {m["key"] for m in input_payload.get("metrics", []) if m.get("status") == "ok"}

    violations = []

    if item.moment_id is not None:
        moment = moments_by_id.get(item.moment_id)
        if moment is None:
            violations.append("unknown_moment_id")
        else:
            valid_observation_ids = {o["id"] for o in moment.get("observations", [])}
            if not set(item.observation_ids) <= valid_observation_ids:
                violations.append("unknown_observation_id")

    if item.category != "coverage" and not set(item.metric_keys) <= ok_metric_keys:
        violations.append("metric_key_not_ok")

    if contains_forbidden_number_content(item.coaching):
        violations.append("number_content")

    if contains_affect_word(item.coaching):
        violations.append("affect_word")

    return violations


def validate(response: VisualFeedbackResponse, input_payload: dict) -> ValidationOutcome:
    summary = normalize_em_dashes(response.summary)
    summary_violations = []
    if contains_forbidden_number_content(summary):
        summary_violations.append("number_content")
    if contains_affect_word(summary):
        summary_violations.append("affect_word")
    if contains_emoji(summary):
        summary_violations.append("emoji")

    valid_items: list[dict] = []
    all_violations: set[str] = set(summary_violations)
    dropped = 0

    for item in response.visual_feedback:
        coaching = normalize_em_dashes(item.coaching)
        item = item.model_copy(update={"coaching": coaching})

        violations = _item_violations(item, input_payload)
        if contains_emoji(item.coaching):
            violations.append("emoji")

        if violations:
            all_violations.update(violations)
            dropped += 1
            continue

        valid_items.append(item.model_dump())

    if summary_violations:
        summary = ""

    kept = valid_items[:MAX_ITEMS]
    dropped += max(0, len(valid_items) - MAX_ITEMS)

    return ValidationOutcome(
        items=kept,
        summary=summary,
        violated_rules=sorted(all_violations),
        dropped_count=dropped,
    )
