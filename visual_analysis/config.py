"""
Every threshold and constant for visual analysis, in one place.

ALL VALUES ARE PROVISIONAL. They came from the task document,
not from data. Tune them with docs/video-analysis/THRESHOLD_TUNING.md
against labelled sessions before trusting them. Do not scatter
literals through metrics.py / events.py; add them here.
"""

# ------------------------------------------------------------
# Contract
# ------------------------------------------------------------

SIGNAL_SCHEMA = "debatecoach.visual_signals"
SUPPORTED_SIGNAL_SCHEMA_VERSIONS = frozenset({"1.0"})

RESULT_SCHEMA = "debatecoach.video_analysis"
RESULT_SCHEMA_VERSION = "1.0"

METRICS_VERSION = "visual-metrics-1.0"

# ------------------------------------------------------------
# Ingest limits (see signals.py and app/services/visual_signals.py)
# ------------------------------------------------------------

MAX_FRAMES = 20000                    # ~33 min at 10 fps
MAX_COMPRESSED_BYTES = 2 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 12 * 1024 * 1024

# t may run this far past clock.duration_s before it is rejected
T_PAST_DURATION_TOLERANCE_S = 2.0

# clock.duration_s vs stored audio duration, checked at analysis
# time: max(DURATION_MISMATCH_ABS_S, DURATION_MISMATCH_FRACTION *
# audio_duration)
DURATION_MISMATCH_ABS_S = 3.0
DURATION_MISMATCH_FRACTION = 0.02

# Value ranges
ANGLE_RANGE = (-180.0, 180.0)
IRIS_RANGE = (-1.5, 1.5)
COORD_RANGE = (-0.1, 1.1)
UNIT_RANGE = (0.0, 1.0)              # face_scale, scores

# ------------------------------------------------------------
# Signal preparation
# ------------------------------------------------------------

GRID_HZ = 10
MAX_INTERP_GAP_S = 0.3
PRESENCE_NEAREST_S = 0.15
SMOOTH_MEDIAN_WINDOW = 3
SMOOTH_MEAN_WINDOW = 3
SPEECH_GAP_MERGE_S = 0.5             # when deriving speech from words

# ------------------------------------------------------------
# Coverage gates
# ------------------------------------------------------------

FACE_COVERAGE_MIN = 0.60
HANDS_COVERAGE_MIN = 0.50

# ------------------------------------------------------------
# Camera-facing cone (deltas from calibration baseline)
# ------------------------------------------------------------

FACING_YAW_DEG = 15.0
FACING_PITCH_DEG = 12.0
FACING_IRIS_X = 0.35
FACING_IRIS_Y = 0.35
FACING_BRIDGE_S = 0.3                # facing blips shorter than this don't end a gaze-away
GAZE_AWAY_MIN_S = 1.5

# ------------------------------------------------------------
# Head down
# ------------------------------------------------------------

HEAD_DOWN_PITCH_DEG = -15.0          # delta from baseline
HEAD_DOWN_MIN_S = 1.0

# ------------------------------------------------------------
# Hands (speed units: face_scale lengths per second, "fs/s")
# ------------------------------------------------------------

GESTURE_SPEED_FS = 2.0
GESTURE_MIN_S = 0.15
GESTURE_MERGE_GAP_S = 0.20
GESTURE_HAND_SHARE_MIN = 0.30        # a hand "took part" if above threshold this share of the run
STILL_SPEED_FS = 0.3
STILL_MIN_S = 3.0

# ------------------------------------------------------------
# Other events
# ------------------------------------------------------------

SECOND_PERSON_LOW_CONF_RATIO = 0.10
SECOND_PERSON_EVENT_MIN_S = 1.0
FACE_LOST_EVENT_MIN_S = 2.0
CLOCK_UNCERTAINTY_MAX_MS_FOR_MOMENTS = 300

# ------------------------------------------------------------
# Confidence
# ------------------------------------------------------------

CONF_HIGH_COVERAGE = 0.85
CONF_HIGH_FPS = 8.0
CONF_MEDIUM_COVERAGE = 0.60
CALIBRATION_STABILITY_MIN = 0.5

# ------------------------------------------------------------
# Result series
# ------------------------------------------------------------

SERIES_RESOLUTION_S = 1.0

# ------------------------------------------------------------
# Rounding
# ------------------------------------------------------------

ROUND_RATIO = 3
ROUND_RATE = 2
ROUND_SECONDS = 1
ROUND_DEGREES = 1
ROUND_AMPLITUDE = 2
