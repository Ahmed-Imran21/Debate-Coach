"""
Username uniqueness on real Postgres, with the schema that
migrations/0008 created on the local dev database.

- Two users claim the same username at the same moment, on separate
  connections. Both pass the "is it taken?" check (a barrier holds
  them there), then both write: the unique index on lower(username)
  must let exactly one in, and the other gets "That username is taken."
- The database itself refuses a second username differing only in
  case, and anything outside the format.

Separate connections only see committed rows, so this commits tagged
throwaway users and deletes exactly those at the end (profiles
cascade). Skips if the local dev instance isn't reachable.
"""

import os
import threading
import uuid

import pytest
from sqlalchemy import create_engine, delete, text
from sqlalchemy.exc import DataError, IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker

REAL_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://coaching_app:localdevpassword@127.0.0.1:5433/debate_coach_dev",
)


@pytest.fixture
def pg(app_module):
    from app.models.user import User

    engine = create_engine(REAL_DATABASE_URL)
    try:
        engine.connect().close()
    except OperationalError:
        engine.dispose()
        pytest.skip(f"No reachable Postgres at {REAL_DATABASE_URL}")

    Session = sessionmaker(bind=engine)
    tag = uuid.uuid4().hex[:8]
    created: list[uuid.UUID] = []

    def make_user(n: int):
        with Session() as db:
            user = User(email=f"pgprofile-{tag}-{n}@example.test", password_hash="x", first_name="P", last_name=str(n))
            db.add(user)
            db.commit()
            created.append(user.id)
            return user.id

    yield Session, make_user, tag

    with Session() as db:
        db.execute(delete(User).where(User.id.in_(created)))
        db.commit()
    engine.dispose()


def test_two_simultaneous_claims_to_one_username_let_exactly_one_in(pg, monkeypatch):
    from app.models.user import User
    from app.services import profile as profiles

    Session, make_user, tag = pg
    users = [make_user(1), make_user(2)]
    name = f"race_{tag}"

    barrier = threading.Barrier(2)
    real_check = profiles._username_taken
    first_check: set[int] = set()
    lock = threading.Lock()

    def held_check(db, username, user_id):
        taken = real_check(db, username, user_id)
        with lock:
            first = threading.get_ident() not in first_check
            first_check.add(threading.get_ident())
        if first:
            barrier.wait(timeout=15)  # both have now checked; neither has written
        return taken

    monkeypatch.setattr(profiles, "_username_taken", held_check)
    outcomes: list[str] = []

    def claim(user_id, spelled):
        with Session() as db:
            try:
                profiles.update_profile(db, db.get(User, user_id), {"username": spelled})
                outcomes.append("saved")
            except profiles.UsernameTakenError as error:
                outcomes.append(error.message)

    threads = [threading.Thread(target=claim, args=(users[0], name)), threading.Thread(target=claim, args=(users[1], name.upper()))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(outcomes) == ["That username is taken.", "saved"]
    with Session() as db:
        owners = db.execute(text("SELECT count(*) FROM user_profiles WHERE lower(username) = :n"), {"n": name}).scalar()
    assert owners == 1


def test_the_database_enforces_case_insensitive_uniqueness_and_the_format(pg):
    Session, make_user, tag = pg
    a, b = make_user(1), make_user(2)
    name = f"db_{tag}"
    insert = text("INSERT INTO user_profiles (user_id, username) VALUES (:u, :n)")

    with Session() as db:
        db.execute(insert, {"u": a, "n": name})
        db.commit()

    # The format check stops an uppercase copy outright, and the
    # unique index on lower(username) backs it up.
    # (Too long is refused by varchar(20) itself: a DataError.)
    for bad in (name.upper(), "ab", "has-dash", "x" * 21):
        with Session() as db, pytest.raises((IntegrityError, DataError)):
            db.execute(insert, {"u": b, "n": bad})
            db.commit()
    with Session() as db, pytest.raises(IntegrityError):
        db.execute(insert, {"u": b, "n": name})
        db.commit()

    with Session() as db:
        index = db.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_user_profiles_username_lower'")
        ).scalar()
    assert index and "UNIQUE" in index and "lower((username)::text)" in index
