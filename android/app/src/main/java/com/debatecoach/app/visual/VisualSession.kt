package com.debatecoach.app.visual

import com.debatecoach.app.visual.VisualConfig.CALIBRATION_MIN_SAMPLES
import com.debatecoach.app.visual.VisualConfig.CALIBRATION_STABILITY_YAW_NORM_DEG
import com.debatecoach.app.visual.VisualConfig.CLOCK_OFFSET_S
import com.debatecoach.app.visual.VisualConfig.FACE_MISSING_HINT_AFTER_S
import com.debatecoach.app.visual.VisualConfig.FACE_VISIBLE_WINDOW
import com.debatecoach.app.visual.VisualConfig.HANDEDNESS_LABEL_INVERTED_DEFAULT
import com.debatecoach.app.visual.VisualConfig.HANDS_RAISED_WINDOW_S
import com.debatecoach.app.visual.VisualConfig.LIGHTING_SAMPLE_MS
import com.debatecoach.app.visual.VisualConfig.RIGHT_HAND_CHECK_MIN_RATIO
import com.debatecoach.app.visual.VisualConfig.RIGHT_HAND_CHECK_WINDOW_S
import com.debatecoach.app.visual.VisualConfig.SIGNAL_FRAME_HEIGHT
import com.debatecoach.app.visual.VisualConfig.SIGNAL_FRAME_WIDTH
import com.debatecoach.app.visual.VisualConfig.TIER_FACE_ONLY_MIN_FPS
import com.debatecoach.app.visual.VisualConfig.TIER_FULL_MAX_P90_MS
import com.debatecoach.app.visual.VisualConfig.TIER_FULL_MIN_FPS
import com.debatecoach.app.visual.VisualConfig.TIER_REDUCED_MIN_FPS

/*
 * The per-frame glue of web/features/video-analysis/useVisualCapture.ts
 * (processTick, runBenchmark, runGazeCalibration, runRightHandCheck,
 * sampleLighting, endRecording), without the camera: it takes each
 * frame's detections and timestamps and keeps exactly the state the
 * hook keeps. VisualCaptureController (Android) feeds it frames from
 * CameraX + MediaPipe; the golden tests feed it the web's inputs.
 */

/** One detected face: its landmarks and flattened 4x4 transformation matrix. */
class DetectedFace(val landmarks: List<Landmark?>, val transformMatrix: List<Double>?)

class DetectedHand(val landmarks: List<Landmark?>, val handednessLabel: String, val handednessScore: Double)

class FrameResult(val faces: List<DetectedFace>, val hands: List<DetectedHand>)

data class HandReading(val cx: Double, val cy: Double, val score: Double)

/** processTick()'s derived numbers for one frame. */
data class FrameDerivation(
    val sample: FrameSample,
    val headPose: HeadPose?,
    val iris: IrisOffset?,
    val faceScale: Double?,
    val faceCenter: Point2?,
    val lh: HandReading?,
    val rh: HandReading?,
)

