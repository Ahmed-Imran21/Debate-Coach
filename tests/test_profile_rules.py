"""
The profile page's rules, without HTTP or a database: username and
bio format, weekly goal and time zone validation, streak counting,
Monday-to-Sunday weeks, and personal bests.
"""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.services import profile as p

# ============================================================
# Username
# ============================================================


@pytest.mark.parametrize("raw, stored", [
    ("abc", "abc"),
    ("a_1", "a_1"),
    ("x" * 20, "x" * 20),
    ("debater_2026", "debater_2026"),
    ("  Ahmed_K  ", "ahmed_k"),  # trimmed and lowercased before checking
    ("___", "___"),
])
def test_valid_usernames(raw, stored):
    assert p.normalize_username(raw) == stored


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_a_blank_username_clears_it(raw):
    assert p.normalize_username(raw) is None


@pytest.mark.parametrize("raw", ["ab", "a", "x" * 21, "  ab  ", "🎤🎤"])
def test_username_length(raw):
    with pytest.raises(p.ProfileFieldError) as caught:
        p.normalize_username(raw)
    assert caught.value.field == "username" and caught.value.message == p.USERNAME_LENGTH_MESSAGE


@pytest.mark.parametrize("raw", ["ab-c", "ab c", "abc!", "@abc", "abc.def", "émile", "ab٣c", "abс", "ab\nc"])
def test_username_characters(raw):
    # Includes an Arabic-Indic digit and a Cyrillic "с" that looks like "c".
    with pytest.raises(p.ProfileFieldError) as caught:
        p.normalize_username(raw)
    assert caught.value.message == p.USERNAME_CHARS_MESSAGE


# ============================================================
# Bio
# ============================================================


def test_bio_keeps_line_breaks_and_trims():
    assert p.normalize_bio("  Line one\r\nLine two\rLine three\n  ") == "Line one\nLine two\nLine three"
    assert p.normalize_bio("a\tb") == "a b"


@pytest.mark.parametrize("raw", [None, "", " \n\t "])
def test_a_blank_bio_clears_it(raw):
    assert p.normalize_bio(raw) is None


def test_bio_length_is_in_characters():
    assert p.normalize_bio("x" * 160) == "x" * 160
    assert p.normalize_bio("ü" * 160) == "ü" * 160  # 320 bytes, 160 characters
    assert p.normalize_bio("🎤" * 160) == "🎤" * 160
    for too_long in ("x" * 161, "ü" * 161, "🎤" * 161):
        with pytest.raises(p.ProfileFieldError) as caught:
            p.normalize_bio(too_long)
        assert caught.value.field == "bio" and caught.value.message == p.BIO_LENGTH_MESSAGE


def test_bio_trailing_whitespace_doesnt_count():
    assert p.normalize_bio("x" * 160 + "   \n") == "x" * 160


@pytest.mark.parametrize("raw", ["a\x00b", "a\x07b", "a\x1bb", "a\x7fb"])
def test_bio_refuses_control_characters(raw):
    with pytest.raises(p.ProfileFieldError) as caught:
        p.normalize_bio(raw)
    assert caught.value.message == p.BIO_PLAIN_MESSAGE


def test_bio_is_stored_as_typed_not_formatted():
    text = "**bold** <b>x</b> https://example.com [link](https://x.y)"
    assert p.normalize_bio(text) == text


# ============================================================
# Weekly goal and time zone
# ============================================================


@pytest.mark.parametrize("goal", [1, 3, 7])
def test_weekly_goal_range(goal):
    assert p.validate_weekly_goal(goal) == goal


@pytest.mark.parametrize("goal", [0, 8, -1, True, 3.0, "3", None])
def test_weekly_goal_rejects(goal):
    with pytest.raises(p.ProfileFieldError) as caught:
        p.validate_weekly_goal(goal)
    assert caught.value.message == p.GOAL_MESSAGE


