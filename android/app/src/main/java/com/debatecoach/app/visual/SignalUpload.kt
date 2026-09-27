package com.debatecoach.app.visual

import com.debatecoach.app.core.net.ApiClient
import com.debatecoach.app.core.net.ApiException
import java.io.ByteArrayOutputStream
import java.util.zip.GZIPOutputStream
import kotlinx.coroutines.delay
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody

class VisualSignalUploadError(message: String, cause: Throwable?) : Exception(message, cause)

/**
 * web/features/video-analysis/upload.ts: serialize (TrackJson, byte-
 * identical to the web), gzip, PUT, with the same retry schedule and
 * the same fail-fast rule for requests the server says are invalid.
 */
class SignalUploader(private val api: ApiClient) {

    /** Whether a failed attempt is worth retrying (upload.ts isRetryable). */
    fun isRetryable(error: Throwable): Boolean {
        // Not an ApiException: the request never reached the server.
        if (error !is ApiException) return true
        if (error.status == 408 || error.status == 429) return true
        if (error.status in 400..499) return false
        return true
    }

    /** The exact bytes sent: gzip(JSON.stringify(track)). */
    fun encode(track: VisualSignalTrack): ByteArray {
        val json = TrackJson.encode(track).toByteArray(Charsets.UTF_8)
        val out = ByteArrayOutputStream()
        GZIPOutputStream(out).use { it.write(json) }
        return out.toByteArray()
    }

    /**
     * Uploads with retry. Returns the frame count the server
     * acknowledged, or throws [VisualSignalUploadError] once retries are
     * exhausted, or at once on a non-retryable failure.
     */
    suspend fun uploadWithRetry(
        sessionId: String,
        track: VisualSignalTrack,
        delaysMs: List<Long> = VisualConfig.UPLOAD_RETRY_DELAYS_MS,
    ): Int {
        val body = encode(track.copy(sessionId = sessionId))
        var lastError: Throwable? = null
        var attempts = 0
        for (attempt in 0..delaysMs.size) {
            attempts += 1
            try {
                val ack = api.request(ApiClient.Method.PUT) {
                    api.service.uploadVisualSignals(sessionId, "gzip", body.toRequestBody(JSON))
                }
                return ack.frames
            } catch (error: Exception) {
                if (error is kotlinx.coroutines.CancellationException) throw error
                lastError = error
                if (!isRetryable(error)) break
                if (attempt < delaysMs.size) delay(delaysMs[attempt])
            }
        }
        throw VisualSignalUploadError(
            "Visual signal upload failed after $attempts attempt${if (attempts == 1) "" else "s"}.",
            lastError,
        )
    }

    private companion object {
        val JSON = "application/json".toMediaType()
    }
}
