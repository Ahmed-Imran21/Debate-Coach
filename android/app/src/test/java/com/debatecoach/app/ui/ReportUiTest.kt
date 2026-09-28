package com.debatecoach.app.ui

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollToNode
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.debatecoach.app.core.model.AudioAnalysis
import com.debatecoach.app.core.model.CorrelatedMoment
import com.debatecoach.app.core.model.CountStats
import com.debatecoach.app.core.model.FeedbackItem
import com.debatecoach.app.core.model.InstanceStats
import com.debatecoach.app.core.model.MomentAnchor
import com.debatecoach.app.core.model.MomentObservation
import com.debatecoach.app.core.model.Motion
import com.debatecoach.app.core.model.PauseSpan
import com.debatecoach.app.core.model.RawMetrics
import com.debatecoach.app.core.model.SessionReport
import com.debatecoach.app.core.model.SpeechStats
import com.debatecoach.app.core.model.TimedInstance
import com.debatecoach.app.core.model.VideoAnalysisView
import com.debatecoach.app.core.model.VisualContext
import com.debatecoach.app.core.model.VisualMetric
import com.debatecoach.app.core.model.VisualQuality
import com.debatecoach.app.feature.report.MOTION_NOT_APPLIED_NOTE
import com.debatecoach.app.feature.report.SessionContent
import com.debatecoach.app.feature.report.SessionViewModel
import com.debatecoach.app.testing.FakeBackend
import com.debatecoach.app.testing.session
import com.debatecoach.app.ui.theme.DebateCoachTheme
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class ReportUiTest {
    @get:Rule val compose = createComposeRule()

    private val report = SessionReport(
        id = "s1",
        title = "Second constructive",
        status = "completed",
        motion = Motion("carbon-tax", "Climate policy", "This house would introduce a carbon tax."),
        motionNotApplied = true,
        createdAt = "2026-09-26T10:00:00Z",
        scores = mapOf("overall" to 68.4, "quantitative" to 72.0, "argumentation" to 61.0, "rebuttal" to null, "structure" to 70.0, "persuasion" to 64.0, "logic" to 58.0),
        feedback = listOf(
            FeedbackItem("argumentation", "Claims without warrants", "Two claims had no reasoning.", "high", listOf("It is simply better."), "Explain why.", "Add a because."),
            FeedbackItem("quantitative", "Steady pace", "Your pace held at 140 wpm.", "positive"),
            FeedbackItem("structure", "Signposting", "Transitions were abrupt.", "medium"),
        ),
        rawMetrics = RawMetrics(
            speech = SpeechStats(totalDuration = 130.0, speechDuration = 118.0, wordsPerMinute = 141.6),
            pauses = CountStats(5),
            fillers = InstanceStats(3, listOf(TimedInstance("um", 12.0), TimedInstance("like", 40.0))),
            stutters = InstanceStats(1, listOf(TimedInstance("the", 70.0))),
        ),
        analysis = AudioAnalysis(130.0, listOf(PauseSpan(20.0, 22.0, 2.0), PauseSpan(50.0, 50.5, 0.5))),
        audioUrl = null,
        videoAnalysisStatus = "processed",
        visualCoachingStatus = "failed",
        videoAnalysis = VideoAnalysisView(
            VisualQuality(VisualContext("camera_audience"), listOf("calibration_skipped")),
            mapOf(
                "camera_facing_ratio" to VisualMetric("ok", 0.62, "high"),
                "gesture_rate_per_min" to VisualMetric("insufficient_coverage", null, null),
            ),
        ),
        correlatedMoments = listOf(
            CorrelatedMoment("m1", "improve", MomentAnchor("claim"), 42.0, 55.0, "Nuclear is safe", listOf(MomentObservation("o1", "event", type = "gaze_away", durationS = 2.4, direction = "down")), 0.9),
        ),
    )

    private fun viewModel(r: SessionReport = report): Pair<SessionViewModel, FakeBackend> {
        val backend = FakeBackend().apply {
            getSessionHandler = { session(it) }
            reportHandler = { r }
        }
        return SessionViewModel(backend, "s1", "https://web-debate-coach1.vercel.app") to backend
    }

    private fun show(vm: SessionViewModel, onDeleted: () -> Unit = {}) {
        compose.setContent { DebateCoachTheme { SessionContent(vm, onBack = {}, onDeleted = onDeleted) } }
        compose.waitUntil(5_000) { vm.state.value.report != null }
        compose.waitForIdle()
    }

    private fun openTab(tag: String) {
        compose.onNodeWithTag("tab-$tag").performClick()
        compose.waitForIdle()
    }

    /** Scrolls the current tab's list to the node with this text. */
    private fun scrollTo(list: String, text: String, substring: Boolean = false) {
        compose.onNodeWithTag(list).performScrollToNode(hasText(text, substring = substring))
    }

    @Test
    fun the_header_shows_the_name_and_overall_score() {
        val (vm, _) = viewModel()
        show(vm)
        compose.onAllNodesWithText("Second constructive").onFirst().assertIsDisplayed()
        compose.onNodeWithContentDescription("Overall score 68 out of 100").assertIsDisplayed()
        compose.onAllNodesWithText("Recorded", substring = true).onFirst().assertIsDisplayed()
    }

    @Test
    fun overview_has_the_prompt_scores_figures_and_timeline() {
        val (vm, _) = viewModel()
        show(vm)
        compose.onNodeWithTag("report-meta").assertIsDisplayed()
        compose.onNodeWithText("Motion: This house would introduce a carbon tax.", substring = true).assertIsDisplayed()
        compose.onNodeWithText(MOTION_NOT_APPLIED_NOTE, substring = true).assertIsDisplayed()

        scrollTo("overview", "Not scored: nothing to rebut")
        compose.onNodeWithText("Not scored: nothing to rebut").assertIsDisplayed()

        for (value in listOf("142", "Words per minute", "1:58", "Filler words", "Stutters")) {
            scrollTo("overview", value)
            compose.onNodeWithText(value).assertIsDisplayed()
        }
        scrollTo("overview", "Where each finding landed")
        compose.onNodeWithTag("speech-track").assertIsDisplayed()
        for (legend in listOf("Pause over one second", "Filler word", "Stutter")) {
            scrollTo("overview", legend)
            compose.onNodeWithText(legend).assertIsDisplayed()
        }
    }

    @Test
    fun findings_filter_by_category_in_severity_order_and_expand() {
        val (vm, _) = viewModel()
        show(vm)
        compose.onNodeWithText("Findings (3)").assertIsDisplayed()
        openTab("findings")

        // Every finding is reachable, most severe first.
        for (title in listOf("Claims without warrants", "Signposting", "Steady pace")) scrollTo("findings", title)

        compose.onNodeWithTag("filter-structure").performClick()
        compose.waitForIdle()
        scrollTo("findings", "Signposting")
        compose.onNodeWithText("Worth fixing").assertIsDisplayed()
        // Filtered out: no longer anywhere in the list.
        assertThrows(AssertionError::class.java) { scrollTo("findings", "Claims without warrants") }
        assertThrows(AssertionError::class.java) { scrollTo("findings", "Steady pace") }

        compose.onNodeWithTag("filter-all").performClick()
        compose.waitForIdle()
        scrollTo("findings", "Claims without warrants")
        compose.onNodeWithText("Needs work").assertIsDisplayed()
        // Evidence and advice show once the card is expanded.
        compose.onNodeWithText("It is simply better.").assertDoesNotExist()
        compose.onNodeWithText("Claims without warrants").performClick()
        compose.waitForIdle()
        scrollTo("findings", "It is simply better.", substring = true)
        compose.onNodeWithText("It is simply better.").assertIsDisplayed()
        compose.onNodeWithText("Add a because.").assertIsDisplayed()
    }

    @Test
    fun the_visual_tab_has_delivery_and_key_moments() {
        val (vm, _) = viewModel()
        show(vm)
        openTab("visual")
        for (text in listOf("Visual delivery", "Facing the camera", "62%", "High confidence")) {
            scrollTo("visual", text)
            compose.onNodeWithText(text).assertIsDisplayed()
        }
        scrollTo("visual", "Camera calibration was skipped, so facing measurements are less certain.")
        scrollTo("visual", "Looked down for 2.4s", substring = true)
        compose.onNodeWithText("0:42–0:55. Claim").assertIsDisplayed()
    }

    @Test
    fun no_visual_tab_without_visual_data() {
        val (vm, _) = viewModel(report.copy(videoAnalysisStatus = "not_requested", videoAnalysis = null, correlatedMoments = null, visualCoachingStatus = "not_requested"))
        show(vm)
        compose.onNodeWithTag("tab-overview").assertIsDisplayed()
        compose.onNodeWithTag("tab-findings").assertIsDisplayed()
        compose.onNodeWithTag("tab-visual").assertDoesNotExist()
    }

    @Test
    fun share_sheet_creates_a_link_to_the_website_and_can_stop() {
        val (vm, backend) = viewModel()
        show(vm)
        compose.onNodeWithTag("share-button").performClick()
        compose.waitForIdle()
        compose.onNodeWithText("Only you can see this report.").assertIsDisplayed()
        compose.onNodeWithTag("create-share").performClick()
        compose.waitUntil(5_000) { backend.calls.contains("createShare") }
        compose.waitForIdle()
        compose.onNodeWithText("https://web-debate-coach1.vercel.app/shared/tok_abc-123").assertIsDisplayed()
        compose.onNodeWithText("Anyone with this link can view this report").assertIsDisplayed()
        for (action in listOf("Copy link", "Share via…", "Create new link", "Stop sharing")) compose.onNodeWithText(action).assertIsDisplayed()

        compose.onNodeWithTag("stop-share").performClick()
        compose.waitUntil(5_000) { backend.calls.contains("stopSharing") }
        compose.waitForIdle()
        compose.onNodeWithText("Only you can see this report.").assertIsDisplayed()
    }

    @Test
    fun the_overflow_menu_exports_and_deletes() {
        val (vm, backend) = viewModel()
        var deleted = false
        show(vm, onDeleted = { deleted = true })
        compose.onNodeWithTag("overflow").performClick()
        compose.onNodeWithText("Export as PDF").assertIsDisplayed()
        compose.onNodeWithTag("delete-session").performClick()
        compose.onNodeWithText("Delete this session?").assertIsDisplayed()
        compose.onNodeWithTag("confirm-delete").performClick()
        compose.waitUntil(5_000) { deleted }
        assertTrue(backend.calls.contains("deleteSession:s1"))
    }
}
