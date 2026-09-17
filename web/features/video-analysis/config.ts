/**
 * Every constant for capture, scheduling and framing checks, in
 * one place. ALL VALUES ARE PROVISIONAL (task doc §4.7/§4.9) —
 * tune against docs/video-analysis/MANUAL_TEST_PLAN.md, not by
 * guessing.
 *
 * Mirrors visual_analysis/config.py where a threshold is shared
 * conceptually (e.g. GESTURE_SPEED_FS), but this file is not
 * generated from that one: the backend receives raw signals and
 * computes events from them; nothing here needs to match it
 * exactly for correctness, only the frame *shape* (schema.ts)
 * does.
 */

// ---------------------------------------------------------------
// Clock
// ---------------------------------------------------------------

// Added to (frameTimeMs - t0) / 1000 to correct for the small,
// fixed delay between the MediaRecorder "start" event and the
// first audio sample actually being captured, if one is ever
// measured. Zero until the clap-test manual plan finds otherwise.
export const CLOCK_OFFSET_S = 0;

export const CLOCK_UNCERTAINTY_MS = 150;

// ---------------------------------------------------------------
// Capture
// ---------------------------------------------------------------

export const CAPTURE_WIDTH_IDEAL = 1280;
export const CAPTURE_HEIGHT_IDEAL = 720;
export const CAPTURE_FRAME_RATE_IDEAL = 30;

export const SIGNAL_FRAME_WIDTH = 640;
export const SIGNAL_FRAME_HEIGHT = 360;

// ---------------------------------------------------------------
// Scheduler (adaptive rate)
// ---------------------------------------------------------------

export const TARGET_FPS = 10;
export const MIN_INTERVAL_MS = 100;
export const P90_WINDOW = 30;
export const REDUCE_HANDS_P90_MS = 80;
export const DISABLE_HANDS_P90_MS = 160;
export const DISABLE_ALL_EFFECTIVE_FPS = 3;
export const DISABLE_ALL_SUSTAINED_S = 10;

// ---------------------------------------------------------------
// Setup screen: framing checks
// ---------------------------------------------------------------

export const FACE_VISIBLE_WINDOW = 20;
export const FACE_VISIBLE_MIN_RATIO = 0.8;

export const DISTANCE_SCALE_MIN = 0.04;
export const DISTANCE_SCALE_MAX = 0.16;

export const LIGHTING_SAMPLE_MS = 500;
export const LIGHTING_DIM_LUMA = 50;
export const LIGHTING_BACKLIT_RATIO = 0.6;

export const HANDS_RAISED_WINDOW_S = 2;
export const HANDS_RAISED_MIN_RATIO = 0.6;

// ---------------------------------------------------------------
// Benchmark tiers
// ---------------------------------------------------------------

export const BENCHMARK_DURATION_S = 3;
export const TIER_FULL_MIN_FPS = 9;
export const TIER_FULL_MAX_P90_MS = 80;
export const TIER_REDUCED_MIN_FPS = 6;
export const TIER_FACE_ONLY_MIN_FPS = 5;

// ---------------------------------------------------------------
// Calibration
// ---------------------------------------------------------------

export const CALIBRATION_DURATION_S = 3;
export const CALIBRATION_MIN_SAMPLES = 15;
export const CALIBRATION_STABILITY_YAW_NORM_DEG = 10;
export const RIGHT_HAND_CHECK_WINDOW_S = 2;
export const RIGHT_HAND_CHECK_MIN_RATIO = 0.6;

// MediaPipe's handedness label assumes a mirrored selfie image;
// our frames are unmirrored, so the label is inverted by default.
// Flipped once, automatically, if the calibration right-hand
// check fails with the current mapping (§4.8).
export const HANDEDNESS_LABEL_INVERTED_DEFAULT = true;

// ---------------------------------------------------------------
// During recording
// ---------------------------------------------------------------

export const FACE_MISSING_HINT_AFTER_S = 3;

// ---------------------------------------------------------------
// Upload / persistence
// ---------------------------------------------------------------

export const UPLOAD_RETRY_DELAYS_MS = [1000, 2000, 4000, 8000];
export const INDEXEDDB_MAX_AGE_DAYS = 7;
