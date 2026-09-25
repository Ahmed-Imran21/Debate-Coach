#!/usr/bin/env python3
"""
Fill sessions.score_* (migrations/0003) for sessions coached before
the pipeline started writing them, from each session's feedback.json
in object storage.

Idempotent: only completed sessions with a feedback.json and all five
score columns still NULL are touched, so a second run finds nothing
left to do. A session whose file is missing, isn't valid JSON, or
has no complete in-range scores block is logged and skipped — never
guessed at, never partially written.

Writes only the five score columns. Uses DATABASE_URL and the
storage settings from the environment, like the backend itself; run
it against the environment you mean to change.

Usage:
    python scripts/backfill_category_scores.py --dry-run
    python scripts/backfill_category_scores.py [--batch-size 100]

Exit status is 0 when every candidate was filled (or would be, on a
dry run) and 1 when any were skipped, so a skip is never silent.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import and_, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.models.session import DebateSession, SessionStatus  # noqa: E402
from app.services.category_scores import CATEGORY_COLUMNS, parse_category_scores  # noqa: E402

log = logging.getLogger("backfill_category_scores")


def candidates(db: Session) -> list[DebateSession]:
    all_null = and_(*(getattr(DebateSession, column).is_(None) for column in CATEGORY_COLUMNS.values()))

    return list(
        db.scalars(
            select(DebateSession)
            .where(
                DebateSession.status == SessionStatus.completed,
                DebateSession.coaching_object_key.is_not(None),
                all_null,
            )
            .order_by(DebateSession.created_at, DebateSession.id)
        )
    )


def backfill(db: Session, storage, *, dry_run: bool, batch_size: int = 100) -> dict[str, int]:
    """
    Returns counts: candidates, filled, skipped. `storage` is
    app.services.storage (a parameter so tests can pass a fake).
    """

    rows = candidates(db)
    counts = {"candidates": len(rows), "filled": 0, "skipped": 0}
    pending = 0

    for session in rows:
        try:
            document = storage.download_json(session.coaching_object_key)
        except storage.ObjectNotFoundError:
            log.warning("skip %s: feedback.json not found (%s)", session.id, session.coaching_object_key)
            counts["skipped"] += 1
            continue
        except ValueError as exc:  # json.JSONDecodeError is a ValueError
            log.warning("skip %s: feedback.json is not valid JSON (%s)", session.id, exc)
            counts["skipped"] += 1
            continue

        try:
            if not isinstance(document, dict):
                raise ValueError("feedback.json is not an object")
            values = parse_category_scores(document.get("scores"))
        except ValueError as exc:
            log.warning("skip %s: %s", session.id, exc)
            counts["skipped"] += 1
            continue

        log.info("%s %s: %s", "would fill" if dry_run else "fill", session.id, values)
        counts["filled"] += 1

        if dry_run:
            continue

        for column, value in values.items():
            setattr(session, column, value)

        pending += 1
        if pending >= batch_size:
            db.commit()
            pending = 0

    if dry_run:
        db.rollback()
    else:
        db.commit()

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="read and validate only; write nothing")
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from app.db.database import SessionLocal
    from app.services import storage

    with SessionLocal() as db:
        counts = backfill(db, storage, dry_run=args.dry_run, batch_size=args.batch_size)

    log.info(
        "%s: %d candidates, %d %s, %d skipped",
        "DRY RUN" if args.dry_run else "done",
        counts["candidates"],
        counts["filled"],
        "would be filled" if args.dry_run else "filled",
        counts["skipped"],
    )
    return 1 if counts["skipped"] else 0


if __name__ == "__main__":
    sys.exit(main())
