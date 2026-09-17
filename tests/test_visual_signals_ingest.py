"""
app/services/visual_signals: body decoding with size caps, gzip
bomb safety, parse errors mapped to stable codes, storage
round-trip through a stubbed storage module.
"""

import gzip
import json

import pytest

from tests.visual_analysis.synthetic import simple_track
from visual_analysis import config
from visual_analysis.signals import SignalValidationError


@pytest.fixture
def vs(monkeypatch):
    """Import the module with storage stubbed to an in-memory dict."""
    from app.services import visual_signals as module
    from app.services import storage

    blobs: dict[str, bytes] = {}

    def upload_bytes(key, data, content_type="application/octet-stream"):
        blobs[key] = bytes(data)

    def download_bytes(key):
        if key not in blobs:
            raise storage.ObjectNotFoundError(key)
        return blobs[key]

    monkeypatch.setattr(storage, "upload_bytes", upload_bytes)
    monkeypatch.setattr(storage, "download_bytes", download_bytes)
    module._blobs = blobs  # for assertions
    return module


def test_plain_json_body(vs):
    data = simple_track()
    raw = json.dumps(data).encode()
    assert vs.decode_body(raw, None, "application/json") == data


def test_gzip_body_by_header_and_by_magic(vs):
    data = simple_track()
    gz = gzip.compress(json.dumps(data).encode())
    assert vs.decode_body(gz, "gzip", "application/json") == data
    assert vs.decode_body(gz, None, "application/gzip") == data
    assert vs.decode_body(gz, None, None) == data  # magic bytes


def test_compressed_size_cap(vs, monkeypatch):
    monkeypatch.setattr(config, "MAX_COMPRESSED_BYTES", 100)
    raw = json.dumps(simple_track()).encode()
    with pytest.raises(SignalValidationError) as info:
        vs.decode_body(raw, None, "application/json")
    assert info.value.code == "payload_too_large"


def test_gzip_bomb_is_rejected_at_the_cap(vs, monkeypatch):
    """
    A few KB of gzip that expands to 200 MB. Must be rejected
    without materialising more than the cap.
    """
    monkeypatch.setattr(config, "MAX_DECOMPRESSED_BYTES", 1024 * 1024)

    bomb = gzip.compress(b"0" * (200 * 1024 * 1024), compresslevel=9)
    assert len(bomb) < config.MAX_COMPRESSED_BYTES

    import tracemalloc

    tracemalloc.start()
    with pytest.raises(SignalValidationError) as info:
        vs.decode_body(bomb, "gzip", None)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert info.value.code == "payload_too_large"
    # Bounded by the cap (output buffer + one copy), not by the
    # 200 MB the bomb would expand to.
    assert peak < 4 * config.MAX_DECOMPRESSED_BYTES


def test_invalid_gzip_and_invalid_json(vs):
    with pytest.raises(SignalValidationError) as info:
        vs.decode_body(b"\x1f\x8bnot really gzip", "gzip", None)
    assert info.value.code == "invalid_gzip"

    with pytest.raises(SignalValidationError) as info:
        vs.decode_body(b"{not json", None, "application/json")
    assert info.value.code == "invalid_json"

    with pytest.raises(SignalValidationError) as info:
        vs.decode_body(b"[1,2,3]", None, "application/json")
    assert info.value.code == "invalid_json"


def test_parse_track_maps_schema_errors(vs):
    data = simple_track()
    del data["clock"]
    with pytest.raises(SignalValidationError) as info:
        vs.parse_track(data, "s-test")
    assert info.value.code == "invalid_schema"
    assert "clock" in info.value.detail


def test_store_and_load_round_trip(vs):
    import uuid

    user_id, session_id = uuid.uuid4(), uuid.uuid4()
    data = simple_track(str(session_id))
    track = vs.parse_track(data, str(session_id))

    key = vs.store_track(user_id, session_id, track)
    assert key == f"users/{user_id}/sessions/{session_id}/visual_signals.json.gz"
    assert vs._blobs[key][:2] == b"\x1f\x8b"

    loaded = vs.load_track(key, str(session_id))
    assert loaded.model_dump(by_alias=True) == track.model_dump(by_alias=True)
