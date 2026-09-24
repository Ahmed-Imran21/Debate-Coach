"""
§6.2: correlated moments. Fixtures construct video_analysis/timeline
data directly (not through the full visual_analysis pipeline) so
each rule's condition and salience formula can be checked in
isolation with hand-computed expected values.
"""

import pytest

from audio.transcript_shape import CanonicalSegment, CanonicalTranscript, CanonicalWord
from session_timeline.correlation import build_correlated_moments
from session_timeline.timeline import SessionTimeline


def _canonical(n_segments: int = 30, words_per_segment: int = 10) -> CanonicalTranscript:
    words = []
    segments = []
    i = 0
    for seg_i in range(n_segments):
        lo = i
        for _ in range(words_per_segment):
            words.append(CanonicalWord(i=i, start=float(i), end=i + 0.5, text=f"w{i}", segment_id=f"s_{seg_i:03d}"))
            i += 1
        segments.append(CanonicalSegment(id=f"s_{seg_i:03d}", start=words[lo].start, end=words[-1].end, text="...", word_range=(lo, i)))
    return CanonicalTranscript(words=tuple(words), segments=tuple(segments))


def _unit(id_: str, type_: str, start: float, end: float, segment_ids: list[str]) -> dict:
    return {"id": id_, "type": type_, "start": start, "end": end, "segment_ids": segment_ids}


def _event(id_: str, type_: str, start: float, end: float, **attrs) -> dict:
    return {"id": id_, "type": type_, "start": start, "end": end, "confidence": "high", "attributes": attrs}


def _fill(n_bins: int, spans: list[tuple[int, int, float]]) -> list:
    arr: list = [None] * n_bins
    for lo, hi, value in spans:
        for i in range(lo, hi):
            arr[i] = value
    return arr


def _video_analysis(
    *, status: str = "complete", setting: str = "camera_audience", uses_notes: bool = False,
    clock_uncertainty_ms: int = 150, session_facing=0.8,
    camera_facing=None, hand_activity=None, n_bins: int = 30,
) -> dict:
    return {
        "status": status,
        "quality": {
            "clock_uncertainty_ms": clock_uncertainty_ms,
            "context": {"setting": setting, "uses_notes": uses_notes},
        },
        "metrics": {
            "camera_facing_ratio": {"value": session_facing, "status": "ok" if session_facing is not None else "insufficient_coverage"},
        },
        "series": {
            "resolution_s": 1.0,
            "camera_facing": camera_facing if camera_facing is not None else [None] * n_bins,
            "hand_activity": hand_activity if hand_activity is not None else [None] * n_bins,
        },
    }


def _timeline(units: list[dict], events: list[dict] = ()) -> SessionTimeline:
    return SessionTimeline(
        session_id="s-1", canonical=_canonical(),
        speech_segments=[], pauses=[], fillers=[],
        argument_units=units, visual_events=list(events),
    )


# ---------------------------------------------------------------
# Gates
# ---------------------------------------------------------------

def test_empty_when_status_is_insufficient_data():
    unit = _unit("au_01", "conclusion", 10.0, 20.0, ["s_001"])
    va = _video_analysis(status="insufficient_data", camera_facing=_fill(30, [(10, 20, 0.3)]))
    events = [_event("ve_0001", "gaze_away", 12.0, 18.0, direction="down")]
    assert build_correlated_moments(_timeline([unit], events), va) == []


def test_empty_when_clock_uncertainty_too_high():
    unit = _unit("au_01", "conclusion", 10.0, 20.0, ["s_001"])
    va = _video_analysis(clock_uncertainty_ms=500, camera_facing=_fill(30, [(10, 20, 0.3)]))
    events = [_event("ve_0001", "gaze_away", 12.0, 18.0, direction="down")]
    assert build_correlated_moments(_timeline([unit], events), va) == []


def test_units_below_minimum_duration_never_produce_moments():
    unit = _unit("au_01", "conclusion", 10.0, 12.5, ["s_001"])  # 2.5s < MIN_UNIT_DURATION_S
    va = _video_analysis(camera_facing=_fill(30, [(10, 13, 0.1)]))
    events = [_event("ve_0001", "gaze_away", 10.0, 12.5, direction="down")]
    assert build_correlated_moments(_timeline([unit], events), va) == []


