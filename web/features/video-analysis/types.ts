/**
 * TypeScript mirror of visual_analysis/schema.py
 * (debatecoach.visual_signals, version 1.0). Field names and
 * nesting match exactly, including the "schema" key (a reserved
 * word turned property name, hence the string index rather than
 * an identifier). This file is typing only — track.ts builds and
 * validates the actual object.
 */

export type UserAgentFamily = "chrome" | "edge" | "firefox" | "safari" | "other";
export type DeviceTier = "full" | "reduced" | "face_only";
export type Delegate = "GPU" | "CPU";

export interface RuntimeInfo {
  name: string;
  version: string;
  delegate: Delegate;
}

export interface ModelInfo {
  task: "face_landmarker" | "hand_landmarker";
  model_id: string;
  sha256: string;
}

export interface Source {
  platform: "web";
  client_version: string;
  user_agent_family: UserAgentFamily;
  runtime: RuntimeInfo;
  models: ModelInfo[];
  device_tier: DeviceTier;
  benchmark_fps: number;
}

export interface Capture {
  frame_width: number;
  frame_height: number;
  input_mirrored: boolean;
  handedness_convention: "anatomical";
  target_fps: number;
}

export interface Clock {
  t0_reference: "audio_recording_start";
  sync_method: "mediarecorder_start_event";
  uncertainty_ms: number;
  duration_s: number;
}

export interface CalibrationBaseline {
  head_yaw: number;
  head_pitch: number;
  iris_x: number;
  iris_y: number;
}

export type RightHandCheck = "passed" | "failed" | "skipped";

export interface Calibration {
  performed: boolean;
  baseline: CalibrationBaseline | null;
  samples: number;
  stability: number;
  right_hand_check: RightHandCheck;
}

export type Setting = "camera_audience" | "in_room_practice";

export interface Context {
  setting: Setting;
  uses_notes: boolean;
}

export interface SetupCheck {
  face_visible: boolean;
  hands_visible_when_raised: boolean;
  lighting: "ok" | "dim" | "backlit";
  distance: "ok" | "too_close" | "too_far";
}

export interface Frames {
  t: number[];
  face_count: Array<number | null>;
  head_yaw: Array<number | null>;
  head_pitch: Array<number | null>;
  head_roll: Array<number | null>;
  iris_x: Array<number | null>;
  iris_y: Array<number | null>;
  face_scale: Array<number | null>;
  face_cx: Array<number | null>;
  face_cy: Array<number | null>;
  lh_present: Array<number | null>;
  lh_score: Array<number | null>;
  lh_cx: Array<number | null>;
  lh_cy: Array<number | null>;
  rh_present: Array<number | null>;
  rh_score: Array<number | null>;
  rh_cx: Array<number | null>;
  rh_cy: Array<number | null>;
  infer_ms: Array<number | null>;
}

export const FRAME_COLUMNS = [
  "face_count", "head_yaw", "head_pitch", "head_roll", "iris_x", "iris_y",
  "face_scale", "face_cx", "face_cy",
  "lh_present", "lh_score", "lh_cx", "lh_cy",
  "rh_present", "rh_score", "rh_cx", "rh_cy",
  "infer_ms",
] as const satisfies readonly (keyof Omit<Frames, "t">)[];

export type GapReason = "tab_hidden" | "perf_disabled" | "model_error" | "camera_interrupted";

export interface Gap {
  start: number;
  end: number;
  reason: GapReason;
}

export type DegradationReason = "p90_latency" | "thermal_suspected" | "manual";

export interface Degradation {
  t: number;
  face_fps: number;
  hands_fps: number;
  reason: DegradationReason;
}

export interface VisualSignalTrack {
  schema: "debatecoach.visual_signals";
  schema_version: "1.0";
  session_id: string;

  source: Source;
  capture: Capture;
  clock: Clock;
  calibration: Calibration;
  context: Context;
  setup_check: SetupCheck;

  frames: Frames;
  gaps: Gap[];
  degradations: Degradation[];
}

/** One tick's measurement, before it's appended to the columnar Frames. */
export interface FrameSample {
  face_count: number | null;
  head_yaw: number | null;
  head_pitch: number | null;
  head_roll: number | null;
  iris_x: number | null;
  iris_y: number | null;
  face_scale: number | null;
  face_cx: number | null;
  face_cy: number | null;
  lh_present: number | null;
  lh_score: number | null;
  lh_cx: number | null;
  lh_cy: number | null;
  rh_present: number | null;
  rh_score: number | null;
  rh_cx: number | null;
  rh_cy: number | null;
  infer_ms: number | null;
}

export const EMPTY_SAMPLE: FrameSample = {
  face_count: null,
  head_yaw: null,
  head_pitch: null,
  head_roll: null,
  iris_x: null,
  iris_y: null,
  face_scale: null,
  face_cx: null,
  face_cy: null,
  lh_present: null,
  lh_score: null,
  lh_cx: null,
  lh_cy: null,
  rh_present: null,
  rh_score: null,
  rh_cx: null,
  rh_cy: null,
  infer_ms: null,
};
