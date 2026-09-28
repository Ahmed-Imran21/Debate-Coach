package com.debatecoach.app.core

import com.debatecoach.app.core.auth.TokenStore
import com.debatecoach.app.core.model.DeleteAccountRequest
import com.debatecoach.app.core.model.LatestProgressReport
import com.debatecoach.app.core.model.LoginRequest
import com.debatecoach.app.core.model.Motion
import com.debatecoach.app.core.model.ProgressPoint
import com.debatecoach.app.core.model.ProgressReport
import com.debatecoach.app.core.model.ProgressReportCreate
import com.debatecoach.app.core.model.SessionCreateRequest
import com.debatecoach.app.core.model.SessionCreated
import com.debatecoach.app.core.model.SessionReport
import com.debatecoach.app.core.model.SessionStartRequest
import com.debatecoach.app.core.model.SessionSummary
import com.debatecoach.app.core.model.ShareCreated
import com.debatecoach.app.core.model.ShareStatus
import com.debatecoach.app.core.model.SignupRequest
import com.debatecoach.app.core.model.User
import com.debatecoach.app.core.model.VideoFinalize
import com.debatecoach.app.core.net.ApiClient
import com.debatecoach.app.core.net.ApiClient.Method
import com.debatecoach.app.core.net.PROGRESS_REPORT_TIMEOUT_MS
import com.debatecoach.app.core.net.SignOutReason
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.merge

/**
 * Everything the screens ask of the backend. The same endpoints, and
 * the same account and data, as the website: nothing is stored on the
 * phone beyond the tokens and what's on screen.
 */
interface Backend {
    val signedIn: StateFlow<Boolean>
    /** Emits when the user must see the sign-in screen again, and why. */
    val signedOut: Flow<SignOutReason>

    suspend fun signUp(email: String, password: String, firstName: String, lastName: String, acceptedPrivacyPolicy: Boolean, acceptedTerms: Boolean)
    suspend fun signIn(email: String, password: String)
    fun signOut()
    suspend fun deleteAccount(password: String)
    suspend fun me(): User
    suspend fun heartbeat()

    suspend fun listSessions(): List<SessionSummary>
    suspend fun getSession(id: String): SessionSummary
    suspend fun getReport(id: String): SessionReport
    suspend fun deleteSession(id: String)
    suspend fun motions(): List<Motion>

    suspend fun createSession(contentType: String, title: String?, motionId: String?, videoRequested: Boolean): SessionCreated
    suspend fun startSession(id: String, video: VideoFinalize?): SessionSummary

    suspend fun progress(metric: String, range: String): List<ProgressPoint>
    suspend fun latestProgressReport(): LatestProgressReport
    suspend fun createProgressReport(sessionCount: Int): ProgressReport

    suspend fun shareStatus(sessionId: String): ShareStatus
    suspend fun createShareLink(sessionId: String): ShareCreated
    suspend fun stopSharing(sessionId: String)
}

class RemoteBackend(private val api: ApiClient, private val tokens: TokenStore) : Backend {
    private val localSignOuts = MutableSharedFlow<SignOutReason>(extraBufferCapacity = 4)

    override val signedIn: StateFlow<Boolean> = tokens.signedIn
    override val signedOut: Flow<SignOutReason> = merge(api.sessionEnded, localSignOuts)

    private val s get() = api.service

    override suspend fun signUp(email: String, password: String, firstName: String, lastName: String, acceptedPrivacyPolicy: Boolean, acceptedTerms: Boolean) {
        val t = api.request(Method.POST, auth = false) {
            s.signup(SignupRequest(email, password, firstName, lastName, acceptedPrivacyPolicy, acceptedTerms))
        }
        tokens.store(t)
    }

    override suspend fun signIn(email: String, password: String) {
        val t = api.request(Method.POST, auth = false) { s.login(LoginRequest(email, password)) }
        tokens.store(t)
    }

    override fun signOut() {
        tokens.clear()
        localSignOuts.tryEmit(SignOutReason.SIGNED_OUT)
    }

    /** The backend re-checks the password itself; typing DELETE is only the UI's confirmation. */
    override suspend fun deleteAccount(password: String) {
        api.request(Method.DELETE) { s.deleteAccount(DeleteAccountRequest(password)) }
        tokens.clear()
        localSignOuts.tryEmit(SignOutReason.DELETED)
    }

    override suspend fun me(): User = api.request(Method.GET) { s.me() }

    /**
     * retryOnAuthFailure = false, as on the web: a timer with no user
     * behind it must not keep a session alive by refreshing it.
     */
    override suspend fun heartbeat() {
        api.request(Method.POST, retryOnAuthFailure = false) { s.heartbeat() }
    }

    override suspend fun listSessions() = api.request(Method.GET) { s.listSessions() }
    override suspend fun getSession(id: String) = api.request(Method.GET) { s.getSession(id) }
    override suspend fun getReport(id: String) = api.request(Method.GET) { s.getReport(id) }
    override suspend fun deleteSession(id: String) = api.request(Method.DELETE) { s.deleteSession(id) }
    override suspend fun motions() = api.request(Method.GET) { s.motions() }

    override suspend fun createSession(contentType: String, title: String?, motionId: String?, videoRequested: Boolean) =
        api.request(Method.POST) {
            s.createSession(SessionCreateRequest(contentType, title, if (videoRequested) "requested" else null, motionId))
        }

    /** No video outcome: exactly the bodyless POST the website sends. */
    override suspend fun startSession(id: String, video: VideoFinalize?) = api.request(Method.POST) {
        if (video == null) s.startSession(id) else s.startSessionWithVideo(id, SessionStartRequest(video))
    }

    override suspend fun progress(metric: String, range: String) = api.request(Method.GET) { s.progress(metric, range) }
    override suspend fun latestProgressReport() = api.request(Method.GET) { s.latestProgressReport() }
    override suspend fun createProgressReport(sessionCount: Int) =
        api.request(Method.POST, timeoutMs = PROGRESS_REPORT_TIMEOUT_MS) { s.createProgressReport(ProgressReportCreate(sessionCount)) }

    override suspend fun shareStatus(sessionId: String) = api.request(Method.GET) { s.shareStatus(sessionId) }
    override suspend fun createShareLink(sessionId: String) = api.request(Method.POST) { s.createShareLink(sessionId) }
    override suspend fun stopSharing(sessionId: String) = api.request(Method.DELETE) { s.stopSharing(sessionId) }
}
