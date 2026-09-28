package com.debatecoach.app.feature.auth

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.testTag
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withLink
import androidx.compose.ui.unit.dp
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.createSavedStateHandle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.debatecoach.app.core.Backend
import com.debatecoach.app.core.net.userMessage
import com.debatecoach.app.ui.components.Icons
import com.debatecoach.app.ui.components.InlineMessage
import com.debatecoach.app.ui.components.TextInput
import com.debatecoach.app.ui.components.Tone
import com.debatecoach.app.ui.components.Wordmark
import com.debatecoach.app.ui.theme.Space
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The sign-up checkboxes' wording, as on the website (lib/signup-consent.ts). */
const val CONSENT_LINE_PREFIX = "By clicking this, you agree to our "
const val PRIVACY_POLICY_LABEL = "Privacy Policy"
const val TERMS_LABEL = "Terms and Conditions"
const val PRIVACY_PATH = "/privacy"
const val TERMS_PATH = "/terms"

/** The backend's own refusal, word for word, so the form and the server say the same thing. */
const val CONSENT_REQUIRED_MESSAGE = "To create an account, agree to the Privacy Policy and the Terms and Conditions."

data class AuthState(
    val email: String = "",
    val password: String = "",
    val firstName: String = "",
    val lastName: String = "",
    val acceptedPrivacyPolicy: Boolean = false,
    val acceptedTerms: Boolean = false,
    val error: String? = null,
    val consentError: Boolean = false,
    val busy: Boolean = false,
    val done: Boolean = false,
) {
    val consentGiven: Boolean get() = acceptedPrivacyPolicy && acceptedTerms
}

/**
 * components/AuthForm.tsx: same checks, same messages. The form's fields
 * (never the password) survive the process being killed while a
 * Custom Tab with the privacy policy is open.
 */
class AuthViewModel(
    private val backend: Backend,
    private val signup: Boolean,
    private val saved: SavedStateHandle = SavedStateHandle(),
) : ViewModel() {
    private val _state = MutableStateFlow(
        AuthState(
            email = saved["email"] ?: "",
            firstName = saved["firstName"] ?: "",
            lastName = saved["lastName"] ?: "",
            acceptedPrivacyPolicy = saved["privacy"] ?: false,
            acceptedTerms = saved["terms"] ?: false,
        ),
    )
    val state: StateFlow<AuthState> = _state.asStateFlow()

    fun update(transform: AuthState.() -> AuthState) {
        _state.update { it.transform() }
        val s = _state.value
        saved["email"] = s.email
        saved["firstName"] = s.firstName
        saved["lastName"] = s.lastName
        saved["privacy"] = s.acceptedPrivacyPolicy
        saved["terms"] = s.acceptedTerms
        if (s.consentGiven && s.consentError) _state.update { it.copy(consentError = false) }
    }

    /** A tap on Create account while it's disabled: say why. */
    fun explainConsent() = _state.update { it.copy(consentError = true) }

    fun submit() {
        val s = _state.value
        if (s.busy) return
        _state.update { it.copy(error = null) }
        if (signup && s.password.length < 8) {
            _state.update { it.copy(error = "Use a password of at least 8 characters.") }
            return
        }
        if (signup && !s.consentGiven) {
            _state.update { it.copy(consentError = true) }
            return
        }
        _state.update { it.copy(busy = true, consentError = false) }
        viewModelScope.launch {
            try {
                if (signup) {
                    backend.signUp(s.email.trim(), s.password, s.firstName.trim(), s.lastName.trim(), s.acceptedPrivacyPolicy, s.acceptedTerms)
                } else {
                    backend.signIn(s.email.trim(), s.password)
                }
                _state.update { it.copy(busy = false, done = true) }
            } catch (error: Exception) {
                _state.update { it.copy(busy = false, error = error.userMessage()) }
            }
        }
    }
}

@Composable
private fun authViewModel(backend: Backend, signup: Boolean): AuthViewModel =
    viewModel(key = if (signup) "signup" else "signin", factory = viewModelFactory { initializer { AuthViewModel(backend, signup, createSavedStateHandle()) } })

