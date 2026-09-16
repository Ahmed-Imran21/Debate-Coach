import datetime
import json
import uuid

from pathlib import Path
from typing import Any

from google.api_core.exceptions import NotFound
from google.auth import default as google_auth_default
from google.auth import impersonated_credentials
from google.cloud import storage

from app.core.config import settings


_client = storage.Client(project=settings.gcp_project_id)
_bucket = _client.bucket(settings.gcp_storage_bucket)


def _resolve_signing_credentials():
    """
    Signed URLs need a private key. A downloaded service-account
    key file (local dev, GOOGLE_APPLICATION_CREDENTIALS) already
    has one. Cloud Run's attached runtime service account does
    not, so there we self-impersonate through the IAM Credentials
    API instead, which requires granting that same account
    roles/iam.serviceAccountTokenCreator on itself (see
    setup-gcp.sh).
    """

    credentials, _ = google_auth_default()

    if hasattr(credentials, "sign_bytes"):
        return credentials

    if not settings.gcp_service_account_email:
        raise RuntimeError(
            "GCP_SERVICE_ACCOUNT_EMAIL must be set to generate "
            "signed URLs when running without a service account "
            "key file."
        )

    return impersonated_credentials.Credentials(
        source_credentials=credentials,
        target_principal=settings.gcp_service_account_email,
        target_scopes=[
            "https://www.googleapis.com/auth/devstorage.read_write"
        ],
        lifetime=3600,
    )


_signing_credentials = _resolve_signing_credentials()


class ObjectNotFoundError(LookupError):
    """
    Raised when a key the caller expected to exist does not.
    """


# ============================================================
# KEYS
# ============================================================

def build_object_key(
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    filename: str,
) -> str:
    return f"users/{user_id}/sessions/{session_id}/{filename}"


# ============================================================
# PRESIGNED URLS
# ============================================================

def generate_presigned_upload_url(
    object_key: str,
    content_type: str,
    expires_seconds: int | None = None,
) -> str:
    """
    A short-lived URL the browser or mobile client PUTs audio
    to directly, so raw audio bytes never round-trip through
    the API server.

    content_type is part of the signature, so the client must
    send exactly the same Content-Type header on the PUT. The
    caller is responsible for handing that value back to the
    client alongside the URL.
    """

    blob = _bucket.blob(object_key)

    return blob.generate_signed_url(
        version="v4",
        method="PUT",
        content_type=content_type,
        expiration=datetime.timedelta(
            seconds=(
                expires_seconds
                or settings.storage_url_expiry_seconds
            )
        ),
        credentials=_signing_credentials,
    )


def generate_presigned_download_url(
    object_key: str,
    expires_seconds: int | None = None,
) -> str:
    blob = _bucket.blob(object_key)

    return blob.generate_signed_url(
        version="v4",
        method="GET",
        expiration=datetime.timedelta(
            seconds=(
                expires_seconds
                or settings.storage_url_expiry_seconds
            )
        ),
        credentials=_signing_credentials,
    )


# ============================================================
# EXISTENCE
# ============================================================

def object_exists(object_key: str) -> bool:
    return _bucket.blob(object_key).exists()


def object_size(object_key: str) -> int:
    blob = _bucket.blob(object_key)

    try:
        blob.reload()

    except NotFound as error:
        raise ObjectNotFoundError(object_key) from error

    return blob.size


# ============================================================
# UPLOAD
# ============================================================

def upload_bytes(
    object_key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> None:
    _bucket.blob(object_key).upload_from_string(
        data,
        content_type=content_type,
    )


def upload_json(
    object_key: str,
    payload: Any,
) -> None:
    upload_bytes(
        object_key,
        json.dumps(
            payload,
            ensure_ascii=False,
        ).encode("utf-8"),
        content_type="application/json",
    )


def upload_file(
    object_key: str,
    file_path: str | Path,
    content_type: str = "application/octet-stream",
) -> None:
    _bucket.blob(object_key).upload_from_filename(
        str(file_path),
        content_type=content_type,
    )


# ============================================================
# DOWNLOAD
# ============================================================

def download_bytes(object_key: str) -> bytes:

    try:
        return _bucket.blob(object_key).download_as_bytes()

    except NotFound as error:
        raise ObjectNotFoundError(object_key) from error


def download_json(object_key: str) -> Any:
    return json.loads(
        download_bytes(object_key)
    )


def download_file(
    object_key: str,
    destination: str | Path,
) -> Path:

    destination = Path(destination)

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        _bucket.blob(object_key).download_to_filename(
            str(destination)
        )

    except NotFound as error:
        raise ObjectNotFoundError(object_key) from error

    return destination


# ============================================================
# DELETE
# ============================================================

def delete_prefix(prefix: str) -> int:
    """
    Delete every object under a prefix. Used when a user
    deletes a session.
    """

    blobs = list(_client.list_blobs(_bucket, prefix=prefix))

    if not blobs:
        return 0

    _bucket.delete_blobs(blobs)

    return len(blobs)
