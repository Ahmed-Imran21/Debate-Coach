package com.debatecoach.app.ui

import android.Manifest
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.debatecoach.app.core.model.Motion
import com.debatecoach.app.core.util.ConsentStore
import com.debatecoach.app.core.util.Connectivity
import com.debatecoach.app.feature.FakeCapture
import com.debatecoach.app.feature.FakeInterruptions
import com.debatecoach.app.feature.FakeRecorder
import com.debatecoach.app.feature.recorder.AudioUploader
import com.debatecoach.app.feature.recorder.RecorderContent
import com.debatecoach.app.feature.recorder.RecorderViewModel
import com.debatecoach.app.feature.recorder.TrackUploader
import com.debatecoach.app.feature.recorder.UploadManager
import com.debatecoach.app.testing.FakeBackend
import com.debatecoach.app.testing.MemoryStore
import com.debatecoach.app.ui.theme.DebateCoachTheme
import com.debatecoach.app.visual.VisualSignalTrack
import java.io.File
import java.nio.file.Files
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Shadows.shadowOf

@RunWith(AndroidJUnit4::class)
class RecorderUiTest {
    @get:Rule val compose = createComposeRule()

    private val backend = FakeBackend().apply {
        motionsHandler = { listOf(Motion("carbon-tax", "Climate policy", "This house would introduce a carbon tax.")) }
    }
    private val recorder = FakeRecorder()
    private var clock = 0.0

    @Before
    fun grantMicrophone() {
        shadowOf(ApplicationProvider.getApplicationContext<android.app.Application>()).grantPermissions(Manifest.permission.RECORD_AUDIO)
    }

    private fun viewModel(videoEnabled: Boolean): RecorderViewModel {
        val dir: File = Files.createTempDirectory("recs").toFile()
        // Robolectric keeps the main looper paused; the fakes finish at once, so run the upload inline.
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        val uploads = UploadManager(
            backend,
            object : AudioUploader { override suspend fun put(url: String, headers: Map<String, String>, file: File, onProgress: (Long, Long) -> Unit) = Unit },
            object : TrackUploader { override suspend fun upload(sessionId: String, track: VisualSignalTrack) = 1 },
            object : Connectivity { override val online = MutableStateFlow(true) },
            scope,
        )
        return RecorderViewModel(backend, ConsentStore(MemoryStore()), recorder, FakeInterruptions(), { FakeCapture() }, uploads, { dir }, videoEnabled, clock = { clock })
    }

    @Test
    fun record_stop_review_and_send() {
        val vm = viewModel(videoEnabled = false)
        var uploaded: String? = null
        compose.setContent { DebateCoachTheme { RecorderContent(vm, online = true, onClose = {}, onUploaded = { uploaded = it }) } }

        compose.onNodeWithText("Record a speech").assertIsDisplayed()
        compose.onNodeWithText("Practice prompt (optional)").assertIsDisplayed()
        compose.onNodeWithTag("start-recording").performClick()
        compose.waitForIdle()

        compose.onNodeWithTag("timer").assertIsDisplayed()
        compose.onNodeWithText("Recording in progress.").assertIsDisplayed()
        clock = 84_000.0 // the fake recorder started at 1,000 ms: 83 seconds
        compose.onNodeWithTag("stop-recording").performScrollTo().performClick()
        compose.waitForIdle()

        compose.onNodeWithText("Recording of 1:23").assertIsDisplayed()
        compose.onNodeWithText("Name this session (optional)").performScrollTo().assertIsDisplayed()
        compose.onNodeWithTag("submit-recording").performScrollTo().performClick()
        try {
            compose.waitUntil(5_000) { uploaded != null }
        } catch (e: Throwable) {
            throw AssertionError("phase=${vm.state.value.phase} upload=${vm.uploadState.value} error=${vm.state.value.error} calls=${backend.calls}", e)
        }

        assertEquals("s-new", uploaded)
        assertTrue(backend.calls.any { it.startsWith("createSession:audio/mp4") })
        assertTrue(backend.calls.last().startsWith("startSession:s-new"))
    }

    @Test
    fun asks_about_visual_feedback_first_and_remembers_the_answer() {
        val vm = viewModel(videoEnabled = true)
        compose.setContent { DebateCoachTheme { RecorderContent(vm, online = true, onClose = {}, onUploaded = {}) } }

        compose.onNodeWithTag("start-recording").performClick()
        compose.waitForIdle()
        compose.onNodeWithText("Visual feedback (optional)").assertIsDisplayed()
        compose.onNodeWithText("No video is recorded, uploaded, or saved. No identity recognition. No emotion detection.").assertIsDisplayed()

        compose.onNodeWithTag("consent-out").performScrollTo().performClick()
        compose.waitForIdle()
        compose.onNodeWithText("Speak as you would in a round. Debate Coach will ask for microphone access the first time. Visual feedback is off.").assertIsDisplayed()
        compose.onNodeWithText("Change visual feedback setting").assertIsDisplayed()
    }

    @Test
    fun the_motion_wording_is_shown_when_picked() {
        val vm = viewModel(videoEnabled = false)
        compose.setContent { DebateCoachTheme { RecorderContent(vm, online = true, onClose = {}, onUploaded = {}) } }
        compose.waitForIdle()
        vm.setMotion("carbon-tax")
        compose.waitForIdle()
        compose.onNodeWithText("This house would introduce a carbon tax. Your coaching will also judge how well you address it.").assertIsDisplayed()

        compose.onNodeWithTag("start-recording").performClick()
        compose.waitForIdle()
        compose.onNodeWithText("This house would introduce a carbon tax.").assertIsDisplayed()
        vm.stopRecording()
    }

    @Test
    fun offline_is_explained() {
        val vm = viewModel(videoEnabled = false)
        compose.setContent { DebateCoachTheme { RecorderContent(vm, online = false, onClose = {}, onUploaded = {}) } }
        compose.onNodeWithTag("offline-banner").assertIsDisplayed()
    }
}
