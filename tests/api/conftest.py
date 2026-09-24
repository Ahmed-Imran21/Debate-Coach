"""
FastAPI test harness.

- The ORM is bound to an in-memory SQLite engine with FK
  enforcement on and a compile hook so Postgres JSONB renders.
- app.services.storage needs Application Default Credentials at
  import; a throwaway service-account key (fresh RSA key, fake
  email) is generated so the client constructs without network.
- storage, jobs and the pipeline are stubbed per test.
- The lifespan is NOT run (no create_all against a real DB, no
  API-key pool), so TestClient is used without a context manager.
"""

import json
import os
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):
    return "JSON"


def _write_fake_service_account(path: str) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "type": "service_account",
                "project_id": "test-project",
                "private_key_id": "test",
                "private_key": pem,
                "client_email": "test@test-project.iam.gserviceaccount.com",
                "client_id": "0",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            },
            fh,
        )


@pytest.fixture(scope="session")
def app_module(tmp_path_factory):
    key_path = tmp_path_factory.mktemp("creds") / "sa.json"
    _write_fake_service_account(str(key_path))
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(key_path)

    from app import main as main_module

    return main_module


@pytest.fixture
def engine():
    # TestClient runs sync endpoints on a worker thread; one shared
    # in-memory connection must be usable from any thread.
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    from app.db.database import Base
    import app.models  # noqa: F401  (registers every table)

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Session:
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


class FakeStorage:
    """In-memory stand-in for the parts of app.services.storage the routes use."""

    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}
        self.deleted_prefixes: list[str] = []
        self.sizes: dict[str, int] = {}

    def install(self, monkeypatch) -> None:
        from app.services import storage

        monkeypatch.setattr(storage, "generate_presigned_upload_url", lambda object_key, content_type: f"https://upload.test/{object_key}")
        monkeypatch.setattr(storage, "generate_presigned_download_url", lambda object_key, expires_seconds=None: f"https://download.test/{object_key}")
        monkeypatch.setattr(storage, "upload_bytes", self._upload_bytes)
        monkeypatch.setattr(storage, "upload_json", self._upload_json)
        monkeypatch.setattr(storage, "download_bytes", self._download_bytes)
        monkeypatch.setattr(storage, "download_json", self._download_json)
        monkeypatch.setattr(storage, "object_size", self._object_size)
        monkeypatch.setattr(storage, "delete_prefix", self._delete_prefix)

    def _upload_bytes(self, key, data, content_type="application/octet-stream"):
        self.blobs[key] = bytes(data)

    def _upload_json(self, key, payload):
        self.blobs[key] = json.dumps(payload).encode()

    def _download_bytes(self, key):
        from app.services import storage

        if key not in self.blobs:
            raise storage.ObjectNotFoundError(key)
        return self.blobs[key]

    def _download_json(self, key):
        return json.loads(self._download_bytes(key))

    def _object_size(self, key):
        from app.services import storage

        if key in self.sizes:
            return self.sizes[key]
        if key in self.blobs:
            return len(self.blobs[key])
        raise storage.ObjectNotFoundError(key)

    def _delete_prefix(self, prefix):
        self.deleted_prefixes.append(prefix)
        gone = [k for k in self.blobs if k.startswith(prefix)]
        for k in gone:
            del self.blobs[k]
        return len(gone)


@pytest.fixture
def fake_storage(monkeypatch) -> FakeStorage:
    fs = FakeStorage()
    fs.install(monkeypatch)
    return fs


@pytest.fixture
def fake_jobs(monkeypatch):
    from app.services import jobs, pipeline

    submitted: list[uuid.UUID] = []
    monkeypatch.setattr(jobs, "submit", lambda session_id, fn: submitted.append(session_id) or True)
    monkeypatch.setattr(jobs, "is_running", lambda session_id: False)
    monkeypatch.setattr(pipeline, "build_job", lambda session_id: (lambda: None))
    return submitted


@pytest.fixture
def video_flag(monkeypatch):
    from app.core.config import settings

    def set_flag(enabled: bool) -> None:
        monkeypatch.setattr(settings, "video_analysis_enabled", enabled)

    set_flag(True)
    return set_flag


@pytest.fixture
def make_user(db):
    from app.models.user import User

    def _make(email: str):
        user = User(email=email, password_hash="x", first_name="T", last_name="U")
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _make


@pytest.fixture
def client_for(app_module, db, fake_storage, fake_jobs, video_flag):
    """
    Returns a factory: client_for(user) -> TestClient authenticated
    as that user, sharing the test DB session.
    """
    from fastapi.testclient import TestClient

    from app.db.database import get_db
    from app.routes.deps import get_current_user

    app = app_module.app

    def _client(user):
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    yield _client
    app.dependency_overrides.clear()
