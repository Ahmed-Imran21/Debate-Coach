package com.debatecoach.app.core

import com.debatecoach.app.core.net.ApiException
import com.debatecoach.app.core.util.HEARTBEAT_INTERVAL_MS
import com.debatecoach.app.core.util.Heartbeat
import com.debatecoach.app.testing.jwt
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

/** lib/heartbeat.ts: only with a live token, never refreshing, stopped for good by a 401. */
class HeartbeatTest {
    @Test
    fun `sends now and then every 60 seconds while the token is live`() = runTest {
        var sent = 0
        val beat = Heartbeat(backgroundScope, getToken = { jwt(10_000) }, send = { sent++ }, now = { 0L })
        beat.start()
        runCurrent()
        assertEquals(1, sent)
        advanceTimeBy(HEARTBEAT_INTERVAL_MS)
        runCurrent()
        assertEquals(2, sent)
        beat.pause()
        advanceTimeBy(5 * HEARTBEAT_INTERVAL_MS)
        assertEquals(2, sent)
    }

    @Test
    fun `never starts or continues with an expired token`() = runTest {
        var now = 0L
        var sent = 0
        val beat = Heartbeat(backgroundScope, getToken = { jwt(90) }, send = { sent++ }, now = { now })
        beat.start()
        runCurrent()
        assertEquals(1, sent)
        now = 90_000 // the token's exp
        advanceTimeBy(HEARTBEAT_INTERVAL_MS)
        runCurrent()
        assertEquals(1, sent)

        var sentExpired = 0
        Heartbeat(backgroundScope, getToken = { jwt(1) }, send = { sentExpired++ }, now = { 5_000L }).start()
        runCurrent()
        assertEquals(0, sentExpired)
    }

    @Test
    fun `a 401 stops it for good`() = runTest {
        var sent = 0
        val beat = Heartbeat(backgroundScope, getToken = { jwt(10_000) }, send = { sent++; throw ApiException(401, "no") }, now = { 0L })
        beat.start()
        runCurrent()
        advanceTimeBy(3 * HEARTBEAT_INTERVAL_MS)
        beat.start()
        runCurrent()
        assertEquals(1, sent)
        assertFalse(beat.running)
    }

    @Test
    fun `other failures are ignored and it keeps going`() = runTest {
        var sent = 0
        val beat = Heartbeat(backgroundScope, getToken = { jwt(10_000) }, send = { sent++; throw ApiException(503, "busy") }, now = { 0L })
        beat.start()
        runCurrent()
        advanceTimeBy(HEARTBEAT_INTERVAL_MS)
        runCurrent()
        assertEquals(2, sent)
    }
}
