package com.debatecoach.app.core

import com.debatecoach.app.core.auth.TokenStore
import com.debatecoach.app.core.model.Tokens
import com.debatecoach.app.core.net.ApiClient
import com.debatecoach.app.core.net.ApiClient.Method
import com.debatecoach.app.core.net.ApiException
import com.debatecoach.app.core.net.AppJson
import com.debatecoach.app.core.net.ColdStartTracker
import com.debatecoach.app.core.net.GENERIC_ERROR_MESSAGE
import com.debatecoach.app.core.net.Network
import com.debatecoach.app.core.net.NetworkException
import com.debatecoach.app.core.net.SERVER_ERROR_MESSAGE
import com.debatecoach.app.core.net.SignOutReason
import com.debatecoach.app.testing.FakeCipher
import com.debatecoach.app.testing.MemoryStore
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

/**
 * The request executor against a real HTTP server: the same behaviour
 * as web/lib/api.ts's request() and refreshTokens().
 */
class ApiClientTest {
    private val server = MockWebServer()
    private lateinit var tokens: TokenStore
    private lateinit var api: ApiClient
    private lateinit var backend: RemoteBackend

    @Before
    fun setUp() {
        server.start()
        tokens = TokenStore(MemoryStore(), FakeCipher())
        val http = Network.okHttp(tokens)
        api = ApiClient(Network.service(server.url("/").toString(), http), tokens, ColdStartTracker { 0L }, AppJson, CoroutineScope(Dispatchers.IO))
        backend = RemoteBackend(api, tokens)
    }

    @After
    fun tearDown() {
        runCatching { server.shutdown() }
    }

    private fun json(code: Int, body: String) = MockResponse().setResponseCode(code).setHeader("Content-Type", "application/json").setBody(body)

    private val sessionsJson = """[{"id":"s1","title":null,"status":"completed","created_at":"2026-09-26T10:00:00Z"}]"""

    @Test
    fun `sends the bearer token, and none when signing in`() = runBlocking {
        tokens.store(Tokens("access-1", "refresh-1"))
        server.enqueue(json(200, sessionsJson))
        backend.listSessions()
        assertEquals("Bearer access-1", server.takeRequest().getHeader("Authorization"))

        server.enqueue(json(200, """{"access_token":"a2","refresh_token":"r2","token_type":"bearer"}"""))
        backend.signIn("a@example.com", "pw")
        val login = server.takeRequest()
        assertEquals("/v1/auth/login", login.path)
        assertNull(login.getHeader("Authorization"))
        assertNull("the internal marker header never leaves the phone", login.getHeader("X-DC-No-Auth"))
        assertEquals("a2", tokens.accessToken)
    }

    @Test
    fun `error messages come from the backend's detail, like the website`() = runBlocking {
        suspend fun messageFor(response: MockResponse): String {
            server.enqueue(response)
            return try {
                backend.listSessions()
                fail("expected an error")
                ""
            } catch (e: ApiException) {
                e.message!!
            }
        }
        assertEquals("Unknown motion.", messageFor(json(422, """{"detail":"Unknown motion."}""")))
        assertEquals("Value error, bad", messageFor(json(422, """{"detail":[{"loc":["body"],"msg":"Value error, bad"}]}""")))
        assertEquals(SERVER_ERROR_MESSAGE, messageFor(MockResponse().setResponseCode(502).setBody("<html>bad gateway</html>")))
        assertEquals(GENERIC_ERROR_MESSAGE, messageFor(MockResponse().setResponseCode(404)))
    }