# ---------------------------------------------------------------
# Rule 1: long_gaze_away_in_key_unit@1
# ---------------------------------------------------------------

def test_long_gaze_away_fires_with_exact_salience_and_observations():
    unit = _unit("au_01", "conclusion", 10.0, 20.0, ["s_001"])
    # facing only 0.2 below session (under rule 2's 0.25 delta gate),
    # so rule 2 doesn't also fire and steal this unit's "improve" slot.
    va = _video_analysis(session_facing=0.8, camera_facing=_fill(30, [(10, 20, 0.6)]))
    events = [_event("ve_0001", "gaze_away", 12.0, 18.0, direction="down")]  # 6s, fully inside the unit

    moments = build_correlated_moments(_timeline([unit], events), va)
    assert len(moments) == 1
    m = moments[0]

    assert m["id"] == "m_01"
    assert m["rule_id"] == "long_gaze_away_in_key_unit@1"
    assert m["polarity"] == "improve"
    assert m["anchor"] == {"argument_unit_id": "au_01", "type": "conclusion"}
    assert m["start"] == pytest.approx(10.0)
    assert m["end"] == pytest.approx(20.0)
    # min(1, 6/8)*0.6 + 0.4 (conclusion) = 0.45 + 0.4
    assert m["salience"] == pytest.approx(0.85, abs=1e-6)

    assert m["observations"][0] == {
        "id": "o_01a", "kind": "event", "event_ref": "ve_0001",
        "type": "gaze_away", "duration_s": 6.0, "direction": "down",
    }
    assert m["observations"][1] == {
        "id": "o_01b", "kind": "metric", "metric": "camera_facing_ratio",
        "unit_value": 0.6, "session_value": 0.8,
    }
    assert m["excerpt_word_range"] == [10, 20]
    assert m["excerpt_text"] == " ".join(f"w{i}" for i in range(10, 20))


def test_long_gaze_away_does_not_fire_in_room_practice():
    unit = _unit("au_01", "conclusion", 10.0, 20.0, ["s_001"])
    va = _video_analysis(setting="in_room_practice", camera_facing=_fill(30, [(10, 20, 0.3)]))
    events = [_event("ve_0001", "gaze_away", 12.0, 18.0, direction="down")]
    assert build_correlated_moments(_timeline([unit], events), va) == []


def test_long_gaze_away_requires_half_the_event_inside_the_unit():
    unit = _unit("au_01", "conclusion", 10.0, 14.0, ["s_001"])  # only 4s wide
    va = _video_analysis()  # no camera_facing data -- keeps rule 2 from also firing
    # 6s event, only 2s (33%) inside the unit -- below the 50% threshold.
    events = [_event("ve_0001", "gaze_away", 12.0, 18.0, direction="down")]
    assert build_correlated_moments(_timeline([unit], events), va) == []


# ---------------------------------------------------------------
# Rule 2: low_camera_facing_in_key_unit@1
# ---------------------------------------------------------------

def test_low_camera_facing_fires_with_exact_salience():
    unit = _unit("au_01", "rebuttal", 10.0, 20.0, ["s_001"])
    va = _video_analysis(session_facing=0.8, camera_facing=_fill(30, [(10, 20, 0.3)]))
    moments = build_correlated_moments(_timeline([unit]), va)

    assert len(moments) == 1
    m = moments[0]
    assert m["rule_id"] == "low_camera_facing_in_key_unit@1"
    assert m["polarity"] == "improve"
    # min(1, (0.8-0.3)/0.5)*0.6 + 0.35 (rebuttal) = 0.6 + 0.35
    assert m["salience"] == pytest.approx(0.95, abs=1e-6)
    assert m["observations"] == [{
        "id": "o_01a", "kind": "metric", "metric": "camera_facing_ratio",
        "unit_value": 0.3, "session_value": 0.8,
    }]


