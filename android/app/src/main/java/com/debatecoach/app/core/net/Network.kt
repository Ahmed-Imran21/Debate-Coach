package com.debatecoach.app.core.net

import com.debatecoach.app.core.auth.TokenStore
import java.io.File
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.TimeoutCancellationException
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.Json
import okhttp3.Call
import okhttp3.Callback
import okhttp3.Interceptor
import okhttp3.MediaType
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.Response
import okio.BufferedSink
import okio.source
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory

val AppJson = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    coerceInputValues = true
    encodeDefaults = true
}

/** Adds the bearer token, except on endpoints marked ApiService.NO_AUTH. */
class AuthHeaderInterceptor(private val tokens: TokenStore) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        if (request.header(ApiService.NO_AUTH_HEADER) != null) {
            return chain.proceed(request.newBuilder().removeHeader(ApiService.NO_AUTH_HEADER).build())
        }
        val token = tokens.accessToken ?: return chain.proceed(request)
        return chain.proceed(request.newBuilder().header("Authorization", "Bearer $token").build())
    }
}

object Network {
    /**
     * Per-request limits are enforced by ApiClient (coroutine timeouts,
     * like the website's AbortSignal.timeout), so OkHttp's own are only
     * a backstop.
     */
    fun okHttp(tokens: TokenStore): OkHttpClient = OkHttpClient.Builder()
        .addInterceptor(AuthHeaderInterceptor(tokens))
        .connectTimeout(130, TimeUnit.SECONDS)
        .readTimeout(130, TimeUnit.SECONDS)
        .writeTimeout(130, TimeUnit.SECONDS)
        .build()

    fun service(baseUrl: String, client: OkHttpClient): ApiService = Retrofit.Builder()
        .baseUrl(baseUrl.trimEnd('/') + "/")
        .client(client)
        .addConverterFactory(AppJson.asConverterFactory("application/json".toMediaType()))
        .build()
        .create(ApiService::class.java)
}

// ---------------------------------------------------------------
// Signed-URL upload (web/lib/api.ts putToSignedUrl)
// ---------------------------------------------------------------

const val UPLOAD_TIMEOUT_MS = 10 * 60_000L
const val UPLOAD_TIMEOUT_MESSAGE = "The upload timed out. Check your connection and try again."
const val UPLOAD_FAILED_MESSAGE = "The recording could not be uploaded. Check your connection and try again."

/** A file body that reports bytes written, for the upload progress bar. */
class ProgressFileBody(
    private val file: File,
    private val type: MediaType?,
    private val onProgress: (sent: Long, total: Long) -> Unit,
) : RequestBody() {
    override fun contentType(): MediaType? = type
    override fun contentLength(): Long = file.length()

    override fun writeTo(sink: BufferedSink) {
        val total = contentLength()
        var sent = 0L
        file.source().use { source ->
            val buffer = okio.Buffer()
            while (true) {
                val read = source.read(buffer, 64 * 1024)
                if (read == -1L) break
                sink.write(buffer, read)
                sent += read
                onProgress(sent, total)
            }
        }
    }
}

/**
 * PUTs the recording straight to the storage signed URL; the API
 * server never sees these bytes. Retried by the caller on a network
 * failure (a PUT to the same URL is idempotent).
 */
class SignedUploader(private val client: OkHttpClient) {
    suspend fun put(url: String, headers: Map<String, String>, file: File, onProgress: (Long, Long) -> Unit) {
        val contentType = headers.entries.firstOrNull { it.key.equals("Content-Type", ignoreCase = true) }?.value
        val request = Request.Builder()
            .url(url)
            .apply { headers.forEach { (k, v) -> header(k, v) } }
            .put(ProgressFileBody(file, contentType?.toMediaType(), onProgress))
            .build()
        val response = try {
            withTimeout(UPLOAD_TIMEOUT_MS) { client.newCall(request).await() }
        } catch (_: TimeoutCancellationException) {
            throw ApiException(408, UPLOAD_TIMEOUT_MESSAGE)
        } catch (io: IOException) {
            throw UploadNetworkException(io)
        }
        response.use {
            if (!it.isSuccessful) throw ApiException(it.code, UPLOAD_FAILED_MESSAGE)
        }
    }
}

class UploadNetworkException(cause: IOException) : Exception(UPLOAD_FAILED_MESSAGE, cause)

suspend fun Call.await(): Response = withContext(Dispatchers.IO) {
    suspendCancellableCoroutine { cont ->
        cont.invokeOnCancellation { cancel() }
        enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                if (!cont.isCancelled) cont.resumeWith(Result.failure(e))
            }

            override fun onResponse(call: Call, response: Response) {
                cont.resumeWith(Result.success(response))
            }
        })
    }
}
