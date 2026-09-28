package com.debatecoach.app.ui

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.longClick
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTextReplacement
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeLeft
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.debatecoach.app.core.model.LatestProgressReport
import com.debatecoach.app.core.model.Motion
import com.debatecoach.app.core.model.ProgressPoint
import com.debatecoach.app.core.model.ProgressReport
import com.debatecoach.app.core.util.ConsentStore
import com.debatecoach.app.feature.account.AccountContent
import com.debatecoach.app.feature.account.AccountViewModel
import com.debatecoach.app.feature.account.DeleteAccountContent
import com.debatecoach.app.feature.progress.InsightsScreen
import com.debatecoach.app.feature.progress.ProgressScreen
import com.debatecoach.app.feature.progress.ProgressViewModel
import com.debatecoach.app.feature.sessions.SessionsScreen
import com.debatecoach.app.feature.sessions.SessionsViewModel
import com.debatecoach.app.testing.FakeBackend
import com.debatecoach.app.testing.MemoryStore
import com.debatecoach.app.testing.session
import com.debatecoach.app.ui.theme.DebateCoachTheme
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** The redesigned top-level screens: Sessions, Progress, Insights, Account. */
@RunWith(AndroidJUnit4::class)
class ScreensUiTest {
    @get:Rule val compose = createComposeRule()

    // ---------------------------------------------------------------
    // Sessions
    // ---------------------------------------------------------------

    private fun sessions(backend: FakeBackend, onOpen: (String) -> Unit = {}, onRecord: () -> Unit = {}): SessionsViewModel {
        val vm = SessionsViewModel(backend)
        compose.setContent { DebateCoachTheme { SessionsScreen(vm, online = true, onOpenSession = onOpen, onRecord = onRecord) } }
        compose.waitUntil(5_000) { vm.state.value.sessions != null }
        compose.waitForIdle()
        return vm
    }

    @Test
    fun an_empty_list_invites_a_first_recording() {
        var record = false
        sessions(FakeBackend(), onRecord = { record = true })
        compose.onNodeWithText("No sessions yet").assertIsDisplayed()
        compose.onNodeWithText("Record a speech").performClick()
        assertTrue(record)
    }

    @Test
    fun rows_show_name_score_motion_and_status_chips() {
        val backend = FakeBackend().apply {
            sessionsHandler = {
                listOf(
                    session("s1", title = "Nuclear energy", shared = true, motion = Motion("carbon-tax", "Climate policy", "x")),
                    session("s2", status = "transcribing", score = null, queueWait = 12.4, progress = 0.3),
                )
            }
        }
        var opened: String? = null
        sessions(backend, onOpen = { opened = it })
        compose.onNodeWithText("Nuclear energy").assertIsDisplayed()
        compose.onNodeWithContentDescription("Score 71").assertIsDisplayed()
        compose.onNodeWithText("Motion: Climate policy").assertIsDisplayed()
        compose.onNodeWithText("Shared").assertIsDisplayed()
        compose.onNodeWithText("Transcribing").assertIsDisplayed()
        compose.onNodeWithText("Waiting about 12 seconds for capacity").assertIsDisplayed()
        compose.onNodeWithTag("session-row-s1").assertHeightIsAtLeast(48.dp).performClick()
        assertEquals("s1", opened)
    }

    @Test
    fun swipe_to_delete_offers_undo_and_undo_sends_nothing() {
        val backend = FakeBackend().apply { sessionsHandler = { listOf(session("s1", title = "First"), session("s2", title = "Second")) } }
        val vm = sessions(backend)
        compose.onNodeWithTag("session-row-s1").performTouchInput { swipeLeft() }
        compose.waitForIdle()
        compose.onNodeWithText("Session deleted").assertIsDisplayed()
        compose.onNodeWithText("First").assertDoesNotExist()
        compose.onNodeWithText("Undo").performClick()
        compose.waitForIdle()
        compose.onNodeWithText("First").assertIsDisplayed()
        assertTrue(backend.calls.none { it.startsWith("deleteSession") })
        assertEquals(null, vm.state.value.pendingDelete)
    }

