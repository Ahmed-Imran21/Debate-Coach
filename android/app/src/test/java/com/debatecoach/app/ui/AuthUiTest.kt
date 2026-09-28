package com.debatecoach.app.ui

import androidx.compose.ui.test.DeviceConfigurationOverride
import androidx.compose.ui.test.FontScale
import androidx.compose.ui.test.assertHeightIsAtLeast
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.assertIsOff
import androidx.compose.ui.test.assertIsOn
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.click
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.text.TextLayoutResult
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.debatecoach.app.core.net.ApiException
import com.debatecoach.app.feature.auth.CONSENT_REQUIRED_MESSAGE
import com.debatecoach.app.feature.auth.SignInScreen
import com.debatecoach.app.feature.auth.SignUpScreen
import com.debatecoach.app.navigation.reasonMessage
import com.debatecoach.app.testing.FakeBackend
import com.debatecoach.app.ui.theme.DebateCoachTheme
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class AuthUiTest {
    @get:Rule val compose = createComposeRule()

    // ---------------------------------------------------------------
    // Sign in
    // ---------------------------------------------------------------

    @Test
    fun signs_in_and_moves_on() {
        val backend = FakeBackend()
        var signedIn = false
        compose.setContent { DebateCoachTheme { SignInScreen(backend, null, onSignedIn = { signedIn = true }, onCreateAccount = {}) } }

        compose.onAllNodesWithText("Sign in").onFirst().assertIsDisplayed()
        compose.onNodeWithTag("email-field").performTextInput("ada@example.com")
        compose.onNodeWithTag("password-field").performTextInput("correct horse")
        compose.onNodeWithTag("auth-submit").performClick()
        compose.waitForIdle()

        assertEquals(listOf("signIn:ada@example.com"), backend.calls)
        assertTrue(signedIn)
    }

    @Test
    fun shows_the_servers_message_on_failure() {
        val backend = FakeBackend().apply { signInHandler = { _, _ -> throw ApiException(401, "Incorrect email or password.") } }
        compose.setContent { DebateCoachTheme { SignInScreen(backend, null, onSignedIn = {}, onCreateAccount = {}) } }
        compose.onNodeWithTag("email-field").performTextInput("ada@example.com")
        compose.onNodeWithTag("password-field").performTextInput("nope")
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
    fun sign_in_works_at_twice_the_font_size_with_48dp_targets() {
        compose.setContent {
            DeviceConfigurationOverride(DeviceConfigurationOverride.FontScale(2f)) {
                DebateCoachTheme { SignInScreen(FakeBackend(), null, onSignedIn = {}, onCreateAccount = {}) }
            }
        }
        compose.onNodeWithTag("auth-submit").performScrollTo().assertIsDisplayed().assertHeightIsAtLeast(48.dp)
        compose.onNodeWithText("Create one").performScrollTo().assertIsDisplayed().assertHeightIsAtLeast(48.dp)
    }

    // ---------------------------------------------------------------
    // Create an account: the Privacy Policy and Terms boxes
    // ---------------------------------------------------------------

    private fun signUp(backend: FakeBackend = FakeBackend(), opened: MutableList<String> = mutableListOf(), onDone: () -> Unit = {}) {
        compose.setContent { DebateCoachTheme { SignUpScreen(backend, onSignedUp = onDone, onSignIn = {}, onOpenLink = { opened += it }) } }
    }

    private fun fillForm() {
        compose.onNodeWithTag("first-name-field").performTextInput("Ada")
        compose.onNodeWithTag("last-name-field").performTextInput("Lovelace")
        compose.onNodeWithTag("email-field").performTextInput("ada@example.com")
        compose.onNodeWithTag("password-field").performTextInput("correct horse")
    }

    @Test
    fun both_boxes_start_unticked_with_the_websites_wording() {
        signUp()
        compose.onNodeWithTag("consent-privacy").performScrollTo().assertIsOff()
        compose.onNodeWithTag("consent-terms").performScrollTo().assertIsOff()
        compose.onNodeWithText("By clicking this, you agree to our Privacy Policy").assertIsDisplayed()
        compose.onNodeWithText("By clicking this, you agree to our Terms and Conditions").assertIsDisplayed()
    }

    @Test
    fun create_account_stays_disabled_until_both_boxes_are_ticked() {
        signUp()
        fillForm()
        val button = compose.onNodeWithTag("auth-submit")
        button.performScrollTo().assertIsNotEnabled()
        compose.onNodeWithTag("consent-privacy").performScrollTo().performClick().assertIsOn()
        button.assertIsNotEnabled()
        compose.onNodeWithTag("consent-terms").performScrollTo().performClick().assertIsOn()
        button.assertIsEnabled()
        compose.onNodeWithTag("consent-privacy").performClick().assertIsOff()
        button.assertIsNotEnabled()
    }

    @Test
    fun tapping_create_account_anyway_explains_why_and_sends_nothing() {
        val backend = FakeBackend()
        signUp(backend)
        fillForm()
        compose.onNodeWithTag("consent-terms").performScrollTo().performClick()
        compose.onNodeWithTag("auth-submit-blocked").performScrollTo().performClick()
        compose.waitForIdle()
        compose.onNodeWithTag("consent-error").assertIsDisplayed()
        compose.onNodeWithText(CONSENT_REQUIRED_MESSAGE).assertIsDisplayed()
        assertTrue(backend.calls.isEmpty())

        compose.onNodeWithTag("consent-privacy").performScrollTo().performClick()
        compose.waitForIdle()
        compose.onNodeWithText(CONSENT_REQUIRED_MESSAGE).assertDoesNotExist()
    }

    /** Taps the middle of [link] inside [line], where a finger would, using the text's own layout. */
    private fun clickLink(line: String, link: String) {
        compose.onNodeWithText(line).performScrollTo()
        val text = compose.onNode(hasText(line), useUnmergedTree = true)
        val layouts = mutableListOf<TextLayoutResult>()
        text.fetchSemanticsNode().config[SemanticsActions.GetTextLayoutResult].action!!.invoke(layouts)
        val box = layouts.first().getBoundingBox(line.indexOf(link) + link.length / 2)
        text.performTouchInput { click(box.center) }
        compose.waitForIdle()
    }

    @Test
    fun each_link_opens_its_page_and_does_not_tick_its_box() {
        val opened = mutableListOf<String>()
        signUp(opened = opened)
        clickLink("By clicking this, you agree to our Privacy Policy", "Privacy Policy")
        assertEquals(listOf("/privacy"), opened)
        compose.onNodeWithTag("consent-privacy").assertIsOff()

        clickLink("By clicking this, you agree to our Terms and Conditions", "Terms and Conditions")
        assertEquals(listOf("/privacy", "/terms"), opened)
        compose.onNodeWithTag("consent-terms").assertIsOff()
    }

    @Test
    fun creates_the_account_with_both_acceptances() {
        val backend = FakeBackend()
        var done = false
        signUp(backend, onDone = { done = true })
        fillForm()
        compose.onNodeWithTag("consent-privacy").performScrollTo().performClick()
        compose.onNodeWithTag("consent-terms").performScrollTo().performClick()
        compose.onNodeWithTag("auth-submit").performScrollTo().performClick()
        compose.waitForIdle()
        assertEquals(listOf("signUp"), backend.calls)
        assertEquals(true to true, backend.lastSignUpConsent)
        assertTrue(done)
    }

    @Test
    fun sign_up_works_at_twice_the_font_size_with_48dp_targets() {
        compose.setContent {
            DeviceConfigurationOverride(DeviceConfigurationOverride.FontScale(2f)) {
                DebateCoachTheme { SignUpScreen(FakeBackend(), onSignedUp = {}, onSignIn = {}, onOpenLink = {}) }
            }
        }
        for (tag in listOf("consent-privacy", "consent-terms", "auth-submit")) {
            compose.onNodeWithTag(tag).performScrollTo().assertIsDisplayed().assertHeightIsAtLeast(48.dp)
        }
    }
}
