package com.debatecoach.app.core.net

import com.debatecoach.app.core.auth.TokenStore
import com.debatecoach.app.core.model.ErrorBody
import com.debatecoach.app.core.model.RefreshRequest
import java.io.IOException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import retrofit2.Response

/** The server answered with an error (web: ApiError). [message] is safe to show. */
class ApiException(val status: Int, message: String) : Exception(message)

/** The request never reached the server (web: fetch() itself rejected). */
class NetworkException(cause: IOException) : Exception(cause.message, cause)

const val DEFAULT_TIMEOUT_MS = 30_000L
const val COLD_START_TIMEOUT_MS = 60_000L
const val COLD_AFTER_MS = 10 * 60_000L
const val PROGRESS_REPORT_TIMEOUT_MS = 120_000L

const val TIMEOUT_MESSAGE = "The request timed out. Check your connection and try again."
const val SERVER_ERROR_MESSAGE = "The server could not complete that request. Try again shortly."
const val GENERIC_ERROR_MESSAGE = "That request could not be completed."
const val UNREACHABLE_MESSAGE = "Could not reach the server. Check your connection and try again."

/**
 * Cloud Run scales the backend to zero, and the first request after
 * that waits ~27s for an instance. While the backend may be cold (no
 * response yet since the app started, or none for [COLD_AFTER_MS]) a
 * request gets at least [COLD_START_TIMEOUT_MS], and a GET that still
 * times out is retried once. Same rule as web/lib/api.ts.
 */
class ColdStartTracker(private val clock: () -> Long) {
    @Volatile private var lastResponseAt: Long? = null

    fun mayBeCold(): Boolean {
        val last = lastResponseAt ?: return true
        return clock() - last > COLD_AFTER_MS
    }

    fun markResponse() {
        lastResponseAt = clock()
    }
}

/** Why the user is being sent back to sign-in. */
enum class SignOutReason { EXPIRED, DELETED, SIGNED_OUT }

/**
 * Runs every API call the way web/lib/api.ts's request() does:
 * timeouts, the cold-start retry, one refresh-and-replay on a 401,
 * and error messages taken from the backend's `detail`.
 */
class ApiClient(
    val service: ApiService,
    private val tokens: TokenStore,
    private val coldStart: ColdStartTracker,
    private val json: Json,
    private val scope: CoroutineScope,
) {
    private val refreshMutex = Mutex()
    private val _sessionEnded = MutableSharedFlow<SignOutReason>(extraBufferCapacity = 4)

    /** Emits when a refresh fails: tokens are gone and the user must sign in again. */
    val sessionEnded: SharedFlow<SignOutReason> = _sessionEnded.asSharedFlow()

    enum class Method { GET, HEAD, POST, PUT, DELETE }

    suspend fun <T> request(
        method: Method,
        auth: Boolean = true,
        retryOnAuthFailure: Boolean = true,
        timeoutMs: Long = DEFAULT_TIMEOUT_MS,
        call: suspend () -> Response<T>,
    ): T {
        val sentWith = tokens.accessToken
        val cold = coldStart.mayBeCold()
        val idempotent = method == Method.GET || method == Method.HEAD
        var attemptsLeft = if (cold && idempotent) 2 else 1
        val limit = if (cold) maxOf(timeoutMs, COLD_START_TIMEOUT_MS) else timeoutMs

        var response: Response<T>
        while (true) {
            try {
                response = withTimeout(limit) { call() }
                coldStart.markResponse()
                break
            } catch (timeout: TimeoutCancellationException) {
                attemptsLeft -= 1
                // A cold backend that still hasn't answered: try the GET once more.
                if (attemptsLeft > 0) continue
                throw ApiException(408, TIMEOUT_MESSAGE)
            } catch (io: IOException) {
                throw NetworkException(io)
            } catch (bad: kotlinx.serialization.SerializationException) {
                // A success status with a body this build can't read.
                coldStart.markResponse()
                throw ApiException(0, GENERIC_ERROR_MESSAGE)
            }
        }

        // An expired access token is the common case, not an error.
        // Swap it for a fresh one and replay once.
        if (response.code() == 401 && auth && retryOnAuthFailure) {
            if (refreshTokens(sentWith)) {
                return request(method, auth, retryOnAuthFailure = false, timeoutMs = timeoutMs, call = call)
            }
        }

        if (!response.isSuccessful) {
            throw ApiException(response.code(), readError(response))
        }

        @Suppress("UNCHECKED_CAST")
        return (response.body() ?: Unit) as T
    }

    /**
     * lib/api.ts's refreshTokens(). A network failure is treated exactly
     * like a rejected refresh: tokens are cleared and the session ends.
     * Concurrent 401s share one refresh: whoever gets the lock second
     * sees the token has already changed and just replays.
     */
    suspend fun refreshTokens(failedWith: String?): Boolean = refreshMutex.withLock {
        val current = tokens.accessToken
        if (current != null && current != failedWith) return@withLock true

        val refresh = tokens.refreshToken ?: return@withLock endSession()
        // A refresh that can't reach the server, times out, or answers
        // with something unreadable is treated like a rejected one.
        val response = try {
            withTimeout(DEFAULT_TIMEOUT_MS) { service.refresh(RefreshRequest(refresh)) }
        } catch (_: TimeoutCancellationException) {
            return@withLock endSession()
        } catch (cancel: kotlinx.coroutines.CancellationException) {
            throw cancel
        } catch (_: Exception) {
            return@withLock endSession()
        }
        coldStart.markResponse()
        val body = response.body()
        if (!response.isSuccessful || body == null) return@withLock endSession()
        tokens.store(body)
        true
    }

    private fun endSession(): Boolean {
        val hadSession = tokens.accessToken != null || tokens.refreshToken != null
        tokens.clear()
        if (hadSession) _sessionEnded.tryEmit(SignOutReason.EXPIRED)
        return false
    }

    /** Fire-and-forget GET /health on app start, so a cold backend is warming while the user reads. */
    fun warmUp() {
        scope.launch {
            try {
                service.health()
                coldStart.markResponse()
            } catch (_: Exception) {
                // Never surfaces: the real request that follows reports any problem.
            }
        }
    }

    private fun readError(response: Response<*>): String {
        val text = try {
            response.errorBody()?.string()
        } catch (_: IOException) {
            null
        }
        if (text != null) {
            try {
                when (val detail = json.decodeFromString(ErrorBody.serializer(), text).detail) {
                    is JsonPrimitive -> if (detail.isString) return detail.content
                    is JsonArray -> {
                        val msg = (detail.firstOrNull() as? JsonObject)?.get("msg") as? JsonPrimitive
                        msg?.contentOrNull?.let { return it }
                    }
                    else -> Unit
                }
            } catch (_: Exception) {
                // Fall through to the status-based message.
            }
        }
        return if (response.code() >= 500) SERVER_ERROR_MESSAGE else GENERIC_ERROR_MESSAGE
    }
}

/** The message to show for any failure from [ApiClient.request]. */
fun Throwable.userMessage(fallback: String = UNREACHABLE_MESSAGE): String = when (this) {
    is ApiException -> message ?: GENERIC_ERROR_MESSAGE
    else -> fallback
}