def test_low_camera_facing_does_not_fire_above_the_delta_threshold():
    unit = _unit("au_01", "rebuttal", 10.0, 20.0, ["s_001"])
    # Only 0.1 below session average -- short of the 0.25 delta required.
    va = _video_analysis(session_facing=0.8, camera_facing=_fill(30, [(10, 20, 0.7)]))
    assert build_correlated_moments(_timeline([unit]), va) == []


def test_low_camera_facing_does_not_fire_with_poor_unit_face_coverage():
    unit = _unit("au_01", "rebuttal", 10.0, 20.0, ["s_001"])
    # Only 5 of 10 bins have face data -- coverage 0.5 < the 0.6 gate.
    va = _video_analysis(session_facing=0.8, camera_facing=_fill(30, [(10, 15, 0.3)]))
    assert build_correlated_moments(_timeline([unit]), va) == []


# ---------------------------------------------------------------
# Rule 3: head_down_in_key_unit@1
# ---------------------------------------------------------------

def test_head_down_fires_and_is_suppressed_for_claim_units_with_notes():
    unit = _unit("au_01", "claim", 0.0, 10.0, ["s_000"])
    va = _video_analysis(uses_notes=False)
    events = [_event("ve_0001", "head_down", 1.0, 9.0)]  # 8s of 10s = 0.8

    moments = build_correlated_moments(_timeline([unit], events), va)
    assert len(moments) == 1
    # 0.8*0.6 + 0.3 (claim) = 0.48 + 0.3
    assert moments[0]["salience"] == pytest.approx(0.78, abs=1e-6)

    va_notes = _video_analysis(uses_notes=True)
    assert build_correlated_moments(_timeline([unit], events), va_notes) == []


def test_head_down_not_suppressed_for_conclusion_units_with_notes():
    unit = _unit("au_01", "conclusion", 0.0, 10.0, ["s_000"])
    va = _video_analysis(uses_notes=True)
    events = [_event("ve_0001", "head_down", 1.0, 9.0)]
    moments = build_correlated_moments(_timeline([unit], events), va)
    assert len(moments) == 1


def test_head_down_does_not_fire_below_half_coverage():
    unit = _unit("au_01", "claim", 0.0, 10.0, ["s_000"])
    va = _video_analysis()
    events = [_event("ve_0001", "head_down", 1.0, 5.0)]  # 4s of 10s = 0.4 < 0.5
    assert build_correlated_moments(_timeline([unit], events), va) == []


# ---------------------------------------------------------------
# Rule 4: hands_still_in_key_unit@1
# ---------------------------------------------------------------

def test_hands_still_fires_with_exact_salience():
    unit = _unit("au_01", "rebuttal", 0.0, 10.0, ["s_000"])
    va = _video_analysis(hand_activity=_fill(30, [(0, 10, 0.1)]))
    events = [_event("ve_0001", "hands_still", 1.0, 8.0)]  # 7s of 10s = 0.7

    moments = build_correlated_moments(_timeline([unit], events), va)
    assert len(moments) == 1
    # 0.7*0.5 + 0.35 (rebuttal) = 0.35 + 0.35
    assert moments[0]["salience"] == pytest.approx(0.70, abs=1e-6)
    assert moments[0]["observations"] == [{"id": "o_01a", "kind": "metric", "metric": "hands_still_fraction", "unit_value": 0.7, "session_value": None}]


def test_hands_still_does_not_fire_without_hand_coverage():
    unit = _unit("au_01", "rebuttal", 0.0, 10.0, ["s_000"])
    va = _video_analysis()  # no hand_activity data at all -> unit_hand_cov == 0
    events = [_event("ve_0001", "hands_still", 1.0, 8.0)]
    assert build_correlated_moments(_timeline([unit], events), va) == []


# ---------------------------------------------------------------
# Rule 5: physical_emphasis_in_key_unit@1
# ---------------------------------------------------------------