    @Test
    fun `a 401 refreshes once and replays with the new token`() = runBlocking {
        tokens.store(Tokens("old-access", "refresh-1"))
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"detail":"expired"}"""))
        server.enqueue(json(200, """{"access_token":"new-access","refresh_token":"refresh-2","token_type":"bearer"}"""))
        server.enqueue(json(200, sessionsJson))

        val rows = backend.listSessions()

        assertEquals(1, rows.size)
        assertEquals("Bearer old-access", server.takeRequest().getHeader("Authorization"))
        val refresh = server.takeRequest()
        assertEquals("/v1/auth/refresh", refresh.path)
        assertEquals("""{"refresh_token":"refresh-1"}""", refresh.body.readUtf8())
        assertNull(refresh.getHeader("Authorization"))
        assertEquals("Bearer new-access", server.takeRequest().getHeader("Authorization"))
        assertEquals("refresh-2", tokens.refreshToken)
    }

    @Test
    fun `a refused refresh clears the tokens and ends the session as expired`() = runBlocking {
        tokens.store(Tokens("old", "refresh-past-its-30-days"))
        val ended = async(Dispatchers.Default) { withTimeout(5_000) { api.sessionEnded.first() } }
        Thread.sleep(50)
        server.enqueue(MockResponse().setResponseCode(401))
        server.enqueue(json(401, """{"detail":"Your session has expired. Please log in again."}"""))

        try {
            backend.listSessions()
            fail("expected 401")
        } catch (e: ApiException) {
            assertEquals(401, e.status)
        }
        assertNull(tokens.accessToken)
        assertNull(tokens.refreshToken)
        assertFalse(tokens.signedIn.value)
        assertEquals(SignOutReason.EXPIRED, ended.await())
        assertEquals(2, server.requestCount)
    }

    @Test
    fun `a refresh that can't reach the server is treated as refused`() = runBlocking {
        tokens.store(Tokens("old", "r"))
        server.dispatcher = object : okhttp3.mockwebserver.Dispatcher() {
            override fun dispatch(request: okhttp3.mockwebserver.RecordedRequest): MockResponse =
                if (request.path == "/v1/auth/refresh") MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_START)
                else MockResponse().setResponseCode(401)
        }
        try {
            backend.listSessions()
            fail()
        } catch (e: ApiException) {
            assertEquals(401, e.status)
        }
        assertNull(tokens.accessToken)
    }

    @Test
    fun `a refresh answered with an unreadable body also ends the session`() = runBlocking {
        tokens.store(Tokens("old", "r"))
        server.enqueue(MockResponse().setResponseCode(401))
        server.enqueue(MockResponse().setResponseCode(200).setBody("<html>proxy</html>"))
        try {
            backend.listSessions()
            fail()
        } catch (e: ApiException) {
            assertEquals(401, e.status)
        }
        assertNull(tokens.accessToken)
    }

    @Test
    fun `an unreadable success body is an error with a message, not a crash`() = runBlocking {
        tokens.store(Tokens("a", "r"))
        server.enqueue(MockResponse().setResponseCode(200).setBody("not json"))
        try {
            backend.listSessions()
            fail()
        } catch (e: ApiException) {
            assertEquals(GENERIC_ERROR_MESSAGE, e.message)
        }
    }

    @Test
    fun `the replayed request is never refreshed a second time`() = runBlocking {
        tokens.store(Tokens("a1", "r1"))
        server.enqueue(MockResponse().setResponseCode(401))
        server.enqueue(json(200, """{"access_token":"a2","refresh_token":"r2","token_type":"bearer"}"""))
        server.enqueue(json(401, """{"detail":"Incorrect password."}"""))

        try {
            backend.deleteAccount("wrong")
            fail()
        } catch (e: ApiException) {
            assertEquals(401, e.status)
            assertEquals("Incorrect password.", e.message)
        }
        assertEquals(3, server.requestCount)
        assertEquals("still signed in after a wrong password", "a2", tokens.accessToken)
    }

    @Test
    fun `the heartbeat never refreshes a token`() = runBlocking {
        tokens.store(Tokens("expired-access", "r1"))
        server.enqueue(MockResponse().setResponseCode(401))
        try {
            backend.heartbeat()
            fail()
        } catch (e: ApiException) {
            assertEquals(401, e.status)
        }
        assertEquals(1, server.requestCount)
        assertEquals("expired-access", tokens.accessToken)
    }

    @Test
    fun `concurrent 401s share one refresh`() = runBlocking {
        tokens.store(Tokens("old", "r1"))
        server.dispatcher = object : okhttp3.mockwebserver.Dispatcher() {
            @Volatile var refreshes = 0
            override fun dispatch(request: okhttp3.mockwebserver.RecordedRequest): MockResponse = when {
                request.path == "/v1/auth/refresh" -> {
                    refreshes++
                    Thread.sleep(100)
                    json(200, """{"access_token":"new","refresh_token":"r2","token_type":"bearer"}""")
                }
                request.getHeader("Authorization") == "Bearer new" -> json(200, sessionsJson)
                else -> MockResponse().setResponseCode(401)
            }
        }
        (1..4).map { async(Dispatchers.IO) { backend.listSessions() } }.awaitAll()
        val refreshes = (0 until server.requestCount).map { server.takeRequest(1, TimeUnit.SECONDS)?.path }.count { it == "/v1/auth/refresh" }
        assertEquals(1, refreshes)
    }

    @Test
    fun `204 responses are fine`() = runBlocking {
        tokens.store(Tokens("a", "r"))
        server.enqueue(MockResponse().setResponseCode(204))
        backend.deleteSession("s1")
        assertEquals("DELETE", server.takeRequest().method)
    }

    @Test
    fun `a request that never reaches the server is a NetworkException`() = runBlocking {
        server.shutdown()
        try {
            backend.listSessions()
            fail()
        } catch (e: NetworkException) {
            assertTrue(true)
        }
    }

    @Test
    fun `start without a video outcome is the website's bodyless POST, with one it sends it`() = runBlocking {
        tokens.store(Tokens("a", "r"))
        val queued = """{"id":"s1","status":"queued","created_at":"2026-09-26T10:00:00Z"}"""
        server.enqueue(json(202, queued))
        server.enqueue(json(202, queued))
        backend.startSession("s1", null)
        backend.startSession("s1", com.debatecoach.app.core.model.VideoFinalize("unavailable", "camera_denied"))
        assertEquals(0L, server.takeRequest().bodySize)
        assertEquals("""{"video":{"status":"unavailable","reason":"camera_denied"}}""", server.takeRequest().body.readUtf8())
    }

    @Test
    fun `sessions are created as audio mp4, with video and motion only when asked`() = runBlocking {
        tokens.store(Tokens("a", "r"))
        val created = """{"id":"s1","status":"created","upload_url":"https://x","upload_headers":{"Content-Type":"audio/mp4"},"expires_in_seconds":900}"""
        server.enqueue(json(201, created))
        server.enqueue(json(201, created))
        backend.createSession("audio/mp4", null, null, videoRequested = false)
        backend.createSession("audio/mp4", "Round 2", "carbon-tax", videoRequested = true)
        // Absent keys are what the backend's defaults mean: no title, no video, no motion.
        assertEquals("""{"content_type":"audio/mp4"}""", server.takeRequest().body.readUtf8())
        assertEquals(
            """{"content_type":"audio/mp4","title":"Round 2","video_analysis":"requested","motion_id":"carbon-tax"}""",
            server.takeRequest().body.readUtf8(),
        )
    }
}
