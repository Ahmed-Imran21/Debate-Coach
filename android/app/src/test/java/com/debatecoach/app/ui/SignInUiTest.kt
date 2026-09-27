package com.debatecoach.app.ui

import androidx.compose.ui.test.DeviceConfigurationOverride
import androidx.compose.ui.test.FontScale
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.debatecoach.app.core.net.ApiException
import com.debatecoach.app.feature.auth.SignInScreen
import com.debatecoach.app.navigation.reasonMessage
import com.debatecoach.app.testing.FakeBackend
import com.debatecoach.app.ui.theme.DebateCoachTheme
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SignInUiTest {
    @get:Rule val compose = createComposeRule()

    @Test
    fun signs_in_and_moves_on() {
        val backend = FakeBackend()
        var signedIn = false
        compose.setContent { DebateCoachTheme { SignInScreen(backend, null, onSignedIn = { signedIn = true }, onCreateAccount = {}) } }

        compose.onAllNodesWithText("Sign in").onFirst().assertIsDisplayed()
        compose.onNodeWithContentDescription("Email").performTextInput("ada@example.com")
        compose.onNodeWithContentDescription("Password").performTextInput("correct horse")
        compose.onNodeWithTag("auth-submit").performClick()
        compose.waitForIdle()

        assertEquals(listOf("signIn:ada@example.com"), backend.calls)
        assertTrue(signedIn)
    }

    @Test
    fun shows_the_servers_message_on_failure() {
        val backend = FakeBackend().apply { signInHandler = { _, _ -> throw ApiException(401, "Incorrect email or password.") } }
        compose.setContent { DebateCoachTheme { SignInScreen(backend, null, onSignedIn = {}, onCreateAccount = {}) } }
        compose.onNodeWithContentDescription("Email").performTextInput("ada@example.com")
        compose.onNodeWithContentDescription("Password").performTextInput("nope")
        compose.onNodeWithTag("auth-submit").performClick()
        compose.waitForIdle()
        compose.onNodeWithText("Incorrect email or password.").assertIsDisplayed()
    }

    @Test
    fun an_expired_session_says_so() {
        compose.setContent { DebateCoachTheme { SignInScreen(FakeBackend(), reasonMessage("expired"), onSignedIn = {}, onCreateAccount = {}) } }
        compose.onNodeWithText("Your session expired. Please log in again.").assertIsDisplayed()
    }

    @Test
    fun works_at_twice_the_font_size_with_48dp_targets() {
        compose.setContent {
            DeviceConfigurationOverride(DeviceConfigurationOverride.FontScale(2f)) {
                DebateCoachTheme { SignInScreen(FakeBackend(), null, onSignedIn = {}, onCreateAccount = {}) }
            }
        }
        compose.onNodeWithTag("auth-submit").performScrollTo().assertIsDisplayed().assertHeightIsAtLeast(48.dp)
        compose.onNodeWithText("Create one").performScrollTo().assertIsDisplayed().assertHeightIsAtLeast(48.dp)
    }
}
