package com.debatecoach.app.visual

import com.debatecoach.app.core.auth.TokenStore
import com.debatecoach.app.core.model.Tokens
import com.debatecoach.app.core.net.ApiClient
import com.debatecoach.app.core.net.ApiException
import com.debatecoach.app.core.net.AppJson
import com.debatecoach.app.core.net.ColdStartTracker
import com.debatecoach.app.core.net.Network
import com.debatecoach.app.core.net.NetworkException
import com.debatecoach.app.testing.FakeCipher
import com.debatecoach.app.testing.MemoryStore
import java.io.IOException
import java.util.zip.GZIPInputStream
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

/** features/video-analysis/upload.ts and its tests, on Android. */
class SignalUploadTest {
    private val server = MockWebServer()
    private lateinit var uploader: SignalUploader

    private val track by lazy {
        val b = TrackBuilder()
        b.appendSample(0.1, FrameSample(faceCount = 1.0, headYaw = 2.34, inferMs = 30.2))
        b.appendEmpty(0.2)
        b.build(
            sessionId = "",
            source = Source("android", "android-1.0.0", "other", RuntimeInfo("mediapipe-tasks-vision", "1.0.0", "GPU"), VisualConfig.MODELS, "full", 11.3),
            capture = Capture(640, 360, false, "anatomical", 10),
            clockUncertaintyMs = 150,
            durationS = 0.3,
            calibration = Calibration(false, null, 0, 0.0, "skipped"),
            context = TrackContext("camera_audience", false),
            setupCheck = SetupCheck(true, false, "ok", "ok"),
        )
    }

    @Before
    fun setUp() {
        server.start()
        val tokens = TokenStore(MemoryStore(), FakeCipher()).apply { store(Tokens("a", "r")) }
        val api = ApiClient(Network.service(server.url("/").toString(), Network.okHttp(tokens)), tokens, ColdStartTracker { 0L }, AppJson, CoroutineScope(Dispatchers.IO))
        api.javaClass // warm: the cold-start retry isn't what these tests are about
        uploader = SignalUploader(api)
    }

    @After
    fun tearDown() {
        runCatching { server.shutdown() }
    }

    @Test
    fun `the body is gzip of the byte-identical JSON, with the session id filled in`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"status":"received","frames":2}"""))
        assertEquals(2, uploader.uploadWithRetry("sess-1", track, listOf(1, 1, 1)))
        val request = server.takeRequest()
        assertEquals("PUT", request.method)
        assertEquals("/v1/sessions/sess-1/visual-signals", request.path)
        assertEquals("gzip", request.getHeader("Content-Encoding"))
        assertTrue(request.getHeader("Content-Type")!!.startsWith("application/json"))
        val json = GZIPInputStream(request.body.inputStream()).readBytes().decodeToString()
        assertEquals(TrackJson.encode(track.copy(sessionId = "sess-1")), json)
        assertTrue(json.contains("\"platform\":\"android\""))
        assertTrue(json.contains("\"head_yaw\":[2.3,null]"))
    }

    private fun attemptsFor(vararg responses: MockResponse): Pair<Int, Throwable?> = runBlocking {
        responses.forEach(server::enqueue)
        val error = try {
            uploader.uploadWithRetry("s1", track, listOf(1, 1, 1))
            null
        } catch (e: VisualSignalUploadError) {
            e
        }
        server.requestCount to error
    }

    @Test
    fun `a 422, 409 or 413 fails at once, one attempt`() {
        for (code in listOf(422, 409, 413)) {
            tearDown(); server.let { }
            val fresh = MockWebServer().also { it.start() }
            val tokens = TokenStore(MemoryStore(), FakeCipher()).apply { store(Tokens("a", "r")) }
            uploader = SignalUploader(ApiClient(Network.service(fresh.url("/").toString(), Network.okHttp(tokens)), tokens, ColdStartTracker { 0L }, AppJson, CoroutineScope(Dispatchers.IO)))
            repeat(4) { fresh.enqueue(MockResponse().setResponseCode(code)) }
            val error = runBlocking {
                try {
                    uploader.uploadWithRetry("s1", track, listOf(1, 1, 1)); null
                } catch (e: VisualSignalUploadError) {
                    e
                }
            }
            assertEquals("status $code", 1, fresh.requestCount)
            assertEquals("Visual signal upload failed after 1 attempt.", error!!.message)
            fresh.shutdown()
        }
    }

    @Test
    fun `429, 408 and 500 are retried through the whole schedule`() {
        val (count, error) = attemptsFor(*Array(4) { MockResponse().setResponseCode(500) })
        assertEquals(4, count)
        assertEquals("Visual signal upload failed after 4 attempts.", error!!.message)
    }

    @Test
    fun `succeeds on a later attempt`() {
        val (count, error) = attemptsFor(
            MockResponse().setResponseCode(429),
            MockResponse().setResponseCode(408),
            MockResponse().setResponseCode(200).setBody("""{"status":"received","frames":2}"""),
        )
        assertEquals(3, count)
        assertEquals(null, error)
    }

    @Test
    fun `retry classification matches the web's isRetryable`() {
        assertTrue(uploader.isRetryable(NetworkException(IOException("down"))))
        assertTrue(uploader.isRetryable(ApiException(408, "")))
        assertTrue(uploader.isRetryable(ApiException(429, "")))
        assertTrue(uploader.isRetryable(ApiException(500, "")))
        assertTrue(uploader.isRetryable(ApiException(503, "")))
        assertFalse(uploader.isRetryable(ApiException(400, "")))
        assertFalse(uploader.isRetryable(ApiException(422, "")))
        assertFalse(uploader.isRetryable(ApiException(413, "")))
    }
}
