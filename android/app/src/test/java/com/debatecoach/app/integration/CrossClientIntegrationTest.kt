package com.debatecoach.app.integration

import com.debatecoach.app.core.RemoteBackend
import com.debatecoach.app.core.auth.TokenStore
import com.debatecoach.app.core.net.ApiClient
import com.debatecoach.app.core.net.ApiException
import com.debatecoach.app.core.net.AppJson
import com.debatecoach.app.core.net.ColdStartTracker
import com.debatecoach.app.core.net.Network
import com.debatecoach.app.core.net.SignedUploader
import com.debatecoach.app.core.util.Connectivity
import com.debatecoach.app.feature.recorder.AudioUploader
import com.debatecoach.app.feature.recorder.TrackUploader
import com.debatecoach.app.feature.recorder.UploadJob
import com.debatecoach.app.feature.recorder.UploadManager
import com.debatecoach.app.feature.recorder.UploadState
import com.debatecoach.app.feature.recorder.VideoPlan
import com.debatecoach.app.testing.FakeCipher
import com.debatecoach.app.testing.MemoryStore
import com.debatecoach.app.visual.Calibration
import com.debatecoach.app.visual.CalibrationBaseline
import com.debatecoach.app.visual.Capture
import com.debatecoach.app.visual.FrameSample
import com.debatecoach.app.visual.RuntimeInfo
import com.debatecoach.app.visual.SetupCheck
import com.debatecoach.app.visual.SignalUploader
import com.debatecoach.app.visual.Source
import com.debatecoach.app.visual.TrackBuilder
import com.debatecoach.app.visual.TrackContext
import com.debatecoach.app.visual.VisualConfig
import com.debatecoach.app.visual.VisualSignalTrack
import java.io.File
import java.util.UUID
import kotlin.math.sin
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test

/**
 * One account, website and app: runs against a real backend (your
 * local one) when DC_BACKEND_URL and DC_TEST_AUDIO (an .m4a) are set,
 * and is skipped otherwise.
 *
 *   DC_BACKEND_URL=http://localhost:8000 DC_TEST_AUDIO=/path/speech.m4a \
 *     ./gradlew :app:testLocalDebugUnitTest --tests '*CrossClient*'
 *
 * "The website" here is plain HTTP calls made exactly as web/lib/api.ts
 * makes them; "the app" is the app's own networking, upload and visual
 * code. It uses a throwaway account and deletes it at the end.
 */
class CrossClientIntegrationTest {
    private val base = System.getenv("DC_BACKEND_URL")
    private val audioPath = System.getenv("DC_TEST_AUDIO")
    private val http = OkHttpClient()
    private val json = Json { ignoreUnknownKeys = true }

    /** The website's request(): JSON in, JSON out, Bearer token. */
    private fun web(method: String, path: String, token: String?, body: String? = null): Pair<Int, String> {
        val request = Request.Builder().url(base!!.trimEnd('/') + path)
            .method(method, body?.toRequestBody("application/json".toMediaType()) ?: if (method == "POST") "".toRequestBody() else null)
            .apply { if (token != null) header("Authorization", "Bearer $token") }
            .build()
        http.newCall(request).execute().use { return it.code to (it.body?.string() ?: "") }
    }

    private fun webLogin(email: String, password: String): String? {
        val (code, text) = web("POST", "/v1/auth/login", null, """{"email":"$email","password":"$password"}""")
        return if (code == 200) json.parseToJsonElement(text).jsonObject["access_token"]!!.jsonPrimitive.content else null
    }

    /** A plausible Android track: a face near the centre, hands moving, 10 fps. */
    private fun androidTrack(durationS: Double): VisualSignalTrack {
        val b = TrackBuilder()
        var t = 0.05
        while (t < durationS - 0.1) {
            val k = t * 1.3
            b.appendSample(t, FrameSample(
                faceCount = 1.0, headYaw = 4 * sin(k), headPitch = -3 + 2 * sin(k / 2), headRoll = 1.0,
                irisX = 0.1 * sin(k), irisY = -0.05, faceScale = 0.09, faceCx = 0.5, faceCy = 0.4,
                lhPresent = 1.0, lhScore = 0.9, lhCx = 0.35 + 0.05 * sin(k * 2), lhCy = 0.7,
                rhPresent = 1.0, rhScore = 0.9, rhCx = 0.65 + 0.05 * sin(k * 2.2), rhCy = 0.7, inferMs = 35.0,
            ))
            t += 0.1
        }
        return b.build(
            sessionId = "",
            source = Source("android", "android-1.0.0", "other", RuntimeInfo("mediapipe-tasks-vision", "1.0.0", "GPU"), VisualConfig.MODELS, "full", 10.3),
            capture = Capture(640, 360, false, "anatomical", 10),
            clockUncertaintyMs = VisualConfig.CLOCK_UNCERTAINTY_MS,
            durationS = durationS,
            calibration = Calibration(true, CalibrationBaseline(0.0, -3.0, 0.0, -0.05), 28, 0.9, "passed"),
            context = TrackContext("camera_audience", false),
            setupCheck = SetupCheck(true, true, "ok", "ok"),
        )
    }

