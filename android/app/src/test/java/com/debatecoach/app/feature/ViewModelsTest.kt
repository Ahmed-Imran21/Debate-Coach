package com.debatecoach.app.feature

import com.debatecoach.app.core.model.LatestProgressReport
import com.debatecoach.app.core.model.ProgressPoint
import com.debatecoach.app.core.model.ProgressReport
import com.debatecoach.app.core.model.SessionReport
import com.debatecoach.app.core.model.ShareStatus
import com.debatecoach.app.core.net.ApiException
import com.debatecoach.app.core.net.NetworkException
import com.debatecoach.app.core.net.UNREACHABLE_MESSAGE
import com.debatecoach.app.feature.account.AccountViewModel
import com.debatecoach.app.feature.auth.AuthViewModel
import com.debatecoach.app.feature.auth.CONSENT_REQUIRED_MESSAGE
import com.debatecoach.app.feature.progress.ProgressViewModel
import com.debatecoach.app.feature.progress.buildChart
import com.debatecoach.app.feature.progress.describeChart
import com.debatecoach.app.feature.report.SESSION_POLL_MS
import com.debatecoach.app.feature.report.SessionViewModel
import com.debatecoach.app.feature.report.ShareUi
import com.debatecoach.app.feature.sessions.POLL_MS
import com.debatecoach.app.feature.sessions.SessionsEvent
import com.debatecoach.app.feature.sessions.SessionsViewModel
import com.debatecoach.app.feature.sessions.rowMeta
import com.debatecoach.app.testing.FakeBackend
import com.debatecoach.app.testing.MainDispatcherRule
import com.debatecoach.app.testing.session
import java.io.IOException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

class AuthViewModelTest {
    @get:Rule val main = MainDispatcherRule()

    @Test
    fun `sign-up refuses a short password before calling the server`() = runTest(main.dispatcher) {
        val backend = FakeBackend()
        val vm = AuthViewModel(backend, signup = true)
        vm.update { copy(email = "a@example.com", password = "short", firstName = "A", lastName = "B") }
        vm.submit()
        assertEquals("Use a password of at least 8 characters.", vm.state.value.error)
        assertTrue(backend.calls.isEmpty())
    }

    @Test
    fun `sign-up needs both boxes ticked before calling the server, then sends both`() = runTest(main.dispatcher) {
        val backend = FakeBackend()
        val vm = AuthViewModel(backend, signup = true)
        vm.update { copy(email = "a@example.com", password = "long enough", firstName = "A", lastName = "B") }
        assertFalse(vm.state.value.consentGiven)
        vm.submit()
        assertTrue(vm.state.value.consentError)
        assertTrue(backend.calls.isEmpty())

        vm.update { copy(acceptedPrivacyPolicy = true) }
        vm.submit()
        assertTrue(backend.calls.isEmpty())

        vm.update { copy(acceptedTerms = true) }
        assertFalse("ticking both clears the explanation", vm.state.value.consentError)
        vm.submit()
        advanceUntilIdle()
        assertEquals(listOf("signUp"), backend.calls)
        assertEquals(true to true, backend.lastSignUpConsent)
        assertTrue(vm.state.value.done)
    }

    @Test
    fun `the backend's consent refusal is shown as is`() = runTest(main.dispatcher) {
        val backend = FakeBackend().apply { signUpHandler = { _, _, _, _ -> throw ApiException(422, CONSENT_REQUIRED_MESSAGE) } }
        val vm = AuthViewModel(backend, signup = true)
        vm.update { copy(email = "a@example.com", password = "long enough", firstName = "A", lastName = "B", acceptedPrivacyPolicy = true, acceptedTerms = true) }
        vm.submit()
        advanceUntilIdle()
        assertEquals(CONSENT_REQUIRED_MESSAGE, vm.state.value.error)
    }

