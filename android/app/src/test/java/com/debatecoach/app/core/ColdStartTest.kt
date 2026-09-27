package com.debatecoach.app.core

import com.debatecoach.app.core.auth.TokenStore
import com.debatecoach.app.core.net.ApiClient
import com.debatecoach.app.core.net.ApiClient.Method
import com.debatecoach.app.core.net.ApiException
import com.debatecoach.app.core.net.AppJson
import com.debatecoach.app.core.net.COLD_AFTER_MS
import com.debatecoach.app.core.net.ColdStartTracker
import com.debatecoach.app.core.net.Network
import com.debatecoach.app.core.net.PROGRESS_REPORT_TIMEOUT_MS
import com.debatecoach.app.core.net.TIMEOUT_MESSAGE
import com.debatecoach.app.testing.FakeCipher
import com.debatecoach.app.testing.MemoryStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.currentTime
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import retrofit2.Response

/**
 * web/lib/api.ts's cold-start rule, in virtual time: while the backend
 * may be cold (nothing heard yet, or nothing for 10 minutes) a request
 * gets at least 60s and a GET that still times out is retried once;
 * once warm, the normal 30s and no retry. POSTs are never retried.
 */
class ColdStartTest {
    private var clock = 0L
    private val coldStart = ColdStartTracker { clock }
    private val api = ApiClient(
        Network.service("http://localhost:1/", Network.okHttp(TokenStore(MemoryStore(), FakeCipher()))),
        TokenStore(MemoryStore(), FakeCipher()),
        coldStart,
        AppJson,
        CoroutineScope(Dispatchers.Unconfined),
    )

    /** A fake call that answers after [takesMs] of (virtual) time. */
    private fun answering(takesMs: Long, calls: MutableList<Long>, now: () -> Long): suspend () -> Response<String> = {
        calls += now()
        delay(takesMs)
        Response.success("ok")
    }

    @Test
    fun `the first request waits up to 60 seconds for a cold backend`() = runTest {
        val calls = mutableListOf<Long>()
        val result = api.request(Method.GET, call = answering(45_000, calls) { currentTime })
        assertEquals("ok", result)
        assertEquals(1, calls.size)
        assertFalse(coldStart.mayBeCold())
    }

    @Test
    fun `a cold GET that times out is retried once, then succeeds`() = runTest {
        val calls = mutableListOf<Long>()
        var attempt = 0
        val result = api.request(Method.GET) {
            calls += currentTime
            attempt++
            delay(if (attempt == 1) 70_000 else 5_000)
            Response.success("ok")
        }
        assertEquals("ok", result)
        assertEquals(listOf(0L, 60_000L), calls)
    }

    @Test
    fun `a cold GET that times out twice is a 408 with the website's message`() = runTest {
        val calls = mutableListOf<Long>()
        try {
            api.request(Method.GET, call = answering(90_000, calls) { currentTime })
            fail()
        } catch (e: ApiException) {
            assertEquals(408, e.status)
            assertEquals(TIMEOUT_MESSAGE, e.message)
        }
        assertEquals(2, calls.size)
        assertEquals(120_000L, currentTime)
    }

    @Test
    fun `a cold POST gets the longer timeout but is never retried`() = runTest {
        val calls = mutableListOf<Long>()
        assertEquals("ok", api.request(Method.POST, call = answering(50_000, calls) { currentTime }))

        clock += COLD_AFTER_MS + 1
        calls.clear()
        try {
            api.request(Method.POST, call = answering(90_000, calls) { currentTime })
            fail()
        } catch (e: ApiException) {
            assertEquals(408, e.status)
        }
        assertEquals(1, calls.size)
    }

    @Test
    fun `once warm, requests get 30 seconds and no retry`() = runTest {
        coldStart.markResponse()
        val calls = mutableListOf<Long>()
        try {
            api.request(Method.GET, call = answering(45_000, calls) { currentTime })
            fail()
        } catch (e: ApiException) {
            assertEquals(408, e.status)
        }
        assertEquals(1, calls.size)
        assertEquals(30_000L, currentTime)
    }

    @Test
    fun `after 10 minutes without a response the backend counts as cold again`() = runTest {
        coldStart.markResponse()
        clock += COLD_AFTER_MS
        assertFalse("exactly 10 minutes is still warm", coldStart.mayBeCold())
        clock += 1
        assertTrue(coldStart.mayBeCold())
        val calls = mutableListOf<Long>()
        assertEquals("ok", api.request(Method.GET, call = answering(45_000, calls) { currentTime }))
    }

    @Test
    fun `a longer timeout a call asks for is kept`() = runTest {
        coldStart.markResponse()
        val calls = mutableListOf<Long>()
        assertEquals("ok", api.request(Method.POST, timeoutMs = PROGRESS_REPORT_TIMEOUT_MS, call = answering(100_000, calls) { currentTime }))
    }

    @Test
    fun `the warm-up call marks the backend warm and never throws`() = runBlocking {
        val server = MockWebServer()
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"status":"ok"}"""))
        server.start()
        val tracker = ColdStartTracker(System::currentTimeMillis)
        val warm = ApiClient(
            Network.service(server.url("/").toString(), Network.okHttp(TokenStore(MemoryStore(), FakeCipher()))),
            TokenStore(MemoryStore(), FakeCipher()),
            tracker,
            AppJson,
            CoroutineScope(Dispatchers.IO),
        )
        warm.warmUp()
        val deadline = System.currentTimeMillis() + 5_000
        while (tracker.mayBeCold() && System.currentTimeMillis() < deadline) Thread.sleep(20)
        assertFalse(tracker.mayBeCold())
        assertEquals("/health", server.takeRequest().path)
        server.shutdown()

        // Unreachable: nothing thrown, still cold.
        val unreachable = ColdStartTracker(System::currentTimeMillis)
        ApiClient(
            Network.service("http://127.0.0.1:1/", Network.okHttp(TokenStore(MemoryStore(), FakeCipher()))),
            TokenStore(MemoryStore(), FakeCipher()),
            unreachable,
            AppJson,
            CoroutineScope(Dispatchers.IO),
        ).warmUp()
        Thread.sleep(300)
        assertTrue(unreachable.mayBeCold())
    }
}
