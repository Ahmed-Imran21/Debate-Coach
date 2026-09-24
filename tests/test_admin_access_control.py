"""
require_admin is the actual security boundary for every route in
app/routes/admin.py (see its own docstring) — the frontend's
middleware gate is UX, this is enforcement. Tested directly
against the dependency function, not through a full app/DB
harness: it's pure logic over settings.admin_emails_list and a
User's .email.
"""

import os
import uuid
from dataclasses import dataclass, field

import pytest
from fastapi import HTTPException

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("GCP_PROJECT_ID", "test-project")
os.environ.setdefault("GCP_STORAGE_BUCKET", "test-bucket")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@127.0.0.1:1/never")

from app.core.config import settings  # noqa: E402
from app.routes.deps import require_admin  # noqa: E402


@dataclass
class _FakeUser:
    """Duck-types the one attribute require_admin reads."""
    email: str
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@pytest.fixture(autouse=True)
def _reset_admin_emails(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "")
    yield


def test_empty_admin_emails_rejects_everyone(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "")

    with pytest.raises(HTTPException) as exc_info:
        require_admin(current_user=_FakeUser(email="anyone@example.com"))

    assert exc_info.value.status_code == 403


def test_listed_email_is_admitted(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "owner@example.com")

    user = _FakeUser(email="owner@example.com")
    assert require_admin(current_user=user) is user


def test_unlisted_email_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "owner@example.com")

    with pytest.raises(HTTPException) as exc_info:
        require_admin(current_user=_FakeUser(email="someone-else@example.com"))

    assert exc_info.value.status_code == 403


def test_comparison_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "Owner@Example.com")

    user = _FakeUser(email="owner@example.com")
    assert require_admin(current_user=user) is user


def test_multiple_comma_separated_emails(monkeypatch):
    monkeypatch.setattr(
        settings, "admin_emails", "first@example.com, second@example.com"
    )

    assert require_admin(current_user=_FakeUser(email="second@example.com"))

    with pytest.raises(HTTPException):
        require_admin(current_user=_FakeUser(email="third@example.com"))


def test_whitespace_and_empty_entries_are_ignored(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", " admin@example.com , , ")

    assert require_admin(current_user=_FakeUser(email="admin@example.com"))
    assert settings.admin_emails_list == ["admin@example.com"]