    @Test
    fun `the form survives the process being killed, except the password`() = runTest(main.dispatcher) {
        val saved = androidx.lifecycle.SavedStateHandle()
        val vm = AuthViewModel(FakeBackend(), signup = true, saved)
        vm.update { copy(email = "a@example.com", password = "secret123", firstName = "Ada", lastName = "L", acceptedPrivacyPolicy = true) }
        val restored = AuthViewModel(FakeBackend(), signup = true, saved).state.value
        assertEquals("a@example.com", restored.email)
        assertEquals("Ada", restored.firstName)
        assertTrue(restored.acceptedPrivacyPolicy)
        assertFalse(restored.acceptedTerms)
        assertEquals("", restored.password)
    }

    @Test
    fun `sign-in shows the server's message, or the connection message`() = runTest(main.dispatcher) {
        val backend = FakeBackend()
        val vm = AuthViewModel(backend, signup = false)
        vm.update { copy(email = " a@example.com ", password = "pw") }
        backend.signInHandler = { _, _ -> throw ApiException(401, "Incorrect email or password.") }
        vm.submit()
        advanceUntilIdle()
        assertEquals("Incorrect email or password.", vm.state.value.error)
        assertEquals("signIn:a@example.com", backend.calls.single())

        backend.signInHandler = { _, _ -> throw NetworkException(IOException("offline")) }
        vm.submit()
        advanceUntilIdle()
        assertEquals(UNREACHABLE_MESSAGE, vm.state.value.error)
        assertFalse(vm.state.value.busy)

        backend.signInHandler = { _, _ -> }
        vm.submit()
        advanceUntilIdle()
        assertTrue(vm.state.value.done)
        assertNull(vm.state.value.error)
    }
}

class SessionsViewModelTest {
    @get:Rule val main = MainDispatcherRule()

    @Test
    fun `polls every 4 seconds while something is still moving, then stops`() = runTest(main.dispatcher) {
        var status = "transcribing"
        val backend = FakeBackend().apply { sessionsHandler = { listOf(session("s1", status = status, score = null, queueWait = 12.4, progress = 0.29)) } }
        val vm = SessionsViewModel(backend)
        vm.startPolling()
        runCurrent()
        assertEquals(1, backend.calls.count { it == "listSessions" })
        assertEquals("Transcribing. Waiting about 12 seconds for capacity.", rowMeta(vm.state.value.sessions!!.single()))
        advanceTimeBy(POLL_MS)
        runCurrent()
        assertEquals(2, backend.calls.count { it == "listSessions" })
        status = "completed"
        advanceTimeBy(POLL_MS)
        runCurrent()
        advanceTimeBy(10 * POLL_MS)
        runCurrent()
        assertEquals("stops once everything is terminal", 3, backend.calls.count { it == "listSessions" })
        vm.stopPolling()
    }

    @Test
    fun `a load error keeps retrying with the website's message`() = runTest(main.dispatcher) {
        val backend = FakeBackend().apply { sessionsHandler = { throw NetworkException(IOException("x")) } }
        val vm = SessionsViewModel(backend)
        vm.startPolling()
        runCurrent()
        assertEquals("Could not load your sessions. Retrying.", vm.state.value.error)
        advanceTimeBy(POLL_MS)
        runCurrent()
        assertEquals(2, backend.calls.size)
        vm.stopPolling()
    }

    @Test
    fun `swipe delete hides the row at once and only deletes when the undo window closes`() = runTest(main.dispatcher) {
        val backend = FakeBackend().apply { sessionsHandler = { listOf(session("s1"), session("s2")) } }
        val vm = SessionsViewModel(backend)
        val events = mutableListOf<SessionsEvent>()
        val collector = backgroundScope.launch { vm.events.collect { events += it } }
        runCurrent()
        vm.load()

        vm.deleteWithUndo(vm.state.value.visible!!.first())
        runCurrent()
        assertEquals(listOf("s2"), vm.state.value.visible!!.map { it.id })
        assertEquals("s1", (events.single() as SessionsEvent.Deleted).session.id)
        assertTrue("nothing sent while Undo is on offer", backend.calls.none { it.startsWith("deleteSession") })

        vm.commitDelete()
        advanceUntilIdle()
        assertEquals(listOf("deleteSession:s1"), backend.calls.filter { it.startsWith("deleteSession") })
        assertEquals(listOf("s2"), vm.state.value.visible!!.map { it.id })
        assertNull(vm.state.value.pendingDelete)
        collector.cancel()
    }