    @Test
    fun the_website_and_the_app_share_one_account_and_its_data() = runBlocking {
        assumeTrue("set DC_BACKEND_URL and DC_TEST_AUDIO to run", base != null && audioPath != null)
        val audio = File(audioPath!!)
        val email = "android-crossclient-${UUID.randomUUID().toString().take(8)}@example.com"
        val password = "Cross-client-" + UUID.randomUUID()

        // --- The app creates the account.
        val tokens = TokenStore(MemoryStore(), FakeCipher())
        val okHttp = Network.okHttp(tokens)
        val api = ApiClient(Network.service(base!!, okHttp), tokens, ColdStartTracker(System::currentTimeMillis), AppJson, CoroutineScope(Dispatchers.IO))
        val app = RemoteBackend(api, tokens)
        app.signUp(email, password, "Cross", "Client")

        try {
            // --- The website signs in with the same email and password.
            val webToken = webLogin(email, password)
            assertTrue("the website accepts the account the app created", webToken != null)

            // --- A session created on the website...
            val (createCode, created) = web("POST", "/v1/sessions", webToken, """{"content_type":"audio/mp4","title":"Recorded on the website"}""")
            assertEquals(201, createCode)
            val createdObj = json.parseToJsonElement(created).jsonObject
            val webSessionId = createdObj["id"]!!.jsonPrimitive.content
            val uploadUrl = createdObj["upload_url"]!!.jsonPrimitive.content
            val put = Request.Builder().url(uploadUrl).put(audio.asRequestBody("audio/mp4".toMediaType())).header("Content-Type", "audio/mp4").build()
            http.newCall(put).execute().use { assertTrue("signed PUT from the web side: ${it.code}", it.isSuccessful) }
            assertEquals(202, web("POST", "/v1/sessions/$webSessionId/start", webToken).first)

            // ...appears in the app's list.
            val appList = app.listSessions()
            assertTrue("the app lists the website's session", appList.any { it.id == webSessionId && it.title == "Recorded on the website" })

            // --- A session recorded in the app, with an Android visual track...
            val connectivity = object : Connectivity { override val online = MutableStateFlow(true) }
            val signed = SignedUploader(okHttp)
            val signals = SignalUploader(api)
            val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
            val uploads = UploadManager(
                app,
                object : AudioUploader { override suspend fun put(url: String, headers: Map<String, String>, file: File, onProgress: (Long, Long) -> Unit) = signed.put(url, headers, file, onProgress) },
                object : TrackUploader { override suspend fun upload(sessionId: String, track: VisualSignalTrack) = signals.uploadWithRetry(sessionId, track) },
                connectivity,
                scope,
            )
            uploads.start(UploadJob(audio, "audio/mp4", "Recorded on Android", null, VideoPlan.Track(androidTrack(62.8))))
            val done = withTimeout(120_000) { uploads.state.first { it is UploadState.Done || it is UploadState.Failed } }
            assertTrue("app upload: $done", done is UploadState.Done)
            val appSessionId = (done as UploadState.Done).sessionId

            // ...appears on the website's list.
            val (listCode, listText) = web("GET", "/v1/sessions", webToken)
            assertEquals(200, listCode)
            val webList = json.parseToJsonElement(listText).jsonArray
            val fromApp = webList.map { it.jsonObject }.firstOrNull { it["id"]!!.jsonPrimitive.content == appSessionId }
            assertTrue("the website lists the app's session", fromApp != null)
            assertEquals("Recorded on Android", fromApp!!["title"]!!.jsonPrimitive.content)
            assertEquals("the Android track was accepted", "received", fromApp["video_analysis_status"]!!.jsonPrimitive.content.let { if (it == "processing" || it == "processed" || it == "partial") "received" else it })

            // Both pipelines finish, and each side can read the other's report.
            for (id in listOf(webSessionId, appSessionId)) {
                val status = withTimeout(600_000) {
                    var s: String
                    while (true) {
                        s = app.getSession(id).status
                        if (s == "completed" || s == "failed") break
                        delay(4_000)
                    }
                    s
                }
                assertEquals("session $id", "completed", status)
            }
            val appReport = app.getReport(webSessionId)
            assertEquals("Recorded on the website", appReport.title)
            val (reportCode, reportText) = web("GET", "/v1/sessions/$appSessionId/report", webToken)
            assertEquals(200, reportCode)
            val webReport = json.parseToJsonElement(reportText).jsonObject
            val videoStatus = webReport["video_analysis_status"]!!.jsonPrimitive.content
            println("Android session visual analysis: $videoStatus")
            assertTrue("the Android track was processed: $videoStatus", videoStatus in setOf("processed", "partial", "insufficient_data"))
            val platform = (webReport["video_analysis"] as? JsonObject)?.get("source_summary")?.jsonObject?.get("platform")?.jsonPrimitive?.content
            if (platform != null) assertEquals("android", platform)

            // The daily progress-report limit is shared too.
            val latestWeb = web("GET", "/v1/progress-reports/latest", webToken).second
            val latestApp = app.latestProgressReport()
            assertEquals(json.parseToJsonElement(latestWeb).jsonObject["can_generate"]!!.jsonPrimitive.content.toBoolean(), latestApp.canGenerate)
        } finally {
            // Deleting from the app deletes it everywhere: the website can no longer sign in.
            app.deleteAccount(password)
            assertEquals(null, webLogin(email, password))
        }
    }
}
