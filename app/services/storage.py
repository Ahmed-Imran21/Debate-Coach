import json
import uuid

from pathlib import Path
from typing import Any

import boto3

from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings


_client = boto3.client(
    "s3",
    endpoint_url=settings.storage_endpoint_url,
    aws_access_key_id=settings.storage_access_key_id,
    aws_secret_access_key=settings.storage_secret_access_key,
    region_name=settings.storage_region,
    config=Config(signature_version="s3v4"),
)

_BUCKET = settings.storage_bucket_name


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

    return _client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": _BUCKET,
            "Key": object_key,
            "ContentType": content_type,
        },
        ExpiresIn=(
            expires_seconds
            or settings.storage_url_expiry_seconds
        ),
    )


def generate_presigned_download_url(
    object_key: str,
    expires_seconds: int | None = None,
) -> str:
    return _client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": _BUCKET,
            "Key": object_key,
        },
        ExpiresIn=(
            expires_seconds
            or settings.storage_url_expiry_seconds
        ),
    )


# ============================================================
# EXISTENCE
# ============================================================

def object_exists(object_key: str) -> bool:

    try:
        _client.head_object(
            Bucket=_BUCKET,
            Key=object_key,
        )

    except ClientError as error:

        code = error.response.get(
            "Error",
            {},
        ).get("Code")

        if code in ("404", "NoSuchKey", "NotFound"):
            return False

        raise

    return True


def object_size(object_key: str) -> int:

    try:
        response = _client.head_object(
            Bucket=_BUCKET,
            Key=object_key,
        )

    except ClientError as error:

        code = error.response.get(
            "Error",
            {},
        ).get("Code")

        if code in ("404", "NoSuchKey", "NotFound"):
            raise ObjectNotFoundError(object_key) from error

        raise

    return int(response["ContentLength"])


# ============================================================
# UPLOAD
# ============================================================

def upload_bytes(
    object_key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> None:
    _client.put_object(
        Bucket=_BUCKET,
        Key=object_key,
        Body=data,
        ContentType=content_type,
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
    _client.upload_file(
        Filename=str(file_path),
        Bucket=_BUCKET,
        Key=object_key,
        ExtraArgs={"ContentType": content_type},
    )


# ============================================================
# DOWNLOAD
# ============================================================

def download_bytes(object_key: str) -> bytes:

    try:
        response = _client.get_object(
            Bucket=_BUCKET,
            Key=object_key,
        )

    except ClientError as error:

        code = error.response.get(
            "Error",
            {},
        ).get("Code")

        if code in ("404", "NoSuchKey", "NotFound"):
            raise ObjectNotFoundError(object_key) from error

        raise

    return response["Body"].read()


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
        _client.download_file(
            Bucket=_BUCKET,
            Key=object_key,
            Filename=str(destination),
        )

    except ClientError as error:

        code = error.response.get(
            "Error",
            {},
        ).get("Code")

        if code in ("404", "NoSuchKey", "NotFound"):
            raise ObjectNotFoundError(object_key) from error

        raise

    return destination


# ============================================================
# DELETE
# ============================================================

def delete_prefix(prefix: str) -> int:
    """
    Delete every object under a prefix. Used when a user
    deletes a session.
    """

    paginator = _client.get_paginator("list_objects_v2")

    deleted = 0

    for page in paginator.paginate(
        Bucket=_BUCKET,
        Prefix=prefix,
    ):

        contents = page.get("Contents", [])

        if not contents:
            continue

        _client.delete_objects(
            Bucket=_BUCKET,
            Delete={
                "Objects": [
                    {"Key": item["Key"]}
                    for item in contents
                ]
            },
        )

        deleted += len(contents)

    return deleted