    @Test
    fun `undo brings the row back and sends nothing`() = runTest(main.dispatcher) {
        val backend = FakeBackend().apply { sessionsHandler = { listOf(session("s1"), session("s2")) } }
        val vm = SessionsViewModel(backend)
        vm.load()
        vm.deleteWithUndo(vm.state.value.visible!!.first())
        vm.undoDelete()
        vm.commitDelete() // the snackbar going away after Undo: a no-op
        advanceUntilIdle()
        assertEquals(listOf("s1", "s2"), vm.state.value.visible!!.map { it.id })
        assertTrue(backend.calls.none { it.startsWith("deleteSession") })
    }

    @Test
    fun `a polled refresh doesn't bring a pending delete back`() = runTest(main.dispatcher) {
        val backend = FakeBackend().apply { sessionsHandler = { listOf(session("s1"), session("s2")) } }
        val vm = SessionsViewModel(backend)
        vm.load()
        vm.deleteWithUndo(vm.state.value.visible!!.first())
        vm.load()
        assertEquals(listOf("s2"), vm.state.value.visible!!.map { it.id })
        assertEquals("the completed count ignores it too", 1, vm.state.value.completedCount)
    }

    @Test
    fun `a failed delete restores the row, with the website's messages`() = runTest(main.dispatcher) {
        val backend = FakeBackend().apply { sessionsHandler = { listOf(session("s1"), session("s2")) } }
        val vm = SessionsViewModel(backend)
        val events = mutableListOf<SessionsEvent>()
        val collector = backgroundScope.launch { vm.events.collect { events += it } }
        runCurrent()
        vm.load()

        backend.deleteSessionHandler = { throw ApiException(409, "still analysing") }
        vm.deleteWithUndo(vm.state.value.visible!!.first())
        vm.commitDelete()
        advanceUntilIdle()
        runCurrent() // advanceUntilIdle leaves background work (the collector) for runCurrent
        assertEquals(listOf("s1", "s2"), vm.state.value.visible!!.map { it.id })
        assertEquals("Could not delete that session. Try again.", events.filterIsInstance<SessionsEvent.Message>().last().text)

        backend.deleteSessionHandler = { throw ApiException(404, "Not found") }
        vm.deleteWithUndo(vm.state.value.visible!!.first())
        vm.commitDelete()
        advanceUntilIdle()
        runCurrent()
        assertEquals(listOf("s2"), vm.state.value.visible!!.map { it.id })
        assertEquals("That session was already gone.", events.filterIsInstance<SessionsEvent.Message>().last().text)
        collector.cancel()
    }

    @Test
    fun `row text matches the practice page`() {
        val done = session("s1", status = "completed", motion = com.debatecoach.app.core.model.Motion("m", "Climate policy", "x"))
        assertTrue(rowMeta(done).startsWith("Motion: Climate policy. "))
        assertTrue(rowMeta(done).endsWith("2:05 of speech at 142 words per minute. 7 findings."))
        assertEquals("Analysis failed.", rowMeta(session("s", status = "failed")))
        assertEquals("Queued.", rowMeta(session("s", status = "queued")))
    }
}

class ProgressViewModelTest {
    @get:Rule val main = MainDispatcherRule()

    @Test
    fun `a slower response for an earlier selection never overwrites the current one`() = runTest(main.dispatcher) {
        val slow = CompletableDeferred<List<ProgressPoint>>()
        val backend = FakeBackend().apply {
            progressHandler = { metric, _ -> if (metric == "overall") slow.await() else listOf(ProgressPoint("a", "2026-09-01T00:00:00Z", null, 50.0)) }
        }
        val vm = ProgressViewModel(backend)
        vm.loadChart()
        runCurrent()
        vm.setMetric("logic")
        runCurrent()
        slow.complete(listOf(ProgressPoint("z", "2026-09-01T00:00:00Z", null, 99.0)))
        advanceUntilIdle()
        assertEquals("a", vm.state.value.points!!.single().sessionId)
    }

