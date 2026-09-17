"""
Ingest and persistence for VisualSignalTracks. The only module
that moves signal bytes between the network, storage and the
pure visual_analysis package.

Never log signal arrays here; log sizes, row counts, statuses.
"""

import gzip
import io
import json
import uuid
import zlib

from typing import Optional

from pydantic import ValidationError

from app.services import storage
from visual_analysis import config
from visual_analysis.schema import VisualSignalTrack
from visual_analysis.signals import SignalValidationError, validate_track


SIGNAL_TRACK_FILENAME = "visual_signals.json.gz"
RESULT_FILENAME = "video_analysis.json"
FEEDBACK_FILENAME = "visual_feedback.json"

_GZIP_MAGIC = b"\x1f\x8b"
_CHUNK = 64 * 1024


# ------------------------------------------------------------
# Decoding
# ------------------------------------------------------------

def _is_gzip(raw: bytes, content_encoding: Optional[str], content_type: Optional[str]) -> bool:
    if raw[:2] == _GZIP_MAGIC:
        return True
    if content_encoding and "gzip" in content_encoding.lower():
        return True
    if content_type and "application/gzip" in content_type.lower():
        return True
    return False


def gunzip_capped(raw: bytes, max_bytes: Optional[int] = None) -> bytes:
    """
    Decompress incrementally and stop the moment the output
    would exceed max_bytes, so a gzip bomb costs on the order of
    max_bytes of memory rather than its full expansion. The cap
    is read at call time so it always follows config.
    """

    if max_bytes is None:
        max_bytes = config.MAX_DECOMPRESSED_BYTES

    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = io.BytesIO()
    total = 0

    source = io.BytesIO(raw)
    while True:
        chunk = source.read(_CHUNK)
        if not chunk:
            break
        produced = decompressor.decompress(chunk, max_bytes - total + 1)
        total += len(produced)
        if total > max_bytes:
            raise SignalValidationError("payload_too_large", f"decompressed body exceeds {max_bytes} bytes")
        out.write(produced)
        # decompress() may have held back input beyond max_length;
        # drain it under the same cap.
        while decompressor.unconsumed_tail:
            produced = decompressor.decompress(decompressor.unconsumed_tail, max_bytes - total + 1)
            total += len(produced)
            if total > max_bytes:
                raise SignalValidationError("payload_too_large", f"decompressed body exceeds {max_bytes} bytes")
            out.write(produced)

    try:
        tail = decompressor.flush()
    except zlib.error as exc:
        raise SignalValidationError("invalid_gzip", "body is not valid gzip") from exc

    total += len(tail)
    if total > max_bytes:
        raise SignalValidationError("payload_too_large", f"decompressed body exceeds {max_bytes} bytes")
    out.write(tail)

    return out.getvalue()


def decode_body(raw: bytes, content_encoding: Optional[str], content_type: Optional[str]) -> dict:
    if len(raw) > config.MAX_COMPRESSED_BYTES:
        raise SignalValidationError("payload_too_large", f"body exceeds {config.MAX_COMPRESSED_BYTES} bytes")

    if _is_gzip(raw, content_encoding, content_type):
        try:
            raw = gunzip_capped(raw)
        except zlib.error as exc:
            raise SignalValidationError("invalid_gzip", "body is not valid gzip") from exc
    elif len(raw) > config.MAX_DECOMPRESSED_BYTES:
        raise SignalValidationError("payload_too_large", f"body exceeds {config.MAX_DECOMPRESSED_BYTES} bytes")

    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SignalValidationError("invalid_json", "body is not valid JSON") from exc

    if not isinstance(data, dict):
        raise SignalValidationError("invalid_json", "body must be a JSON object")

    return data


# ------------------------------------------------------------
# Parsing
# ------------------------------------------------------------

def parse_track(data: dict, expected_session_id: str) -> VisualSignalTrack:
    try:
        track = VisualSignalTrack.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", ()))
        raise SignalValidationError("invalid_schema", f"{loc}: {first.get('msg', 'invalid')}") from exc

    validate_track(track, expected_session_id)
    return track


# ------------------------------------------------------------
# Storage
# ------------------------------------------------------------

def track_key(user_id: uuid.UUID, session_id: uuid.UUID) -> str:
    return storage.build_object_key(user_id, session_id, SIGNAL_TRACK_FILENAME)


def result_key(user_id: uuid.UUID, session_id: uuid.UUID) -> str:
    return storage.build_object_key(user_id, session_id, RESULT_FILENAME)


def feedback_key(user_id: uuid.UUID, session_id: uuid.UUID) -> str:
    return storage.build_object_key(user_id, session_id, FEEDBACK_FILENAME)


def serialize_track(track: VisualSignalTrack) -> bytes:
    payload = json.dumps(track.model_dump(by_alias=True), separators=(",", ":")).encode("utf-8")
    return gzip.compress(payload, compresslevel=6)


def store_track(user_id: uuid.UUID, session_id: uuid.UUID, track: VisualSignalTrack) -> str:
    key = track_key(user_id, session_id)
    storage.upload_bytes(key, serialize_track(track), content_type="application/gzip")
    return key


def load_track(key: str, expected_session_id: str) -> VisualSignalTrack:
    raw = storage.download_bytes(key)
    data = decode_body(raw, "gzip", "application/gzip")
    return parse_track(data, expected_session_id)
