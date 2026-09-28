package com.debatecoach.app.testing

import com.debatecoach.app.core.Backend
import com.debatecoach.app.core.auth.KeyValueStore
import com.debatecoach.app.core.auth.TokenCipher
import com.debatecoach.app.core.model.LatestProgressReport
import com.debatecoach.app.core.model.Motion
import com.debatecoach.app.core.model.ProgressPoint
import com.debatecoach.app.core.model.ProgressReport
import com.debatecoach.app.core.model.SessionCreated
import com.debatecoach.app.core.model.SessionReport
import com.debatecoach.app.core.model.SessionSummary
import com.debatecoach.app.core.model.ShareCreated
import com.debatecoach.app.core.model.ShareStatus
import com.debatecoach.app.core.model.User
import com.debatecoach.app.core.model.VideoFinalize
import com.debatecoach.app.core.net.SignOutReason
import java.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.rules.TestWatcher
import org.junit.runner.Description

@OptIn(ExperimentalCoroutinesApi::class)
class MainDispatcherRule(val dispatcher: TestDispatcher = StandardTestDispatcher()) : TestWatcher() {
    override fun starting(description: Description) = Dispatchers.setMain(dispatcher)
    override fun finished(description: Description) = Dispatchers.resetMain()
}

class MemoryStore : KeyValueStore {
    val values = mutableMapOf<String, String>()
    override fun get(key: String): String? = values[key]
    override fun put(values: Map<String, String?>) {
        values.forEach { (k, v) -> if (v == null) this.values.remove(k) else this.values[k] = v }
    }
}

/** Reversible but not plaintext: proves the store only ever writes what the cipher produced. */
class FakeCipher : TokenCipher {
    var failDecrypt = false
    override fun encrypt(plain: String) = "enc:" + Base64.getEncoder().encodeToString(plain.reversed().toByteArray())
    override fun decrypt(encoded: String): String? {
        if (failDecrypt || !encoded.startsWith("enc:")) return null
        return String(Base64.getDecoder().decode(encoded.removePrefix("enc:"))).reversed()
    }
}

/** A JWT whose payload carries `exp` (seconds); the signature is irrelevant, nothing here verifies it. */
fun jwt(expSeconds: Long, sub: String = "u1"): String {
    val enc = Base64.getUrlEncoder().withoutPadding()
    val header = enc.encodeToString("""{"alg":"HS256","typ":"JWT"}""".toByteArray())
    val payload = enc.encodeToString("""{"sub":"$sub","exp":$expSeconds,"type":"access"}""".toByteArray())
    return "$header.$payload.sig"
}

fun session(
    id: String,
    status: String = "completed",
    title: String? = null,
    createdAt: String = "2026-09-26T10:00:00Z",
    score: Double? = 71.0,
    shared: Boolean = false,
    motion: Motion? = null,
    queueWait: Double? = null,
    progress: Double = 1.0,
) = SessionSummary(
    id = id, title = title, status = status, shared = shared, motion = motion, progress = progress,
    queueWaitSeconds = queueWait, overallScore = score, durationSeconds = 125.0, wordsPerMinute = 142.4,
    feedbackCount = 7, errorMessage = null, createdAt = createdAt,
)

/** A Backend whose every call can be scripted per test. */
open class FakeBackend : Backend {
    val signedInFlow = MutableStateFlow(true)
    val signedOutFlow = MutableSharedFlow<SignOutReason>(extraBufferCapacity = 8)
    override val signedIn: StateFlow<Boolean> = signedInFlow
    override val signedOut = signedOutFlow

    val calls = mutableListOf<String>()

