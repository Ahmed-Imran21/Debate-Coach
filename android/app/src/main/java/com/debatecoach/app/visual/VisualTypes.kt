package com.debatecoach.app.visual

/*
 * web/features/video-analysis/types.ts: the VisualSignalTrack
 * (debatecoach.visual_signals, version 1.0). Field names, nesting and
 * key order match the web's objects exactly; TrackJson writes them in
 * that order so the serialized track is byte-identical to the web's
 * JSON.stringify() output (VisualTrackParityTest).
 */

const val SCHEMA = "debatecoach.visual_signals"
const val SCHEMA_VERSION = "1.0"

data class RuntimeInfo(val name: String, val version: String, val delegate: String)

data class ModelInfo(val task: String, val modelId: String, val sha256: String)

data class Source(
    val platform: String,
    val clientVersion: String,
    val userAgentFamily: String,
    val runtime: RuntimeInfo,
    val models: List<ModelInfo>,
    val deviceTier: String,
    val benchmarkFps: Double,
)

data class Capture(
    val frameWidth: Int,
    val frameHeight: Int,
    val inputMirrored: Boolean,
    val handednessConvention: String,
    val targetFps: Int,
)

data class Clock(
    val t0Reference: String,
    val syncMethod: String,
    val uncertaintyMs: Int,
    val durationS: Double,
)

data class CalibrationBaseline(val headYaw: Double, val headPitch: Double, val irisX: Double, val irisY: Double)

data class Calibration(
    val performed: Boolean,
    val baseline: CalibrationBaseline?,
    val samples: Int,
    val stability: Double,
    val rightHandCheck: String,
)

data class TrackContext(val setting: String, val usesNotes: Boolean)

data class SetupCheck(
    val faceVisible: Boolean,
    val handsVisibleWhenRaised: Boolean,
    val lighting: String,
    val distance: String,
)

data class Gap(val start: Double, val end: Double, val reason: String)

data class Degradation(val t: Double, val faceFps: Int, val handsFps: Int, val reason: String)

/** Column order of frames (types.ts FRAME_COLUMNS). */
val FRAME_COLUMNS = listOf(
    "face_count", "head_yaw", "head_pitch", "head_roll", "iris_x", "iris_y",
    "face_scale", "face_cx", "face_cy",
    "lh_present", "lh_score", "lh_cx", "lh_cy",
    "rh_present", "rh_score", "rh_cx", "rh_cy",
    "infer_ms",
)

/** One tick's measurement, in FRAME_COLUMNS order. */
data class FrameSample(
    val faceCount: Double? = null,
    val headYaw: Double? = null,
    val headPitch: Double? = null,
    val headRoll: Double? = null,
    val irisX: Double? = null,
    val irisY: Double? = null,
    val faceScale: Double? = null,
    val faceCx: Double? = null,
    val faceCy: Double? = null,
    val lhPresent: Double? = null,
    val lhScore: Double? = null,
    val lhCx: Double? = null,
    val lhCy: Double? = null,
    val rhPresent: Double? = null,
    val rhScore: Double? = null,
    val rhCx: Double? = null,
    val rhCy: Double? = null,
    val inferMs: Double? = null,
) {
    fun columns(): List<Double?> = listOf(
        faceCount, headYaw, headPitch, headRoll, irisX, irisY, faceScale, faceCx, faceCy,
        lhPresent, lhScore, lhCx, lhCy, rhPresent, rhScore, rhCx, rhCy, inferMs,
    )

    companion object {
        val EMPTY = FrameSample()

        fun fromColumns(values: List<Double?>): FrameSample {
            require(values.size == FRAME_COLUMNS.size)
            return FrameSample(
                values[0], values[1], values[2], values[3], values[4], values[5], values[6], values[7], values[8],
                values[9], values[10], values[11], values[12], values[13], values[14], values[15], values[16], values[17],
            )
        }
    }
}

/** Columnar frames: `t` plus one list per FRAME_COLUMNS entry. */
data class Frames(val t: List<Double>, val columns: List<List<Double?>>)

data class VisualSignalTrack(
    val sessionId: String,
    val source: Source,
    val capture: Capture,
    val clock: Clock,
    val calibration: Calibration,
    val context: TrackContext,
    val setupCheck: SetupCheck,
    val frames: Frames,
    val gaps: List<Gap>,
    val degradations: List<Degradation>,
) {
    val frameCount: Int get() = frames.t.size
}