    @Test
    fun `already used today (429) says nothing and shows the next time from latest`() = runTest(main.dispatcher) {
        val backend = FakeBackend().apply {
            createReportHandler = { throw ApiException(429, "One progress report per day.") }
            latestHandler = { LatestProgressReport(ProgressReport("r", "2026-09-27", "2026-09-27T09:00:00Z", 5, 5, listOf("Better.")), false, "2026-09-28T00:00:00Z") }
        }
        val vm = ProgressViewModel(backend)
        vm.setCount(7)
        vm.generate()
        advanceUntilIdle()
        assertEquals("createReport:7", backend.calls.first { it.startsWith("createReport") })
        assertNull(vm.state.value.generateError)
        assertFalse(vm.state.value.latest!!.canGenerate)
    }

    @Test
    fun `pull to refresh reloads both, keeping the chart on screen meanwhile`() = runTest(main.dispatcher) {
        var score = 50.0
        val gate = CompletableDeferred<Unit>()
        val backend = FakeBackend().apply {
            progressHandler = { _, _ -> if (score > 50.0) gate.await(); listOf(ProgressPoint("a", "2026-09-01T00:00:00Z", null, score)) }
        }
        val vm = ProgressViewModel(backend)
        vm.loadChart()
        advanceUntilIdle()
        score = 80.0 // changed on the website
        vm.refresh()
        runCurrent()
        assertTrue(vm.state.value.refreshing)
        assertEquals(50.0, vm.state.value.points!!.single().score!!, 0.0)
        gate.complete(Unit)
        advanceUntilIdle()
        assertFalse(vm.state.value.refreshing)
        assertEquals(80.0, vm.state.value.points!!.single().score!!, 0.0)
        assertEquals(1, backend.calls.count { it == "latest" })
    }

    @Test
    fun `other failures show a message`() = runTest(main.dispatcher) {
        val backend = FakeBackend().apply { createReportHandler = { throw NetworkException(IOException("x")) } }
        val vm = ProgressViewModel(backend)
        vm.generate()
        advanceUntilIdle()
        assertEquals("Could not generate the report. Try again shortly.", vm.state.value.generateError)
    }

    @Test
    fun `the chart skips unscored sessions and needs two points`() {
        val points = listOf(
            ProgressPoint("a", "2026-09-01T00:00:00Z", null, 40.0),
            ProgressPoint("b", "2026-09-02T00:00:00Z", null, null),
            ProgressPoint("c", "2026-09-03T00:00:00Z", "Round 3", 70.0),
        )
        val chart = buildChart(points)
        assertTrue(chart.enough)
        assertEquals(listOf("a", "c"), chart.points.map { it.sessionId })
        assertEquals(0f, chart.points[0].x)
        assertEquals(1f, chart.points[1].x)
        assertEquals(0.3f, chart.points[1].y, 1e-6f)
        assertFalse(buildChart(points.take(2)).enough)
        assertEquals("Logic score over 2 sessions, from 40 on 1 Sept to 70 on 3 Sept.", describeChart(chart, "Logic"))
    }
}

class SessionViewModelTest {
    @get:Rule val main = MainDispatcherRule()

    private val report = SessionReport(id = "s1", status = "completed", createdAt = "2026-09-26T10:00:00Z")

    @Test
    fun `polls until the session completes, then loads the report and sharing`() = runTest(main.dispatcher) {
        var status = "coaching"
        val backend = FakeBackend().apply {
            getSessionHandler = { session(it, status = status) }
            reportHandler = { report }
            shareStatusHandler = { ShareStatus(true) }
        }
        val vm = SessionViewModel(backend, "s1", "https://web.example")
        vm.startPolling()
        runCurrent()
        assertNull(vm.state.value.report)
        status = "completed"
        advanceTimeBy(SESSION_POLL_MS)
        advanceUntilIdle()
        assertEquals(report, vm.state.value.report)
        assertEquals(ShareUi.Shared(null), vm.state.value.share)
        val requests = backend.calls.count { it.startsWith("getSession") }
        advanceTimeBy(5 * SESSION_POLL_MS)
        assertEquals(requests, backend.calls.count { it.startsWith("getSession") })
    }