@pytest.mark.parametrize("zone", ["Asia/Karachi", "America/New_York", "UTC", "Asia/Calcutta", "Europe/London"])
def test_known_time_zones(zone):
    assert p.validate_time_zone(zone) == zone


@pytest.mark.parametrize("zone", ["", "Mars/Olympus", "../../etc/passwd", "/etc/localtime", "America", "asia/karachi", None, 5, "A" * 65])
def test_unknown_time_zones(zone):
    with pytest.raises(p.ProfileFieldError) as caught:
        p.validate_time_zone(zone)
    assert caught.value.message == p.TIME_ZONE_MESSAGE


# ============================================================
# Streak
# ============================================================

TODAY = date(2026, 9, 23)  # a Wednesday


def days_before(*offsets):
    return [TODAY - timedelta(days=n) for n in offsets]


def test_no_sessions():
    assert p.compute_streak([], TODAY) == p.Streak(current=0, longest=0, practised_today=False)


def test_consecutive_days_up_to_today():
    assert p.compute_streak(days_before(0, 1, 2), TODAY) == p.Streak(current=3, longest=3, practised_today=True)


def test_several_sessions_on_one_day_count_once():
    assert p.compute_streak(days_before(0, 0, 0, 1), TODAY).current == 2


def test_practised_yesterday_but_not_today_still_counts():
    streak = p.compute_streak(days_before(1, 2, 3), TODAY)
    assert streak == p.Streak(current=3, longest=3, practised_today=False)


def test_a_missed_day_resets_the_streak_but_keeps_the_longest():
    # Last practised two days ago: yesterday was missed.
    assert p.compute_streak(days_before(2, 3, 4, 5), TODAY) == p.Streak(current=0, longest=4, practised_today=False)


def test_a_gap_splits_the_current_streak_from_an_older_longer_one():
    streak = p.compute_streak(days_before(0, 1, 3, 4, 5, 6, 7), TODAY)
    assert (streak.current, streak.longest) == (2, 5)


def test_only_today():
    assert p.compute_streak(days_before(0), TODAY) == p.Streak(current=1, longest=1, practised_today=True)


def test_longest_across_month_and_year_boundaries():
    days = [date(2025, 12, 30), date(2025, 12, 31), date(2026, 1, 1), date(2026, 1, 2)]
    assert p.compute_streak(days, date(2026, 3, 1)) == p.Streak(current=0, longest=4, practised_today=False)
    leap = [date(2028, 2, 28), date(2028, 2, 29), date(2028, 3, 1)]
    assert p.compute_streak(leap, date(2028, 3, 1)).current == 3


def local_day(utc_iso, zone):
    return p.local_date(datetime.fromisoformat(utc_iso), ZoneInfo(zone))


def test_days_follow_the_users_time_zone():
    # 20:30 UTC on the 22nd is 01:30 on the 23rd in Karachi (UTC+5).
    assert local_day("2026-09-22T20:30:00+00:00", "Asia/Karachi") == date(2026, 9, 23)
    assert local_day("2026-09-22T20:30:00+00:00", "UTC") == date(2026, 9, 22)
    # 03:00 UTC on the 23rd is still the 22nd in New York.
    assert local_day("2026-09-23T03:00:00+00:00", "America/New_York") == date(2026, 9, 22)


def test_naive_timestamps_are_utc():
    assert p.local_date(datetime(2026, 9, 22, 20, 30), ZoneInfo("Asia/Karachi")) == date(2026, 9, 23)


def test_karachi_user_is_not_cut_off_at_5am():
    """
    Sessions at 23:00 Karachi time on three evenings are three
    consecutive local days, though in UTC they fall at 18:00.
    A session at 02:00 Karachi time belongs to that local day,
    not the previous UTC day.
    """

    zone = ZoneInfo("Asia/Karachi")
    utc = [datetime(2026, 9, d, 18, 0, tzinfo=timezone.utc) for d in (20, 21, 22)]
    utc.append(datetime(2026, 9, 22, 21, 0, tzinfo=timezone.utc))  # 02:00 on the 23rd locally
    days = [p.local_date(moment, zone) for moment in utc]
    assert p.compute_streak(days, date(2026, 9, 23)).current == 4
    # In UTC the last one lands on the 22nd: only three days.
    assert p.compute_streak([m.date() for m in utc], date(2026, 9, 23)).current == 3


