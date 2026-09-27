"""
Password hashing moved from passlib to bcrypt directly. Every hash the
passlib code ever produced must keep verifying, and the edge cases
must behave exactly as they did.

tests/fixtures/passlib_hashes.json holds real hashes produced by the
passlib-based app/core/security.py before the change: long ASCII,
long non-ASCII, a multi-byte character split at byte 72, and more.
"""

import json
from pathlib import Path

import pytest

from app.core import security

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "passlib_hashes.json").read_text(encoding="utf-8"))
CASES = FIXTURE["hashes"]


@pytest.mark.parametrize("case", CASES, ids=[c["case"] for c in CASES])
def test_every_passlib_hash_still_verifies(case):
    assert security.verify_password(case["password"], case["hash"])


@pytest.mark.parametrize("case", CASES, ids=[c["case"] for c in CASES])
def test_a_wrong_password_still_fails_against_passlib_hashes(case):
    # Changed at the start: anything past byte 72 never counted.
    wrong = "#" + case["password"][1:] if case["password"] else "x"
    assert not security.verify_password(wrong, case["hash"])


def test_the_72_byte_cut_is_unchanged_for_passlib_hashes():
    """Past byte 72 nothing counts, and a character split at 72 is dropped whole, as before."""
    by_case = {c["case"]: c for c in CASES}

    long_ascii = by_case["long ascii (100 bytes)"]
    assert security.verify_password("Z" * 72 + "anything else", long_ascii["hash"])

    split = by_case["multibyte char split at byte 72"]  # "a"*71 + "é"...: the é is dropped, 71 bytes hashed
    assert security.verify_password("a" * 71, split["hash"])
    assert security.verify_password("a" * 71 + "é-and-more", split["hash"])
    assert not security.verify_password("a" * 72, split["hash"])

    emoji = by_case["4-byte char split at byte 72"]  # "b"*70 + a 4-byte emoji: 70 bytes hashed
    assert security.verify_password("b" * 70, emoji["hash"])


def test_new_hashes_have_the_same_format():
    h = security.hash_password("CorrectHorse9")
    assert h.startswith("$2b$12$") and len(h) == 60
    assert security.verify_password("CorrectHorse9", h)
    assert not security.verify_password("correcthorse9", h)
    assert security.hash_password("CorrectHorse9") != h  # salted


@pytest.mark.parametrize("password", ["ü" * 60, "a" * 71 + "é" + "tail", "pässwörd—Ünïcödé✓", "Z" * 100])
def test_new_hashes_apply_the_same_cut(password):
    h = security.hash_password(password)
    assert security.verify_password(password, h)
    assert security.verify_password(security._prepare(password), h)


def test_a_nul_character_is_refused_as_before():
    with pytest.raises(ValueError):
        security.hash_password("ab\x00cd")
    with pytest.raises(ValueError):
        security.verify_password("ab\x00cd", CASES[0]["hash"])


@pytest.mark.parametrize(
    "stored",
    ["x", "", "$2b$12$tooshort", "not-a-hash-at-all", "$2b$12$" + "a" * 52, "$2b$12$" + "a" * 54, "$3b$12$" + "a" * 53],
)
def test_a_malformed_stored_hash_raises_valueerror_as_before(stored):
    with pytest.raises(ValueError):
        security.verify_password("anything", stored)


def test_nothing_imports_passlib_any_more():
    import re

    root = Path(__file__).resolve().parents[1]
    importing = re.compile(r"^\s*(from|import)\s+passlib\b", re.MULTILINE)
    for folder in ("app", "api", "audio", "coaching_engine", "progress_report", "raw_metrics", "speech_analysis",
                   "session_timeline", "visual_analysis", "visual_coaching"):
        for path in (root / folder).rglob("*.py"):
            assert not importing.search(path.read_text(encoding="utf-8")), path
