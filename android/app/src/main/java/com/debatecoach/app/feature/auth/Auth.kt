package com.debatecoach.app.feature.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.debatecoach.app.core.Backend
import com.debatecoach.app.core.net.userMessage
import com.debatecoach.app.ui.components.Alert
import com.debatecoach.app.ui.components.Field
import com.debatecoach.app.ui.components.Lede
import com.debatecoach.app.ui.components.LinkButton
import com.debatecoach.app.ui.components.Note
import com.debatecoach.app.ui.components.PageTitle
import com.debatecoach.app.ui.components.Panel
import com.debatecoach.app.ui.components.PrimaryButton
import com.debatecoach.app.ui.components.Wordmark
import com.debatecoach.app.ui.components.appViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class AuthState(
    val email: String = "",
    val password: String = "",
    val firstName: String = "",
    val lastName: String = "",
    val error: String? = null,
    val busy: Boolean = false,
    val done: Boolean = false,
)

/** components/AuthForm.tsx: same checks, same messages. */
class AuthViewModel(private val backend: Backend, private val signup: Boolean) : ViewModel() {
    private val _state = MutableStateFlow(AuthState())
    val state: StateFlow<AuthState> = _state.asStateFlow()

    fun update(transform: AuthState.() -> AuthState) = _state.update { it.transform() }

    fun submit() {
        val s = _state.value
        if (s.busy) return
        _state.update { it.copy(error = null) }
        if (signup && s.password.length < 8) {
            _state.update { it.copy(error = "Use a password of at least 8 characters.") }
            return
        }
        _state.update { it.copy(busy = true) }
        viewModelScope.launch {
            try {
                if (signup) backend.signUp(s.email.trim(), s.password, s.firstName.trim(), s.lastName.trim())
                else backend.signIn(s.email.trim(), s.password)
                _state.update { it.copy(busy = false, done = true) }
            } catch (error: Exception) {
                _state.update { it.copy(busy = false, error = error.userMessage()) }
            }
        }
    }
}

@Composable
private fun AuthLayout(content: @Composable () -> Unit) {
    Column(
        Modifier
            .fillMaxSize()
            .safeDrawingPadding()
            .imePadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Column(Modifier.widthIn(max = 460.dp).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Wordmark()
            Spacer(Modifier.height(8.dp))
            content()
        }
    }
}

@Composable
fun SignInScreen(backend: Backend, message: String?, onSignedIn: () -> Unit, onCreateAccount: () -> Unit) {
    val vm = appViewModel(key = "signin") { AuthViewModel(backend, signup = false) }
    val state by vm.state.collectAsStateWithLifecycle()
    if (state.done) {
        androidx.compose.runtime.LaunchedEffect(Unit) { onSignedIn() }
    }
    AuthLayout {
        PageTitle("Sign in")
        if (message != null) Alert(message, quiet = true)
        Panel {
            state.error?.let { Alert(it, Modifier.testTag("auth-error")) }
            Field("Email", state.email, { v -> vm.update { copy(email = v) } }, keyboardType = KeyboardType.Email, enabled = !state.busy)
            Field("Password", state.password, { v -> vm.update { copy(password = v) } }, password = true, enabled = !state.busy)
            PrimaryButton(
                if (state.busy) "Signing in" else "Sign in",
                onClick = vm::submit,
                enabled = !state.busy,
                modifier = Modifier.fillMaxWidth().testTag("auth-submit"),
            )
            Row(verticalAlignment = Alignment.CenterVertically) {
                Note("No account yet?")
                LinkButton("Create one", onCreateAccount)
            }
        }
    }
}

@Composable
fun SignUpScreen(backend: Backend, onSignedUp: () -> Unit, onSignIn: () -> Unit, onOpenLink: (String) -> Unit) {
    val vm = appViewModel(key = "signup") { AuthViewModel(backend, signup = true) }
    val state by vm.state.collectAsStateWithLifecycle()
    if (state.done) {
        androidx.compose.runtime.LaunchedEffect(Unit) { onSignedUp() }
    }
    AuthLayout {
        PageTitle("Create an account")
        Lede("You need one to record a session, because your recordings and feedback are stored against it.")
        Panel {
            state.error?.let { Alert(it, Modifier.testTag("auth-error")) }
            Field("First name", state.firstName, { v -> vm.update { copy(firstName = v) } }, enabled = !state.busy)
            Field("Last name", state.lastName, { v -> vm.update { copy(lastName = v) } }, enabled = !state.busy)
            Field("Email", state.email, { v -> vm.update { copy(email = v) } }, keyboardType = KeyboardType.Email, enabled = !state.busy)
            Field("Password", state.password, { v -> vm.update { copy(password = v) } }, password = true, enabled = !state.busy)
            PrimaryButton(
                if (state.busy) "Creating account" else "Create account",
                onClick = vm::submit,
                enabled = !state.busy,
                modifier = Modifier.fillMaxWidth().testTag("auth-submit"),
            )
            Row(verticalAlignment = Alignment.CenterVertically) {
                Note("Already have an account?")
                LinkButton("Sign in", onSignIn)
            }
            Note("By creating one you agree to the terms and privacy policy.")
            Row {
                LinkButton("Terms", { onOpenLink("/terms") })
                LinkButton("Privacy policy", { onOpenLink("/privacy") })
            }
        }
    }
}
