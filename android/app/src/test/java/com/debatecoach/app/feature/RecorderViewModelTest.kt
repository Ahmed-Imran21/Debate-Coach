package com.debatecoach.app.feature

import com.debatecoach.app.core.util.ConsentChoice
import com.debatecoach.app.core.util.ConsentStore
import com.debatecoach.app.core.util.Connectivity
import com.debatecoach.app.core.model.Motion
import com.debatecoach.app.feature.recorder.AudioUploader
import com.debatecoach.app.feature.recorder.Interruption
import com.debatecoach.app.feature.recorder.InterruptionWatcher
import com.debatecoach.app.feature.recorder.Phase
import com.debatecoach.app.feature.recorder.RecorderViewModel
import com.debatecoach.app.feature.recorder.SetupStep
import com.debatecoach.app.feature.recorder.SpeechRecorder
import com.debatecoach.app.feature.recorder.TrackUploader
import com.debatecoach.app.feature.recorder.UploadManager
import com.debatecoach.app.feature.recorder.UploadState
import com.debatecoach.app.feature.recorder.VisualCapture
import com.debatecoach.app.testing.FakeBackend
import com.debatecoach.app.testing.MainDispatcherRule
import com.debatecoach.app.testing.MemoryStore
import com.debatecoach.app.visual.Calibration
import com.debatecoach.app.visual.CalibrationBaseline
import com.debatecoach.app.visual.FramingChecks
import com.debatecoach.app.visual.TrackBuilder
import com.debatecoach.app.visual.TrackContext
import com.debatecoach.app.visual.UnavailableReason
import com.debatecoach.app.visual.VisualSignalTrack
import java.io.File
import java.nio.file.Files
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class FakeRecorder : SpeechRecorder {
    var started: File? = null
    var stopResult = true
    var failStart = false
    var released = false
    override fun start(file: File): Double {
        if (failStart) throw IllegalStateException("mic busy")
        started = file
        file.writeBytes(ByteArray(10))
        return 1_000.0
    }
    override fun level() = 42
    override fun stop() = stopResult
    override fun release() {
        released = true
    }
}

class FakeInterruptions : InterruptionWatcher {
    var callback: ((Interruption) -> Unit)? = null
    var active = false
    override fun start(onInterrupted: (Interruption) -> Unit) {
        callback = onInterrupted
        active = true
    }
    override fun stop() {
        active = false
        callback = null
    }
    fun fire(i: Interruption) = callback?.invoke(i)
}

class FakeCapture(
    var startResult: UnavailableReason? = null,
    var tier: String = "full",
    var track: VisualSignalTrack? = TrackBuilder().apply { appendEmpty(0.1) }.build(
        "", com.debatecoach.app.visual.Source("android", "v", "other", com.debatecoach.app.visual.RuntimeInfo("mediapipe-tasks-vision", "1.0.0", "CPU"), emptyList(), "full", 10.0),
        com.debatecoach.app.visual.Capture(640, 360, false, "anatomical", 10), 150, 1.0,
        Calibration(false, null, 0, 0.0, "skipped"), TrackContext("camera_audience", false),
        com.debatecoach.app.visual.SetupCheck(true, true, "ok", "ok"),
    ),
) : VisualCapture {
    override val framing: StateFlow<FramingChecks> = MutableStateFlow(FramingChecks(true, "ok", "ok", false))
    override val faceMissingSeconds: StateFlow<Double> = MutableStateFlow(0.0)
    override val handsInView: StateFlow<Boolean> = MutableStateFlow(false)
    var beganAt: Double? = null
    var endedWith: Pair<Calibration, TrackContext>? = null
    var stopped = false
    override suspend fun start() = startResult
    override suspend fun runBenchmark() = tier to 11.5
    override suspend fun runGazeCalibration() = Calibration(true, CalibrationBaseline(1.0, -2.0, 0.1, 0.0), 28, 0.9, "skipped")
    override suspend fun runRightHandCheck() = "passed"
    override fun beginRecording(t0Ms: Double) {
        beganAt = t0Ms
    }
    override fun endRecording(durationS: Double, calibration: Calibration, context: TrackContext): VisualSignalTrack? {
        endedWith = calibration to context
        return track
    }
    override fun stop() {
        stopped = true
    }
}

class RecorderViewModelTest {
    @get:Rule val main = MainDispatcherRule()

    private val backend = FakeBackend().apply { motionsHandler = { listOf(Motion("carbon-tax", "Climate policy", "This house would introduce a carbon tax.")) } }
    private val consent = ConsentStore(MemoryStore())
    private val recorder = FakeRecorder()
    private val interruptions = FakeInterruptions()
    private val dir: File = Files.createTempDirectory("recs").toFile()
    private val online = MutableStateFlow(true)
    private var clock = 1_000.0

