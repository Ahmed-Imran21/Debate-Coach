package com.debatecoach.app.core.net

import com.debatecoach.app.core.model.DeleteAccountRequest
import com.debatecoach.app.core.model.LatestProgressReport
import com.debatecoach.app.core.model.LoginRequest
import com.debatecoach.app.core.model.Motion
import com.debatecoach.app.core.model.ProgressPoint
import com.debatecoach.app.core.model.ProgressReport
import com.debatecoach.app.core.model.ProgressReportCreate
import com.debatecoach.app.core.model.RefreshRequest
import com.debatecoach.app.core.model.SessionCreateRequest
import com.debatecoach.app.core.model.SessionCreated
import com.debatecoach.app.core.model.SessionReport
import com.debatecoach.app.core.model.SessionStartRequest
import com.debatecoach.app.core.model.SessionSummary
import com.debatecoach.app.core.model.ShareCreated
import com.debatecoach.app.core.model.ShareStatus
import com.debatecoach.app.core.model.SignupRequest
import com.debatecoach.app.core.model.Tokens
import com.debatecoach.app.core.model.User
import com.debatecoach.app.core.model.VisualSignalsAck
import okhttp3.RequestBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.HTTP
import retrofit2.http.Header
import retrofit2.http.Headers
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * Every endpoint the website calls (web/lib/api.ts), minus the admin
 * and profile ones. Calls go through [ApiClient.request], never
 * directly: that's where the timeouts, the cold-start retry, the
 * token refresh and the error messages live.
 *
 * Endpoints marked [NO_AUTH] are sent without the Authorization
 * header (AuthHeaderInterceptor reads and strips the marker).
 */
interface ApiService {
    @GET("health")
    @Headers(NO_AUTH)
    suspend fun health(): Response<Unit>

    @POST("v1/auth/signup")
    @Headers(NO_AUTH)
    suspend fun signup(@Body body: SignupRequest): Response<Tokens>

    @POST("v1/auth/login")
    @Headers(NO_AUTH)
    suspend fun login(@Body body: LoginRequest): Response<Tokens>

    @POST("v1/auth/refresh")
    @Headers(NO_AUTH)
    suspend fun refresh(@Body body: RefreshRequest): Response<Tokens>

    @GET("v1/users/me")
    suspend fun me(): Response<User>

    @HTTP(method = "DELETE", path = "v1/users/me", hasBody = true)
    suspend fun deleteAccount(@Body body: DeleteAccountRequest): Response<Unit>

    @POST("v1/users/heartbeat")
    suspend fun heartbeat(): Response<Unit>

    @GET("v1/sessions")
    suspend fun listSessions(): Response<List<SessionSummary>>

    @GET("v1/sessions/{id}")
    suspend fun getSession(@Path("id") id: String): Response<SessionSummary>

    @GET("v1/sessions/{id}/report")
    suspend fun getReport(@Path("id") id: String): Response<SessionReport>

    @DELETE("v1/sessions/{id}")
    suspend fun deleteSession(@Path("id") id: String): Response<Unit>

    @POST("v1/sessions")
    suspend fun createSession(@Body body: SessionCreateRequest): Response<SessionCreated>

    @POST("v1/sessions/{id}/start")
    suspend fun startSession(@Path("id") id: String): Response<SessionSummary>

    @POST("v1/sessions/{id}/start")
    suspend fun startSessionWithVideo(@Path("id") id: String, @Body body: SessionStartRequest): Response<SessionSummary>

    @PUT("v1/sessions/{id}/visual-signals")
    suspend fun uploadVisualSignals(
        @Path("id") id: String,
        @Header("Content-Encoding") contentEncoding: String?,
        @Body body: RequestBody,
    ): Response<VisualSignalsAck>

    @GET("v1/sessions/progress")
    suspend fun progress(@Query("metric") metric: String, @Query("range") range: String): Response<List<ProgressPoint>>

    @POST("v1/progress-reports")
    suspend fun createProgressReport(@Body body: ProgressReportCreate): Response<ProgressReport>

    @GET("v1/progress-reports/latest")
    suspend fun latestProgressReport(): Response<LatestProgressReport>

    @GET("v1/sessions/{id}/share")
    suspend fun shareStatus(@Path("id") id: String): Response<ShareStatus>

    @POST("v1/sessions/{id}/share")
    suspend fun createShareLink(@Path("id") id: String): Response<ShareCreated>

    @DELETE("v1/sessions/{id}/share")
    suspend fun stopSharing(@Path("id") id: String): Response<Unit>

    @GET("v1/motions")
    suspend fun motions(): Response<List<Motion>>

    companion object {
        const val NO_AUTH_HEADER = "X-DC-No-Auth"
        const val NO_AUTH = "$NO_AUTH_HEADER: 1"
    }
}
