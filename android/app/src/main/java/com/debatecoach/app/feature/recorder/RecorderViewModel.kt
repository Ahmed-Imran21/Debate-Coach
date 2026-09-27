package com.debatecoach.app.feature.recorder

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.debatecoach.app.core.Backend
import com.debatecoach.app.core.model.Motion
import com.debatecoach.app.core.util.ConsentChoice
import com.debatecoach.app.core.util.ConsentStore
import com.debatecoach.app.visual.Calibration
import com.debatecoach.app.visual.FramingChecks
import com.debatecoach.app.visual.TrackContext
import com.debatecoach.app.visual.UnavailableReason
import com.debatecoach.app.visual.nowMs
import java.io.File
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

enum class Phase { IDLE, CONSENT, SETUP, RECORDING, REVIEW, UPLOADING }

enum class SetupStep { STARTING, FRAMING, BENCHMARK, CALIBRATE_GAZE, CALIBRATE_HAND, CONTEXT, READY, UNAVAILABLE }

data class SetupState(
    val step: SetupStep = SetupStep.STARTING,
    val busy: Boolean = false,
    val benchmarkFps: Double = 0.0,
    val deviceTier: String? = null,
    val calibration: Calibration = Calibration(false, null, 0, 0.0, "skipped"),
    val unavailable: UnavailableReason? = null,
    val setting: String = "camera_audience",
    val usesNotes: Boolean = false,
)

data class RecorderState(
    val phase: Phase = Phase.IDLE,
    val videoFeatureEnabled: Boolean = false,
    val consent: ConsentChoice? = null,
    val motions: List<Motion> = emptyList(),
    val motionsFailed: Boolean = false,
    val motionId: String? = null,
    val title: String = "",
    val setup: SetupState = SetupState(),
    val usingVideo: Boolean = false,
    val elapsedSeconds: Int = 0,
    val level: Int = 0,
    val showPreview: Boolean = false,
    val recordingFile: File? = null,
    val recordedSeconds: Double = 0.0,
    val interruption: Interruption? = null,
    val error: String? = null,
) {
    val chosenMotion: Motion? get() = motions.firstOrNull { it.id == motionId }
}

/** The camera side, as the recorder sees it (VisualCaptureController on a device; faked in tests). */
interface VisualCapture {
    val framing: StateFlow<FramingChecks>
    val faceMissingSeconds: StateFlow<Double>
    val handsInView: StateFlow<Boolean>
    suspend fun start(): UnavailableReason?
    suspend fun runBenchmark(): Pair<String, Double>
    suspend fun runGazeCalibration(): Calibration
    suspend fun runRightHandCheck(): String
    fun beginRecording(t0Ms: Double)
    fun endRecording(durationS: Double, calibration: Calibration, context: TrackContext): com.debatecoach.app.visual.VisualSignalTrack?
    fun stop()
}

/**
 * components/Recorder.tsx and SetupScreen.tsx's flow, natively:
 * idle -> (consent) -> (setup: framing, device check, calibration,
 * context) -> recording -> review -> upload. Visual feedback falls
 * back to audio-only with the web's unavailable reasons.
 */
