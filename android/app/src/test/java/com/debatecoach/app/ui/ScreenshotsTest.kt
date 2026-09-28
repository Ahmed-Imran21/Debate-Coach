package com.debatecoach.app.ui

import android.graphics.Bitmap
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.test.DeviceConfigurationOverride
import androidx.compose.ui.test.FontScale
import androidx.compose.ui.test.captureToImage
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performClick
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.debatecoach.app.core.model.AudioAnalysis
import com.debatecoach.app.core.model.CorrelatedMoment
import com.debatecoach.app.core.model.CountStats
import com.debatecoach.app.core.model.FeedbackItem
import com.debatecoach.app.core.model.InstanceStats
import com.debatecoach.app.core.model.LatestProgressReport
import com.debatecoach.app.core.model.MomentAnchor
import com.debatecoach.app.core.model.MomentObservation
import com.debatecoach.app.core.model.Motion
import com.debatecoach.app.core.model.PauseSpan
import com.debatecoach.app.core.model.ProgressPoint
import com.debatecoach.app.core.model.ProgressReport
import com.debatecoach.app.core.model.RawMetrics
import com.debatecoach.app.core.model.SessionReport
import com.debatecoach.app.core.model.SpeechStats
import com.debatecoach.app.core.model.TimedInstance
import com.debatecoach.app.core.model.VideoAnalysisView
import com.debatecoach.app.core.model.VisualContext
import com.debatecoach.app.core.model.VisualFeedbackDocument
import com.debatecoach.app.core.model.VisualFeedbackItem
import com.debatecoach.app.core.model.VisualMetric
import com.debatecoach.app.core.model.VisualQuality
import com.debatecoach.app.core.util.ConsentChoice
import com.debatecoach.app.core.util.ConsentStore
import com.debatecoach.app.feature.account.AccountContent
import com.debatecoach.app.feature.account.AccountViewModel
import com.debatecoach.app.feature.account.DeleteAccountContent
import com.debatecoach.app.feature.auth.SignInScreen
import com.debatecoach.app.feature.auth.SignUpScreen
import com.debatecoach.app.feature.progress.InsightsScreen
import com.debatecoach.app.feature.progress.ProgressScreen
import com.debatecoach.app.feature.progress.ProgressViewModel
import com.debatecoach.app.feature.report.SessionContent
import com.debatecoach.app.feature.report.SessionViewModel
import com.debatecoach.app.feature.sessions.SessionsScreen
import com.debatecoach.app.feature.sessions.SessionsViewModel
import com.debatecoach.app.testing.FakeBackend
import com.debatecoach.app.testing.MemoryStore
import com.debatecoach.app.testing.session
import com.debatecoach.app.ui.theme.DebateCoachTheme
import java.io.File
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * Not a test: renders each redesigned screen to PNG for a visual review,
 * light and dark. Skipped unless -PscreenshotsDir=... is given.
 */