    @Test
    fun `a missing session says so and stops`() = runTest(main.dispatcher) {
        val backend = FakeBackend().apply { getSessionHandler = { throw ApiException(404, "Not found") } }
        val vm = SessionViewModel(backend, "gone", "https://web.example")
        vm.startPolling()
        advanceUntilIdle()
        assertEquals("That session does not exist.", vm.state.value.error)
    }

    @Test
    fun `creating a link shows the website's shared URL, stopping hides it`() = runTest(main.dispatcher) {
        val backend = FakeBackend().apply {
            getSessionHandler = { session(it) }
            reportHandler = { report }
        }
        val vm = SessionViewModel(backend, "s1", "https://web-debate-coach1.vercel.app/")
        vm.startPolling()
        advanceUntilIdle()
        assertEquals(ShareUi.Private, vm.state.value.share)
        vm.createShareLink()
        advanceUntilIdle()
        assertEquals(ShareUi.Shared("https://web-debate-coach1.vercel.app/shared/tok_abc-123"), vm.state.value.share)
        vm.markCopied()
        assertTrue(vm.state.value.copied)
        advanceTimeBy(2_001)
        assertFalse(vm.state.value.copied)
        vm.stopSharing()
        advanceUntilIdle()
        assertEquals(ShareUi.Private, vm.state.value.share)

        backend.createShareHandler = { throw NetworkException(IOException("x")) }
        vm.createShareLink()
        advanceUntilIdle()
        assertEquals("Could not create a share link. Try again.", vm.state.value.shareError)
    }

    @Test
    fun `delete from the report's menu, with the website's messages`() = runTest(main.dispatcher) {
        val backend = FakeBackend().apply { deleteSessionHandler = { throw ApiException(409, "still analysing") } }
        val vm = SessionViewModel(backend, "s1", "https://web.example")
        vm.delete()
        advanceUntilIdle()
        assertEquals("Could not delete that session. Try again.", vm.state.value.deleteError)
        assertFalse(vm.state.value.deleted)

        backend.deleteSessionHandler = {}
        vm.delete()
        advanceUntilIdle()
        assertTrue(vm.state.value.deleted)
        assertEquals(2, backend.calls.count { it == "deleteSession:s1" })

        // Already gone elsewhere (the website): still leaves the report.
        val gone = SessionViewModel(FakeBackend().apply { deleteSessionHandler = { throw ApiException(404, "Not found") } }, "s2", "https://web.example")
        gone.delete()
        advanceUntilIdle()
        assertTrue(gone.state.value.deleted)
    }
}

class AccountViewModelTest {
    @get:Rule val main = MainDispatcherRule()

    @Test
    fun `delete needs DELETE typed and a password`() = runTest(main.dispatcher) {
        val backend = FakeBackend()
        val vm = AccountViewModel(backend)
        vm.openDelete()
        vm.setConfirm("delete")
        vm.setPassword("pw")
        assertFalse(vm.state.value.canDelete)
        vm.delete()
        assertTrue(backend.calls.isEmpty())
        vm.setConfirm("DELETE")
        assertTrue(vm.state.value.canDelete)
        vm.delete()
        advanceUntilIdle()
        assertEquals(listOf("deleteAccount"), backend.calls)
    }

    @Test
    fun `a wrong password keeps the dialog open with the web's message`() = runTest(main.dispatcher) {
        val backend = FakeBackend().apply { deleteAccountHandler = { throw ApiException(401, "Incorrect password.") } }
        val vm = AccountViewModel(backend)
        vm.openDelete()
        vm.setConfirm("DELETE")
        vm.setPassword("wrong")
        vm.delete()
        advanceUntilIdle()
        assertEquals("Incorrect password.", vm.state.value.deleteError)
        assertTrue(vm.state.value.deleteOpen)

        backend.deleteAccountHandler = { throw NetworkException(IOException("x")) }
        vm.delete()
        advanceUntilIdle()
        assertEquals("Could not delete your account. Try again.", vm.state.value.deleteError)
    }
}
