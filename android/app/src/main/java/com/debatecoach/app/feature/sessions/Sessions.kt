package com.debatecoach.app.feature.sessions

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.LifecycleStartEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.debatecoach.app.core.Backend
import com.debatecoach.app.core.model.SessionSummary
import com.debatecoach.app.core.model.TERMINAL
import com.debatecoach.app.core.model.statusLabel
import com.debatecoach.app.core.net.ApiException
import com.debatecoach.app.core.util.formatClock
import com.debatecoach.app.core.util.formatRecordedShort
import com.debatecoach.app.core.util.jsRound
import com.debatecoach.app.core.util.sessionName
import com.debatecoach.app.ui.components.Alert
import com.debatecoach.app.ui.components.Divider
import com.debatecoach.app.ui.components.Loading
import com.debatecoach.app.ui.components.Note
import com.debatecoach.app.ui.components.QuietButton
import com.debatecoach.app.ui.components.StateLabel
import com.debatecoach.app.ui.components.ThinProgress
import com.debatecoach.app.ui.components.Tone
import com.debatecoach.app.ui.theme.Dc
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

const val POLL_MS = 4_000L

data class SessionsState(
    val sessions: List<SessionSummary>? = null,
    val error: String? = null,
    val refreshing: Boolean = false,
    val confirmDelete: SessionSummary? = null,
    val deleting: String? = null,
    val deleteError: String? = null,
) {
    /** Changes when a session finishes, so the progress tab refetches. */
    val completedCount: Int get() = sessions?.count { it.status == "completed" } ?: 0
}

/** app/practice/page.tsx: the list, its polling, and delete. */
class SessionsViewModel(private val backend: Backend) : ViewModel() {
    private val _state = MutableStateFlow(SessionsState())
    val state: StateFlow<SessionsState> = _state.asStateFlow()
    private var polling: Job? = null

    /** Returns whether to keep polling: while anything is still moving, or after an error. */
    suspend fun load(): Boolean = try {
        val rows = backend.listSessions()
        _state.update { it.copy(sessions = rows, error = null) }
        rows.any { it.status !in TERMINAL }
    } catch (error: ApiException) {
        if (error.status == 401) {
            false // ApiClient already ended the session; the app is on its way to sign-in
        } else {
            _state.update { it.copy(error = "Could not load your sessions. Retrying.") }
            true
        }
    } catch (_: Exception) {
        _state.update { it.copy(error = "Could not load your sessions. Retrying.") }
        true
    }

    /** While the screen is visible (web: while the page is open). */
    fun startPolling() {
        polling?.cancel()
        polling = viewModelScope.launch {
            while (isActive) {
                val keepGoing = load()
                if (!keepGoing) break
                delay(POLL_MS)
            }
        }
    }

    fun stopPolling() {
        polling?.cancel()
        polling = null
    }

    fun refresh() {
        _state.update { it.copy(refreshing = true) }
        viewModelScope.launch {
            load()
            _state.update { it.copy(refreshing = false) }
            startPolling()
        }
    }

    fun askDelete(session: SessionSummary) = _state.update { it.copy(confirmDelete = session, deleteError = null) }

    fun cancelDelete() = _state.update { it.copy(confirmDelete = null) }

    fun confirmDelete() {
        val session = _state.value.confirmDelete ?: return
        _state.update { it.copy(confirmDelete = null, deleting = session.id, deleteError = null) }
        viewModelScope.launch {
            try {
                backend.deleteSession(session.id)
                _state.update { s -> s.copy(sessions = s.sessions?.filterNot { it.id == session.id }, deleting = null) }
            } catch (error: Exception) {
                _state.update {
                    it.copy(
                        deleting = null,
                        deleteError = if (error is ApiException && error.status == 404) "That session was already gone." else "Could not delete that session. Try again.",
                    )
                }
            }
        }
    }
}

