package com.debatecoach.app.feature.recorder

import com.debatecoach.app.core.Backend
import com.debatecoach.app.core.model.SessionCreated
import com.debatecoach.app.core.model.VideoFinalize
import com.debatecoach.app.core.net.ApiException
import com.debatecoach.app.core.net.NetworkException
import com.debatecoach.app.core.net.UPLOAD_FAILED_MESSAGE
import com.debatecoach.app.core.net.UploadNetworkException
import com.debatecoach.app.core.net.userMessage
import com.debatecoach.app.core.util.Connectivity
import com.debatecoach.app.visual.UnavailableReason
import com.debatecoach.app.visual.VisualSignalTrack
import java.io.File
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

/** What visual analysis produced for this recording. */
sealed interface VideoPlan {
    /** Visual analysis was never in play: the website's plain uploadAndStart path. */
    data object None : VideoPlan
    /** A track to upload (it may still fail: upload_failed). */
    data class Track(val track: VisualSignalTrack) : VideoPlan
    /** Requested but unavailable, and why. */
    data class Unavailable(val reason: UnavailableReason) : VideoPlan
}

data class UploadJob(
    val audio: File,
    val contentType: String,
    val title: String?,
    val motionId: String?,
    val video: VideoPlan,
)

sealed interface UploadState {
    data object Idle : UploadState
    data class Running(val step: Step, val progress: Float?) : UploadState
    data class Failed(val message: String) : UploadState
    data class Done(val sessionId: String) : UploadState

    enum class Step(val label: String) {
        CREATING("Starting the session"),
        UPLOADING_AUDIO("Uploading your recording"),
        UPLOADING_SIGNALS("Uploading the visual signals"),
        STARTING("Starting the analysis"),
        WAITING_FOR_CONNECTION("Waiting for a connection"),
    }
}

interface AudioUploader {
    suspend fun put(url: String, headers: Map<String, String>, file: File, onProgress: (Long, Long) -> Unit)
}

interface TrackUploader {
    /** Returns the acknowledged frame count, or throws when it gives up. */
    suspend fun upload(sessionId: String, track: VisualSignalTrack): Int
}

/**
 * Sends a finished recording, the same way the website's Recorder
 * submit() does: create the session (with video_analysis when it was
 * requested), PUT the audio to the signed URL, upload the signal track
 * if there is one, then start the pipeline with the video outcome.
 *
 * Application-scoped, so it survives rotation and leaving the screen.
 * A failed step can be retried without creating a second session:
 * the created session is kept and the job resumes where it stopped.
 * The audio PUT and the start call retry on their own through a flaky
 * connection; creating the session doesn't (a repeat could double up),
 * the user presses Try again instead.
 */
class UploadManager(
    private val backend: Backend,
    private val audioUploader: AudioUploader,
    private val trackUploader: TrackUploader,
    private val connectivity: Connectivity,
    private val scope: CoroutineScope,
    private val retryDelaysMs: List<Long> = listOf(1_000, 2_000, 4_000, 8_000, 16_000),
) {
    private val _state = MutableStateFlow<UploadState>(UploadState.Idle)
    val state: StateFlow<UploadState> = _state.asStateFlow()

    private var job: UploadJob? = null
    private var created: SessionCreated? = null
    private var audioSent = false
    private var finalize: VideoFinalize? = null
    private var running: Job? = null

    fun start(upload: UploadJob) {
        if (running?.isActive == true) return
        job = upload
        created = null
        audioSent = false
        finalize = null
        run()
    }

    /** Resume after a failure, from the step that failed. */
    fun retry() {
        if (running?.isActive == true || job == null) return
        run()
    }

    /** Forget a finished or abandoned upload. */
    fun reset() {
        running?.cancel()
        running = null
        job = null
        created = null
        _state.value = UploadState.Idle
    }

    private fun run() {
        val upload = job ?: return
        running = scope.launch {
            try {
                val sessionId = send(upload)
                _state.value = UploadState.Done(sessionId)
            } catch (cancel: CancellationException) {
                throw cancel
            } catch (error: Throwable) {
                _state.value = UploadState.Failed(
                    when (error) {
                        is UploadNetworkException -> UPLOAD_FAILED_MESSAGE
                        is ApiException -> error.userMessage()
                        else -> "The recording could not be sent. Check your connection and try again."
                    },
                )
            }
        }
    }

    private suspend fun send(upload: UploadJob): String {
        val videoRequested = upload.video != VideoPlan.None

        val session = created ?: run {
            _state.value = UploadState.Running(UploadState.Step.CREATING, null)
            waitUntilOnline()
            backend.createSession(upload.contentType, upload.title, upload.motionId, videoRequested).also { created = it }
        }

        if (!audioSent) {
            withRetries {
                _state.value = UploadState.Running(UploadState.Step.UPLOADING_AUDIO, 0f)
                audioUploader.put(session.uploadUrl, session.uploadHeaders, upload.audio) { sent, total ->
                    if (total > 0) _state.value = UploadState.Running(UploadState.Step.UPLOADING_AUDIO, sent.toFloat() / total)
                }
            }
            audioSent = true
        }

        if (finalize == null && videoRequested) {
            finalize = when (val video = upload.video) {
                is VideoPlan.Track -> {
                    // The backend may have video analysis switched off
                    // (it then created the session as not_requested):
                    // nothing to upload and nothing to report.
                    if (session.videoAnalysisStatus == "not_requested") {
                        null
                    } else {
                        _state.value = UploadState.Running(UploadState.Step.UPLOADING_SIGNALS, null)
                        try {
                            trackUploader.upload(session.id, video.track)
                            VideoFinalize("uploaded")
                        } catch (cancel: CancellationException) {
                            throw cancel
                        } catch (_: Exception) {
                            VideoFinalize("unavailable", UnavailableReason.UPLOAD_FAILED.wire)
                        }
                    }
                }
                is VideoPlan.Unavailable -> VideoFinalize("unavailable", video.reason.wire)
                VideoPlan.None -> null
            }
        }

        _state.value = UploadState.Running(UploadState.Step.STARTING, null)
        withRetries {
            try {
                backend.startSession(session.id, finalize)
            } catch (error: ApiException) {
                // A start whose response was lost the first time: the
                // session is already running, which is what we wanted.
                if (error.status == 409 && alreadyStarted(session.id)) return@withRetries
                throw error
            } catch (error: NetworkException) {
                if (alreadyStarted(session.id)) return@withRetries
                throw error
            }
        }
        return session.id
    }

    private suspend fun alreadyStarted(id: String): Boolean = try {
        backend.getSession(id).status !in setOf("created", "failed")
    } catch (_: Exception) {
        false
    }

    private suspend fun waitUntilOnline() {
        if (connectivity.online.value) return
        val previous = _state.value
        _state.value = UploadState.Running(UploadState.Step.WAITING_FOR_CONNECTION, null)
        connectivity.online.first { it }
        _state.value = previous
    }

    /** Network failures, timeouts and 5xx: wait for a connection, back off, try again. */
    private suspend fun withRetries(block: suspend () -> Unit) {
        var attempt = 0
        while (true) {
            waitUntilOnline()
            try {
                block()
                return
            } catch (cancel: CancellationException) {
                throw cancel
            } catch (error: Exception) {
                val transient = error is UploadNetworkException || error is NetworkException ||
                    (error is ApiException && (error.status == 408 || error.status == 429 || error.status >= 500 || error.status == 0))
                if (!transient || attempt >= retryDelaysMs.size) throw error
                delay(retryDelaysMs[attempt])
                attempt += 1
            }
        }
    }
}