class RecorderViewModel(
    private val backend: Backend,
    private val consentStore: ConsentStore,
    private val recorder: SpeechRecorder,
    private val interruptions: InterruptionWatcher,
    private val captureFactory: () -> VisualCapture,
    private val uploads: UploadManager,
    private val recordingsDir: () -> File,
    videoFeatureEnabled: Boolean,
    private val clock: () -> Double = ::nowMs,
) : ViewModel() {

    private val _state = MutableStateFlow(RecorderState(videoFeatureEnabled = videoFeatureEnabled, consent = consentStore.choice.value))
    val state: StateFlow<RecorderState> = _state.asStateFlow()

    val uploadState: StateFlow<UploadState> get() = uploads.state

    var capture: VisualCapture? = null
        private set
    private var videoOutcome: VideoPlan? = null
    private var t0: Double? = null
    private var ticker: Job? = null
    private var lastSubmitted: UploadJob? = null

    init {
        loadMotions()
    }

    fun loadMotions() {
        viewModelScope.launch {
            try {
                val motions = backend.motions()
                _state.update { it.copy(motions = motions, motionsFailed = false) }
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                _state.update { it.copy(motionsFailed = true) }
            }
        }
    }

    fun setMotion(id: String?) = _state.update { it.copy(motionId = id) }
    fun setTitle(title: String) = _state.update { it.copy(title = title.take(200)) }
    fun togglePreview() = _state.update { it.copy(showPreview = !it.showPreview) }
    fun changeConsent() = _state.update { it.copy(phase = Phase.CONSENT) }

    // ---------------------------------------------------------------
    // Start
    // ---------------------------------------------------------------

    /**
     * Pressed "Start recording" with the microphone granted. [cameraGranted]
     * is only consulted when visual feedback is on.
     */
    fun startRecording(cameraGranted: Boolean) {
        val s = _state.value
        _state.update { it.copy(error = null, interruption = null) }
        videoOutcome = null
        if (s.videoFeatureEnabled && s.consent == null) {
            _state.update { it.copy(phase = Phase.CONSENT) }
            return
        }
        if (s.videoFeatureEnabled && s.consent == ConsentChoice.IN) {
            if (!cameraGranted) {
                showUnavailable(UnavailableReason.CAMERA_DENIED)
                return
            }
            beginSetup()
            return
        }
        beginAudioOnly(null)
    }

    /** ConsentPanel: remembered, then back to idle so the user presses Start again (as on the web). */
    fun decideConsent(choice: ConsentChoice) {
        consentStore.set(choice)
        _state.update { it.copy(consent = choice, phase = Phase.IDLE) }
    }

    private fun beginSetup() {
        val c = captureFactory()
        capture = c
        _state.update { it.copy(phase = Phase.SETUP, usingVideo = true, setup = SetupState(step = SetupStep.STARTING)) }
        viewModelScope.launch {
            val reason = c.start()
            if (reason != null) {
                c.stop()
                capture = null
                showUnavailable(reason)
            } else {
                _state.update { it.copy(setup = it.setup.copy(step = SetupStep.FRAMING)) }
            }
        }
    }

    /** Visual analysis can't run: say why, then record audio-only when the user continues. */
    private fun showUnavailable(reason: UnavailableReason) {
        _state.update {
            it.copy(phase = Phase.SETUP, usingVideo = false, setup = it.setup.copy(step = SetupStep.UNAVAILABLE, unavailable = reason))
        }
    }

    fun continueAudioOnly() {
        val reason = _state.value.setup.unavailable ?: UnavailableReason.USER_OPTED_OUT
        skipVisual(reason)
    }

    /** "Skip visual feedback", or an automatic skip (too slow). */
    fun skipVisual(reason: UnavailableReason = UnavailableReason.USER_OPTED_OUT) {
        capture?.stop()
        capture = null
        beginAudioOnly(VideoPlan.Unavailable(reason))
    }

    // ---------------------------------------------------------------
    // Setup steps
    // ---------------------------------------------------------------

    fun framingContinue() = _state.update { it.copy(setup = it.setup.copy(step = SetupStep.BENCHMARK)) }

    fun runBenchmark() {
        val c = capture ?: return
        _state.update { it.copy(setup = it.setup.copy(busy = true)) }
        viewModelScope.launch {
            val (tier, fps) = c.runBenchmark()
            if (tier == "too_slow") {
                _state.update { it.copy(setup = it.setup.copy(busy = false, benchmarkFps = fps, unavailable = UnavailableReason.DEVICE_TOO_SLOW)) }
                skipVisual(UnavailableReason.DEVICE_TOO_SLOW)
            } else {
                _state.update { it.copy(setup = it.setup.copy(busy = false, benchmarkFps = fps, deviceTier = tier, step = SetupStep.CALIBRATE_GAZE)) }
            }
        }
    }

    fun runGazeCalibration() {
        val c = capture ?: return
        _state.update { it.copy(setup = it.setup.copy(busy = true)) }
        viewModelScope.launch {
            val result = c.runGazeCalibration()
            _state.update { s ->
                s.copy(setup = s.setup.copy(
                    busy = false,
                    step = SetupStep.CALIBRATE_HAND,
                    calibration = s.setup.calibration.copy(performed = result.performed, baseline = result.baseline ?: s.setup.calibration.baseline, samples = result.samples, stability = if (result.performed) result.stability else s.setup.calibration.stability),
                ))
            }
        }
    }

    fun skipGazeCalibration() = _state.update { it.copy(setup = it.setup.copy(step = SetupStep.CALIBRATE_HAND)) }

    fun runRightHandCheck() {
        val c = capture ?: return
        _state.update { it.copy(setup = it.setup.copy(busy = true)) }
        viewModelScope.launch {
            val result = c.runRightHandCheck()
            _state.update { s -> s.copy(setup = s.setup.copy(busy = false, step = SetupStep.CONTEXT, calibration = s.setup.calibration.copy(rightHandCheck = result))) }
        }
    }

    /** "Skip" on the right-hand step: the web resets the whole calibration. */
    fun skipCalibration() = _state.update {
        it.copy(setup = it.setup.copy(step = SetupStep.CONTEXT, calibration = Calibration(false, null, 0, 0.0, "skipped")))
    }

    fun setSetting(setting: String) = _state.update { it.copy(setup = it.setup.copy(setting = setting)) }
    fun setUsesNotes(uses: Boolean) = _state.update { it.copy(setup = it.setup.copy(usesNotes = uses)) }
    fun contextContinue() = _state.update { it.copy(setup = it.setup.copy(step = SetupStep.READY)) }

    /** "Start recording" at the end of setup. */
    fun setupReady() {
        val c = capture ?: return beginAudioOnly(VideoPlan.Unavailable(UnavailableReason.MODEL_LOAD_FAILED))
        startRecorder { t0 -> c.beginRecording(t0) }
    }

    // ---------------------------------------------------------------
    // Recording
    // ---------------------------------------------------------------

    private fun beginAudioOnly(outcome: VideoPlan?) {
        videoOutcome = outcome
        _state.update { it.copy(usingVideo = false) }
        startRecorder(null)
    }

    private fun startRecorder(onStart: ((Double) -> Unit)?) {
        val file = File(recordingsDir(), "recording-${System.currentTimeMillis()}.m4a")
        recordingsDir().listFiles()?.filter { it != file }?.forEach { it.delete() }
        val start = try {
            recorder.start(file)
        } catch (_: Exception) {
            capture?.stop()
            capture = null
            _state.update { it.copy(phase = Phase.IDLE, error = "Could not start recording. Try again.") }
            return
        }
        t0 = start
        onStart?.invoke(start)
        interruptions.start { reason -> stopRecording(reason) }
        _state.update { it.copy(phase = Phase.RECORDING, recordingFile = file, elapsedSeconds = 0, level = 0, showPreview = false) }
        ticker?.cancel()
        ticker = viewModelScope.launch {
            while (isActive) {
                val began = t0 ?: break
                _state.update { it.copy(elapsedSeconds = ((clock() - began) / 1000).toInt(), level = recorder.level()) }
                delay(60)
            }
        }
    }

    /** Stop pressed, or an interruption (a call, another app's audio, leaving the screen). */
    fun stopRecording(interruption: Interruption? = null) {
        if (_state.value.phase != Phase.RECORDING) return
        ticker?.cancel()
        ticker = null
        interruptions.stop()
        val began = t0 ?: clock()
        val durationS = (clock() - began) / 1000
        val ok = recorder.stop()

        val c = capture
        if (c != null) {
            val s = _state.value.setup
            val track = c.endRecording(durationS, s.calibration, TrackContext(s.setting, s.usesNotes))
            videoOutcome = if (track != null) VideoPlan.Track(track) else VideoPlan.Unavailable(UnavailableReason.FACE_NOT_FOUND)
            capture = null
        }

        if (!ok) {
            _state.update { it.copy(phase = Phase.IDLE, error = "Nothing was recorded. Try again.", level = 0) }
            return
        }
        _state.update { it.copy(phase = Phase.REVIEW, recordedSeconds = durationS, level = 0, interruption = interruption) }
    }

    /** "Record again": throw this recording away. */
    fun discard() {
        _state.value.recordingFile?.delete()
        uploads.reset()
        lastSubmitted = null
        videoOutcome = null
        _state.update { it.copy(phase = Phase.IDLE, recordingFile = null, elapsedSeconds = 0, recordedSeconds = 0.0, error = null, interruption = null, title = "") }
    }

    // ---------------------------------------------------------------
    // Upload
    // ---------------------------------------------------------------

    fun submit() {
        val s = _state.value
        val file = s.recordingFile ?: return
        val job = UploadJob(
            audio = file,
            contentType = RECORDING_CONTENT_TYPE,
            title = s.title.trim().ifEmpty { null },
            motionId = s.motionId,
            video = videoOutcome ?: VideoPlan.None,
        )
        _state.update { it.copy(phase = Phase.UPLOADING, error = null) }
        // After a failure, resume the same upload (no second session)
        // unless the title or motion changed since.
        if (lastSubmitted == job && uploads.state.value is UploadState.Failed) uploads.retry() else uploads.start(job)
        lastSubmitted = job
    }

    /** The upload failed: back to review with the message, recording kept. */
    fun onUploadFailed(message: String) = _state.update { it.copy(phase = Phase.REVIEW, error = message) }

    fun onUploadDone() {
        uploads.reset()
        _state.value.recordingFile?.delete()
        lastSubmitted = null
        _state.update { RecorderState(videoFeatureEnabled = it.videoFeatureEnabled, consent = it.consent, motions = it.motions, motionsFailed = it.motionsFailed) }
    }

    override fun onCleared() {
        ticker?.cancel()
        interruptions.stop()
        recorder.release()
        capture?.stop()
    }
}
