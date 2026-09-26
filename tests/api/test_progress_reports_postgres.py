"""
The once-per-UTC-day limit under a real race, on real Postgres: two
generations for the same user run on separate connections, both pass
the "already generated today?" check (a barrier holds them at the LLM
call until both are there), then both try to store. The
(user_id, report_date) unique constraint must let exactly one in.

Separate connections only see committed rows, so this commits a
tagged throwaway user and deletes it at the end (sessions and
reports cascade). Skips if the local dev instance isn't reachable.
"""

import json
import os
import threading
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

REAL_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://coaching_app:localdevpassword@127.0.0.1:5433/debate_coach_dev",
)
NOW = datetime(2030, 1, 1, 12, 0, tzinfo=timezone.utc)


class Reply:
    success, error = True, None
    content = json.dumps({"bullets": ["You now back up your claims with reasons more often."]})


class BarrierLLM:
    def __init__(self, barrier):
        self.barrier = barrier

    def generate(self, **kwargs):
        self.barrier.wait(timeout=15)
        return Reply()


def test_two_simultaneous_generations_store_exactly_one_report(app_module, monkeypatch):
    from app.models.progress_report import ProgressReport
    from app.models.session import DebateSession, SessionStatus
    from app.models.user import User
    from app.services import progress_reports as reports
    from app.services import storage

    engine = create_engine(REAL_DATABASE_URL)
    try:
        engine.connect().close()
    except OperationalError:
        engine.dispose()
        pytest.skip(f"No reachable Postgres at {REAL_DATABASE_URL}")
    Session = sessionmaker(bind=engine)

    monkeypatch.setattr(
        storage,
        "download_json",
        lambda key: {"scores": {"overall": 60.0}, "feedback": []} if key.endswith("feedback.json") else {},
    )

    email = f"pgrace-{uuid.uuid4().hex[:8]}@example.test"
    with Session() as db:
        user = User(email=email, password_hash="x", first_name="R", last_name="C")
        db.add(user)
        db.flush()
        for _ in range(2):
            db.add(DebateSession(user_id=user.id, status=SessionStatus.completed, coaching_object_key=f"k/{uuid.uuid4()}/feedback.json"))
        db.commit()
        user_id = user.id

    barrier = threading.Barrier(2)
    outcomes = []

    def run():
        with Session() as db:
            me = db.get(User, user_id)
            try:
                reports.generate(db, me, 3, BarrierLLM(barrier), now=lambda: NOW)
                outcomes.append("stored")
            except reports.AlreadyGeneratedToday:
                outcomes.append("refused")

    try:
        threads = [threading.Thread(target=run) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert sorted(outcomes) == ["refused", "stored"]
        with Session() as db:
            stored = db.scalars(select(ProgressReport).where(ProgressReport.user_id == user_id)).all()
            assert len(stored) == 1
    finally:
        with Session() as db:
            db.delete(db.get(User, user_id))
            db.commit()
            assert db.scalar(select(ProgressReport).where(ProgressReport.user_id == user_id)) is None
        engine.dispose()
