"""
Sign-up needs both boxes ticked (Privacy Policy, Terms and Conditions),
whatever client sends it, and records when each was accepted. Accounts
from before the boxes existed still sign in and aren't asked again.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.routes.auth import SIGNUP_CONSENT_MESSAGE

PASSWORD = "CorrectHorse1"


@pytest.fixture
def client(app_module, db, fake_storage, fake_jobs, video_flag):
    from fastapi.testclient import TestClient

    from app.db.database import get_db

    app = app_module.app
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def lenient(monkeypatch):
    """The rollout step before the website sends the boxes."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "signup_consent_required", False)


def _signup(client, email="c@test.com", **consent):
    body = {"email": email, "password": PASSWORD, "first_name": "A", "last_name": "B", **consent}
    return client.post("/v1/auth/signup", json=body)


def _user(db, email="c@test.com"):
    from app.models.user import User

    return db.query(User).filter(User.email == email).one_or_none()


@pytest.mark.parametrize(
    "consent",
    [
        {},
        {"accepted_privacy_policy": True},
        {"accepted_terms": True},
        {"accepted_privacy_policy": True, "accepted_terms": False},
        {"accepted_privacy_policy": False, "accepted_terms": True},
        {"accepted_privacy_policy": False, "accepted_terms": False},
        {"accepted_privacy_policy": None, "accepted_terms": None},
    ],
)
def test_signup_without_both_acceptances_is_refused(client, db, consent):
    r = _signup(client, **consent)
    assert r.status_code == 422
    assert r.json() == {"detail": SIGNUP_CONSENT_MESSAGE}
    assert _user(db) is None


def test_signup_with_both_records_when_each_was_accepted(client, db):
    before = datetime.now(timezone.utc)
    r = _signup(client, accepted_privacy_policy=True, accepted_terms=True)
    assert r.status_code == 201, r.text
    user = _user(db)
    for at in (user.privacy_policy_accepted_at, user.terms_accepted_at):
        assert at is not None
        at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)  # SQLite drops the zone
        assert before - timedelta(seconds=1) <= at <= datetime.now(timezone.utc) + timedelta(seconds=1)


def test_consent_is_checked_before_anything_else_is_revealed(client, db):
    # An existing email without the boxes gets the consent message, not
    # "That email already has an account."
    assert _signup(client, accepted_privacy_policy=True, accepted_terms=True).status_code == 201
    r = _signup(client)
    assert r.status_code == 422
    assert r.json()["detail"] == SIGNUP_CONSENT_MESSAGE


def test_existing_users_without_a_record_still_sign_in(client, db, make_user):
    from app.core.security import hash_password

    user = make_user("old@test.com")
    user.password_hash = hash_password(PASSWORD)
    db.commit()
    assert user.privacy_policy_accepted_at is None and user.terms_accepted_at is None
    r = client.post("/v1/auth/login", json={"email": "old@test.com", "password": PASSWORD})
    assert r.status_code == 200, r.text


def test_rollout_step_allows_a_signup_that_leaves_them_out(client, db, lenient):
    r = _signup(client)
    assert r.status_code == 201, r.text
    user = _user(db)
    assert user.privacy_policy_accepted_at is None and user.terms_accepted_at is None


def test_rollout_step_still_records_and_still_refuses_an_explicit_no(client, db, lenient):
    assert _signup(client, "yes@test.com", accepted_privacy_policy=True, accepted_terms=True).status_code == 201
    assert _user(db, "yes@test.com").terms_accepted_at is not None
    r = _signup(client, "no@test.com", accepted_privacy_policy=True, accepted_terms=False)
    assert r.status_code == 422
    assert _user(db, "no@test.com") is None