@Composable
fun SessionsTab(vm: SessionsViewModel, onOpenSession: (String) -> Unit, contentPadding: PaddingValues) {
    val state by vm.state.collectAsStateWithLifecycle()

    // Poll only while this screen is visible (and resume on return),
    // so a session recorded on the website shows up here too.
    LifecycleStartEffect(vm) {
        vm.startPolling()
        onStopOrDispose { vm.stopPolling() }
    }

    state.confirmDelete?.let { session ->
        AlertDialog(
            onDismissRequest = vm::cancelDelete,
            title = { Text("Delete this session?") },
            text = { Text("“${sessionName(session.title, session.createdAt)}” will be deleted. This cannot be undone.") },
            confirmButton = { QuietButton("Delete", vm::confirmDelete, tone = Tone.DANGER, modifier = Modifier.testTag("confirm-delete")) },
            dismissButton = { QuietButton("Cancel", vm::cancelDelete) },
            containerColor = Dc.colors.paperRaised,
        )
    }

    PullToRefreshBox(isRefreshing = state.refreshing, onRefresh = vm::refresh, modifier = Modifier.fillMaxSize()) {
        LazyColumn(
            Modifier.fillMaxSize().testTag("session-list"),
            contentPadding = PaddingValues(
                start = 20.dp,
                end = 20.dp,
                top = contentPadding.calculateTopPadding() + 8.dp,
                bottom = contentPadding.calculateBottomPadding() + 96.dp,
            ),
        ) {
            item {
                Text("Your sessions", style = MaterialTheme.typography.headlineSmall, color = Dc.colors.ink, modifier = Modifier.padding(bottom = 12.dp))
            }
            state.error?.let { item { Alert(it, quiet = true, modifier = Modifier.padding(bottom = 12.dp)) } }
            state.deleteError?.let { item { Alert(it, modifier = Modifier.padding(bottom = 12.dp)) } }
            val sessions = state.sessions
            when {
                sessions == null && state.error == null -> item { Loading() }
                sessions != null && sessions.isEmpty() -> item {
                    Note("Nothing here yet. Record a speech and it will appear in this list while it is being analysed.")
                }
                sessions != null -> {
                    item { Divider() }
                    items(sessions, key = { it.id }) { session ->
                        SessionRow(
                            session = session,
                            deleting = state.deleting == session.id,
                            onOpen = { onOpenSession(session.id) },
                            onDelete = { vm.askDelete(session) },
                        )
                        Divider()
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun SessionRow(session: SessionSummary, deleting: Boolean, onOpen: () -> Unit, onDelete: () -> Unit) {
    val haptics = LocalHapticFeedback.current
    val dismiss = rememberSwipeToDismissBoxState()
    LaunchedEffect(dismiss.currentValue) {
        if (dismiss.currentValue == SwipeToDismissBoxValue.EndToStart) {
            onDelete()
            dismiss.reset()
        }
    }

    SwipeToDismissBox(
        state = dismiss,
        enableDismissFromStartToEnd = false,
        backgroundContent = {
            Box(Modifier.fillMaxSize().background(Dc.colors.brick).padding(horizontal = 20.dp), contentAlignment = Alignment.CenterEnd) {
                Text("Delete", color = Dc.colors.onPine, style = MaterialTheme.typography.labelLarge)
            }
        },
    ) {
        Row(
            Modifier
                .fillMaxWidth()
                .background(Dc.colors.paper)
                .combinedClickable(
                    onClick = onOpen,
                    onLongClick = {
                        haptics.performHapticFeedback(HapticFeedbackType.LongPress)
                        onDelete()
                    },
                    onClickLabel = "Open the report",
                    onLongClickLabel = "Delete this session",
                )
                .semantics { customActions = listOf(CustomAccessibilityAction("Delete this session") { onDelete(); true }) }
                .heightIn(min = 64.dp)
                .padding(vertical = 14.dp)
                .animateContentSize()
                .testTag("session-row-${session.id}"),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        sessionName(session.title, session.createdAt),
                        style = MaterialTheme.typography.titleSmall,
                        color = Dc.colors.ink,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f, fill = false),
                    )
                    if (session.shared) {
                        Spacer(Modifier.width(10.dp))
                        StateLabel("Shared")
                    }
                }
                Text(rowMeta(session), style = MaterialTheme.typography.bodySmall, color = Dc.colors.inkSoft)
                val done = session.status == "completed"
                val failed = session.status == "failed"
                if (!done && !failed) ThinProgress(session.progress.toFloat(), Modifier.padding(top = 6.dp))
                if (deleting) Note("Deleting.")
            }
            Spacer(Modifier.width(16.dp))
            when (session.status) {
                "completed" -> Text(jsRound(session.overallScore ?: 0.0).toString(), style = MaterialTheme.typography.headlineSmall, color = Dc.colors.ink)
                "failed" -> StateLabel("Failed", tone = "failed")
                else -> StateLabel(statusLabel(session.status))
            }
        }
    }
}

/** The row's second line, word for word as on /practice. */
fun rowMeta(session: SessionSummary): String = buildString {
    session.motion?.let { append("Motion: ${it.title}. ") }
    when (session.status) {
        "completed" -> {
            append("${formatRecordedShort(session.createdAt)}. ")
            append("${formatClock(session.durationSeconds ?: 0.0)} of speech at ${jsRound(session.wordsPerMinute ?: 0.0)} words per minute. ")
            append("${session.feedbackCount ?: 0} findings.")
        }
        "failed" -> append(session.errorMessage ?: "Analysis failed.")
        else -> {
            append(statusLabel(session.status))
            val wait = session.queueWaitSeconds
            append(if (wait != null && wait > 0) ". Waiting about ${jsRound(wait)} seconds for capacity." else ".")
        }
    }
}