# ============================================================
# Week
# ============================================================


@pytest.mark.parametrize("today, monday", [
    (date(2026, 9, 21), date(2026, 9, 21)),  # Monday
    (date(2026, 9, 23), date(2026, 9, 21)),  # Wednesday
    (date(2026, 9, 27), date(2026, 9, 21)),  # Sunday: still the same week
    (date(2026, 9, 28), date(2026, 9, 28)),  # next Monday: a new week
    (date(2026, 1, 1), date(2025, 12, 29)),  # across a year
])
def test_weeks_run_monday_to_sunday(today, monday):
    assert p.week_bounds(today) == (monday, monday + timedelta(days=6))


# ============================================================
# Personal bests
# ============================================================


def row(n, created, status_ok=True, **scores):
    values = {column: None for column in p.BEST_COLUMNS.values() if column}
    values.update(scores)
    return SimpleNamespace(id=f"s{n}", title=f"Speech {n}", created_at=created, coaching_object_key=None, **values)


def best(bests, category):
    return next(b for b in bests if b["category"] == category)


def test_bests_pick_the_highest_and_the_earliest_on_a_tie():
    t = datetime(2026, 9, 1, tzinfo=timezone.utc)
    rows = [
        row(1, t, overall_score=60.0, score_logic=70.0),
        row(2, t + timedelta(days=1), overall_score=75.0, score_logic=70.0),
        row(3, t + timedelta(days=2), overall_score=74.9, score_logic=65.0),
    ]
    bests = p.personal_bests(rows, {})
    assert best(bests, "overall")["session_id"] == "s2" and best(bests, "overall")["score"] == 75.0
    assert best(bests, "logic")["session_id"] == "s1"


def test_unscored_rebuttal_never_counts_as_zero():
    t = datetime(2026, 9, 1, tzinfo=timezone.utc)
    rows = [row(1, t, score_rebuttal=None), row(2, t + timedelta(days=1), score_rebuttal=None)]
    rebuttal = best(p.personal_bests(rows, {}), "rebuttal")
    assert rebuttal == {"category": "rebuttal", "score": None, "session_id": None, "title": None, "created_at": None}

    rows.append(row(3, t + timedelta(days=2), score_rebuttal=0.0))
    rebuttal = best(p.personal_bests(rows, {}), "rebuttal")
    assert rebuttal["session_id"] == "s3" and rebuttal["score"] == 0.0  # a real zero does count


def test_delivery_comes_from_the_cache_map():
    t = datetime(2026, 9, 1, tzinfo=timezone.utc)
    rows = [row(1, t), row(2, t + timedelta(days=1)), row(3, t + timedelta(days=2))]
    delivery = best(p.personal_bests(rows, {"s1": 55.0, "s2": 81.5, "s3": None}), "quantitative")
    assert delivery["session_id"] == "s2" and delivery["score"] == 81.5


def test_bests_list_every_category_in_page_order():
    assert [b["category"] for b in p.personal_bests([], {})] == [
        "overall", "quantitative", "argumentation", "rebuttal", "structure", "persuasion", "logic",
    ]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0, 100.5, True, "90"])
def test_bests_ignore_impossible_scores(bad):
    t = datetime(2026, 9, 1, tzinfo=timezone.utc)
    rows = [row(1, t, overall_score=40.0), row(2, t, overall_score=bad)]
    assert best(p.personal_bests(rows, {}), "overall")["session_id"] == "s1"
    # On its own it is never a best either: "No score yet".
    assert best(p.personal_bests([row(2, t, overall_score=bad)], {}), "overall")["score"] is None
    assert best(p.personal_bests([row(2, t)], {"s2": bad}), "quantitative")["score"] is None