object FrameDerivations {
    /**
     * processTick()'s face and hand derivation, verbatim. `inferMs` is
     * the time since the frame was captured; `runHands` is whether the
     * hand model ran on this frame (presence columns are null if not).
     */
    fun derive(result: FrameResult, baseline: Point2?, handednessInverted: Boolean, runHands: Boolean, inferMs: Double): FrameDerivation {
        val w = SIGNAL_FRAME_WIDTH.toDouble()
        val h = SIGNAL_FRAME_HEIGHT.toDouble()

        // --- Face ---
        val candidates = result.faces.map { f ->
            VisionMath.FaceCandidate(
                center = VisionMath.computeFaceCenter(f.landmarks) ?: Point2(0.5, 0.5),
                scale = VisionMath.computeFaceScale(f.landmarks, w) ?: 0.0,
            )
        }
        val primaryIndex = if (result.faces.isNotEmpty()) VisionMath.selectPrimaryFace(candidates, baseline) else -1
        val primary = if (primaryIndex >= 0) result.faces[primaryIndex] else null

        val headPose = primary?.transformMatrix?.let { VisionMath.headPoseFromMatrix(it) }
        val iris = primary?.let { VisionMath.computeIrisOffset(it.landmarks, w, h) }
        val faceScale = primary?.let { VisionMath.computeFaceScale(it.landmarks, w) }
        val faceCenter = primary?.let { VisionMath.computeFaceCenter(it.landmarks) }

        // --- Hands ---
        var lh: HandReading? = null
        var rh: HandReading? = null
        if (result.hands.size == 2) {
            val centroids = result.hands.map { hand ->
                val c = VisionMath.computePalmCentroid(hand.landmarks) ?: Point2(0.5, 0.5)
                HandReading(c.cx, c.cy, hand.handednessScore)
            }
            val (rhIndex, lhIndex) = VisionMath.assignTwoHandSides(centroids[0].cx, centroids[1].cx)
            rh = centroids[rhIndex]
            lh = centroids[lhIndex]
        } else if (result.hands.size == 1) {
            val hand = result.hands[0]
            val centroid = VisionMath.computePalmCentroid(hand.landmarks)
            if (centroid != null) {
                val value = HandReading(centroid.cx, centroid.cy, hand.handednessScore)
                if (VisionMath.resolveHandSideFromLabel(hand.handednessLabel, handednessInverted) == HandSide.RH) rh = value else lh = value
            }
        }

        val sample = FrameSample(
            faceCount = result.faces.size.toDouble(),
            headYaw = headPose?.yaw,
            headPitch = headPose?.pitch,
            headRoll = headPose?.roll,
            irisX = iris?.x,
            irisY = iris?.y,
            faceScale = faceScale,
            faceCx = faceCenter?.cx,
            faceCy = faceCenter?.cy,
            lhPresent = if (runHands) (if (lh != null) 1.0 else 0.0) else null,
            lhScore = lh?.score,
            lhCx = lh?.cx,
            lhCy = lh?.cy,
            rhPresent = if (runHands) (if (rh != null) 1.0 else 0.0) else null,
            rhScore = rh?.score,
            rhCx = rh?.cx,
            rhCy = rh?.cy,
            inferMs = inferMs,
        )
        return FrameDerivation(sample, headPose, iris, faceScale, faceCenter, lh, rh)
    }
}

/** runBenchmark()'s tier decision. */
data class BenchmarkResult(val tier: String, val fps: Double, val benchmarkFps: Double) {
    val tooSlow: Boolean get() = tier == "too_slow"
}

object Benchmark {
    fun decide(tickCount: Int, latencies: List<Double>): BenchmarkResult {
        val fps = tickCount / VisualConfig.BENCHMARK_DURATION_S
        val p90 = Stats.percentile90(latencies)
        val p90Ok = p90.isNaN() || p90 <= TIER_FULL_MAX_P90_MS
        val tier = when {
            fps >= TIER_FULL_MIN_FPS && p90Ok -> "full"
            fps >= TIER_REDUCED_MIN_FPS -> "reduced"
            fps >= TIER_FACE_ONLY_MIN_FPS -> "face_only"
            else -> "too_slow"
        }
        return BenchmarkResult(tier, fps, JsMath.round(fps * 10) / 10)
    }
}

/** runGazeCalibration()'s math. */
data class GazeCalibration(val performed: Boolean, val baseline: CalibrationBaseline?, val samples: Int, val stability: Double, val faceCenter: Point2?)

object GazeCalibrationMath {
    fun compute(yaw: List<Double>, pitch: List<Double>, irisX: List<Double>, irisY: List<Double>, cx: List<Double>, cy: List<Double>): GazeCalibration {
        if (yaw.size < CALIBRATION_MIN_SAMPLES) return GazeCalibration(false, null, yaw.size, 0.0, null)
        val baseline = CalibrationBaseline(
            headYaw = Stats.median(yaw),
            headPitch = Stats.median(pitch),
            irisX = Stats.median(irisX),
            irisY = Stats.median(irisY),
        )
        val mad = Stats.meanAbsoluteDeviation(yaw, baseline.headYaw)
        val stability = 1 - Stats.clamp(mad / CALIBRATION_STABILITY_YAW_NORM_DEG, 0.0, 1.0)
        val center = if (cx.isNotEmpty()) Point2(Stats.median(cx), Stats.median(cy)) else null
        return GazeCalibration(true, baseline, yaw.size, stability, center)
    }

