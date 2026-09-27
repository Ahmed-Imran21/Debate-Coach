package com.debatecoach.app.visual

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Matrix
import android.hardware.camera2.CameraCharacteristics
import android.os.SystemClock
import android.util.Size
import androidx.camera.camera2.interop.Camera2CameraInfo
import androidx.camera.camera2.interop.ExperimentalCamera2Interop
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.lifecycle.awaitInstance
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import com.debatecoach.app.BuildConfig
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Why visual analysis isn't available (the backend's VideoFinalize reasons). */
enum class UnavailableReason(val wire: String) {
    CAMERA_DENIED("camera_denied"),
    UNSUPPORTED("unsupported"),
    MODEL_LOAD_FAILED("model_load_failed"),
    DEVICE_TOO_SLOW("device_too_slow"),
    USER_OPTED_OUT("user_opted_out"),
    UPLOAD_FAILED("upload_failed"),
    FACE_NOT_FOUND("face_not_found"),
}

/** Milliseconds on the clock every visual timestamp uses (elapsedRealtime). */
fun nowMs(): Double = SystemClock.elapsedRealtimeNanos() / 1_000_000.0

/**
 * useVisualCapture's camera side: CameraX frames -> MediaPipe ->
 * VisualSession. Holds no logic of its own beyond feeding frames;
 * everything the track contains is decided by the ported code.
 */
class VisualCaptureController(private val context: Context, private val scope: CoroutineScope) {
    val session = VisualSession()

    private var extractor: MediaPipeExtractor? = null
    private var provider: ProcessCameraProvider? = null
    private var analysisExecutor: ExecutorService? = null
    private var preview: Preview? = null
    private var monitorJob: Job? = null

    private var timestampOffsetNs = 0L
    @Volatile private var lastFrameAtMs: Double? = null
    @Volatile private var active = false

    private val _framing = MutableStateFlow(FramingChecks())
    val framing: StateFlow<FramingChecks> = _framing.asStateFlow()

    private val _live = MutableStateFlow<LiveReading?>(null)
    val live: StateFlow<LiveReading?> = _live.asStateFlow()

    private val _faceMissingSeconds = MutableStateFlow(0.0)
    val faceMissingSeconds: StateFlow<Double> = _faceMissingSeconds.asStateFlow()

    var source: Source? = null
        private set

    /**
     * Loads the models and starts the camera (web: acquireAndStartSetup).
     * Returns null on success, else why visual analysis can't run.
     */
    suspend fun start(owner: LifecycleOwner): UnavailableReason? {
        val loaded = withContext(Dispatchers.Default) { runCatching { MediaPipeExtractor.create(context) } }
        val mp = loaded.getOrElse { return UnavailableReason.MODEL_LOAD_FAILED }
        extractor = mp
        source = Source(
            platform = "android",
            clientVersion = "android-${BuildConfig.VERSION_NAME}",
            userAgentFamily = "other",
            runtime = RuntimeInfo(MediaPipeExtractor.RUNTIME_NAME, MediaPipeExtractor.runtimeVersion, mp.delegate),
            models = VisualConfig.MODELS,
            deviceTier = "full",
            benchmarkFps = 0.0,
        )

        val cameraProvider = try {
            ProcessCameraProvider.awaitInstance(context)
        } catch (_: Exception) {
            stop()
            return UnavailableReason.UNSUPPORTED
        }
        provider = cameraProvider
        if (!cameraProvider.hasCamera(CameraSelector.DEFAULT_FRONT_CAMERA)) {
            stop()
            return UnavailableReason.UNSUPPORTED
        }

        val selector = ResolutionSelector.Builder()
            .setAspectRatioStrategy(AspectRatioStrategy.RATIO_16_9_FALLBACK_AUTO_STRATEGY)
            .setResolutionStrategy(
                ResolutionStrategy(
                    Size(VisualConfig.CAPTURE_WIDTH_IDEAL, VisualConfig.CAPTURE_HEIGHT_IDEAL),
                    ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER,
                ),
            )
            .build()
        val previewUseCase = Preview.Builder().setResolutionSelector(selector).build()
        val analysis = ImageAnalysis.Builder()
            .setResolutionSelector(selector)
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
            .build()
        val executor = Executors.newSingleThreadExecutor()
        analysisExecutor = executor
        analysis.setAnalyzer(executor) { image -> analyze(image) }

        try {
            cameraProvider.unbindAll()
            val camera = cameraProvider.bindToLifecycle(owner, CameraSelector.DEFAULT_FRONT_CAMERA, previewUseCase, analysis)
            timestampOffsetNs = timestampOffset(camera.cameraInfo)
        } catch (_: Exception) {
            stop()
            return UnavailableReason.UNSUPPORTED
        }
        preview = previewUseCase
        active = true
        startMonitor()
        return null
    }

    /** Where the camera preview draws (the one visible PreviewView), or null while hidden. */
    fun setSurfaceProvider(surfaceProvider: Preview.SurfaceProvider?) {
        preview?.surfaceProvider = surfaceProvider
    }

    /**
     * Frame timestamps come from the sensor clock: elapsedRealtime when
     * the camera reports a REALTIME source, else the monotonic clock,
     * which is converted so frames and the recorder's start share one.
     */
    @SuppressLint("UnsafeOptInUsageError")
    @OptIn(ExperimentalCamera2Interop::class)
    private fun timestampOffset(info: androidx.camera.core.CameraInfo): Long = try {
        val sourceType = Camera2CameraInfo.from(info).getCameraCharacteristic(CameraCharacteristics.SENSOR_INFO_TIMESTAMP_SOURCE)
        if (sourceType == CameraCharacteristics.SENSOR_INFO_TIMESTAMP_SOURCE_REALTIME) 0L
        else SystemClock.elapsedRealtimeNanos() - System.nanoTime()
    } catch (_: Exception) {
        SystemClock.elapsedRealtimeNanos() - System.nanoTime()
    }

