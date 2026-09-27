package com.debatecoach.app.visual

/**
 * web/features/video-analysis/config.ts, value for value. The golden
 * test VisualConfigParityTest compares every constant against the web
 * module's own export, so a change there fails here until ported.
 */
object VisualConfig {
    // Clock
    const val CLOCK_OFFSET_S = 0.0
    const val CLOCK_UNCERTAINTY_MS = 150

    // Capture
    const val CAPTURE_WIDTH_IDEAL = 1280
    const val CAPTURE_HEIGHT_IDEAL = 720
    const val CAPTURE_FRAME_RATE_IDEAL = 30
    const val SIGNAL_FRAME_WIDTH = 640
    const val SIGNAL_FRAME_HEIGHT = 360

    // Scheduler (adaptive rate)
    const val TARGET_FPS = 10
    const val MIN_INTERVAL_MS = 100.0
    const val P90_WINDOW = 30
    const val REDUCE_HANDS_P90_MS = 80.0
    const val DISABLE_HANDS_P90_MS = 160.0
    const val DISABLE_ALL_EFFECTIVE_FPS = 3
    const val DISABLE_ALL_SUSTAINED_S = 10.0

    // Setup screen: framing checks
    const val FACE_VISIBLE_WINDOW = 20
    const val FACE_VISIBLE_MIN_RATIO = 0.8
    const val DISTANCE_SCALE_MIN = 0.04
    const val DISTANCE_SCALE_MAX = 0.16
    const val LIGHTING_SAMPLE_MS = 500.0
    const val LIGHTING_DIM_LUMA = 50.0
    const val LIGHTING_BACKLIT_RATIO = 0.6
    const val HANDS_RAISED_WINDOW_S = 2.0
    const val HANDS_RAISED_MIN_RATIO = 0.6

    // Benchmark tiers
    const val BENCHMARK_DURATION_S = 3.0
    const val TIER_FULL_MIN_FPS = 9.0
    const val TIER_FULL_MAX_P90_MS = 80.0
    const val TIER_REDUCED_MIN_FPS = 6.0
    const val TIER_FACE_ONLY_MIN_FPS = 5.0

    // Calibration
    const val CALIBRATION_DURATION_S = 3.0
    const val CALIBRATION_MIN_SAMPLES = 15
    const val CALIBRATION_STABILITY_YAW_NORM_DEG = 10.0
    const val RIGHT_HAND_CHECK_WINDOW_S = 2.0
    const val RIGHT_HAND_CHECK_MIN_RATIO = 0.6
    const val HANDEDNESS_LABEL_INVERTED_DEFAULT = true

    // During recording
    const val FACE_MISSING_HINT_AFTER_S = 3.0

    // Upload / persistence
    val UPLOAD_RETRY_DELAYS_MS = listOf(1000L, 2000L, 4000L, 8000L)
    const val INDEXEDDB_MAX_AGE_DAYS = 7

    /** Every constant by its web name, for the parity test. */
    val all: Map<String, Any> = mapOf(
        "CLOCK_OFFSET_S" to CLOCK_OFFSET_S,
        "CLOCK_UNCERTAINTY_MS" to CLOCK_UNCERTAINTY_MS,
        "CAPTURE_WIDTH_IDEAL" to CAPTURE_WIDTH_IDEAL,
        "CAPTURE_HEIGHT_IDEAL" to CAPTURE_HEIGHT_IDEAL,
        "CAPTURE_FRAME_RATE_IDEAL" to CAPTURE_FRAME_RATE_IDEAL,
        "SIGNAL_FRAME_WIDTH" to SIGNAL_FRAME_WIDTH,
        "SIGNAL_FRAME_HEIGHT" to SIGNAL_FRAME_HEIGHT,
        "TARGET_FPS" to TARGET_FPS,
        "MIN_INTERVAL_MS" to MIN_INTERVAL_MS,
        "P90_WINDOW" to P90_WINDOW,
        "REDUCE_HANDS_P90_MS" to REDUCE_HANDS_P90_MS,
        "DISABLE_HANDS_P90_MS" to DISABLE_HANDS_P90_MS,
        "DISABLE_ALL_EFFECTIVE_FPS" to DISABLE_ALL_EFFECTIVE_FPS,
        "DISABLE_ALL_SUSTAINED_S" to DISABLE_ALL_SUSTAINED_S,
        "FACE_VISIBLE_WINDOW" to FACE_VISIBLE_WINDOW,
        "FACE_VISIBLE_MIN_RATIO" to FACE_VISIBLE_MIN_RATIO,
        "DISTANCE_SCALE_MIN" to DISTANCE_SCALE_MIN,
        "DISTANCE_SCALE_MAX" to DISTANCE_SCALE_MAX,
        "LIGHTING_SAMPLE_MS" to LIGHTING_SAMPLE_MS,
        "LIGHTING_DIM_LUMA" to LIGHTING_DIM_LUMA,
        "LIGHTING_BACKLIT_RATIO" to LIGHTING_BACKLIT_RATIO,
        "HANDS_RAISED_WINDOW_S" to HANDS_RAISED_WINDOW_S,
        "HANDS_RAISED_MIN_RATIO" to HANDS_RAISED_MIN_RATIO,
        "BENCHMARK_DURATION_S" to BENCHMARK_DURATION_S,
        "TIER_FULL_MIN_FPS" to TIER_FULL_MIN_FPS,
        "TIER_FULL_MAX_P90_MS" to TIER_FULL_MAX_P90_MS,
        "TIER_REDUCED_MIN_FPS" to TIER_REDUCED_MIN_FPS,
        "TIER_FACE_ONLY_MIN_FPS" to TIER_FACE_ONLY_MIN_FPS,
        "CALIBRATION_DURATION_S" to CALIBRATION_DURATION_S,
        "CALIBRATION_MIN_SAMPLES" to CALIBRATION_MIN_SAMPLES,
        "CALIBRATION_STABILITY_YAW_NORM_DEG" to CALIBRATION_STABILITY_YAW_NORM_DEG,
        "RIGHT_HAND_CHECK_WINDOW_S" to RIGHT_HAND_CHECK_WINDOW_S,
        "RIGHT_HAND_CHECK_MIN_RATIO" to RIGHT_HAND_CHECK_MIN_RATIO,
        "HANDEDNESS_LABEL_INVERTED_DEFAULT" to HANDEDNESS_LABEL_INVERTED_DEFAULT,
        "FACE_MISSING_HINT_AFTER_S" to FACE_MISSING_HINT_AFTER_S,
        "UPLOAD_RETRY_DELAYS_MS" to UPLOAD_RETRY_DELAYS_MS,
        "INDEXEDDB_MAX_AGE_DAYS" to INDEXEDDB_MAX_AGE_DAYS,
    )

    /** web/public/mediapipe/manifest.json's models; the app bundles the same files (app/build.gradle.kts). */
    val MODELS = listOf(
        ModelInfo("face_landmarker", "face_landmarker.task", "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"),
        ModelInfo("hand_landmarker", "hand_landmarker.task", "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"),
    )
}
