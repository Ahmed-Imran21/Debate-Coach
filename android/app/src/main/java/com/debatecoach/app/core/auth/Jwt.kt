package com.debatecoach.app.core.auth

import java.util.Base64
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull

/**
 * Reads a JWT's `exp` without verifying it (web/lib/jwt.ts): for
 * scheduling only, never for trust. Milliseconds, or null.
 */
fun tokenExpiresAt(token: String?): Long? {
    if (token == null) return null
    return try {
        val payload = token.split(".").getOrNull(1)?.takeIf { it.isNotEmpty() } ?: return null
        val bytes = Base64.getUrlDecoder().decode(payload.padEnd((payload.length + 3) / 4 * 4, '='))
        val exp = Json.parseToJsonElement(bytes.decodeToString()).jsonObject["exp"]?.jsonPrimitive
        val seconds = exp?.longOrNull ?: exp?.content?.toDoubleOrNull()?.toLong()
        seconds?.times(1000)
    } catch (_: Exception) {
        null
    }
}

/** lib/heartbeat.ts's isLive: a token whose exp is still in the future. */
fun isLive(token: String?, nowMs: Long): Boolean {
    val expiresAt = tokenExpiresAt(token) ?: return false
    return expiresAt > nowMs
}