    private fun TestScope.vm(videoEnabled: Boolean = true, capture: FakeCapture = FakeCapture()): Pair<RecorderViewModel, FakeCapture> {
        val uploads = UploadManager(
            backend,
            object : AudioUploader { override suspend fun put(url: String, headers: Map<String, String>, file: File, onProgress: (Long, Long) -> Unit) = Unit },
            object : TrackUploader { override suspend fun upload(sessionId: String, track: VisualSignalTrack) = track.frameCount },
            object : Connectivity { override val online = this@RecorderViewModelTest.online },
            this,
        )
        return RecorderViewModel(backend, consent, recorder, interruptions, { capture }, uploads, { dir }, videoEnabled, clock = { clock }) to capture
    }

    @Test
    fun `loads motions and starts on No prompt`() = runTest(main.dispatcher) {
        val (vm, _) = vm()
        advanceUntilIdle()
        assertEquals(1, vm.state.value.motions.size)
        assertNull(vm.state.value.motionId)
    }

    @Test
    fun `asks for visual feedback consent before the first recording, remembers it, and waits for Start again`() = runTest(main.dispatcher) {
        val (vm, _) = vm()
        vm.startRecording(cameraGranted = true)
        assertEquals(Phase.CONSENT, vm.state.value.phase)
        assertNull(recorder.started)

        vm.decideConsent(ConsentChoice.OUT)
        assertEquals(Phase.IDLE, vm.state.value.phase)
        assertEquals(ConsentChoice.OUT, consent.choice.value)

        vm.startRecording(cameraGranted = true)
        assertEquals(Phase.RECORDING, vm.state.value.phase)
        assertNotNull(recorder.started)
        assertFalse(vm.state.value.usingVideo)
        vm.stopRecording() // the recording timer would otherwise tick forever in virtual time
    }

    @Test
    fun `with the video feature off it records audio only, straight away`() = runTest(main.dispatcher) {
        val (vm, _) = vm(videoEnabled = false)
        vm.startRecording(cameraGranted = false)
        assertEquals(Phase.RECORDING, vm.state.value.phase)
        vm.stopRecording()
    }

    @Test
    fun `camera denied is explained, then audio only reporting camera_denied`() = runTest(main.dispatcher) {
        consent.set(ConsentChoice.IN)
        val (vm, _) = vm()
        vm.startRecording(cameraGranted = false)
        assertEquals(Phase.SETUP, vm.state.value.phase)
        assertEquals(SetupStep.UNAVAILABLE, vm.state.value.setup.step)
        assertEquals(UnavailableReason.CAMERA_DENIED, vm.state.value.setup.unavailable)

        vm.continueAudioOnly()
        assertEquals(Phase.RECORDING, vm.state.value.phase)
        vm.stopRecording()
        vm.submit()
        advanceUntilIdle()
        assertEquals("startSession:s-new:unavailable:camera_denied", backend.calls.last())
    }

    @Test
    fun `the full setup of framing, device check, calibration and context, then the track is uploaded`() = runTest(main.dispatcher) {
        consent.set(ConsentChoice.IN)
        val (vm, capture) = vm()
        vm.startRecording(cameraGranted = true)
        advanceUntilIdle()
        assertEquals(SetupStep.FRAMING, vm.state.value.setup.step)
        vm.framingContinue()
        vm.runBenchmark()
        advanceUntilIdle()
        assertEquals(SetupStep.CALIBRATE_GAZE, vm.state.value.setup.step)
        assertEquals("full", vm.state.value.setup.deviceTier)
        vm.runGazeCalibration()
        advanceUntilIdle()
        vm.runRightHandCheck()
        advanceUntilIdle()
        assertEquals(SetupStep.CONTEXT, vm.state.value.setup.step)
        vm.setSetting("in_room_practice")
        vm.setUsesNotes(true)
        vm.contextContinue()
        vm.setupReady()
        assertEquals(Phase.RECORDING, vm.state.value.phase)
        assertEquals(1_000.0, capture.beganAt)

        clock = 64_000.0
        vm.stopRecording()
        assertEquals(Phase.REVIEW, vm.state.value.phase)
        assertEquals(63.0, vm.state.value.recordedSeconds, 1e-9)
        val (calibration, context) = capture.endedWith!!
        assertTrue(calibration.performed)
        assertEquals("passed", calibration.rightHandCheck)
        assertEquals(TrackContext("in_room_practice", true), context)

        vm.setTitle("Round 2")
        vm.submit()
        advanceUntilIdle()
        assertEquals("createSession:audio/mp4:Round 2:null:true", backend.calls.first { it.startsWith("createSession") })
        assertEquals("startSession:s-new:uploaded:null", backend.calls.last())
        assertTrue(vm.uploadState.value is UploadState.Done)
    }