def test_physical_emphasis_fires_for_conclusion_not_claim():
    # Unit's own bins run hot (5.0); the rest of the 30-bin series is
    # a calm baseline (1.0) so the session-wide median lands on 1.0.
    hand_activity = _fill(30, [(0, 10, 5.0), (10, 30, 1.0)])
    camera_facing = _fill(30, [(0, 10, 0.9)])

    conclusion_unit = _unit("au_01", "conclusion", 0.0, 10.0, ["s_000"])
    va = _video_analysis(session_facing=0.8, camera_facing=camera_facing, hand_activity=hand_activity)
    moments = build_correlated_moments(_timeline([conclusion_unit]), va)

    assert len(moments) == 1
    m = moments[0]
    assert m["rule_id"] == "physical_emphasis_in_key_unit@1"
    assert m["polarity"] == "strength"
    # activity_ratio = 5.0/1.0 = 5.0 -> min(1, 5/3)*0.5 + 0.4 (conclusion)
    assert m["salience"] == pytest.approx(0.9, abs=1e-6)

    claim_unit = _unit("au_02", "claim", 0.0, 10.0, ["s_000"])
    assert build_correlated_moments(_timeline([claim_unit]), va) == []


def test_physical_emphasis_requires_facing_at_or_above_session_unless_in_room():
    hand_activity = _fill(30, [(0, 10, 5.0), (10, 30, 1.0)])
    unit = _unit("au_01", "conclusion", 0.0, 10.0, ["s_000"])

    # Facing well below session average, camera_audience context: rule 5
    # doesn't fire (low facing independently satisfies rule 2 instead,
    # which is expected and irrelevant to what this test checks).
    va_away = _video_analysis(session_facing=0.8, camera_facing=_fill(30, [(0, 10, 0.1)]), hand_activity=hand_activity)
    rule_ids_away = {m["rule_id"] for m in build_correlated_moments(_timeline([unit]), va_away)}
    assert "physical_emphasis_in_key_unit@1" not in rule_ids_away

    # Same low facing, but in_room_practice doesn't care about it.
    va_in_room = _video_analysis(setting="in_room_practice", session_facing=0.8, camera_facing=_fill(30, [(0, 10, 0.1)]), hand_activity=hand_activity)
    assert len(build_correlated_moments(_timeline([unit]), va_in_room)) == 1


# ---------------------------------------------------------------
# Selection: dedup, per-rule cap, top-8
# ---------------------------------------------------------------

def test_dedup_keeps_one_per_polarity_per_unit():
    # Both rule 1 and rule 2 qualify for the same unit (both "improve"):
    # only the higher-salience one should survive for that unit.
    unit = _unit("au_01", "conclusion", 10.0, 20.0, ["s_001"])
    va = _video_analysis(session_facing=0.8, camera_facing=_fill(30, [(10, 20, 0.2)]))
    events = [_event("ve_0001", "gaze_away", 12.0, 18.0, direction="down")]  # rule 1: salience 0.85

    moments = build_correlated_moments(_timeline([unit], events), va)
    improve_moments = [m for m in moments if m["polarity"] == "improve"]
    assert len(improve_moments) == 1
    # rule 2 salience here: min(1,(0.8-0.2)/0.5)*0.6+0.4 = 1.0*0.6+0.4 = 1.0 > rule 1's 0.85
    assert improve_moments[0]["rule_id"] == "low_camera_facing_in_key_unit@1"


def test_dedup_keeps_both_polarities_for_the_same_unit():
    # Rule 1 (long_gaze_away, "improve") doesn't gate on the facing
    # *value* at all, only on camera_audience context -- so it can
    # co-fire with rule 5 (physical_emphasis, "strength"), which
    # needs unit_facing >= session_facing under camera_audience.
    # Setting unit_facing high satisfies both simultaneously.
    unit = _unit("au_01", "conclusion", 10.0, 20.0, ["s_001"])
    events = [_event("ve_0001", "gaze_away", 12.0, 18.0, direction="down")]
    hand_activity = _fill(30, [(10, 20, 5.0), (0, 10, 1.0)])
    camera_facing = _fill(30, [(10, 20, 0.9)])  # >= session_facing

    va = _video_analysis(session_facing=0.8, camera_facing=camera_facing, hand_activity=hand_activity)
    moments = build_correlated_moments(_timeline([unit], events), va)

    assert {m["anchor"]["argument_unit_id"] for m in moments} == {"au_01"}
    assert {m["polarity"] for m in moments} == {"improve", "strength"}
    assert {m["rule_id"] for m in moments} == {"long_gaze_away_in_key_unit@1", "physical_emphasis_in_key_unit@1"}


