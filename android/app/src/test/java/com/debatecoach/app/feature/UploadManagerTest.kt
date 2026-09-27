package com.debatecoach.app.feature

import com.debatecoach.app.core.net.ApiException
import com.debatecoach.app.core.net.NetworkException
import com.debatecoach.app.core.net.UploadNetworkException
import com.debatecoach.app.core.util.Connectivity
import com.debatecoach.app.feature.recorder.AudioUploader
import com.debatecoach.app.feature.recorder.TrackUploader
import com.debatecoach.app.feature.recorder.UploadJob
import com.debatecoach.app.feature.recorder.UploadManager
import com.debatecoach.app.feature.recorder.UploadState
import com.debatecoach.app.feature.recorder.VideoPlan
import com.debatecoach.app.testing.FakeBackend
import com.debatecoach.app.testing.session
import com.debatecoach.app.visual.Calibration
import com.debatecoach.app.visual.Capture
import com.debatecoach.app.visual.RuntimeInfo
import com.debatecoach.app.visual.SetupCheck
import com.debatecoach.app.visual.Source
import com.debatecoach.app.visual.TrackBuilder
import com.debatecoach.app.visual.TrackContext
import com.debatecoach.app.visual.UnavailableReason
import com.debatecoach.app.visual.VisualConfig
import com.debatecoach.app.visual.VisualSignalTrack
import java.io.File
import java.io.IOException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class UploadManagerTest {
    private val audio = File.createTempFile("rec", ".m4a").apply { writeBytes(ByteArray(1024)); deleteOnExit() }
    private val online = MutableStateFlow(true)
    private val connectivity = object : Connectivity { override val online = this@UploadManagerTest.online }

    private val track: VisualSignalTrack = TrackBuilder().apply { appendEmpty(0.1) }.build(
        "", Source("android", "v", "other", RuntimeInfo("mediapipe-tasks-vision", "1.0.0", "CPU"), VisualConfig.MODELS, "full", 10.0),
        Capture(640, 360, false, "anatomical", 10), 150, 1.0, Calibration(false, null, 0, 0.0, "skipped"),
        TrackContext("camera_audience", false), SetupCheck(true, true, "ok", "ok"),
    )

    private class Audio : AudioUploader {
        val puts = mutableListOf<String>()
        var failures: MutableList<Exception> = mutableListOf()
        override suspend fun put(url: String, headers: Map<String, String>, file: File, onProgress: (Long, Long) -> Unit) {
            puts += url
            if (failures.isNotEmpty()) throw failures.removeAt(0)
            onProgress(file.length(), file.length())
        }
    }

    private class Tracks : TrackUploader {
        val uploads = mutableListOf<String>()
        var fail = false
        override suspend fun upload(sessionId: String, track: VisualSignalTrack): Int {
            uploads += sessionId
            if (fail) throw IllegalStateException("gave up")
            return track.frameCount
        }
    }

    private fun TestScope.manager(backend: FakeBackend, audio: Audio = Audio(), tracks: Tracks = Tracks()) =
        UploadManager(backend, audio, tracks, connectivity, this, retryDelaysMs = listOf(10, 10, 10))

    private fun job(video: VideoPlan = VideoPlan.None, title: String? = null, motion: String? = null) =
        UploadJob(audio, "audio/mp4", title, motion, video)

    @Test
    fun `with no video it creates, PUTs the audio and starts bodyless, exactly the website path`() = runTest {
        val backend = FakeBackend()
        val audioUp = Audio()
        val m = manager(backend, audioUp)
        m.start(job(title = "Round 2", motion = "carbon-tax"))
        advanceUntilIdle()
        assertEquals(UploadState.Done("s-new"), m.state.value)
        assertEquals(
            listOf("createSession:audio/mp4:Round 2:carbon-tax:false", "startSession:s-new:null:null"),
            backend.calls,
        )
        assertEquals(listOf("https://upload.test/put"), audioUp.puts)
    }

    @Test
    fun `a captured track is uploaded, then start reports it uploaded`() = runTest {
        val backend = FakeBackend()
        val tracks = Tracks()
        val m = manager(backend, tracks = tracks)
        m.start(job(VideoPlan.Track(track)))
        advanceUntilIdle()
        assertEquals(listOf("s-new"), tracks.uploads)
        assertEquals("startSession:s-new:uploaded:null", backend.calls.last())
        assertTrue(backend.calls.first().endsWith(":true"))
    }

    @Test
    fun `a track that can't be uploaded is reported as upload_failed, and the session still starts`() = runTest {
        val backend = FakeBackend()
        val m = manager(backend, tracks = Tracks().apply { fail = true })
        m.start(job(VideoPlan.Track(track)))
        advanceUntilIdle()
        assertEquals("startSession:s-new:unavailable:upload_failed", backend.calls.last())
        assertEquals(UploadState.Done("s-new"), m.state.value)
    }

    @Test
    fun `an unavailable reason goes to start as-is`() = runTest {
        for (reason in UnavailableReason.entries) {
            val backend = FakeBackend()
            val m = manager(backend)
            m.start(job(VideoPlan.Unavailable(reason)))
            advanceUntilIdle()
            assertEquals("startSession:s-new:unavailable:${reason.wire}", backend.calls.last())
        }
    }

    @Test
    fun `with video analysis off on the backend, the track is skipped and start is bodyless`() = runTest {
        val backend = FakeBackend().apply {
            createSessionHandler = { _, _, _, _ -> com.debatecoach.app.core.model.SessionCreated("s-off", "created", "https://u", emptyMap(), 900, "not_requested") }
        }
        val tracks = Tracks()
        val m = manager(backend, tracks = tracks)
        m.start(job(VideoPlan.Track(track)))
        advanceUntilIdle()
        assertTrue(tracks.uploads.isEmpty())
        assertEquals("startSession:s-off:null:null", backend.calls.last())
    }

    @Test
    fun `a flaky connection during the audio upload is retried`() = runTest {
        val backend = FakeBackend()
        val audioUp = Audio().apply { failures = mutableListOf(UploadNetworkException(IOException("reset")), ApiException(503, "busy")) }
        val m = manager(backend, audioUp)
        m.start(job())
        advanceUntilIdle()
        assertEquals(3, audioUp.puts.size)
        assertEquals(UploadState.Done("s-new"), m.state.value)
    }

    @Test
    fun `after a failure, Try again resumes without creating a second session`() = runTest {
        val backend = FakeBackend()
        val audioUp = Audio().apply { failures = MutableList(4) { UploadNetworkException(IOException("down")) } }
        val m = manager(backend, audioUp)
        m.start(job())
        advanceUntilIdle()
        assertTrue(m.state.value is UploadState.Failed)
        assertEquals(1, backend.calls.count { it.startsWith("createSession") })

        m.retry()
        advanceUntilIdle()
        assertEquals(UploadState.Done("s-new"), m.state.value)
        assertEquals("still one session", 1, backend.calls.count { it.startsWith("createSession") })
    }

    @Test
    fun `a start whose response was lost counts as started`() = runTest {
        var first = true
        val backend = FakeBackend().apply {
            startSessionHandler = { id, _ ->
                if (first) {
                    first = false
                    throw NetworkException(IOException("lost"))
                }
                session(id, status = "queued")
            }
            getSessionHandler = { session(it, status = "queued") }
        }
        val m = manager(backend)
        m.start(job())
        advanceUntilIdle()
        assertEquals(UploadState.Done("s-new"), m.state.value)
        assertEquals(1, backend.calls.count { it.startsWith("startSession") })
    }

    @Test
    fun `waits for a connection before starting`() = runTest {
        online.value = false
        val backend = FakeBackend()
        val m = manager(backend)
        m.start(job())
        advanceUntilIdle()
        assertEquals(UploadState.Running(UploadState.Step.WAITING_FOR_CONNECTION, null), m.state.value)
        assertTrue(backend.calls.isEmpty())
        online.value = true
        advanceUntilIdle()
        assertEquals(UploadState.Done("s-new"), m.state.value)
    }

    @Test
    fun `a server rejection is shown with the server's message`() = runTest {
        val backend = FakeBackend().apply { createSessionHandler = { _, _, _, _ -> throw ApiException(422, "Unknown motion.") } }
        val m = manager(backend)
        m.start(job(motion = "nope"))
        advanceUntilIdle()
        assertEquals(UploadState.Failed("Unknown motion."), m.state.value)
    }
}
