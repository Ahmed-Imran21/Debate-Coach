package com.debatecoach.app.feature.recorder

import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import com.debatecoach.app.visual.nowMs
import java.io.File

/** What the backend is told the upload is (ALLOWED_CONTENT_TYPES: audio/mp4 -> .m4a). */
const val RECORDING_CONTENT_TYPE = "audio/mp4"

/** A recorder the recording screen can drive; faked in tests. */
interface SpeechRecorder {
    /** Starts recording to [file]; returns the start time on the visual clock (nowMs). */
    fun start(file: File): Double
    /** 0..100, like the website's level meter. */
    fun level(): Int
    /** Stops; false if nothing usable was recorded. */
    fun stop(): Boolean
    fun release()
}

/**
 * AAC in an MPEG-4 (.m4a) container, mono. The start time is taken
 * right after MediaRecorder.start() returns: the t0 the visual track's
 * clock is measured from ("mediarecorder_start_event", as on the web).
 */
class AndroidSpeechRecorder(private val context: Context) : SpeechRecorder {
    private var recorder: MediaRecorder? = null

    override fun start(file: File): Double {
        release()
        val r = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) MediaRecorder(context) else @Suppress("DEPRECATION") MediaRecorder()
        try {
            r.setAudioSource(MediaRecorder.AudioSource.MIC)
            r.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            r.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            r.setAudioChannels(1)
            r.setAudioSamplingRate(44_100)
            r.setAudioEncodingBitRate(96_000)
            r.setOutputFile(file.absolutePath)
            r.prepare()
            r.start()
        } catch (error: Exception) {
            r.release()
            throw error
        }
        recorder = r
        return nowMs()
    }

    /**
     * The website maps the RMS of the waveform to 0..100 (rms × 260).
     * MediaRecorder only reports the peak since the last call; speech's
     * peak runs about 2-3× its RMS, hence the gentler factor.
     */
    override fun level(): Int {
        val amplitude = try {
            recorder?.maxAmplitude ?: 0
        } catch (_: Exception) {
            0
        }
        return minOf(100, Math.round(amplitude / 32767.0 * 100 * 1.6).toInt())
    }

    override fun stop(): Boolean {
        val r = recorder ?: return false
        recorder = null
        return try {
            r.stop()
            true
        } catch (_: RuntimeException) {
            false // stopped before any audio was captured
        } finally {
            r.release()
        }
    }

    override fun release() {
        recorder?.let { runCatching { it.release() } }
        recorder = null
    }
}
