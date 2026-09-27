package com.debatecoach.app.feature.recorder

import android.content.Context
import androidx.camera.view.PreviewView
import androidx.lifecycle.ProcessLifecycleOwner
import com.debatecoach.app.visual.Calibration
import com.debatecoach.app.visual.FramingChecks
import com.debatecoach.app.visual.TrackContext
import com.debatecoach.app.visual.UnavailableReason
import com.debatecoach.app.visual.VisualCaptureController
import com.debatecoach.app.visual.VisualSignalTrack
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn

/**
 * The recorder's camera side on a real device. The camera is bound to
 * the app's process lifecycle: it closes when the app goes to the
 * background (and the recording stops, see RecorderScreen) and never
 * runs behind the user's back.
 */
class AndroidVisualCapture(context: Context, scope: CoroutineScope) : VisualCapture {
    val controller = VisualCaptureController(context.applicationContext, scope)

    override val framing: StateFlow<FramingChecks> = controller.framing
    override val faceMissingSeconds: StateFlow<Double> = controller.faceMissingSeconds
    override val handsInView: StateFlow<Boolean> =
        controller.live.map { it != null && it.lhPresent && it.rhPresent }.stateIn(scope, SharingStarted.Eagerly, false)

    override suspend fun start(): UnavailableReason? = controller.start(ProcessLifecycleOwner.get())

    override suspend fun runBenchmark(): Pair<String, Double> {
        val result = controller.runBenchmark()
        return result.tier to result.benchmarkFps
    }

    override suspend fun runGazeCalibration(): Calibration {
        val g = controller.runGazeCalibration()
        return Calibration(g.performed, g.baseline, g.samples, g.stability, "skipped")
    }

    override suspend fun runRightHandCheck(): String = controller.runRightHandCheck()

    override fun beginRecording(t0Ms: Double) = controller.beginRecording(t0Ms)

    override fun endRecording(durationS: Double, calibration: Calibration, context: TrackContext): VisualSignalTrack? =
        controller.endRecording(durationS, calibration, context)

    override fun stop() = controller.stop()

    /** Draw the preview into [view], or stop drawing it (analysis carries on either way). */
    fun attachPreview(view: PreviewView?) = controller.setSurfaceProvider(view?.surfaceProvider)
}
