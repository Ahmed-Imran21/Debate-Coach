package com.debatecoach.app.core.auth

import android.content.Context
import android.content.SharedPreferences
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.debatecoach.app.core.model.Tokens
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Encrypts short strings. The app's one implementation is [KeystoreCipher]. */
interface TokenCipher {
    fun encrypt(plain: String): String
    /** Null when the ciphertext can't be decrypted (key gone, data corrupt). */
    fun decrypt(encoded: String): String?
}

/** A tiny key-value store, so tests don't need Android. */
interface KeyValueStore {
    fun get(key: String): String?
    fun put(values: Map<String, String?>)
}

class SharedPreferencesStore(private val prefs: SharedPreferences) : KeyValueStore {
    override fun get(key: String): String? = prefs.getString(key, null)

    override fun put(values: Map<String, String?>) {
        prefs.edit().apply {
            values.forEach { (k, v) -> if (v == null) remove(k) else putString(k, v) }
        }.commit()
    }
}

/**
 * The access and refresh tokens, encrypted at rest with a key that
 * never leaves the Android Keystore. Mirrors lib/api.ts's storeTokens
 * and clearTokens: every token change goes through [store] or [clear].
 *
 * The refresh token is what the backend's 30-day session cap is
 * measured on (it carries the session's start); this class only
 * keeps it safe, the backend enforces the cap.
 */
class TokenStore(private val kv: KeyValueStore, private val cipher: TokenCipher) {
    private val _signedIn = MutableStateFlow(read(ACCESS_KEY) != null)

    /** True while an access token is stored (it may be expired; a refresh decides). */
    val signedIn: StateFlow<Boolean> = _signedIn.asStateFlow()

    @Volatile private var cachedAccess: String? = null
    @Volatile private var cachedRefresh: String? = null

    val accessToken: String?
        get() = cachedAccess ?: read(ACCESS_KEY)?.also { cachedAccess = it }

    val refreshToken: String?
        get() = cachedRefresh ?: read(REFRESH_KEY)?.also { cachedRefresh = it }

    @Synchronized
    fun store(tokens: Tokens) {
        kv.put(mapOf(ACCESS_KEY to cipher.encrypt(tokens.accessToken), REFRESH_KEY to cipher.encrypt(tokens.refreshToken)))
        cachedAccess = tokens.accessToken
        cachedRefresh = tokens.refreshToken
        _signedIn.value = true
    }

    @Synchronized
    fun clear() {
        kv.put(mapOf(ACCESS_KEY to null, REFRESH_KEY to null))
        cachedAccess = null
        cachedRefresh = null
        _signedIn.value = false
    }

    private fun read(key: String): String? {
        val stored = kv.get(key) ?: return null
        return cipher.decrypt(stored)
    }

    companion object {
        const val ACCESS_KEY = "dc.access"
        const val REFRESH_KEY = "dc.refresh"

        fun create(context: Context): TokenStore = TokenStore(
            SharedPreferencesStore(context.getSharedPreferences("dc.tokens", Context.MODE_PRIVATE)),
            KeystoreCipher(),
        )
    }
}

/**
 * AES-256-GCM with a non-exportable key in the Android Keystore.
 * Stored form: base64(iv) + ":" + base64(ciphertext+tag).
 */
class KeystoreCipher(private val alias: String = "dc.token-key") : TokenCipher {
    private fun key(): SecretKey {
        val keyStore = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        (keyStore.getKey(alias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE)
        generator.init(
            KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return generator.generateKey()
    }

    override fun encrypt(plain: String): String {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val sealed = cipher.doFinal(plain.toByteArray(Charsets.UTF_8))
        return b64(cipher.iv) + ":" + b64(sealed)
    }

    override fun decrypt(encoded: String): String? = try {
        val (iv, sealed) = encoded.split(":", limit = 2).map { Base64.decode(it, Base64.NO_WRAP) }
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, iv))
        String(cipher.doFinal(sealed), Charsets.UTF_8)
    } catch (_: Exception) {
        null
    }

    private fun b64(bytes: ByteArray) = Base64.encodeToString(bytes, Base64.NO_WRAP)

    private companion object {
        const val KEYSTORE = "AndroidKeyStore"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}
