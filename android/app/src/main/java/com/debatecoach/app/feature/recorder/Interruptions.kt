package com.debatecoach.app.feature.recorder

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.os.Build
import androidx.core.content.ContextCompat

/** Why a recording stopped without the user pressing Stop. */
enum class Interruption { CALL, AUDIO_TAKEN, BACKGROUND }

fun Interruption.message(): String = when (this) {
    Interruption.CALL -> "Recording stopped because a call came in. You can send what was recorded, or record again."
    Interruption.AUDIO_TAKEN -> "Recording stopped because another app started using audio. You can send what was recorded, or record again."
    Interruption.BACKGROUND -> "Recording stopped because Debate Coach left the screen. You can send what was recorded, or record again."
}

interface InterruptionWatcher {
    fun start(onInterrupted: (Interruption) -> Unit)
    fun stop()
}

/**
 * Holds audio focus while recording (so music pauses) and reports when
 * something takes it away: a phone call rings or starts, or another app
 * claims the audio. On Android 12+ call-mode changes are watched too.
 */
class AndroidInterruptionWatcher(context: Context) : InterruptionWatcher {
    private val audio = context.getSystemService(AudioManager::class.java)
    private val executor = ContextCompat.getMainExecutor(context)
    private var focusRequest: AudioFocusRequest? = null
    private var modeListener: Any? = null
    private var callback: ((Interruption) -> Unit)? = null

    override fun start(onInterrupted: (Interruption) -> Unit) {
        stop()
        callback = onInterrupted
        val request = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_EXCLUSIVE)
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build(),
            )
            .setOnAudioFocusChangeListener { change ->
                if (change == AudioManager.AUDIOFOCUS_LOSS || change == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT ||
                    change == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK
                ) {
                    fire(if (inCall()) Interruption.CALL else Interruption.AUDIO_TAKEN)
                }
            }
            .build()
        focusRequest = request
        audio.requestAudioFocus(request)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val listener = AudioManager.OnModeChangedListener { mode ->
                if (mode == AudioManager.MODE_IN_CALL || mode == AudioManager.MODE_RINGTONE || mode == AudioManager.MODE_CALL_SCREENING) {
                    fire(Interruption.CALL)
                }
            }
            audio.addOnModeChangedListener(executor, listener)
            modeListener = listener
        }
    }

    private fun inCall(): Boolean = when (audio.mode) {
        AudioManager.MODE_IN_CALL, AudioManager.MODE_IN_COMMUNICATION, AudioManager.MODE_RINGTONE -> true
        else -> false
    }

    private fun fire(interruption: Interruption) {
        val cb = callback ?: return
        callback = null
        executor.execute { cb(interruption) }
    }

    override fun stop() {
        callback = null
        focusRequest?.let { audio.abandonAudioFocusRequest(it) }
        focusRequest = null
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            (modeListener as? AudioManager.OnModeChangedListener)?.let { audio.removeOnModeChangedListener(it) }
        }
        modeListener = null
    }
}
