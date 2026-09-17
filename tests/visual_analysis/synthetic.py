"""
Generators for VisualSignalTrack-shaped dicts, used by the
signals/events/metrics/pipeline tests. Everything here is built
in memory; nothing is read from disk or recorded.
"""

from __future__ import annotations

import copy
from typing import Callable, Optional

SHA = "a" * 64


def base_track(session_id: str = "s-test", duration_s: float = 30.0) -> dict:
    return {
        "schema": "debatecoach.visual_signals",
        "schema_version": "1.0",
        "session_id": session_id,
        "source": {
            "platform": "web",
            "client_version": "test",
            "user_agent_family": "chrome",
            "runtime": {"name": "mediapipe-tasks-vision", "version": "1.0.1", "delegate": "GPU"},
            "models": [
                {"task": "face_landmarker", "model_id": "face_landmarker.task", "sha256": SHA},
                {"task": "hand_landmarker", "model_id": "hand_landmarker.task", "sha256": SHA},
            ],
            "device_tier": "full",
            "benchmark_fps": 11.5,
        },
        "capture": {
            "frame_width": 640,
            "frame_height": 360,
            "input_mirrored": False,
            "handedness_convention": "anatomical",
            "target_fps": 10,
        },
        "clock": {
            "t0_reference": "audio_recording_start",
            "sync_method": "mediarecorder_start_event",
            "uncertainty_ms": 150,
            "duration_s": duration_s,
        },
        "calibration": {
            "performed": True,
            "baseline": {"head_yaw": 0.0, "head_pitch": 0.0, "iris_x": 0.0, "iris_y": 0.0},
            "samples": 28,
            "stability": 0.91,
            "right_hand_check": "passed",
        },
        "context": {"setting": "camera_audience", "uses_notes": False},
        "setup_check": {
            "face_visible": True,
            "hands_visible_when_raised": True,
            "lighting": "ok",
            "distance": "ok",
        },
        "frames": {
            "t": [], "face_count": [], "head_yaw": [], "head_pitch": [], "head_roll": [],
            "iris_x": [], "iris_y": [], "face_scale": [], "face_cx": [], "face_cy": [],
            "lh_present": [], "lh_score": [], "lh_cx": [], "lh_cy": [],
            "rh_present": [], "rh_score": [], "rh_cx": [], "rh_cy": [],
            "infer_ms": [],
        },
        "gaps": [],
        "degradations": [],
    }


def add_frames(
    track: dict,
    *,
    fps: float = 10.0,
    start_s: float = 0.0,
    end_s: Optional[float] = None,
    face: bool = True,
    yaw=0.0,
    pitch=0.0,
    roll: float = 0.0,
    iris_x: float = 0.0,
    iris_y: float = 0.0,
    face_scale: float = 0.09,
    lh: Optional[Callable[[float], tuple[float, float]]] = None,
    rh: Optional[Callable[[float], tuple[float, float]]] = None,
    hands_ran: bool = True,
    face_count: int = 1,
    infer_ms: float = 40.0,
) -> dict:
    end_s = track["clock"]["duration_s"] if end_s is None else end_s
    f = track["frames"]
    step = 1.0 / fps
    n = int(round((end_s - start_s) * fps))

    for k in range(n):
        t = round(start_s + k * step + 1e-6, 4)
        f["t"].append(t)
        f["infer_ms"].append(infer_ms)

        if face:
            f["face_count"].append(face_count)
            f["head_yaw"].append(round(yaw(t) if callable(yaw) else yaw, 2))
            f["head_pitch"].append(round(pitch(t) if callable(pitch) else pitch, 2))
            f["head_roll"].append(roll)
            f["iris_x"].append(iris_x)
            f["iris_y"].append(iris_y)
            f["face_scale"].append(face_scale)
            f["face_cx"].append(0.5)
            f["face_cy"].append(0.4)
        else:
            f["face_count"].append(0)
            for key in ("head_yaw", "head_pitch", "head_roll", "iris_x", "iris_y", "face_scale", "face_cx", "face_cy"):
                f[key].append(None)

        for side, fn in (("lh", lh), ("rh", rh)):
            if not hands_ran:
                for suffix in ("present", "score", "cx", "cy"):
                    f[f"{side}_{suffix}"].append(None)
                continue
            pos = fn(t) if fn else None
            if pos is None:
                f[f"{side}_present"].append(0)
                for suffix in ("score", "cx", "cy"):
                    f[f"{side}_{suffix}"].append(None)
            else:
                f[f"{side}_present"].append(1)
                f[f"{side}_score"].append(0.95)
                f[f"{side}_cx"].append(round(pos[0], 4))
                f[f"{side}_cy"].append(round(pos[1], 4))

    return track


def speech_segments(*spans: tuple[float, float]) -> list[dict]:
    return [{"start": s, "end": e} for s, e in spans]


def simple_track(session_id: str = "s-test", duration_s: float = 10.0, fps: float = 10.0) -> dict:
    """
    A valid, boring track: face present and facing, hands still.
    Used by the Phase 1 schema/ingest tests, which only need
    something that passes validation, not any particular event/
    metric outcome (see visual_strong for that).
    """
    track = base_track(session_id, duration_s)
    add_frames(
        track,
        fps=fps,
        lh=lambda t: (0.35, 0.75),
        rh=lambda t: (0.65, 0.75),
    )
    return track


def clone(track: dict) -> dict:
    return copy.deepcopy(track)


def still_hands(lh_pos=(0.35, 0.7), rh_pos=(0.65, 0.7)):
    return (lambda t: lh_pos), (lambda t: rh_pos)


def oscillating(center: tuple[float, float], amplitude: float, hz: float):
    import math

    def fn(t: float) -> tuple[float, float]:
        return (center[0] + amplitude * math.sin(2 * math.pi * hz * t), center[1])

    return fn


# ---------------------------------------------------------------
# Named fixtures (§5.8)
# ---------------------------------------------------------------

def visual_strong(duration_s: float = 30.0) -> dict:
    """Face present and facing baseline ~90% of speech, regular gestures, no long stillness."""
    track = base_track(duration_s=duration_s)
    lh, rh = still_hands()
    add_frames(track, yaw=0.0, pitch=0.0, lh=lh, rh=rh)
    return track


def visual_weak(duration_s: float = 30.0) -> dict:
    """Frequent long look-downs, hands visible but still for long runs."""
    track = base_track(duration_s=duration_s)
    lh, rh = still_hands()

    def pitch(t: float) -> float:
        cycle = t % 10.0
        return -25.0 if cycle < 4.0 else 0.0

    add_frames(track, pitch=pitch, lh=lh, rh=rh)
    return track


def visual_mixed(duration_s: float = 30.0) -> dict:
    """Good first half, poor second half."""
    track = base_track(duration_s=duration_s)
    lh, rh = still_hands()
    half = duration_s / 2

    add_frames(track, start_s=0.0, end_s=half, yaw=0.0, pitch=0.0, lh=lh, rh=rh)
    add_frames(track, start_s=half, end_s=duration_s, yaw=25.0, pitch=-20.0, hands_ran=True)
    return track
