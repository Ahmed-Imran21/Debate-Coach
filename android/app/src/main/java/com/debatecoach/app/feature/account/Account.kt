package com.debatecoach.app.feature.account

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.debatecoach.app.AppContainer
import com.debatecoach.app.BuildConfig
import com.debatecoach.app.core.Backend
import com.debatecoach.app.core.model.User
import com.debatecoach.app.core.net.ApiException
import com.debatecoach.app.core.util.ConsentChoice
import com.debatecoach.app.core.util.ConsentStore
import com.debatecoach.app.ui.components.Alert
import com.debatecoach.app.ui.components.ButtonRow
import com.debatecoach.app.ui.components.Divider
import com.debatecoach.app.ui.components.Field
import com.debatecoach.app.ui.components.FilterChip
import com.debatecoach.app.ui.components.Icons
import com.debatecoach.app.ui.components.LinkButton
import com.debatecoach.app.ui.components.Note
import com.debatecoach.app.ui.components.PrimaryButton
import com.debatecoach.app.ui.components.QuietButton
import com.debatecoach.app.ui.components.SectionTitle
import com.debatecoach.app.ui.components.ChipRow
import com.debatecoach.app.ui.components.Tone
import com.debatecoach.app.ui.components.appViewModel
import com.debatecoach.app.ui.theme.Dc
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

const val CONFIRM_WORD = "DELETE"

data class AccountState(
    val user: User? = null,
    val deleteOpen: Boolean = false,
    val confirmText: String = "",
    val password: String = "",
    val deleteError: String? = null,
    val deleting: Boolean = false,
) {
    val canDelete: Boolean get() = confirmText == CONFIRM_WORD && password.isNotEmpty() && !deleting
}

/** Sign out and DeleteAccountModal.tsx. Typing DELETE is the UI's confirmation; the password is the real check. */
class AccountViewModel(private val backend: Backend) : ViewModel() {
    private val _state = MutableStateFlow(AccountState())
    val state: StateFlow<AccountState> = _state.asStateFlow()

    fun load() {
        viewModelScope.launch {
            runCatching { backend.me() }.onSuccess { user -> _state.update { it.copy(user = user) } }
        }
    }

    fun signOut() = backend.signOut()

    fun openDelete() = _state.update { it.copy(deleteOpen = true, confirmText = "", password = "", deleteError = null) }

    fun closeDelete() {
        if (_state.value.deleting) return
        _state.update { it.copy(deleteOpen = false, confirmText = "", password = "", deleteError = null) }
    }

    fun setConfirm(text: String) = _state.update { it.copy(confirmText = text) }
    fun setPassword(text: String) = _state.update { it.copy(password = text) }

    fun delete() {
        val s = _state.value
        if (!s.canDelete) return
        _state.update { it.copy(deleting = true, deleteError = null) }
        viewModelScope.launch {
            try {
                // On success the backend object ends the session and the
                // app returns to sign-in: "Your account has been deleted."
                backend.deleteAccount(s.password)
            } catch (error: Exception) {
                val message = when {
                    error is ApiException && error.status == 401 && error.message == "Incorrect password." -> "Incorrect password."
                    error is ApiException && error.status == 401 -> null // session ended; on the way to sign-in
                    else -> "Could not delete your account. Try again."
                }
                _state.update { it.copy(deleting = false, deleteError = message) }
            }
        }
    }
}

@Composable
fun AccountScreen(container: AppContainer, onBack: () -> Unit, onOpenLink: (String) -> Unit) {
    val vm = appViewModel { AccountViewModel(container.backend) }
    AccountContent(vm, container.consent, onBack, onOpenLink)
}

@Composable
fun AccountContent(vm: AccountViewModel, consent: ConsentStore, onBack: () -> Unit, onOpenLink: (String) -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    val choice by consent.choice.collectAsStateWithLifecycle()
    val c = Dc.colors
    LaunchedEffect(Unit) { vm.load() }

    Scaffold(
        containerColor = c.paper,
        topBar = {
            TopAppBar(
                title = { Text("Account", style = MaterialTheme.typography.titleLarge) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.Back, contentDescription = "Back") } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = c.paper),
            )
        },
    ) { padding ->
        Column(
            Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Column(Modifier.widthIn(max = 560.dp).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                state.user?.let { user ->
                    Column {
                        Text("${user.firstName} ${user.lastName}", style = MaterialTheme.typography.headlineSmall, color = c.ink)
                        Note(user.email)
                    }
                }
                ButtonRow { QuietButton("Sign out", vm::signOut, modifier = Modifier.testTag("sign-out")) }

                if (BuildConfig.VIDEO_ANALYSIS_ENABLED) {
                    Divider()
                    SectionTitle("Visual feedback")
                    Note(
                        when (choice) {
                            ConsentChoice.IN -> "Visual feedback is on: the camera's movement numbers are analysed with your audio. No video leaves this phone."
                            ConsentChoice.OUT -> "Visual feedback is off: sessions record audio only."
                            null -> "You'll be asked the first time you record."
                        },
                    )
                    ChipRow(label = "Visual feedback") {
                        FilterChip("On", choice == ConsentChoice.IN, { consent.set(ConsentChoice.IN) })
                        FilterChip("Off", choice == ConsentChoice.OUT, { consent.set(ConsentChoice.OUT) })
                    }
                }

                Divider()
                SectionTitle("About")
                Note("Your account, sessions and reports are the same on the website and in the app.")
                ButtonRow {
                    LinkButton("Privacy policy", { onOpenLink("/privacy") })
                    LinkButton("Terms", { onOpenLink("/terms") })
                }
                Note("Version ${BuildConfig.VERSION_NAME}")

                Divider()
                SectionTitle("Delete account")
                Note("This permanently deletes your account, every recorded session and every report. This cannot be undone.")
                QuietButton("Delete account", vm::openDelete, tone = Tone.DANGER, modifier = Modifier.testTag("open-delete"))
            }
        }
    }

    if (state.deleteOpen) {
        AlertDialog(
            onDismissRequest = vm::closeDelete,
            title = { Text("Delete your account") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Note("This permanently deletes your account, every recorded session and every report. This cannot be undone.")
                    state.deleteError?.let { Alert(it, Modifier.testTag("delete-error")) }
                    Field("Type DELETE to confirm", state.confirmText, vm::setConfirm, enabled = !state.deleting)
                    Field("Current password", state.password, vm::setPassword, password = true, enabled = !state.deleting)
                }
            },
            confirmButton = {
                PrimaryButton(
                    if (state.deleting) "Deleting." else "Delete account permanently",
                    vm::delete,
                    enabled = state.canDelete,
                    tone = Tone.DANGER,
                    modifier = Modifier.testTag("confirm-delete-account"),
                )
            },
            dismissButton = { QuietButton("Cancel", vm::closeDelete, enabled = !state.deleting) },
            containerColor = c.paperRaised,
        )
    }
}
