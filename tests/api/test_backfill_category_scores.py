"""
scripts/backfill_category_scores.py: fills sessions.score_* from each
session's feedback.json. Idempotent; a missing, corrupt or incomplete
file is logged and skipped, never guessed at or partially written.
"""

import json
import logging
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import backfill_category_scores as backfill_script  # noqa: E402

COLUMNS = ("score_argumentation", "score_rebuttal", "score_structure", "score_persuasion", "score_logic")

GOOD = {
    "quantitative": 85.0,
    "argumentation": 75.0,
    "rebuttal": 60.0,
    "structure": 75.0,
    "persuasion": 60.0,
    "logic": 40.0,
    "overall": 65.8,
}


@pytest.fixture
def storage_module(fake_storage):
    from app.services import storage

    return storage


@pytest.fixture
def add(db, make_user, fake_storage):
    from app.models.session import DebateSession, SessionStatus

    owner = make_user("a@test")

    def _add(document=None, *, raw=None, status=SessionStatus.completed, key=True, **columns):
        sid = uuid.uuid4()
        object_key = f"users/{owner.id}/sessions/{sid}/feedback.json" if key else None
        if raw is not None:
            fake_storage.blobs[object_key] = raw
        elif document is not None:
            fake_storage.blobs[object_key] = json.dumps(document).encode()
        row = DebateSession(id=sid, user_id=owner.id, status=status, coaching_object_key=object_key, **columns)
        db.add(row)
        db.commit()
        return row

    return _add


def scores_of(db, row):
    db.refresh(row)
    return tuple(getattr(row, c) for c in COLUMNS)


def run(db, storage_module, dry_run=False):
    return backfill_script.backfill(db, storage_module, dry_run=dry_run, batch_size=2)


def test_fills_scores_from_feedback_json(db, storage_module, add):
    row = add({"session_id": "x", "scores": GOOD, "feedback": []})

    counts = run(db, storage_module)

    assert counts == {"candidates": 1, "filled": 1, "skipped": 0}
    assert scores_of(db, row) == (75.0, 60.0, 75.0, 60.0, 40.0)


def test_second_run_is_a_no_op(db, storage_module, add):
    rows = [add({"scores": GOOD}) for _ in range(5)]  # more than one batch
    assert run(db, storage_module)["filled"] == 5

    assert run(db, storage_module) == {"candidates": 0, "filled": 0, "skipped": 0}
    assert all(scores_of(db, r) == (75.0, 60.0, 75.0, 60.0, 40.0) for r in rows)


def test_rebuttal_not_scored_is_filled_as_null_and_not_retried(db, storage_module, add):
    row = add({"scores": {**GOOD, "rebuttal": None}})

    assert run(db, storage_module)["filled"] == 1
    assert scores_of(db, row) == (75.0, None, 75.0, 60.0, 40.0)
    assert run(db, storage_module)["candidates"] == 0


def test_never_overwrites_sessions_that_already_have_scores(db, storage_module, add):
    row = add({"scores": GOOD}, score_argumentation=20.0, score_rebuttal=20.0, score_structure=20.0, score_persuasion=20.0, score_logic=20.0)

    assert run(db, storage_module)["candidates"] == 0
    assert scores_of(db, row) == (20.0,) * 5


def test_only_completed_sessions_with_a_feedback_file(db, storage_module, add):
    from app.models.session import SessionStatus

    add({"scores": GOOD}, status=SessionStatus.failed)
    add({"scores": GOOD}, status=SessionStatus.coaching)
    add(key=False)

    assert run(db, storage_module)["candidates"] == 0


@pytest.mark.parametrize(
    "kwargs, reason",
    [
        ({}, "not found"),  # key set, no object stored
        ({"raw": b"{not json"}, "not valid JSON"),
        ({"raw": b"\xff\xfe\x00garbage"}, "not valid JSON"),
        ({"document": ["a", "list"]}, "not an object"),
        ({"document": {"feedback": []}}, "scores is not an object"),
        ({"document": {"scores": {k: v for k, v in GOOD.items() if k != "logic"}}}, "missing 'logic'"),
        ({"document": {"scores": {**GOOD, "argumentation": None}}}, "argumentation is null"),
        ({"document": {"scores": {**GOOD, "structure": "75"}}}, "not a number"),
        ({"document": {"scores": {**GOOD, "structure": True}}}, "not a number"),
        ({"document": {"scores": {**GOOD, "logic": 140.0}}}, "out of range"),
        ({"document": {"scores": {**GOOD, "logic": -1}}}, "out of range"),
        ({"document": {"scores": {**GOOD, "logic": float("nan")}}}, "out of range"),
    ],
    ids=["missing", "bad-json", "bad-bytes", "not-object", "no-scores", "missing-cat", "null-cat", "string", "bool", "over", "under", "nan"],
)
def test_bad_files_are_logged_and_skipped_without_writing(db, storage_module, add, caplog, kwargs, reason):
    bad = add(**kwargs)
    good = add({"scores": GOOD})

    with caplog.at_level(logging.WARNING, logger="backfill_category_scores"):
        counts = run(db, storage_module)

    assert counts == {"candidates": 2, "filled": 1, "skipped": 1}
    assert scores_of(db, bad) == (None,) * 5
    assert scores_of(db, good) == (75.0, 60.0, 75.0, 60.0, 40.0)
    assert str(bad.id) in caplog.text and reason in caplog.text


def test_dry_run_writes_nothing(db, storage_module, add):
    row = add({"scores": GOOD})

    assert run(db, storage_module, dry_run=True) == {"candidates": 1, "filled": 1, "skipped": 0}
    assert scores_of(db, row) == (None,) * 5
    assert run(db, storage_module)["filled"] == 1