    fun rightHandCheck(flags: List<Boolean>): String =
        if (Framing.ratioTrue(flags) >= RIGHT_HAND_CHECK_MIN_RATIO) "passed" else "failed"
}

/** sampleLighting(): mean luma of a small RGBA frame and of its centered face box. */
object Lighting {
    data class Luma(val meanLuma: Double, val faceLuma: Double?)

    /** [rgba] holds width*height*4 bytes (0-255), row-major, like canvas getImageData. */
    fun measure(width: Int, height: Int, rgba: IntArray): Luma {
        var sum = 0.0
        var faceSum = 0.0
        var faceN = 0
        val fx0 = kotlin.math.floor(width * 0.35).toInt()
        val fx1 = kotlin.math.ceil(width * 0.65).toInt()
        val fy0 = kotlin.math.floor(height * 0.2).toInt()
        val fy1 = kotlin.math.ceil(height * 0.7).toInt()
        for (y in 0 until height) {
            for (x in 0 until width) {
                val i = (y * width + x) * 4
                val luma = 0.299 * rgba[i] + 0.587 * rgba[i + 1] + 0.114 * rgba[i + 2]
                sum += luma
                if (x in fx0 until fx1 && y in fy0 until fy1) {
                    faceSum += luma
                    faceN += 1
                }
            }
        }
        return Luma(sum / (width * height), if (faceN > 0) faceSum / faceN else null)
    }
}

// ---------------------------------------------------------------
// The stateful part: one capture session's refs and modes
// ---------------------------------------------------------------

data class FramingChecks(
    val faceVisible: Boolean = false,
    val distance: String = "too_far",
    val lighting: String = "ok",
    val handsRaised: Boolean = false,
)

data class LiveReading(
    val faceCount: Int,
    val headPose: HeadPose?,
    val iris: IrisOffset?,
    val faceScale: Double?,
    val lhPresent: Boolean,
    val rhPresent: Boolean,
    val effectiveFps: Int,
    val handsMode: HandsMode,
    val inferMs: Double,
)

enum class CaptureMode { IDLE, BENCHMARK, CALIBRATION_GAZE, CALIBRATION_HAND, RECORDING }

/**
 * useVisualCapture's refs, and processTick's state updates, for one
 * session. All times are milliseconds on one clock (the caller uses
 * elapsedRealtime for camera frames and the recorder's start alike).
 * Thread-safe: frames arrive on the camera thread, commands on main.
 */
class VisualSession {
    private val lock = Any()

    val scheduler = AdaptiveScheduler()
    private val track = TrackBuilder()
    private var mode = CaptureMode.IDLE
    private var t0Ms: Double? = null
    private var handednessInverted = HANDEDNESS_LABEL_INVERTED_DEFAULT
    private var lastMpTimestamp = -1.0

    private val faceVisibleWindow = ArrayList<Boolean>()
    private val faceScaleWindow = ArrayList<Double>()
    private val handsRaisedWindow = ArrayList<Boolean>()
    private val rightHandWindow = ArrayList<Boolean>()
    private val benchmarkTicks = ArrayList<Double>()
    private val benchmarkLatencies = ArrayList<Double>()
    private val gazeYaw = ArrayList<Double>()
    private val gazePitch = ArrayList<Double>()
    private val gazeIrisX = ArrayList<Double>()
    private val gazeIrisY = ArrayList<Double>()
    private val gazeCx = ArrayList<Double>()
    private val gazeCy = ArrayList<Double>()
    private var baselineFaceCenter: Point2? = null
    private var faceMissingSinceMs: Double? = null
    private var lastLightingSampleMs = 0.0

    var framing = FramingChecks()
        private set
    var live: LiveReading? = null
        private set
    var faceMissingSeconds = 0.0
        private set

    val currentMode: CaptureMode get() = synchronized(lock) { mode }
    val hasOpenGap: Boolean get() = synchronized(lock) { track.hasOpenGap }