    @Test
    fun long_press_menu_deletes_once_the_undo_window_closes() {
        val backend = FakeBackend().apply { sessionsHandler = { listOf(session("s1", title = "First"), session("s2", title = "Second")) } }
        sessions(backend)
        compose.onNodeWithTag("session-row-s1").performTouchInput { longClick() }
        compose.waitForIdle()
        compose.onNodeWithText("Open report").assertIsDisplayed()
        compose.onNodeWithTag("menu-delete").performClick()
        compose.waitForIdle()
        compose.onNodeWithText("Session deleted").assertIsDisplayed()
        assertTrue(backend.calls.none { it.startsWith("deleteSession") })
        compose.mainClock.advanceTimeBy(11_000)
        compose.waitUntil(5_000) { backend.calls.contains("deleteSession:s1") }
    }

    // ---------------------------------------------------------------
    // Progress and Insights
    // ---------------------------------------------------------------

    private val points = listOf(
        ProgressPoint("a", "2026-09-20T10:00:00Z", "Opening", 52.0),
        ProgressPoint("b", "2026-09-22T10:00:00Z", "Rebuttal drill", 61.0),
        ProgressPoint("c", "2026-09-24T10:00:00Z", null, 68.0),
    )

    @Test
    fun progress_tapping_a_point_shows_its_card_and_tapping_again_opens_it() {
        val backend = FakeBackend().apply { progressHandler = { _, _ -> points } }
        val vm = ProgressViewModel(backend)
        var opened: String? = null
        compose.setContent { DebateCoachTheme { ProgressScreen(vm, completedCount = 3, onOpenSession = { opened = it }) } }
        compose.waitUntil(5_000) { vm.state.value.points != null }
        compose.waitForIdle()
        compose.onNodeWithTag("progress-tab").performScrollToNode(hasText("+16"))
        compose.onNodeWithText("Latest").assertIsDisplayed()
        compose.onNodeWithText("+16").assertIsDisplayed()
        compose.onNodeWithTag("progress-tab").performScrollToNode(hasTestTag("progress-chart"))

        compose.onNodeWithTag("progress-point-1").performClick()
        compose.waitForIdle()
        compose.onNodeWithTag("progress-tooltip").assertIsDisplayed()
        compose.onNodeWithText("Rebuttal drill").assertIsDisplayed()
        compose.onNodeWithText("Overall: 61").assertIsDisplayed()
        compose.onNodeWithTag("progress-point-1").performClick()
        assertEquals("b", opened)
    }

    @Test
    fun progress_score_type_is_a_native_dropdown() {
        val backend = FakeBackend().apply { progressHandler = { _, _ -> points } }
        val vm = ProgressViewModel(backend)
        compose.setContent { DebateCoachTheme { ProgressScreen(vm, completedCount = 3, onOpenSession = {}) } }
        compose.waitForIdle()
        compose.onNodeWithTag("metric").performClick()
        // Robolectric's injected touches don't always reach a popup window; call the item's own click.
        compose.onNodeWithTag("metric-logic").performSemanticsAction(SemanticsActions.OnClick)
        compose.waitUntil(5_000) { backend.calls.contains("progress:logic:10") }
        assertEquals("logic", vm.state.value.metric)
    }

    @Test
    fun progress_says_when_there_are_too_few_sessions() {
        val backend = FakeBackend().apply { progressHandler = { _, _ -> points.take(1) } }
        val vm = ProgressViewModel(backend)
        compose.setContent { DebateCoachTheme { ProgressScreen(vm, completedCount = 1, onOpenSession = {}) } }
        compose.waitUntil(5_000) { vm.state.value.points != null }
        compose.onNodeWithTag("progress-tab").performScrollToNode(hasText("Not enough sessions in this range yet."))
        compose.onNodeWithText("Not enough sessions in this range yet.").assertIsDisplayed()
    }

    @Test
    fun insights_generate_with_the_segmented_choice() {
        val backend = FakeBackend().apply {
            createReportHandler = { n -> ProgressReport("r", "2026-09-27", "2026-09-27T09:00:00Z", n, 3, listOf("Clearer structure.")) }
        }
        val vm = ProgressViewModel(backend)
        compose.setContent { DebateCoachTheme { InsightsScreen(vm, completedCount = 3) } }
        compose.waitUntil(5_000) { vm.state.value.latest != null }
        compose.waitForIdle()
        for (n in listOf(3, 5, 7)) compose.onNodeWithTag("count-$n").assertIsDisplayed().assertHeightIsAtLeast(48.dp)
        compose.onNodeWithTag("count-7").performClick()
        compose.onNodeWithTag("generate-report").assertIsEnabled().performClick()
        compose.waitUntil(5_000) { backend.calls.any { it.startsWith("createReport") } }
        assertEquals("createReport:7", backend.calls.first { it.startsWith("createReport") })
    }