@RunWith(AndroidJUnit4::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(qualifiers = "w393dp-h852dp-xxhdpi")
class ScreenshotsTest {
    @get:Rule val compose = createComposeRule()

    private val dir = System.getProperty("screenshots.dir").orEmpty()

    private fun shoot(name: String, fontScale: Float = 1f, setup: () -> Unit = {}, content: @Composable () -> Unit) {
        assumeTrue("set -PscreenshotsDir to render screenshots", dir.isNotEmpty())
        var dark by mutableStateOf(false)
        compose.setContent {
            DeviceConfigurationOverride(DeviceConfigurationOverride.FontScale(fontScale)) {
                DebateCoachTheme(darkTheme = dark) { content() }
            }
        }
        compose.waitForIdle()
        setup()
        compose.mainClock.advanceTimeBy(2_000)
        compose.waitForIdle()
        save("$name-light")
        dark = true
        compose.mainClock.advanceTimeBy(500)
        compose.waitForIdle()
        save("$name-dark")
    }

    private fun save(name: String) {
        val bitmap = compose.onRoot().captureToImage().asAndroidBitmap()
        File(dir).mkdirs()
        File(dir, "$name.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    private val motion = Motion("carbon-tax", "Climate policy", "This house would introduce a carbon tax.")

    private val backend = FakeBackend().apply {
        sessionsHandler = {
            listOf(
                session("s0", status = "transcribing", title = "Semi-final, first proposition", score = null, queueWait = 12.0, progress = 0.35),
                session("s1", title = "Second constructive", shared = true, motion = motion, score = 68.4),
                session("s2", title = null, createdAt = "2026-09-24T10:00:00Z", score = 61.0),
                session("s3", title = "Rebuttal drill: nuclear energy", createdAt = "2026-09-22T10:00:00Z", score = 57.0),
                session("s4", status = "failed", title = "Too quiet", createdAt = "2026-09-20T10:00:00Z", score = null),
            )
        }
        progressHandler = { _, _ ->
            listOf(
                ProgressPoint("a", "2026-09-10T10:00:00Z", "Opening", 48.0),
                ProgressPoint("b", "2026-09-14T10:00:00Z", "Rebuttal drill", 55.0),
                ProgressPoint("c", "2026-09-18T10:00:00Z", null, 53.0),
                ProgressPoint("d", "2026-09-22T10:00:00Z", "Rebuttal drill: nuclear energy", 57.0),
                ProgressPoint("e", "2026-09-24T10:00:00Z", null, 61.0),
                ProgressPoint("f", "2026-09-26T10:00:00Z", "Second constructive", 68.0),
            )
        }
        getSessionHandler = { session(it) }
        reportHandler = { report }
    }

    private val report = SessionReport(
        id = "s1",
        title = "Second constructive",
        status = "completed",
        motion = motion,
        motionNotApplied = false,
        createdAt = "2026-09-26T10:00:00Z",
        scores = mapOf("overall" to 68.4, "quantitative" to 72.0, "argumentation" to 61.0, "rebuttal" to null, "structure" to 70.0, "persuasion" to 64.0, "logic" to 58.0),
        feedback = listOf(
            FeedbackItem("argumentation", "Claims without warrants", "Two of your claims had no reasoning behind them, so they read as assertions.", "high", listOf("It is simply better for everyone."), "A judge can't weigh a claim they can't follow.", "After each claim, add a 'because' and one piece of evidence."),
            FeedbackItem("structure", "Signposting", "Transitions between arguments were abrupt.", "medium"),
            FeedbackItem("quantitative", "Steady pace", "Your pace held at about 140 words per minute.", "positive"),
            FeedbackItem("logic", "Slippery slope", "One step in the harms argument assumed an extreme outcome.", "medium"),
        ),
        rawMetrics = RawMetrics(
            speech = SpeechStats(totalDuration = 190.0, speechDuration = 172.0, wordsPerMinute = 141.6),
            pauses = CountStats(9),
            fillers = InstanceStats(4, listOf(TimedInstance("um", 12.0), TimedInstance("like", 40.0), TimedInstance("um", 96.0), TimedInstance("so", 150.0))),
            stutters = InstanceStats(1, listOf(TimedInstance("the", 70.0))),
        ),
        analysis = AudioAnalysis(190.0, listOf(PauseSpan(20.0, 22.0, 2.0), PauseSpan(84.0, 85.6, 1.6), PauseSpan(130.0, 131.2, 1.2))),
        audioUrl = null,
        videoAnalysisStatus = "processed",
        visualCoachingStatus = "completed",
        videoAnalysis = VideoAnalysisView(
            VisualQuality(VisualContext("camera_audience"), listOf("calibration_skipped")),
            mapOf(
                "face_tracked_ratio" to VisualMetric("ok", 0.94, "high"),
                "camera_facing_ratio" to VisualMetric("ok", 0.62, "high"),
                "gaze_away_events_per_min" to VisualMetric("ok", 3.4, "medium"),
                "gesture_rate_per_min" to VisualMetric("ok", 7.1, "medium"),
            ),
        ),
        correlatedMoments = listOf(
            CorrelatedMoment("m1", "improve", MomentAnchor("claim"), 42.0, 55.0, "Nuclear is the safest source we have", listOf(MomentObservation("o1", "event", type = "gaze_away", durationS = 2.4, direction = "down")), 0.9),
        ),
        visualFeedback = VisualFeedbackDocument(
            listOf(
                VisualFeedbackItem("vf1", "gaze", "strength", null, "You faced the camera through most of your rebuttal, which keeps an online judge with you."),
                VisualFeedbackItem("vf2", "gaze", "improve", "m1", "You looked down while stating your main claim. Say the claim to the lens, then check your notes."),
            ),
        ),
    )

    @Test fun sessions() = shoot("01-sessions") {
        SessionsScreen(SessionsViewModel(backend), online = true, onOpenSession = {}, onRecord = {})
    }

    @Test fun sessions_empty() = shoot("02-sessions-empty") {
        SessionsScreen(SessionsViewModel(FakeBackend()), online = true, onOpenSession = {}, onRecord = {})
    }

    @Test fun report_overview() = shoot("03-report-overview") {
        SessionContent(SessionViewModel(backend, "s1", "https://web.example"), onBack = {})
    }

    @Test fun report_findings() = shoot("04-report-findings", setup = { compose.onNodeWithTag("tab-findings").performClick() }) {
        SessionContent(SessionViewModel(backend, "s1", "https://web.example"), onBack = {})
    }

    @Test fun report_visual() = shoot("05-report-visual", setup = { compose.onNodeWithTag("tab-visual").performClick() }) {
        SessionContent(SessionViewModel(backend, "s1", "https://web.example"), onBack = {})
    }

    @Test fun progress() = shoot("06-progress", setup = { compose.onNodeWithTag("progress-point-5").performClick() }) {
        ProgressScreen(ProgressViewModel(backend), completedCount = 6, onOpenSession = {})
    }

    @Test fun insights_generate() = shoot("07-insights-generate") {
        InsightsScreen(ProgressViewModel(backend), completedCount = 6)
    }

    @Test fun insights_used_today() {
        val b = FakeBackend().apply {
            latestHandler = {
                LatestProgressReport(
                    ProgressReport("r", "2026-09-27", "2026-09-27T09:00:00Z", 5, 5, listOf(
                        "Your pace has settled at around 140 words per minute, up from a rushed 170 in your first sessions.",
                        "Rebuttals now answer the other side's strongest point first. Keep doing that.",
                        "Claims still arrive without their warrants. Add a 'because' after each one.",
                    )),
                    canGenerate = false,
                    nextAvailableAt = "2026-09-28T00:00:00Z",
                )
            }
        }
        shoot("08-insights-used-today") { InsightsScreen(ProgressViewModel(b), completedCount = 6) }
    }

    @Test fun account() = shoot("09-account") {
        AccountContent(AccountViewModel(backend), ConsentStore(MemoryStore()).apply { set(ConsentChoice.IN) }, onOpenLink = {}, onDeleteAccount = {})
    }

    @Test fun delete_account() = shoot("10-delete-account") { DeleteAccountContent(AccountViewModel(backend), onClose = {}) }

    @Test fun sign_in() = shoot("11-sign-in") { SignInScreen(backend, null, onSignedIn = {}, onCreateAccount = {}) }

    @Test fun sign_up() = shoot("12-sign-up") { SignUpScreen(backend, onSignedUp = {}, onSignIn = {}, onOpenLink = {}) }

    @Test fun sessions_large_font() = shoot("13-sessions-font2x", fontScale = 2f) {
        SessionsScreen(SessionsViewModel(backend), online = true, onOpenSession = {}, onRecord = {})
    }

    @Test fun report_large_font() = shoot("14-report-font2x", fontScale = 2f) {
        SessionContent(SessionViewModel(backend, "s1", "https://web.example"), onBack = {})
    }

    @Test @Config(qualifiers = "w360dp-h640dp-xhdpi") fun small_phone_sign_up() = shoot("15-signup-small") {
        SignUpScreen(backend, onSignedUp = {}, onSignIn = {}, onOpenLink = {})
    }

    // ---- Recorder ----

    private fun recorderVm(video: Boolean, consent: ConsentChoice? = null): com.debatecoach.app.feature.recorder.RecorderViewModel {
        org.robolectric.Shadows.shadowOf(androidx.test.core.app.ApplicationProvider.getApplicationContext<android.app.Application>())
            .grantPermissions(android.Manifest.permission.RECORD_AUDIO)
        val dir = java.nio.file.Files.createTempDirectory("recs").toFile()
        val b = FakeBackend().apply { motionsHandler = { listOf(motion) } }
        val uploads = com.debatecoach.app.feature.recorder.UploadManager(
            b,
            object : com.debatecoach.app.feature.recorder.AudioUploader { override suspend fun put(url: String, headers: Map<String, String>, file: File, onProgress: (Long, Long) -> Unit) = Unit },
            object : com.debatecoach.app.feature.recorder.TrackUploader { override suspend fun upload(sessionId: String, track: com.debatecoach.app.visual.VisualSignalTrack) = 1 },
            object : com.debatecoach.app.core.util.Connectivity { override val online = kotlinx.coroutines.flow.MutableStateFlow(true) },
            kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.SupervisorJob() + kotlinx.coroutines.Dispatchers.Unconfined),
        )
        val store = ConsentStore(MemoryStore()).apply { consent?.let { set(it) } }
        return com.debatecoach.app.feature.recorder.RecorderViewModel(
            b, store, com.debatecoach.app.feature.FakeRecorder(), com.debatecoach.app.feature.FakeInterruptions(),
            { com.debatecoach.app.feature.FakeCapture() }, uploads, { dir }, video, clock = { clock },
        )
    }

    private var clock = 0.0

    @Test fun recorder_idle() {
        val vm = recorderVm(video = true, consent = ConsentChoice.IN)
        shoot("16-recorder-idle", setup = { vm.setMotion("carbon-tax") }) {
            com.debatecoach.app.feature.recorder.RecorderContent(vm, online = true, onClose = {}, onUploaded = {})
        }
    }

    @Test fun recorder_consent() {
        val vm = recorderVm(video = true)
        shoot("17-recorder-consent", setup = { compose.onNodeWithTag("start-recording").performClick() }) {
            com.debatecoach.app.feature.recorder.RecorderContent(vm, online = true, onClose = {}, onUploaded = {})
        }
    }

    @Test fun recorder_recording() {
        val vm = recorderVm(video = false)
        shoot("18-recorder-recording", setup = {
            vm.setMotion("carbon-tax")
            compose.onNodeWithTag("start-recording").performClick()
            clock = 83_000.0
        }) {
            com.debatecoach.app.feature.recorder.RecorderContent(vm, online = true, onClose = {}, onUploaded = {})
        }
    }

    @Test fun recorder_review() {
        val vm = recorderVm(video = false)
        shoot("19-recorder-review", setup = {
            compose.onNodeWithTag("start-recording").performClick()
            compose.waitForIdle()
            clock = 84_000.0
            vm.stopRecording()
        }) {
            com.debatecoach.app.feature.recorder.RecorderContent(vm, online = true, onClose = {}, onUploaded = {})
        }
    }

    @Test @Config(qualifiers = "w900dp-h1280dp-xhdpi") fun report_tablet() = shoot("20-report-tablet") {
        SessionContent(SessionViewModel(backend, "s1", "https://web.example"), onBack = {})
    }
}