    /** The frame loop's gate: null to skip this frame, else whether to run the hand model. */
    fun beginTick(frameTimeMs: Double): Boolean? = synchronized(lock) {
        if (!scheduler.shouldTick(frameTimeMs)) return null
        if (frameTimeMs <= lastMpTimestamp) return null // must be strictly increasing
        lastMpTimestamp = frameTimeMs
        // The benchmark measures the full face+hands cost, whatever the scheduler would do.
        if (mode == CaptureMode.BENCHMARK) true else scheduler.planHands()
    }

    /** Whether a lighting sample is due for this frame (every LIGHTING_SAMPLE_MS). */
    fun lightingDue(frameTimeMs: Double): Boolean = synchronized(lock) { frameTimeMs - lastLightingSampleMs >= LIGHTING_SAMPLE_MS }

    /** processTick() after detection. [luma] is given when [lightingDue] said so. */
    fun completeTick(frameTimeMs: Double, runHands: Boolean, result: FrameResult, inferMs: Double, luma: Lighting.Luma?) {
        synchronized(lock) {
            val degradation = scheduler.recordTick(frameTimeMs, inferMs, runHands)
            if (degradation != null && mode == CaptureMode.RECORDING) track.pushDegradation(degradation)

            val d = FrameDerivations.derive(result, baselineFaceCenter, handednessInverted, runHands, inferMs)

            pushWindow(faceVisibleWindow, result.faces.isNotEmpty(), FACE_VISIBLE_WINDOW)
            d.faceScale?.let { pushWindow(faceScaleWindow, it, FACE_VISIBLE_WINDOW) }
            pushWindow(handsRaisedWindow, d.lh != null && d.rh != null, JsMath.round(HANDS_RAISED_WINDOW_S * 10).toInt())

            var lighting = framing.lighting
            if (luma != null && frameTimeMs - lastLightingSampleMs >= LIGHTING_SAMPLE_MS) {
                lastLightingSampleMs = frameTimeMs
                lighting = Framing.classifyLighting(luma.meanLuma, luma.faceLuma)
            }
            framing = FramingChecks(
                faceVisible = Framing.faceVisiblePasses(faceVisibleWindow),
                distance = Framing.classifyDistance(faceScaleWindow),
                lighting = lighting,
                handsRaised = Framing.handsRaisedPasses(handsRaisedWindow),
            )

            if (result.faces.isEmpty()) {
                val since = faceMissingSinceMs ?: frameTimeMs.also { faceMissingSinceMs = it }
                val missingS = (frameTimeMs - since) / 1000
                faceMissingSeconds = if (missingS >= FACE_MISSING_HINT_AFTER_S) missingS else 0.0
            } else {
                faceMissingSinceMs = null
                faceMissingSeconds = 0.0
            }

            when (mode) {
                CaptureMode.BENCHMARK -> {
                    pushWindow(benchmarkTicks, frameTimeMs, 10_000)
                    pushWindow(benchmarkLatencies, inferMs, 10_000)
                }
                CaptureMode.CALIBRATION_GAZE -> if (d.headPose != null && d.iris != null) {
                    gazeYaw.add(d.headPose.yaw)
                    gazePitch.add(d.headPose.pitch)
                    gazeIrisX.add(d.iris.x)
                    gazeIrisY.add(d.iris.y)
                    d.faceCenter?.let {
                        gazeCx.add(it.cx)
                        gazeCy.add(it.cy)
                    }
                }
                CaptureMode.CALIBRATION_HAND ->
                    pushWindow(rightHandWindow, d.rh != null, JsMath.round(RIGHT_HAND_CHECK_WINDOW_S * 10).toInt())
                CaptureMode.RECORDING -> {
                    val t0 = t0Ms
                    if (t0 != null) {
                        val tSeconds = (frameTimeMs - t0) / 1000 + CLOCK_OFFSET_S
                        track.appendSample(tSeconds, d.sample)
                        if (scheduler.isDisabled && !track.hasOpenGap) track.openGapAt(tSeconds, "perf_disabled")
                    }
                }
                CaptureMode.IDLE -> Unit
            }

            live = LiveReading(
                faceCount = result.faces.size,
                headPose = d.headPose,
                iris = d.iris,
                faceScale = d.faceScale,
                lhPresent = d.lh != null,
                rhPresent = d.rh != null,
                effectiveFps = scheduler.currentEffectiveFps,
                handsMode = scheduler.currentHandsMode,
                inferMs = inferMs,
            )
        }
    }

