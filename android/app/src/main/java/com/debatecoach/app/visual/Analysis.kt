package com.debatecoach.app.visual

import com.debatecoach.app.visual.VisualConfig.DISABLE_ALL_EFFECTIVE_FPS
import com.debatecoach.app.visual.VisualConfig.DISABLE_ALL_SUSTAINED_S
import com.debatecoach.app.visual.VisualConfig.DISABLE_HANDS_P90_MS
import com.debatecoach.app.visual.VisualConfig.DISTANCE_SCALE_MAX
import com.debatecoach.app.visual.VisualConfig.DISTANCE_SCALE_MIN
import com.debatecoach.app.visual.VisualConfig.FACE_VISIBLE_MIN_RATIO
import com.debatecoach.app.visual.VisualConfig.HANDS_RAISED_MIN_RATIO
import com.debatecoach.app.visual.VisualConfig.LIGHTING_BACKLIT_RATIO
import com.debatecoach.app.visual.VisualConfig.LIGHTING_DIM_LUMA
import com.debatecoach.app.visual.VisualConfig.MIN_INTERVAL_MS
import com.debatecoach.app.visual.VisualConfig.P90_WINDOW
import com.debatecoach.app.visual.VisualConfig.REDUCE_HANDS_P90_MS

// ===============================================================
// stats.ts
// ===============================================================

object Stats {
    /** Nearest-rank 90th percentile; NaN when empty. */
    fun percentile90(values: List<Double>): Double {
        if (values.isEmpty()) return Double.NaN
        val sorted = JsMath.sortNumeric(values)
        val index = minOf(sorted.size - 1, kotlin.math.ceil(0.9 * sorted.size).toInt() - 1)
        return sorted[maxOf(0, index)]
    }

    fun median(values: List<Double>): Double {
        if (values.isEmpty()) return Double.NaN
        val sorted = JsMath.sortNumeric(values)
        val mid = sorted.size / 2
        return if (sorted.size % 2 == 0) (sorted[mid - 1] + sorted[mid]) / 2 else sorted[mid]
    }

    fun meanAbsoluteDeviation(values: List<Double>, center: Double): Double {
        if (values.isEmpty()) return Double.NaN
        var sum = 0.0
        for (v in values) sum += kotlin.math.abs(v - center)
        return sum / values.size
    }

    fun clamp(value: Double, lo: Double, hi: Double): Double = JsMath.min(hi, JsMath.max(lo, value))
}

// ===============================================================
// framing.ts
// ===============================================================

object Framing {
    fun ratioTrue(flags: List<Boolean>): Double {
        if (flags.isEmpty()) return 0.0
        return flags.count { it }.toDouble() / flags.size
    }

    fun faceVisiblePasses(recentFacePresent: List<Boolean>): Boolean = ratioTrue(recentFacePresent) >= FACE_VISIBLE_MIN_RATIO

    /** "ok" | "too_close" | "too_far" */
    fun classifyDistance(recentFaceScales: List<Double>): String {
        if (recentFaceScales.isEmpty()) return "too_far"
        val value = Stats.median(recentFaceScales)
        if (value > DISTANCE_SCALE_MAX) return "too_close"
        if (value < DISTANCE_SCALE_MIN) return "too_far"
        return "ok"
    }

    /** "ok" | "dim" | "backlit" */
    fun classifyLighting(meanLuma: Double, faceLuma: Double?): String {
        if (meanLuma < LIGHTING_DIM_LUMA) return "dim"
        if (faceLuma != null && faceLuma < meanLuma * LIGHTING_BACKLIT_RATIO) return "backlit"
        return "ok"
    }

    fun handsRaisedPasses(recentBothHandsPresent: List<Boolean>): Boolean =
        ratioTrue(recentBothHandsPresent) >= HANDS_RAISED_MIN_RATIO
}

// ===============================================================
// scheduler.ts
// ===============================================================

enum class HandsMode(val wire: String) { FULL("full"), REDUCED("reduced"), OFF("off") }

/**
 * Adaptive frame-rate scheduler. Pure: every timestamp is passed in, so
 * a recorded call sequence replays exactly (VisualSchedulerParityTest).
 * Downgrades only; never upgrades during a recording.
 */
class AdaptiveScheduler {
    private var handsMode = HandsMode.FULL
    private var tickCount = 0
    private var disabled = false

    private val latencyWindow = ArrayDeque<Double>()
    private val recentTickMs = ArrayDeque<Double>()
    private val recentHandsTickMs = ArrayDeque<Double>()
    private var lowFpsSinceMs: Double? = null
    private var lastTickMs: Double? = null

    fun shouldTick(nowMs: Double): Boolean {
        if (disabled) return false
        val last = lastTickMs ?: return true
        return nowMs - last >= MIN_INTERVAL_MS
    }

    fun planHands(): Boolean = when (handsMode) {
        HandsMode.OFF -> false
        HandsMode.FULL -> true
        HandsMode.REDUCED -> tickCount % 2 == 0
    }

    val currentHandsMode: HandsMode get() = handsMode
    val isDisabled: Boolean get() = disabled
    val currentEffectiveFps: Int get() = recentTickMs.size

