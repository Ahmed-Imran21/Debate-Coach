package com.debatecoach.app.feature.account

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
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
import com.debatecoach.app.ui.components.Icons
import com.debatecoach.app.ui.components.InlineMessage
import com.debatecoach.app.ui.components.SkeletonLine
import com.debatecoach.app.ui.components.TextInput
import com.debatecoach.app.ui.components.Tone
import com.debatecoach.app.ui.components.TopLevelBar
import com.debatecoach.app.ui.components.appViewModel
import com.debatecoach.app.ui.theme.Space
import com.debatecoach.app.ui.theme.numberStyle
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


// ---------------------------------------------------------------
// UI: a native settings screen
// ---------------------------------------------------------------

@Composable
fun AccountScreen(container: AppContainer, onOpenLink: (String) -> Unit, onDeleteAccount: () -> Unit) {
    val vm = appViewModel { AccountViewModel(container.backend) }
    AccountContent(vm, container.consent, onOpenLink, onDeleteAccount)
}

@Composable
fun AccountContent(vm: AccountViewModel, consent: ConsentStore, onOpenLink: (String) -> Unit, onDeleteAccount: () -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    val choice by consent.choice.collectAsStateWithLifecycle()
    val haptics = LocalHapticFeedback.current
    val scroll = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    var confirmSignOut by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(Unit) { vm.load() }

    Scaffold(
        modifier = Modifier.nestedScroll(scroll.nestedScrollConnection),
        containerColor = MaterialTheme.colorScheme.surface,
        topBar = { TopLevelBar("Account", scroll) },
    ) { padding ->
        val gutter = Space.gutter
        Box(Modifier.fillMaxSize().padding(top = padding.calculateTopPadding()), contentAlignment = Alignment.TopCenter) {
            Column(
                Modifier
                    .widthIn(max = Space.readingWidth)
                    .fillMaxSize()
                    .verticalScroll(rememberScrollState())
                    .padding(start = gutter, end = gutter, bottom = padding.calculateBottomPadding() + Space.xxl)
                    .testTag("account"),
            ) {
                ProfileHeader(state.user)

                if (BuildConfig.VIDEO_ANALYSIS_ENABLED) {
                    SectionLabel("Recording")
                    SettingsGroup {
                        val on = choice == ConsentChoice.IN
                        ListItem(
                            headlineContent = { Text("Visual feedback") },
                            supportingContent = {
                                Text(
                                    when (choice) {
                                        ConsentChoice.IN -> "On: the camera's movement numbers are analysed with your audio. No video leaves this phone."
                                        ConsentChoice.OUT -> "Off: sessions record audio only."
                                        null -> "You'll be asked the first time you record."
                                    },
                                )
                            },
                            leadingContent = { Icon(Icons.Camera, contentDescription = null) },
                            trailingContent = { Switch(checked = on, onCheckedChange = null) },
                            colors = rowColors(),
                            modifier = Modifier
                                .toggleable(value = on, role = Role.Switch) { checked ->
                                    haptics.performHapticFeedback(if (checked) HapticFeedbackType.ToggleOn else HapticFeedbackType.ToggleOff)
                                    consent.set(if (checked) ConsentChoice.IN else ConsentChoice.OUT)
                                }
                                .testTag("visual-feedback-setting"),
                        )
                    }
                }

                SectionLabel("Legal")
                SettingsGroup {
                    LinkRow("Privacy Policy", Icons.Lock, "privacy") { onOpenLink("/privacy") }
                    HorizontalDivider(Modifier.padding(start = 56.dp), color = MaterialTheme.colorScheme.outlineVariant)
                    LinkRow("Terms and Conditions", Icons.Document, "terms") { onOpenLink("/terms") }
                }

                SectionLabel("About")
                SettingsGroup {
                    ListItem(
                        headlineContent = { Text("Debate Coach ${BuildConfig.VERSION_NAME}") },
                        supportingContent = { Text("Your account, sessions and reports are the same on the website and in the app.") },
                        leadingContent = { Icon(Icons.Info, contentDescription = null) },
                        colors = rowColors(),
                    )
                }

                Spacer(Modifier.height(Space.l))
                SettingsGroup {
                    ListItem(
                        headlineContent = { Text("Sign out") },
                        leadingContent = { Icon(Icons.Logout, contentDescription = null) },
                        colors = rowColors(),
                        modifier = Modifier.clickable { confirmSignOut = true }.testTag("sign-out"),
                    )
                }

                SectionLabel("Danger zone", color = MaterialTheme.colorScheme.error)
                Surface(
                    shape = MaterialTheme.shapes.medium,
                    color = MaterialTheme.colorScheme.surfaceContainerLowest,
                    border = BorderStroke(1.dp, MaterialTheme.colorScheme.error.copy(alpha = 0.5f)),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    ListItem(
                        headlineContent = { Text("Delete account", color = MaterialTheme.colorScheme.error) },
                        supportingContent = { Text("Permanently deletes your account, every recorded session and every report.") },
                        leadingContent = { Icon(Icons.DeleteOutlined, contentDescription = null, tint = MaterialTheme.colorScheme.error) },
                        trailingContent = { Icon(Icons.ChevronRight, contentDescription = null) },
                        colors = rowColors(),
                        modifier = Modifier.clickable(onClick = onDeleteAccount).testTag("open-delete"),
                    )
                }
            }
        }
    }

    if (confirmSignOut) {
        AlertDialog(
            onDismissRequest = { confirmSignOut = false },
            title = { Text("Sign out?") },
            text = { Text("You can sign back in with the same email and password, here or on the website.") },
            confirmButton = {
                TextButton(onClick = {
                    confirmSignOut = false
                    vm.signOut()
                }, modifier = Modifier.testTag("confirm-sign-out")) { Text("Sign out") }
            },
            dismissButton = { TextButton(onClick = { confirmSignOut = false }) { Text("Cancel") } },
        )
    }
}

