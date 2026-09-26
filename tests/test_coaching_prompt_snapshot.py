"""
"No prompt" must produce exactly today's coaching behaviour.

The golden files in tests/fixtures/coaching_prompt_snapshots/ were
captured from the coaching prompt code as it stood before practice
motions existed (main at c7e1844, coaching_engine/ unchanged since
5299a48). With no motion, the system prompt, every user prompt, and
the exact arguments the engine hands the LLM must match them byte for
byte: a changed space fails this.

If the coaching prompt is ever changed on purpose, re-capture these
files in the same commit and say so; never edit them by hand.
"""

import json
import sys
from pathlib import Path

import pytest

from coaching_engine.llm.prompts import build_synthesis_prompt, build_synthesis_system_prompt

SNAPSHOTS = Path(__file__).parent / "fixtures" / "coaching_prompt_snapshots"
SPEECHES = json.loads((SNAPSHOTS / "speeches.json").read_text(encoding="utf-8"))


def golden(name: str) -> str:
    return (SNAPSHOTS / name).read_text(encoding="utf-8")


def test_system_prompt_without_a_motion_is_byte_identical():
    assert build_synthesis_system_prompt() == golden("system_prompt.txt")


@pytest.mark.parametrize("name", sorted(SPEECHES))
def test_user_prompt_without_a_motion_is_byte_identical(name):
    assert build_synthesis_prompt(SPEECHES[name]) == golden(f"user_prompt_{name}.txt")


class RecordingLLM:
    def __init__(self):
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return json.dumps(
            {
                "feedback": [
                    {"category": "logic", "also_affects": [], "title": "t", "issue": "i", "severity": "high",
                     "evidence": [], "explanation": "e", "recommendation": "r"}
                ],
                "rubric": {c: {"level": 3, "reason": "r"} for c in ("argumentation", "rebuttal", "structure", "persuasion", "logic")},
            }
        )


@pytest.fixture
def plain_session(tmp_path, transcription, audio_analysis):
    from raw_metrics.metrics import analyze_metrics

    session = tmp_path / "snap-plain"
    session.mkdir()
    (session / "transcription.json").write_text(json.dumps({**transcription, "session_id": "snap-plain"}))
    (session / "analysis.json").write_text(json.dumps({**audio_analysis, "session_id": "snap-plain"}))
    analyze_metrics("snap-plain", session)
    (session / "speech_content.json").write_text(json.dumps(SPEECHES["plain"]))
    return tmp_path


def test_the_engine_calls_the_llm_exactly_as_before(plain_session):
    from coaching_engine.engine import CoachingEngine

    llm = RecordingLLM()
    CoachingEngine(sessions_dir=str(plain_session), llm_client=llm).analyze_session("snap-plain")

    [call] = llm.calls
    recorded = {k: v for k, v in call.items() if k != "on_queued"}
    recorded["on_queued_is_none"] = call.get("on_queued") is None
    assert recorded == json.loads(golden("engine_call.json"))
