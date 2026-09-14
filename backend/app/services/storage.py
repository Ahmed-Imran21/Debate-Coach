import json
import uuid
from typing import Any

import boto3

from app.core.config import settings

_client = boto3.client(
    "s3",
    endpoint_url=settings.storage_endpoint_url,
    aws_access_key_id=settings.storage_access_key_id,
    aws_secret_access_key=settings.storage_secret_access_key,
)

_BUCKET = settings.storage_bucket_name


def build_object_key(user_id: uuid.UUID, session_id: uuid.UUID, filename: str) -> str:
    return f"users/{user_id}/sessions/{session_id}/{filename}"


def generate_presigned_upload_url(object_key: str, expires_seconds: int = 900) -> str:
    """A short-lived URL the client (iOS/Android/web) uploads audio to directly,
    so raw audio bytes never have to round-trip through our API server."""
    return _client.generate_presigned_url(
        "put_object",
        Params={"Bucket": _BUCKET, "Key": object_key},
        ExpiresIn=expires_seconds,
    )


def generate_presigned_download_url(object_key: str, expires_seconds: int = 900) -> str:
    return _client.generate_presigned_url(
        "get_object",
        Params={"Bucket": _BUCKET, "Key": object_key},
        ExpiresIn=expires_seconds,
    )


def upload_bytes(object_key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    _client.put_object(Bucket=_BUCKET, Key=object_key, Body=data, ContentType=content_type)


def upload_json(object_key: str, payload: dict[str, Any]) -> None:
    upload_bytes(object_key, json.dumps(payload).encode("utf-8"), content_type="application/json")


def download_bytes(object_key: str) -> bytes:
    response = _client.get_object(Bucket=_BUCKET, Key=object_key)
    return response["Body"].read()


def download_json(object_key: str) -> dict[str, Any]:
    return json.loads(download_bytes(object_key))