    var signInHandler: suspend (String, String) -> Unit = { _, _ -> }
    var signUpHandler: suspend (String, String, String, String) -> Unit = { _, _, _, _ -> }
    var lastSignUpConsent: Pair<Boolean, Boolean>? = null
    var deleteAccountHandler: suspend (String) -> Unit = {}
    var sessionsHandler: suspend () -> List<SessionSummary> = { emptyList() }
    var getSessionHandler: suspend (String) -> SessionSummary = { session(it) }
    var reportHandler: suspend (String) -> SessionReport = { error("no report") }
    var deleteSessionHandler: suspend (String) -> Unit = {}
    var motionsHandler: suspend () -> List<Motion> = { emptyList() }
    var createSessionHandler: suspend (String, String?, String?, Boolean) -> SessionCreated =
        { _, _, _, video -> SessionCreated("s-new", "created", "https://upload.test/put", mapOf("Content-Type" to "audio/mp4"), 900, if (video) "awaiting_upload" else "not_requested") }
    var startSessionHandler: suspend (String, VideoFinalize?) -> SessionSummary = { id, _ -> session(id, status = "queued", progress = 0.0) }
    var progressHandler: suspend (String, String) -> List<ProgressPoint> = { _, _ -> emptyList() }
    var latestHandler: suspend () -> LatestProgressReport = { LatestProgressReport(null, true, null) }
    var createReportHandler: suspend (Int) -> ProgressReport = { error("no report") }
    var shareStatusHandler: suspend (String) -> ShareStatus = { ShareStatus(false) }
    var createShareHandler: suspend (String) -> ShareCreated = { ShareCreated("tok_abc-123", "2026-09-27T10:00:00Z") }
    var stopSharingHandler: suspend (String) -> Unit = {}

    override suspend fun signUp(email: String, password: String, firstName: String, lastName: String, acceptedPrivacyPolicy: Boolean, acceptedTerms: Boolean) {
        calls += "signUp"
        lastSignUpConsent = acceptedPrivacyPolicy to acceptedTerms
        signUpHandler(email, password, firstName, lastName)
    }
    override suspend fun signIn(email: String, password: String) {
        calls += "signIn:$email"
        signInHandler(email, password)
    }
    override fun signOut() {
        calls += "signOut"
        signedOutFlow.tryEmit(SignOutReason.SIGNED_OUT)
    }
    override suspend fun deleteAccount(password: String) {
        calls += "deleteAccount"
        deleteAccountHandler(password)
    }
    override suspend fun me() = User("u1", "a@example.com", "Ada", "Lovelace", "2026-01-01T00:00:00Z")
    override suspend fun heartbeat() {
        calls += "heartbeat"
    }
    override suspend fun listSessions(): List<SessionSummary> {
        calls += "listSessions"
        return sessionsHandler()
    }
    override suspend fun getSession(id: String): SessionSummary {
        calls += "getSession:$id"
        return getSessionHandler(id)
    }
    override suspend fun getReport(id: String): SessionReport {
        calls += "getReport:$id"
        return reportHandler(id)
    }
    override suspend fun deleteSession(id: String) {
        calls += "deleteSession:$id"
        deleteSessionHandler(id)
    }
    override suspend fun motions() = motionsHandler()
    override suspend fun createSession(contentType: String, title: String?, motionId: String?, videoRequested: Boolean): SessionCreated {
        calls += "createSession:$contentType:$title:$motionId:$videoRequested"
        return createSessionHandler(contentType, title, motionId, videoRequested)
    }
    override suspend fun startSession(id: String, video: VideoFinalize?): SessionSummary {
        calls += "startSession:$id:${video?.status}:${video?.reason}"
        return startSessionHandler(id, video)
    }
    override suspend fun progress(metric: String, range: String): List<ProgressPoint> {
        calls += "progress:$metric:$range"
        return progressHandler(metric, range)
    }
    override suspend fun latestProgressReport(): LatestProgressReport {
        calls += "latest"
        return latestHandler()
    }
    override suspend fun createProgressReport(sessionCount: Int): ProgressReport {
        calls += "createReport:$sessionCount"
        return createReportHandler(sessionCount)
    }
    override suspend fun shareStatus(sessionId: String) = shareStatusHandler(sessionId)
    override suspend fun createShareLink(sessionId: String): ShareCreated {
        calls += "createShare"
        return createShareHandler(sessionId)
    }
    override suspend fun stopSharing(sessionId: String) {
        calls += "stopSharing"
        stopSharingHandler(sessionId)
    }
}
