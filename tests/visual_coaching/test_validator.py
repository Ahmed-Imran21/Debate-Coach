"""§7.5: deterministic validation of the visual-coaching LLM response."""

import pytest
from pydantic import ValidationError

from visual_coaching.validator import (
    contains_affect_word,
    contains_emoji,
    contains_forbidden_number_content,
    normalize_em_dashes,
    parse_response,
    validate,
)


def _input_payload() -> dict:
    return {
        "metrics": [
            {"key": "camera_facing_ratio", "status": "ok"},
            {"key": "gaze_away_events_per_min", "status": "insufficient_coverage"},
        ],
        "moments": [
            {"id": "m_01", "observations": [{"id": "o_01a", "description": "…"}, {"id": "o_01b", "description": "…"}]},
        ],
    }


def _item(**overrides) -> dict:
    base = {
        "id": "vf_1", "category": "gaze", "polarity": "improve",
        "moment_id": "m_01", "metric_keys": ["camera_facing_ratio"],
        "observation_ids": ["o_01a"], "coaching": "Try to look at the lens more while you speak.",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------
# Structural (rules 1-2)
# ---------------------------------------------------------------

def test_parse_response_accepts_valid_shape():
    response = parse_response({"visual_feedback": [_item()], "summary": "Good work overall."})
    assert response.visual_feedback[0].id == "vf_1"


def test_parse_response_rejects_missing_key():
    with pytest.raises(ValidationError):
        parse_response({"visual_feedback": [_item()]})  # no summary


def test_parse_response_rejects_bad_category_or_polarity():
    with pytest.raises(ValidationError):
        parse_response({"visual_feedback": [_item(category="tone")], "summary": "s"})
    with pytest.raises(ValidationError):
        parse_response({"visual_feedback": [_item(polarity="positive")], "summary": "s"})


# ---------------------------------------------------------------
# Content primitives
# ---------------------------------------------------------------

def test_number_content_detects_digits_percent_and_whole_words_only():
    assert contains_forbidden_number_content("You paused for 4 seconds.")
    assert contains_forbidden_number_content("About 50% of the time.")
    assert contains_forbidden_number_content("You did this twice.")
    assert not contains_forbidden_number_content("You did this several times.")
    # "ten" must not match inside "attention" -- whole-word only.
    assert not contains_forbidden_number_content("Pay attention to your audience.")


def test_affect_word_matches_only_the_exact_listed_forms():
    assert contains_affect_word("You seemed nervous during the opening.")
    assert contains_affect_word("Try not to feel rushed.")
    # "feels" is not itself in the list (only feel/feeling/feelings are) --
    # confirms this is whole-word set matching, not stemming.
    assert not contains_affect_word("Whatever feels natural to you.")
    assert not contains_affect_word("Keep your delivery steady and clear.")


def test_normalize_em_dashes_replaces_with_comma():
    assert normalize_em_dashes("Look up—then continue.") == "Look up,then continue."


def test_contains_emoji_detects_real_emoji_not_punctuation():
    assert contains_emoji("Great job! \U0001F600")
    assert not contains_emoji("Great job! Keep it up.")


# ---------------------------------------------------------------
# validate(): per-item drop rules
# ---------------------------------------------------------------

def test_valid_item_is_kept_with_moment_id_present_even_when_none():
    response = parse_response({"visual_feedback": [_item(moment_id=None, metric_keys=[], observation_ids=[])], "summary": "Solid delivery."})
    outcome = validate(response, _input_payload())
    assert len(outcome.items) == 1
    assert "moment_id" in outcome.items[0]
    assert outcome.items[0]["moment_id"] is None
    assert outcome.violated_rules == []


def test_unknown_moment_id_is_dropped():
    response = parse_response({"visual_feedback": [_item(moment_id="m_99")], "summary": "s"})
    outcome = validate(response, _input_payload())
    assert outcome.items == []
    assert "unknown_moment_id" in outcome.violated_rules
    assert outcome.dropped_count == 1


def test_observation_id_not_belonging_to_its_moment_is_dropped():
    response = parse_response({"visual_feedback": [_item(observation_ids=["o_99"])], "summary": "s"})
    outcome = validate(response, _input_payload())
    assert outcome.items == []
    assert "unknown_observation_id" in outcome.violated_rules


def test_metric_key_not_ok_is_dropped_unless_category_is_coverage():
    response = parse_response({"visual_feedback": [_item(metric_keys=["gaze_away_events_per_min"])], "summary": "s"})
    outcome = validate(response, _input_payload())
    assert outcome.items == []
    assert "metric_key_not_ok" in outcome.violated_rules

    coverage_item = _item(category="coverage", metric_keys=["gaze_away_events_per_min"], moment_id=None, observation_ids=[])
    response2 = parse_response({"visual_feedback": [coverage_item], "summary": "s"})
    outcome2 = validate(response2, _input_payload())
    assert len(outcome2.items) == 1


def test_number_content_and_affect_words_drop_the_item():
    response = parse_response({"visual_feedback": [
        _item(id="vf_1", coaching="You paused for about 4 seconds there."),
        _item(id="vf_2", coaching="You seemed a little nervous in this part."),
    ], "summary": "s"})
    outcome = validate(response, _input_payload())
    assert outcome.items == []
    assert set(outcome.violated_rules) == {"number_content", "affect_word"}
    assert outcome.dropped_count == 2


def test_em_dash_is_normalized_not_dropped():
    response = parse_response({"visual_feedback": [_item(coaching="Look up—then keep going.")], "summary": "s"})
    outcome = validate(response, _input_payload())
    assert len(outcome.items) == 1
    assert outcome.items[0]["coaching"] == "Look up,then keep going."
    assert outcome.violated_rules == []


def test_emoji_in_coaching_drops_the_item():
    response = parse_response({"visual_feedback": [_item(coaching="Great job on this part! \U0001F44D")], "summary": "s"})
    outcome = validate(response, _input_payload())
    assert outcome.items == []
    assert "emoji" in outcome.violated_rules


def test_more_than_six_valid_items_are_capped():
    items = [_item(id=f"vf_{i}") for i in range(8)]
    response = parse_response({"visual_feedback": items, "summary": "s"})
    outcome = validate(response, _input_payload())
    assert len(outcome.items) == 6
    assert outcome.dropped_count == 2


def test_summary_with_number_content_is_blanked_not_the_items():
    response = parse_response({"visual_feedback": [_item()], "summary": "You improved by about 50 percent."})
    outcome = validate(response, _input_payload())
    assert outcome.summary == ""
    assert "number_content" in outcome.violated_rules
    assert len(outcome.items) == 1  # the item itself is unaffected