    fun recordTick(nowMs: Double, inferMs: Double, handsRan: Boolean): Degradation? {
        lastTickMs = nowMs
        tickCount += 1

        recentTickMs.addLast(nowMs)
        while (recentTickMs.isNotEmpty() && nowMs - recentTickMs.first() > 1000) recentTickMs.removeFirst()
        val effectiveFps = recentTickMs.size

        if (handsRan) recentHandsTickMs.addLast(nowMs)
        while (recentHandsTickMs.isNotEmpty() && nowMs - recentHandsTickMs.first() > 1000) recentHandsTickMs.removeFirst()
        val handsFps = recentHandsTickMs.size

        latencyWindow.addLast(inferMs)
        if (latencyWindow.size > P90_WINDOW) latencyWindow.removeFirst()

        checkLatency(nowMs, effectiveFps, handsFps)?.let { return it }
        return checkSustainedLowFps(nowMs, effectiveFps, handsFps)
    }

    private fun checkLatency(nowMs: Double, effectiveFps: Int, handsFps: Int): Degradation? {
        if (disabled || handsMode == HandsMode.OFF || latencyWindow.size < P90_WINDOW) return null
        val p90 = Stats.percentile90(latencyWindow.toList())
        if (p90 > DISABLE_HANDS_P90_MS) {
            handsMode = HandsMode.OFF
            return Degradation(nowMs / 1000, effectiveFps, 0, "p90_latency")
        }
        if (p90 > REDUCE_HANDS_P90_MS && handsMode == HandsMode.FULL) {
            handsMode = HandsMode.REDUCED
            return Degradation(nowMs / 1000, effectiveFps, handsFps, "p90_latency")
        }
        return null
    }

    private fun checkSustainedLowFps(nowMs: Double, effectiveFps: Int, handsFps: Int): Degradation? {
        if (disabled) return null
        if (effectiveFps >= DISABLE_ALL_EFFECTIVE_FPS) {
            lowFpsSinceMs = null
            return null
        }
        val since = lowFpsSinceMs
        if (since == null) {
            lowFpsSinceMs = nowMs
            return null
        }
        if (nowMs - since >= DISABLE_ALL_SUSTAINED_S * 1000) {
            disabled = true
            return Degradation(nowMs / 1000, effectiveFps, handsFps, "thermal_suspected")
        }
        return null
    }
}

// ===============================================================
// track.ts
// ===============================================================

/**
 * Accumulates samples into a VisualSignalTrack. Rounding per column
 * (angles 0.1, iris 0.01, scale/coords 0.001, t 0.001, infer_ms 1)
 * with JavaScript's Math.round, so the numbers match the web's.
 */
class TrackBuilder {
    private val t = ArrayList<Double>()
    private val columns = List(FRAME_COLUMNS.size) { ArrayList<Double?>() }
    private val gapsList = ArrayList<Gap>()
    private val degradationsList = ArrayList<Degradation>()
    private var openGap: Pair<Double, String>? = null
    private var lastT: Double? = null

    val frameCount: Int get() = t.size
    val lastAppendedT: Double? get() = lastT
    val hasOpenGap: Boolean get() = openGap != null

    /** Dropped (false) if t < 0 or not strictly after the previous t. */
    fun appendSample(time: Double, sample: FrameSample): Boolean {
        if (time < 0) return false
        val last = lastT
        if (last != null && time <= last) return false

        val values = sample.columns()
        t.add(round(time, 3)!!)
        for (i in FRAME_COLUMNS.indices) {
            val decimals = ROUNDING[i]
            columns[i].add(if (decimals == null) values[i] else round(values[i], decimals))
        }
        lastT = time
        return true
    }

    fun appendEmpty(time: Double): Boolean = appendSample(time, FrameSample.EMPTY)

    fun openGapAt(start: Double, reason: String) {
        if (openGap != null) return
        openGap = start to reason
    }

    fun closeGapAt(end: Double) {
        val gap = openGap ?: return
        gapsList.add(Gap(gap.first, end, gap.second))
        openGap = null
    }

    fun pushDegradation(degradation: Degradation) {
        degradationsList.add(degradation)
    }

    fun build(
        sessionId: String,
        source: Source,
        capture: Capture,
        clockUncertaintyMs: Int,
        durationS: Double,
        calibration: Calibration,
        context: TrackContext,
        setupCheck: SetupCheck,
    ): VisualSignalTrack {
        if (openGap != null) closeGapAt(durationS)
        return VisualSignalTrack(
            sessionId = sessionId,
            source = source,
            capture = capture,
            clock = Clock("audio_recording_start", "mediarecorder_start_event", clockUncertaintyMs, durationS),
            calibration = calibration,
            context = context,
            setupCheck = setupCheck,
            frames = Frames(t.toList(), columns.map { it.toList() }),
            gaps = gapsList.toList(),
            degradations = degradationsList.toList(),
        )
    }

    companion object {
        /** Decimals per FRAME_COLUMNS entry; null = not rounded (integer columns). */
        private val ROUNDING: List<Int?> = listOf(
            null, 1, 1, 1, 2, 2, 3, 3, 3, null, 2, 3, 3, null, 2, 3, 3, 0,
        )

        fun round(value: Double?, decimals: Int): Double? {
            if (value == null || value.isNaN()) return null
            val factor = Math.pow(10.0, decimals.toDouble())
            return JsMath.round(value * factor) / factor
        }
    }
}
