"""
Cross-language contract: validates the exact fixture the
frontend's TrackBuilder wrote (web/features/video-analysis/
__tests__/track.test.ts, "cross-language fixture" case) against
the same Pydantic schema and §3.3 rules the real upload endpoint
uses. Regenerate it with `npm run test` in web/ if track.ts or
this fixture's expectations change.
"""

import json
from pathlib import Path

import pytest

from visual_analysis.schema import VisualSignalTrack
from visual_analysis.signals import validate_track

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "web"
    / "features"
    / "video-analysis"
    / "__tests__"
    / "__fixtures__"
    / "sample-track.json"
)


@pytest.fixture(scope="module")
def fixture_data() -> dict:
    if not FIXTURE_PATH.exists():
        pytest.skip(
            f"{FIXTURE_PATH} not found; run `npm run test` in web/ to generate it "
            "(TrackBuilder's cross-language fixture test)."
        )
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_frontend_track_matches_the_pydantic_schema(fixture_data):
    track = VisualSignalTrack.model_validate(fixture_data)
    assert track.session_id == "11111111-1111-4111-8111-111111111111"


def test_frontend_track_passes_signal_validation(fixture_data):
    track = VisualSignalTrack.model_validate(fixture_data)
    validate_track(track, expected_session_id=track.session_id)


def test_frontend_rounding_matches_the_documented_precision(fixture_data):
    """
    §3.2: angles to 0.1, iris to 0.01, face_scale/coords to 0.001.
    Confirms track.ts's ROUNDING table actually produced values a
    Python-side consumer can trust bit-for-bit, not just that they
    happen to parse.
    """
    frames = fixture_data["frames"]

    def decimals(value) -> int:
        text = repr(float(value))
        return len(text.split(".")[1]) if "." in text else 0

    for value in frames["head_yaw"]:
        if value is not None:
            assert decimals(value) <= 1, value
    for value in frames["iris_x"] + frames["iris_y"]:
        if value is not None:
            assert decimals(value) <= 2, value
    for value in frames["face_scale"] + frames["face_cx"] + frames["face_cy"]:
        if value is not None:
            assert decimals(value) <= 3, value


def test_frontend_track_has_expected_shape(fixture_data):
    """
    Sanity on the specific scenario track.test.ts builds: a face
    stretch, a gap-covered dropout, recovery, and one degradation
    — so a change that silently stops emitting one of those isn't
    masked by schema validation alone (which would still pass on
    an empty track).
    """
    frames = fixture_data["frames"]
    assert len(frames["t"]) == 13
    assert frames["t"] == sorted(frames["t"])
    assert len(fixture_data["gaps"]) == 1
    assert fixture_data["gaps"][0]["reason"] == "tab_hidden"
    assert len(fixture_data["degradations"]) == 1
    assert fixture_data["degradations"][0]["reason"] == "p90_latency"
    # the two appendEmpty() ticks before the gap
    empty_ticks = [i for i, v in enumerate(frames["face_count"]) if v is None]
    assert len(empty_ticks) == 2