@Composable
private fun rowColors() = ListItemDefaults.colors(containerColor = Color.Transparent)

@Composable
private fun SettingsGroup(content: @Composable () -> Unit) {
    Surface(
        shape = MaterialTheme.shapes.medium,
        color = MaterialTheme.colorScheme.surfaceContainerLowest,
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
        modifier = Modifier.fillMaxWidth(),
    ) { Column { content() } }
}

@Composable
private fun SectionLabel(text: String, color: Color = MaterialTheme.colorScheme.primary) {
    Text(
        text,
        style = MaterialTheme.typography.labelLarge,
        color = color,
        modifier = Modifier.padding(start = Space.l, top = Space.xl, bottom = Space.s).semantics { heading() },
    )
}

@Composable
private fun LinkRow(label: String, icon: ImageVector, tag: String, onClick: () -> Unit) {
    ListItem(
        headlineContent = { Text(label) },
        leadingContent = { Icon(icon, contentDescription = null) },
        trailingContent = { Icon(Icons.OpenInNew, contentDescription = "Opens in the browser", modifier = Modifier.size(20.dp)) },
        colors = rowColors(),
        modifier = Modifier.clickable(onClick = onClick).testTag("link-$tag"),
    )
}

@Composable
private fun ProfileHeader(user: User?) {
    Row(Modifier.fillMaxWidth().padding(top = Space.s, bottom = Space.s), verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier.size(64.dp).clip(CircleShape).background(MaterialTheme.colorScheme.primaryContainer),
            contentAlignment = Alignment.Center,
        ) {
            if (user != null) {
                Text(initials(user), style = numberStyle(24.sp), color = MaterialTheme.colorScheme.onPrimaryContainer)
            }
        }
        Spacer(Modifier.width(Space.l))
        Column(Modifier.weight(1f)) {
            if (user == null) {
                SkeletonLine(0.6f, height = 20.dp)
                Spacer(Modifier.height(Space.s))
                SkeletonLine(0.8f)
            } else {
                Text("${user.firstName} ${user.lastName}", style = MaterialTheme.typography.headlineSmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text(user.email, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

fun initials(user: User): String =
    listOf(user.firstName, user.lastName).mapNotNull { it.trim().firstOrNull()?.uppercaseChar() }.joinToString("").ifEmpty { "?" }

// ---------------------------------------------------------------
// Delete account: its own screen (DeleteAccountModal.tsx)
// ---------------------------------------------------------------

@Composable
fun DeleteAccountScreen(container: AppContainer, onClose: () -> Unit) {
    val vm = appViewModel(key = "delete-account") { AccountViewModel(container.backend) }
    DeleteAccountContent(vm, onClose)
}

@Composable
fun DeleteAccountContent(vm: AccountViewModel, onClose: () -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    val haptics = LocalHapticFeedback.current
    val focus = LocalFocusManager.current
    Scaffold(
        containerColor = MaterialTheme.colorScheme.surface,
        topBar = {
            TopAppBar(
                title = { Text("Delete account") },
                navigationIcon = { IconButton(onClick = onClose, enabled = !state.deleting) { Icon(Icons.Close, contentDescription = "Cancel") } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
            )
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding).imePadding(), contentAlignment = Alignment.TopCenter) {
            Column(
                Modifier.widthIn(max = 520.dp).fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = Space.xl, vertical = Space.l).testTag("delete-account"),
                verticalArrangement = Arrangement.spacedBy(Space.l),
            ) {
                Box(
                    Modifier.size(56.dp).clip(CircleShape).background(MaterialTheme.colorScheme.errorContainer),
                    contentAlignment = Alignment.Center,
                ) { Icon(Icons.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.onErrorContainer) }
                Text("Delete your account", style = MaterialTheme.typography.headlineMedium, modifier = Modifier.semantics { heading() })
                Text(
                    "This permanently deletes your account, every recorded session and every report, on the website and in this app. This cannot be undone.",
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                state.deleteError?.let { InlineMessage(it, tone = Tone.CRITICAL, modifier = Modifier.testTag("delete-error")) }
                TextInput(
                    "Type DELETE to confirm",
                    state.confirmText,
                    vm::setConfirm,
                    enabled = !state.deleting,
                    supporting = "In capitals, as shown",
                    tag = "confirm-field",
                )
                TextInput(
                    "Current password",
                    state.password,
                    vm::setPassword,
                    password = true,
                    imeAction = ImeAction.Done,
                    onIme = { focus.clearFocus() },
                    enabled = !state.deleting,
                    tag = "delete-password",
                )
                Button(
                    onClick = {
                        haptics.performHapticFeedback(HapticFeedbackType.Reject)
                        vm.delete()
                    },
                    enabled = state.canDelete,
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error, contentColor = MaterialTheme.colorScheme.onError),
                    modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp).testTag("confirm-delete-account"),
                ) {
                    if (state.deleting) {
                        CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onError)
                        Spacer(Modifier.width(Space.s))
                        Text("Deleting.")
                    } else {
                        Text("Delete account permanently")
                    }
                }
                OutlinedButton(onClick = onClose, enabled = !state.deleting, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) { Text("Cancel") }
            }
        }
    }
}