def test_cap_per_rule_keeps_only_top_three_by_salience():
    # No camera_facing data at all: rule 1 doesn't need it to fire, and
    # this keeps rule 2 from also firing and contaminating the "improve"
    # dedup slot with its own (here, unvarying) salience per unit.
    units = [_unit(f"au_{i:02d}", "conclusion", i * 10.0, i * 10.0 + 10.0, [f"s_{i:03d}"]) for i in range(5)]
    events = []
    for i, unit in enumerate(units):
        # increasing gaze-away duration per unit -> distinct saliences, all >= 3s.
        duration = 3.0 + i
        events.append(_event(f"ve_{i:04d}", "gaze_away", unit["start"], unit["start"] + duration, direction="down"))

    va = _video_analysis(session_facing=0.8)
    moments = build_correlated_moments(_timeline(units, events), va)

    gaze_moments = [m for m in moments if m["rule_id"] == "long_gaze_away_in_key_unit@1"]
    assert len(gaze_moments) == 3
    saliences = [m["salience"] for m in gaze_moments]
    assert saliences == sorted(saliences, reverse=True)


def test_top_eight_cap_and_descending_order():
    # 3 units per rule across 3 different rules (rule 1, rule 2, rule
    # 4) so the per-rule cap of 3 never binds on its own (each rule
    # contributes exactly its full 3) -- 9 candidates total, so it's
    # genuinely the cross-rule top-8 cut being exercised here, not
    # test_cap_per_rule_keeps_only_top_three_by_salience's mechanism.
    # Each unit only has the series/event data its own rule needs, so
    # the three groups can't cross-trigger each other's rules.
    n_bins = 90
    camera_facing = [None] * n_bins
    hand_activity = [None] * n_bins
    events = []

    # rule 1 (long_gaze_away): au_00..02 at [0,30), saliences 0.625/0.7/0.775
    rule1_units = [_unit(f"au_{i:02d}", "conclusion", i * 10.0, i * 10.0 + 10.0, [f"s_{i:03d}"]) for i in range(3)]
    for i, unit in enumerate(rule1_units):
        duration = 3.0 + i
        events.append(_event(f"ve1_{i:04d}", "gaze_away", unit["start"], unit["start"] + duration, direction="down"))

    # rule 2 (low_camera_facing): au_03..05 at [30,60), saliences 0.76/0.82/0.88
    rule2_units = [_unit(f"au_{i:02d}", "conclusion", i * 10.0, i * 10.0 + 10.0, [f"s_{i:03d}"]) for i in range(3, 6)]
    for facing, unit in zip((0.5, 0.45, 0.4), rule2_units):
        for b in range(int(unit["start"]), int(unit["end"])):
            camera_facing[b] = facing

    # rule 4 (hands_still): au_06..08 at [60,90), saliences 0.7/0.8/0.9
    rule4_units = [_unit(f"au_{i:02d}", "conclusion", i * 10.0, i * 10.0 + 10.0, [f"s_{i:03d}"]) for i in range(6, 9)]
    for i, (fraction, unit) in enumerate(zip((0.6, 0.8, 1.0), rule4_units)):
        for b in range(int(unit["start"]), int(unit["end"])):
            hand_activity[b] = 0.1
        events.append(_event(f"ve4_{i:04d}", "hands_still", unit["start"], unit["start"] + fraction * 10.0))

    units = rule1_units + rule2_units + rule4_units
    va = _video_analysis(session_facing=0.8, camera_facing=camera_facing, hand_activity=hand_activity, n_bins=n_bins)
    moments = build_correlated_moments(_timeline(units, events), va)

    assert len(moments) == 8
    assert [m["id"] for m in moments] == [f"m_{i:02d}" for i in range(1, 9)]
    saliences = [m["salience"] for m in moments]
    assert saliences == sorted(saliences, reverse=True)
    # au_00 (rule 1's shortest gaze-away, salience 0.625) is the
    # unique lowest of all 9 and should be the one dropped.
    kept_units = {m["anchor"]["argument_unit_id"] for m in moments}
    assert "au_00" not in kept_units
    assert len(kept_units) == 8