    @Test
    fun `a device that's too slow falls back to audio only with device_too_slow`() = runTest(main.dispatcher) {
        consent.set(ConsentChoice.IN)
        val (vm, capture) = vm(capture = FakeCapture(tier = "too_slow"))
        vm.startRecording(true)
        advanceUntilIdle()
        vm.framingContinue()
        vm.runBenchmark()
        // runCurrent, not advanceUntilIdle: once recording, the timer ticks forever.
        runCurrent()
        assertEquals(Phase.RECORDING, vm.state.value.phase)
        assertTrue(capture.stopped)
        vm.stopRecording()
        vm.submit()
        advanceUntilIdle()
        assertEquals("startSession:s-new:unavailable:device_too_slow", backend.calls.last())
    }

    @Test
    fun `models that fail to load fall back with model_load_failed`() = runTest(main.dispatcher) {
        consent.set(ConsentChoice.IN)
        val (vm, _) = vm(capture = FakeCapture(startResult = UnavailableReason.MODEL_LOAD_FAILED))
        vm.startRecording(true)
        advanceUntilIdle()
        assertEquals(UnavailableReason.MODEL_LOAD_FAILED, vm.state.value.setup.unavailable)
    }

    @Test
    fun `no frames captured becomes face_not_found`() = runTest(main.dispatcher) {
        consent.set(ConsentChoice.IN)
        val (vm, _) = vm(capture = FakeCapture(track = null))
        vm.startRecording(true)
        advanceUntilIdle()
        vm.skipCalibration()
        vm.contextContinue()
        vm.setupReady()
        vm.stopRecording()
        vm.submit()
        advanceUntilIdle()
        assertEquals("startSession:s-new:unavailable:face_not_found", backend.calls.last())
    }

    @Test
    fun `a call stops the recording cleanly and keeps what was recorded`() = runTest(main.dispatcher) {
        val (vm, _) = vm(videoEnabled = false)
        vm.startRecording(false)
        assertTrue(interruptions.active)
        interruptions.fire(Interruption.CALL)
        assertEquals(Phase.REVIEW, vm.state.value.phase)
        assertEquals(Interruption.CALL, vm.state.value.interruption)
        assertFalse(interruptions.active)
        assertNotNull(vm.state.value.recordingFile)
    }

    @Test
    fun `leaving the app stops the recording the same way`() = runTest(main.dispatcher) {
        val (vm, _) = vm(videoEnabled = false)
        vm.startRecording(false)
        vm.stopRecording(Interruption.BACKGROUND)
        assertEquals(Interruption.BACKGROUND, vm.state.value.interruption)
        vm.stopRecording(Interruption.BACKGROUND) // a second stop is harmless
        assertEquals(Phase.REVIEW, vm.state.value.phase)
    }

    @Test
    fun `the microphone failing to start is reported, not crashed on`() = runTest(main.dispatcher) {
        recorder.failStart = true
        val (vm, _) = vm(videoEnabled = false)
        vm.startRecording(false)
        assertEquals(Phase.IDLE, vm.state.value.phase)
        assertEquals("Could not start recording. Try again.", vm.state.value.error)
    }

    @Test
    fun `Record again discards the recording`() = runTest(main.dispatcher) {
        val (vm, _) = vm(videoEnabled = false)
        vm.startRecording(false)
        vm.stopRecording()
        val file = vm.state.value.recordingFile!!
        vm.discard()
        assertFalse(file.exists())
        assertEquals(Phase.IDLE, vm.state.value.phase)
    }

    @Test
    fun `a failed upload goes back to review with the message, and trying again resumes it`() = runTest(main.dispatcher) {
        var attempts = 0
        backend.startSessionHandler = { id, _ ->
            attempts++
            if (attempts == 1) throw com.debatecoach.app.core.net.ApiException(400, "Record something longer.") else com.debatecoach.app.testing.session(id, "queued")
        }
        val (vm, _) = vm(videoEnabled = false)
        vm.startRecording(false)
        vm.stopRecording()
        vm.submit()
        advanceUntilIdle()
        val failed = vm.uploadState.value as UploadState.Failed
        vm.onUploadFailed(failed.message)
        assertEquals(Phase.REVIEW, vm.state.value.phase)
        assertEquals("Record something longer.", vm.state.value.error)

        vm.submit()
        advanceUntilIdle()
        assertTrue(vm.uploadState.value is UploadState.Done)
        assertEquals(1, backend.calls.count { it.startsWith("createSession") })
    }
}