/** A centred, scrolling form column that stays clear of the keyboard and system bars. */
@Composable
private fun FormColumn(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Box(modifier.fillMaxSize().imePadding(), contentAlignment = Alignment.TopCenter) {
        Column(
            Modifier
                .widthIn(max = 480.dp)
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = Space.xl, vertical = Space.l),
            verticalArrangement = Arrangement.spacedBy(Space.l),
        ) { content() }
    }
}

@Composable
private fun SubmitButton(text: String, busyText: String, busy: Boolean, enabled: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Button(
        onClick = onClick,
        enabled = enabled && !busy,
        modifier = modifier.fillMaxWidth().heightIn(min = 52.dp).testTag("auth-submit"),
    ) {
        if (busy) {
            CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
            Spacer(Modifier.width(Space.s))
            Text(busyText)
        } else {
            Text(text)
        }
    }
}

@Composable
fun SignInScreen(backend: Backend, message: String?, onSignedIn: () -> Unit, onCreateAccount: () -> Unit) {
    val vm = authViewModel(backend, signup = false)
    val state by vm.state.collectAsStateWithLifecycle()
    val focus = LocalFocusManager.current
    if (state.done) LaunchedEffect(Unit) { onSignedIn() }

    Scaffold(containerColor = MaterialTheme.colorScheme.surface) { padding ->
        FormColumn(Modifier.padding(padding).safeDrawingPadding()) {
            Spacer(Modifier.height(Space.xl))
            Wordmark()
            Spacer(Modifier.height(Space.xl))
            Text("Sign in", style = MaterialTheme.typography.displaySmall, modifier = Modifier.semantics { heading() })
            Text(
                "Your sessions and reports are the same here and on the website.",
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (message != null) InlineMessage(message)
            state.error?.let { InlineMessage(it, tone = Tone.CRITICAL, modifier = Modifier.testTag("auth-error")) }
            TextInput(
                "Email",
                state.email,
                { v -> vm.update { copy(email = v) } },
                keyboardType = KeyboardType.Email,
                enabled = !state.busy,
                tag = "email-field",
            )
            TextInput(
                "Password",
                state.password,
                { v -> vm.update { copy(password = v) } },
                password = true,
                imeAction = ImeAction.Done,
                onIme = {
                    focus.clearFocus()
                    vm.submit()
                },
                enabled = !state.busy,
                tag = "password-field",
            )
            SubmitButton("Sign in", "Signing in", state.busy, enabled = true, onClick = vm::submit)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("No account yet?", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                TextButton(onClick = onCreateAccount, modifier = Modifier.heightIn(min = Space.touch)) { Text("Create one") }
            }
        }
    }
}

@Composable
fun SignUpScreen(backend: Backend, onSignedUp: () -> Unit, onSignIn: () -> Unit, onOpenLink: (String) -> Unit) {
    val vm = authViewModel(backend, signup = true)
    val state by vm.state.collectAsStateWithLifecycle()
    val haptics = LocalHapticFeedback.current
    val focus = LocalFocusManager.current
    if (state.done) LaunchedEffect(Unit) { onSignedUp() }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.surface,
        topBar = {
            TopAppBar(
                title = {},
                navigationIcon = { IconButton(onClick = onSignIn) { Icon(Icons.Back, contentDescription = "Back to sign in") } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
            )
        },
    ) { padding ->
        FormColumn(Modifier.padding(padding)) {
            Text("Create an account", style = MaterialTheme.typography.displaySmall, modifier = Modifier.semantics { heading() })
            Text(
                "You need one to record a session, because your recordings and feedback are stored against it.",
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            state.error?.let { InlineMessage(it, tone = Tone.CRITICAL, modifier = Modifier.testTag("auth-error")) }
            TextInput("First name", state.firstName, { v -> vm.update { copy(firstName = v) } }, enabled = !state.busy, tag = "first-name-field")
            TextInput("Last name", state.lastName, { v -> vm.update { copy(lastName = v) } }, enabled = !state.busy, tag = "last-name-field")
            TextInput("Email", state.email, { v -> vm.update { copy(email = v) } }, keyboardType = KeyboardType.Email, enabled = !state.busy, tag = "email-field")
            TextInput(
                "Password",
                state.password,
                { v -> vm.update { copy(password = v) } },
                password = true,
                imeAction = ImeAction.Done,
                onIme = { focus.clearFocus() },
                enabled = !state.busy,
                supporting = "At least 8 characters",
                tag = "password-field",
            )

            Column {
                ConsentRow(
                    checked = state.acceptedPrivacyPolicy,
                    onCheckedChange = { v -> vm.update { copy(acceptedPrivacyPolicy = v) } },
                    linkLabel = PRIVACY_POLICY_LABEL,
                    onOpenLink = { onOpenLink(PRIVACY_PATH) },
                    enabled = !state.busy,
                    tag = "consent-privacy",
                )
                ConsentRow(
                    checked = state.acceptedTerms,
                    onCheckedChange = { v -> vm.update { copy(acceptedTerms = v) } },
                    linkLabel = TERMS_LABEL,
                    onOpenLink = { onOpenLink(TERMS_PATH) },
                    enabled = !state.busy,
                    tag = "consent-terms",
                )
                AnimatedVisibility(state.consentError, enter = fadeIn(), exit = fadeOut()) {
                    Text(
                        CONSENT_REQUIRED_MESSAGE,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.error,
                        modifier = Modifier
                            .padding(start = Space.xs, top = Space.xs)
                            .semantics { liveRegion = LiveRegionMode.Assertive }
                            .testTag("consent-error"),
                    )
                }
            }

            // Disabled until both boxes are ticked. A tap on it anyway
            // lands on the transparent layer above and says why.
            Box {
                SubmitButton(
                    "Create account",
                    "Creating account",
                    state.busy,
                    enabled = state.consentGiven,
                    onClick = vm::submit,
                    modifier = Modifier.semantics {
                        if (!state.consentGiven) stateDescription = "Tick both boxes above to continue"
                    },
                )
                if (!state.consentGiven && !state.busy) {
                    Box(
                        Modifier
                            .matchParentSize()
                            .clearAndSetSemantics { testTag = "auth-submit-blocked" }
                            .clickable(interactionSource = null, indication = null) {
                                haptics.performHapticFeedback(HapticFeedbackType.Reject)
                                vm.explainConsent()
                            },
                    )
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Already have an account?", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                TextButton(onClick = onSignIn, modifier = Modifier.heightIn(min = Space.touch)) { Text("Sign in") }
            }
        }
    }
}

/**
 * One sign-up checkbox. The whole row toggles it (a 48dp target); the
 * link inside only opens its page. TalkBack reads the row as one
 * checkbox and offers "Open …" as an action.
 */
@Composable
fun ConsentRow(
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    linkLabel: String,
    onOpenLink: () -> Unit,
    enabled: Boolean = true,
    tag: String? = null,
) {
    val linkColor = MaterialTheme.colorScheme.primary
    val text = buildAnnotatedString {
        append(CONSENT_LINE_PREFIX)
        withLink(
            LinkAnnotation.Clickable(
                tag = linkLabel,
                styles = TextLinkStyles(SpanStyle(color = linkColor, fontWeight = FontWeight.Medium, textDecoration = TextDecoration.Underline)),
                linkInteractionListener = { onOpenLink() },
            ),
        ) { append(linkLabel) }
    }
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = Space.touch)
            .clip(MaterialTheme.shapes.small)
            .toggleable(value = checked, enabled = enabled, role = Role.Checkbox, onValueChange = onCheckedChange)
            .semantics { customActions = listOf(CustomAccessibilityAction("Open $linkLabel") { onOpenLink(); true }) }
            .padding(vertical = Space.xs)
            .let { if (tag != null) it.testTag(tag) else it },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Checkbox(checked = checked, onCheckedChange = null, enabled = enabled)
        Spacer(Modifier.width(Space.m))
        Text(text, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
