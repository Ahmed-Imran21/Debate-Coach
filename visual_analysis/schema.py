"""
Pydantic models for the client -> backend VisualSignalTrack
(schema debatecoach.visual_signals, version 1.0).

Field semantics are defined in docs/video-analysis/README.md and
must be implemented identically by the browser extractor. This
file is the source of truth for shape; visual_analysis/signals.py
holds the rules Pydantic cannot express (array lengths, ranges,
monotonic time).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    # protected_namespaces=() so a field may be called model_id
    # without Pydantic warning about its own "model_" prefix.
    model_config = ConfigDict(extra="forbid", protected_namespaces=())


# ------------------------------------------------------------
# Provenance
# ------------------------------------------------------------

class RuntimeInfo(_Strict):
    name: str
    version: str
    delegate: Literal["GPU", "CPU"]


class ModelInfo(_Strict):
    task: Literal["face_landmarker", "hand_landmarker"]
    model_id: str
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class Source(_Strict):
    platform: Literal["web"]
    client_version: str
    user_agent_family: Literal["chrome", "edge", "firefox", "safari", "other"]
    runtime: RuntimeInfo
    models: list[ModelInfo]
    device_tier: Literal["full", "reduced", "face_only"]
    benchmark_fps: float = Field(ge=0)


class Capture(_Strict):
    frame_width: int = Field(gt=0)
    frame_height: int = Field(gt=0)
    input_mirrored: bool
    handedness_convention: Literal["anatomical"]
    target_fps: int = Field(gt=0)


class Clock(_Strict):
    t0_reference: Literal["audio_recording_start"]
    sync_method: Literal["mediarecorder_start_event"]
    uncertainty_ms: float = Field(ge=0)
    duration_s: float = Field(ge=0)


class CalibrationBaseline(_Strict):
    head_yaw: float
    head_pitch: float
    iris_x: float
    iris_y: float


class Calibration(_Strict):
    performed: bool
    baseline: Optional[CalibrationBaseline] = None
    samples: int = Field(ge=0)
    stability: float = Field(ge=0, le=1)
    right_hand_check: Literal["passed", "failed", "skipped"]


class Context(_Strict):
    setting: Literal["camera_audience", "in_room_practice"]
    uses_notes: bool


class SetupCheck(_Strict):
    face_visible: bool
    hands_visible_when_raised: bool
    lighting: Literal["ok", "dim", "backlit"]
    distance: Literal["ok", "too_close", "too_far"]


# ------------------------------------------------------------
# Signal columns
# ------------------------------------------------------------

FloatCol = list[Optional[float]]
IntCol = list[Optional[int]]


class Frames(_Strict):
    """
    Columnar samples. Every list has the same length as `t`.
    None means "not measured"; never 0.
    """

    t: list[float]
    face_count: IntCol
    head_yaw: FloatCol
    head_pitch: FloatCol
    head_roll: FloatCol
    iris_x: FloatCol
    iris_y: FloatCol
    face_scale: FloatCol
    face_cx: FloatCol
    face_cy: FloatCol
    lh_present: IntCol
    lh_score: FloatCol
    lh_cx: FloatCol
    lh_cy: FloatCol
    rh_present: IntCol
    rh_score: FloatCol
    rh_cx: FloatCol
    rh_cy: FloatCol
    infer_ms: FloatCol


FRAME_COLUMNS: tuple[str, ...] = tuple(
    name for name in Frames.model_fields if name != "t"
)


class Gap(_Strict):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    reason: Literal["tab_hidden", "perf_disabled", "model_error", "camera_interrupted"]


class Degradation(_Strict):
    t: float = Field(ge=0)
    face_fps: float = Field(ge=0)
    hands_fps: float = Field(ge=0)
    reason: Literal["p90_latency", "thermal_suspected", "manual"]


# ------------------------------------------------------------
# Track
# ------------------------------------------------------------

class VisualSignalTrack(_Strict):
    schema_: str = Field(alias="schema")
    schema_version: str
    session_id: str

    source: Source
    capture: Capture
    clock: Clock
    calibration: Calibration
    context: Context
    setup_check: SetupCheck

    frames: Frames
    gaps: list[Gap] = Field(default_factory=list)
    degradations: list[Degradation] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", populate_by_name=True, protected_namespaces=())

    @property
    def frame_count(self) -> int:
        return len(self.frames.t)


# Every video status value, shared by the API layer.
VIDEO_STATUSES = (
    "not_requested",
    "awaiting_upload",
    "received",
    "processing",
    "processed",
    "partial",
    "insufficient_data",
    "unavailable",
    "failed",
)

UNAVAILABLE_REASONS = (
    "camera_denied",
    "unsupported",
    "model_load_failed",
    "device_too_slow",
    "user_opted_out",
    "upload_failed",
    "face_not_found",
)

COACHING_STATUSES = ("not_requested", "pending", "completed", "failed")