    private fun analyze(image: ImageProxy) {
        try {
            val mp = extractor ?: return
            if (!active) return
            val frameTimeMs = (image.imageInfo.timestamp + timestampOffsetNs) / 1_000_000.0
            lastFrameAtMs = frameTimeMs
            val runHands = session.beginTick(frameTimeMs) ?: return

            val upright = uprightBitmap(image)
            val luma = if (session.lightingDue(frameTimeMs)) sampleLighting(upright) else null
            val result = try {
                mp.process(upright, frameTimeMs, runHands)
            } catch (_: Exception) {
                upright.recycle()
                return // a single bad frame should not kill the loop (as on the web)
            }
            upright.recycle()
            val inferMs = maxOf(0.0, nowMs() - frameTimeMs)
            session.completeTick(frameTimeMs, runHands, result, inferMs, luma)

            _framing.value = session.framing
            _live.value = session.live
            _faceMissingSeconds.value = session.faceMissingSeconds
        } finally {
            image.close()
        }
    }

    /** The frame as the camera saw it, upright and unmirrored (the web's video frame). */
    private fun uprightBitmap(image: ImageProxy): Bitmap {
        val raw = image.toBitmap()
        val rotation = image.imageInfo.rotationDegrees
        if (rotation == 0) return raw
        val matrix = Matrix().apply { postRotate(rotation.toFloat()) }
        return Bitmap.createBitmap(raw, 0, 0, raw.width, raw.height, matrix, true).also { raw.recycle() }
    }

    /** sampleLighting(): the frame drawn at 64x36, as the web's canvas does. */
    private fun sampleLighting(bitmap: Bitmap): Lighting.Luma {
        val small = Bitmap.createScaledBitmap(bitmap, 64, 36, true)
        val pixels = IntArray(64 * 36)
        small.getPixels(pixels, 0, 64, 0, 0, 64, 36)
        small.recycle()
        val rgba = IntArray(pixels.size * 4)
        for (i in pixels.indices) {
            val p = pixels[i]
            rgba[i * 4] = (p shr 16) and 0xff
            rgba[i * 4 + 1] = (p shr 8) and 0xff
            rgba[i * 4 + 2] = p and 0xff
            rgba[i * 4 + 3] = (p ushr 24) and 0xff
        }
        return Lighting.measure(64, 36, rgba)
    }

    /**
     * While recording, a camera that stops delivering frames for over a
     * second (another app took it, the system paused it) is recorded as
     * a camera_interrupted gap, closed when frames come back.
     */
    private fun startMonitor() {
        monitorJob?.cancel()
        monitorJob = scope.launch(Dispatchers.Default) {
            var inGap = false
            while (isActive) {
                delay(250)
                if (session.currentMode != CaptureMode.RECORDING) continue
                val last = lastFrameAtMs ?: continue
                val now = nowMs()
                if (!inGap && now - last > STALL_MS && !session.scheduler.isDisabled) {
                    session.openGap(last, "camera_interrupted")
                    inGap = true
                } else if (inGap && now - last <= STALL_MS) {
                    session.closeGap(last)
                    inGap = false
                }
            }
        }
    }

    // --- setup steps (web: runBenchmark, runGazeCalibration, runRightHandCheck) ---

    suspend fun runBenchmark(): BenchmarkResult {
        session.startBenchmark()
        delay((VisualConfig.BENCHMARK_DURATION_S * 1000).toLong())
        val result = session.finishBenchmark()
        if (!result.tooSlow) source = source?.copy(deviceTier = result.tier, benchmarkFps = result.benchmarkFps)
        return result
    }

    suspend fun runGazeCalibration(): GazeCalibration {
        session.startGazeCalibration()
        delay((VisualConfig.CALIBRATION_DURATION_S * 1000).toLong())
        return session.finishGazeCalibration()
    }

    /** Right-hand check; flips the label mapping and retries once if it fails (§4.8). */
    suspend fun runRightHandCheck(): String {
        session.startRightHandCheck()
        delay((VisualConfig.RIGHT_HAND_CHECK_WINDOW_S * 1000).toLong())
        var result = session.finishRightHandCheck()
        if (result == "failed") {
            session.flipHandedness()
            session.startRightHandCheck()
            delay((VisualConfig.RIGHT_HAND_CHECK_WINDOW_S * 1000).toLong())
            result = session.finishRightHandCheck()
            if (result == "failed") session.resetHandedness()
        }
        return result
    }

    fun beginRecording(t0Ms: Double) = session.beginRecording(t0Ms)

    /** Stops the camera and builds the track (web: endRecording). Null when no frame was captured. */
    fun endRecording(durationS: Double, calibration: Calibration, trackContext: TrackContext): VisualSignalTrack? {
        val framingAtStop = session.framing
        stop()
        val src = source ?: return null
        return session.endRecording(durationS, src, calibration, trackContext, framingAtStop)
    }

    /** Releases the camera and the models. Safe to call more than once. */
    fun stop() {
        active = false
        monitorJob?.cancel()
        monitorJob = null
        runCatching { provider?.unbindAll() }
        provider = null
        preview = null
        analysisExecutor?.let { executor ->
            executor.execute {
                extractor?.close()
                extractor = null
            }
            executor.shutdown()
        } ?: run {
            extractor?.close()
            extractor = null
        }
        analysisExecutor = null
    }

    private companion object {
        const val STALL_MS = 1000.0
    }
}