    @Test
    fun insights_need_two_completed_sessions() {
        val vm = ProgressViewModel(FakeBackend())
        compose.setContent { DebateCoachTheme { InsightsScreen(vm, completedCount = 1) } }
        compose.waitUntil(5_000) { vm.state.value.latest != null }
        compose.onNodeWithTag("generate-report").assertIsNotEnabled()
        compose.onNodeWithText("A report compares sessions, so it needs at least 2 completed ones.").assertIsDisplayed()
    }

    @Test
    fun insights_once_a_day_shows_the_report_and_the_next_time() {
        val backend = FakeBackend().apply {
            latestHandler = {
                LatestProgressReport(
                    ProgressReport("r", "2026-09-27", "2026-09-27T09:00:00Z", 5, 5, listOf("Your pace steadied.", "Rebuttals got sharper.")),
                    canGenerate = false,
                    nextAvailableAt = "2026-09-28T00:00:00Z",
                )
            }
        }
        val vm = ProgressViewModel(backend)
        compose.setContent { DebateCoachTheme { InsightsScreen(vm, completedCount = 5) } }
        compose.waitUntil(5_000) { vm.state.value.latest != null }
        compose.waitForIdle()
        compose.onNodeWithTag("used-today").assertIsDisplayed()
        compose.onNodeWithText("Today's report is ready").assertIsDisplayed()
        compose.onNodeWithText("The next one is available from", substring = true).assertIsDisplayed()
        compose.onNodeWithTag("generate-report").assertDoesNotExist()
        compose.onNodeWithTag("insights").performScrollToNode(hasText("Your pace steadied."))
        compose.onNodeWithText("Your pace steadied.").assertIsDisplayed()
        compose.onNodeWithTag("insights").performScrollToNode(hasText("Rebuttals got sharper."))
        compose.onNodeWithText("Rebuttals got sharper.").assertIsDisplayed()
    }

    // ---------------------------------------------------------------
    // Account
    // ---------------------------------------------------------------

    @Test
    fun account_is_a_settings_list_with_links_sign_out_and_a_danger_zone() {
        val backend = FakeBackend()
        val opened = mutableListOf<String>()
        var deleteOpened = false
        compose.setContent {
            DebateCoachTheme { AccountContent(AccountViewModel(backend), ConsentStore(MemoryStore()), onOpenLink = { opened += it }, onDeleteAccount = { deleteOpened = true }) }
        }
        compose.waitForIdle()
        compose.onNodeWithText("Ada Lovelace").assertIsDisplayed()
        compose.onNodeWithText("a@example.com").assertIsDisplayed()
        compose.onNodeWithTag("link-privacy").performScrollTo().performClick()
        compose.onNodeWithTag("link-terms").performScrollTo().performClick()
        assertEquals(listOf("/privacy", "/terms"), opened)

        compose.onNodeWithTag("sign-out").performScrollTo().performClick()
        compose.onNodeWithText("Sign out?").assertIsDisplayed()
        compose.onNodeWithTag("confirm-sign-out").performClick()
        assertTrue(backend.calls.contains("signOut"))

        compose.onNodeWithTag("open-delete").performScrollTo().assertHeightIsAtLeast(48.dp).performClick()
        assertTrue(deleteOpened)
    }

    @Test
    fun delete_account_needs_delete_typed_and_the_password() {
        val backend = FakeBackend()
        compose.setContent { DebateCoachTheme { DeleteAccountContent(AccountViewModel(backend), onClose = {}) } }
        val button = compose.onNodeWithTag("confirm-delete-account")
        button.performScrollTo().assertIsNotEnabled()
        compose.onNodeWithTag("confirm-field").performTextInput("delete")
        compose.onNodeWithTag("delete-password").performTextInput("pw")
        button.performScrollTo().assertIsNotEnabled()
        compose.onNodeWithTag("confirm-field").performTextReplacement("DELETE")
        button.performScrollTo().assertIsEnabled().performClick()
        compose.waitUntil(5_000) { backend.calls.contains("deleteAccount") }
    }
}