    // --- Benchmark and calibration: the caller waits the duration between start and finish ---

    fun startBenchmark() = synchronized(lock) {
        benchmarkTicks.clear()
        benchmarkLatencies.clear()
        mode = CaptureMode.BENCHMARK
    }

    fun finishBenchmark(): BenchmarkResult = synchronized(lock) {
        mode = CaptureMode.IDLE
        Benchmark.decide(benchmarkTicks.size, benchmarkLatencies.toList())
    }

    fun startGazeCalibration() = synchronized(lock) {
        listOf(gazeYaw, gazePitch, gazeIrisX, gazeIrisY, gazeCx, gazeCy).forEach { it.clear() }
        mode = CaptureMode.CALIBRATION_GAZE
    }

    fun finishGazeCalibration(): GazeCalibration = synchronized(lock) {
        mode = CaptureMode.IDLE
        val result = GazeCalibrationMath.compute(gazeYaw, gazePitch, gazeIrisX, gazeIrisY, gazeCx, gazeCy)
        if (result.performed) result.faceCenter?.let { baselineFaceCenter = it }
        result
    }

    fun startRightHandCheck() = synchronized(lock) {
        rightHandWindow.clear()
        mode = CaptureMode.CALIBRATION_HAND
    }

    /** Result of one right-hand window; the caller flips the mapping and retries once on "failed" (§4.8). */
    fun finishRightHandCheck(): String = synchronized(lock) {
        mode = CaptureMode.IDLE
        GazeCalibrationMath.rightHandCheck(rightHandWindow.toList())
    }

    fun flipHandedness() = synchronized(lock) { handednessInverted = !handednessInverted }

    fun resetHandedness() = synchronized(lock) { handednessInverted = HANDEDNESS_LABEL_INVERTED_DEFAULT }

    // --- Recording ---

    /** The recorder's start moment (web: MediaRecorder onstart). */
    fun beginRecording(t0: Double) = synchronized(lock) {
        t0Ms = t0
        mode = CaptureMode.RECORDING
    }

    /** A pause in frames that aren't the scheduler's doing (web: tab hidden; here the camera stalling). */
    fun openGap(nowMs: Double, reason: String) {
        synchronized(lock) {
            val t0 = t0Ms ?: return
            if (mode != CaptureMode.RECORDING || track.hasOpenGap) return
            track.openGapAt(maxOf(0.0, (nowMs - t0) / 1000 + CLOCK_OFFSET_S), reason)
        }
    }

    fun closeGap(nowMs: Double) {
        synchronized(lock) {
            val t0 = t0Ms ?: return
            track.closeGapAt(maxOf(0.0, (nowMs - t0) / 1000 + CLOCK_OFFSET_S))
        }
    }

    fun endRecording(
        durationS: Double,
        source: Source,
        calibration: Calibration,
        context: TrackContext,
        setupFraming: FramingChecks,
    ): VisualSignalTrack? = synchronized(lock) {
        mode = CaptureMode.IDLE
        val built = track.build(
            sessionId = "",
            source = source,
            capture = Capture(SIGNAL_FRAME_WIDTH, SIGNAL_FRAME_HEIGHT, false, "anatomical", 10),
            clockUncertaintyMs = VisualConfig.CLOCK_UNCERTAINTY_MS,
            durationS = durationS,
            calibration = calibration,
            context = context,
            setupCheck = SetupCheck(setupFraming.faceVisible, setupFraming.handsRaised, setupFraming.lighting, setupFraming.distance),
        )
        if (built.frameCount == 0) null else built
    }

    private fun <T> pushWindow(list: MutableList<T>, value: T, max: Int) {
        list.add(value)
        if (list.size > max) list.removeAt(0)
    }
}
