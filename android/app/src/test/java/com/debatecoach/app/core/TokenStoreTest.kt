package com.debatecoach.app.core

import com.debatecoach.app.core.auth.TokenStore
import com.debatecoach.app.core.auth.isLive
import com.debatecoach.app.core.auth.tokenExpiresAt
import com.debatecoach.app.core.model.Tokens
import com.debatecoach.app.testing.FakeCipher
import com.debatecoach.app.testing.MemoryStore
import com.debatecoach.app.testing.jwt
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class TokenStoreTest {
    @Test
    fun `tokens are stored only as ciphertext`() {
        val kv = MemoryStore()
        val store = TokenStore(kv, FakeCipher())
        store.store(Tokens("the-access-token", "the-refresh-token"))

        assertEquals(setOf(TokenStore.ACCESS_KEY, TokenStore.REFRESH_KEY), kv.values.keys)
        kv.values.values.forEach { stored ->
            assertTrue(stored.startsWith("enc:"))
            assertFalse(stored.contains("access-token") || stored.contains("refresh-token"))
        }
        assertEquals("the-access-token", store.accessToken)
        assertEquals("the-refresh-token", store.refreshToken)
        assertTrue(store.signedIn.value)
    }

    @Test
    fun `tokens survive a restart and clear removes both`() {
        val kv = MemoryStore()
        TokenStore(kv, FakeCipher()).store(Tokens("a", "r"))

        val restarted = TokenStore(kv, FakeCipher())
        assertTrue(restarted.signedIn.value)
        assertEquals("a", restarted.accessToken)

        restarted.clear()
        assertNull(restarted.accessToken)
        assertNull(restarted.refreshToken)
        assertFalse(restarted.signedIn.value)
        assertTrue(kv.values.isEmpty())
    }

    @Test
    fun `tokens that can't be decrypted (keystore key gone) count as signed out`() {
        val kv = MemoryStore()
        TokenStore(kv, FakeCipher()).store(Tokens("a", "r"))
        val broken = FakeCipher().apply { failDecrypt = true }
        val store = TokenStore(kv, broken)
        assertFalse(store.signedIn.value)
        assertNull(store.accessToken)
    }

    @Test
    fun `jwt expiry is read without verifying, like lib-jwt`() {
        assertEquals(1_900_000_000_000L, tokenExpiresAt(jwt(1_900_000_000)))
        assertNull(tokenExpiresAt(null))
        assertNull(tokenExpiresAt("not-a-jwt"))
        assertNull(tokenExpiresAt("a.@@@.c"))
        assertTrue(isLive(jwt(2_000), nowMs = 1_999_999))
        assertFalse(isLive(jwt(2_000), nowMs = 2_000_000))
        assertFalse(isLive(null, 0))
    }
}
