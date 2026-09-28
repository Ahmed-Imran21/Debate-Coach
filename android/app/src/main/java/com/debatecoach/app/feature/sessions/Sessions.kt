package com.debatecoach.app.feature.sessions

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
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
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
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
import com.debatecoach.app.navigation.sessionContainer
import com.debatecoach.app.ui.components.EmptyState
import com.debatecoach.app.ui.components.Icons
import com.debatecoach.app.ui.components.InlineMessage
import com.debatecoach.app.ui.components.OfflineBanner
import com.debatecoach.app.ui.components.SkeletonLine
import com.debatecoach.app.ui.components.StatusChip
import com.debatecoach.app.ui.components.ThinProgress
import com.debatecoach.app.ui.components.Tone
import com.debatecoach.app.ui.components.TopLevelBar
import com.debatecoach.app.ui.components.skeleton
import com.debatecoach.app.ui.theme.Space
import com.debatecoach.app.ui.theme.numberStyle
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

const val POLL_MS = 4_000L

data class SessionsState(
    val sessions: List<SessionSummary>? = null,
    val error: String? = null,
    val refreshing: Boolean = false,
    /** Swiped away, waiting out its undo window: hidden, not yet deleted. */
    val pendingDelete: SessionSummary? = null,
    /** Bumped on each Undo, so a row that comes back also comes back un-swiped. */
    val undoToken: Int = 0,
) {
    /** What the list shows. */
    val visible: List<SessionSummary>? get() = sessions?.filterNot { it.id == pendingDelete?.id }

    /** Changes when a session finishes, so Progress and Insights refetch. */
    val completedCount: Int get() = visible?.count { it.status == "completed" } ?: 0
}

sealed interface SessionsEvent {
    /** Deleted (pending): offer Undo. */
    data class Deleted(val session: SessionSummary) : SessionsEvent
    data class Message(val text: String) : SessionsEvent
}

/** app/practice/page.tsx: the list, its polling, and delete (with undo, the Android way). */
class SessionsViewModel(private val backend: Backend) : ViewModel() {
    private val _state = MutableStateFlow(SessionsState())
    val state: StateFlow<SessionsState> = _state.asStateFlow()
    private val _events = MutableSharedFlow<SessionsEvent>(extraBufferCapacity = 4)
    val events: SharedFlow<SessionsEvent> = _events.asSharedFlow()
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
    } catch (error: Exception) {
        if (error is CancellationException) throw error
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

    /** Loads once if nothing has been loaded yet (Progress and Insights need the completed count). */
    fun ensureLoaded() {
        if (_state.value.sessions == null && polling == null) viewModelScope.launch { load() }
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

    /**
     * Swipe or menu delete: the row goes at once and Undo is offered; the
     * delete is only sent when the undo window closes ([commitDelete]).
     */
    fun deleteWithUndo(session: SessionSummary) {
        if (_state.value.pendingDelete != null) commitDelete()
        _state.update { it.copy(pendingDelete = session) }
        _events.tryEmit(SessionsEvent.Deleted(session))
    }

    fun undoDelete() = _state.update { it.copy(pendingDelete = null, undoToken = it.undoToken + 1) }

    /** Sends the pending delete, if any. On failure the row comes back, with the website's message. */
    fun commitDelete() {
        val session = _state.value.pendingDelete ?: return
        viewModelScope.launch {
            try {
                withContext(NonCancellable) { backend.deleteSession(session.id) }
                _state.update { s -> s.copy(sessions = s.sessions?.filterNot { it.id == session.id }, pendingDelete = s.pendingDelete.takeUnless { it?.id == session.id }) }
            } catch (error: Exception) {
                if (error is ApiException && error.status == 404) {
                    _state.update { s -> s.copy(sessions = s.sessions?.filterNot { it.id == session.id }, pendingDelete = null) }
                    _events.tryEmit(SessionsEvent.Message("That session was already gone."))
                } else {
                    _state.update { it.copy(pendingDelete = null) }
                    if (!(error is ApiException && error.status == 401)) _events.tryEmit(SessionsEvent.Message("Could not delete that session. Try again."))
                }
            }
        }
    }
}

/** The row's supporting line, word for word as on /practice. */
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

/** A queue wait, as the row's quiet caption. */
fun waitCaption(session: SessionSummary): String? =
    session.queueWaitSeconds?.takeIf { it > 0 }?.let { "Waiting about ${jsRound(it)} seconds for capacity" }

// ---------------------------------------------------------------
// UI
// ---------------------------------------------------------------

@Composable
fun SessionsScreen(
    vm: SessionsViewModel,
    online: Boolean,
    onOpenSession: (String) -> Unit,
    onRecord: () -> Unit,
    showFab: Boolean = true,
    selectedId: String? = null,
) {
    val state by vm.state.collectAsStateWithLifecycle()
    val haptics = LocalHapticFeedback.current
    val snackbar = remember { SnackbarHostState() }
    val listState = rememberLazyListState()
    val scroll = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    val fabExpanded by remember { derivedStateOf { listState.firstVisibleItemIndex == 0 } }

    // Poll only while this screen is visible (and resume on return), so a
    // session recorded on the website shows up here too.
    LifecycleStartEffect(vm) {
        vm.startPolling()
        onStopOrDispose { vm.stopPolling() }
    }

    // Undo, or the delete goes through when the snackbar goes (timed
    // out, swiped away, or the screen left).
    LaunchedEffect(vm) {
        vm.events.collect { event ->
            when (event) {
                is SessionsEvent.Deleted -> {
                    var undone = false
                    try {
                        val result = snackbar.showSnackbar("Session deleted", actionLabel = "Undo", withDismissAction = false, duration = SnackbarDuration.Long)
                        undone = result == SnackbarResult.ActionPerformed
                    } finally {
                        if (undone) vm.undoDelete() else vm.commitDelete()
                    }
                }
                is SessionsEvent.Message -> snackbar.showSnackbar(event.text)
            }
        }
    }

    Scaffold(
        modifier = Modifier.nestedScroll(scroll.nestedScrollConnection),
        containerColor = MaterialTheme.colorScheme.surface,
        topBar = {
            TopLevelBar("Sessions", scroll) {
                OverflowMenu(listOf(MenuAction("Refresh", Icons.Refresh, vm::refresh)))
            }
        },
        snackbarHost = { SnackbarHost(snackbar) },
        floatingActionButton = {
            if (showFab) {
                ExtendedFloatingActionButton(
                    onClick = {
                        haptics.performHapticFeedback(HapticFeedbackType.Confirm)
                        onRecord()
                    },
                    expanded = fabExpanded,
                    icon = { Icon(Icons.Mic, contentDescription = null) },
                    text = { Text("Record") },
                    containerColor = MaterialTheme.colorScheme.primary,
                    contentColor = MaterialTheme.colorScheme.onPrimary,
                    modifier = Modifier.testTag("record-button").semantics { contentDescription = "Record a speech" },
                )
            }
        },
    ) { padding ->
        PullToRefreshBox(
            isRefreshing = state.refreshing,
            onRefresh = vm::refresh,
            modifier = Modifier.fillMaxSize().padding(top = padding.calculateTopPadding()),
        ) {
            val sessions = state.visible
            LazyColumn(
                Modifier.fillMaxSize().testTag("session-list"),
                state = listState,
                contentPadding = PaddingValues(bottom = padding.calculateBottomPadding() + 96.dp),
            ) {
                item(key = "banners") {
                    Column(Modifier.padding(horizontal = Space.l), verticalArrangement = Arrangement.spacedBy(Space.s)) {
                        OfflineBanner(online)
                        AnimatedVisibility(state.error != null && sessions != null, enter = fadeIn(), exit = fadeOut()) {
                            InlineMessage(state.error.orEmpty(), modifier = Modifier.padding(bottom = Space.s))
                        }
                    }
                }
                when {
                    sessions == null -> {
                        if (state.error != null) item(key = "error") { InlineMessage(state.error!!, modifier = Modifier.padding(Space.l)) }
                        items(5, key = { "skeleton-$it" }) { SkeletonRow() }
                    }
                    sessions.isEmpty() -> item(key = "empty") {
                        EmptyState(
                            icon = Icons.Mic,
                            title = "No sessions yet",
                            body = "Record a speech and its report will appear here while it's being analysed.",
                            modifier = Modifier.testTag("sessions-empty"),
                            action = { Button(onClick = onRecord, modifier = Modifier.heightIn(min = Space.touch)) { Text("Record a speech") } },
                        )
                    }
                    else -> items(sessions, key = { it.id }) { session ->
                        SessionRow(
                            session = session,
                            undoToken = state.undoToken,
                            selected = session.id == selectedId,
                            onOpen = { onOpenSession(session.id) },
                            onDelete = { vm.deleteWithUndo(session) },
                            modifier = Modifier.animateItem(),
                        )
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun SessionRow(session: SessionSummary, undoToken: Int, selected: Boolean, onOpen: () -> Unit, onDelete: () -> Unit, modifier: Modifier = Modifier) {
    val haptics = LocalHapticFeedback.current
    var menu by remember { mutableStateOf(false) }
    val dismiss = rememberSwipeToDismissBoxState(
        confirmValueChange = { value ->
            if (value == SwipeToDismissBoxValue.EndToStart) {
                haptics.performHapticFeedback(HapticFeedbackType.Confirm)
                onDelete()
                true
            } else {
                false
            }
        },
    )
    // The list keeps a removed row's composition while it fades out; if
    // Undo brings it back in that time, slide it back into place.
    LaunchedEffect(undoToken) {
        if (dismiss.currentValue != SwipeToDismissBoxValue.Settled) dismiss.reset()
    }
    // A tick as the swipe crosses the point of no return.
    var armed by remember { mutableStateOf(false) }
    LaunchedEffect(dismiss.targetValue) {
        val now = dismiss.targetValue == SwipeToDismissBoxValue.EndToStart
        if (now && !armed) haptics.performHapticFeedback(HapticFeedbackType.GestureThresholdActivate)
        armed = now
    }

    SwipeToDismissBox(
        state = dismiss,
        enableDismissFromStartToEnd = false,
        modifier = modifier,
        backgroundContent = {
            val scale by animateFloatAsState(if (armed) 1.15f else 0.9f, label = "delete-icon")
            Box(
                Modifier.fillMaxSize().background(MaterialTheme.colorScheme.errorContainer).padding(horizontal = Space.xl),
                contentAlignment = Alignment.CenterEnd,
            ) {
                Icon(Icons.Delete, contentDescription = null, tint = MaterialTheme.colorScheme.onErrorContainer, modifier = Modifier.scale(scale))
            }
        },
    ) {
        // Opaque, so the delete background never shows through the divider's inset.
        Column(Modifier.background(MaterialTheme.colorScheme.surface)) {
        Box {
            Row(
                Modifier
                    .fillMaxWidth()
                    .sessionContainer(session.id)
                    .background(if (selected) MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.surface)
                    .combinedClickable(
                        onClick = onOpen,
                        onLongClick = {
                            haptics.performHapticFeedback(HapticFeedbackType.LongPress)
                            menu = true
                        },
                        onClickLabel = "Open the report",
                        onLongClickLabel = "More options",
                    )
                    .semantics { customActions = listOf(CustomAccessibilityAction("Delete this session") { onDelete(); true }) }
                    .heightIn(min = 72.dp)
                    .padding(horizontal = Space.l, vertical = Space.m)
                    .testTag("session-row-${session.id}"),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                LeadingTile(session)
                Spacer(Modifier.width(Space.l))
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(
                        sessionName(session.title, session.createdAt),
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurface,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        supportingLine(session),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                    )
                    session.motion?.let {
                        Text(
                            "Motion: ${it.title}",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    StatusLine(session)
                }
            }
            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                DropdownMenuItem(
                    text = { Text("Open report") },
                    leadingIcon = { Icon(Icons.Document, contentDescription = null) },
                    onClick = {
                        menu = false
                        onOpen()
                    },
                )
                DropdownMenuItem(
                    text = { Text("Delete", color = MaterialTheme.colorScheme.error) },
                    leadingIcon = { Icon(Icons.DeleteOutlined, contentDescription = null, tint = MaterialTheme.colorScheme.error) },
                    onClick = {
                        menu = false
                        onDelete()
                    },
                    modifier = Modifier.testTag("menu-delete"),
                )
            }
        }
        HorizontalDivider(Modifier.padding(start = 88.dp), color = MaterialTheme.colorScheme.outlineVariant)
        }
    }
}

/** Date, then length and pace once it's analysed. */
private fun supportingLine(session: SessionSummary): String = buildString {
    append(formatRecordedShort(session.createdAt))
    if (session.status == "completed") {
        append(" · ${formatClock(session.durationSeconds ?: 0.0)}")
        append(" · ${jsRound(session.wordsPerMinute ?: 0.0)} wpm")
    }
}

/** The score (serif) once done; a progress ring while it runs; a warning if it failed. */
@Composable
private fun LeadingTile(session: SessionSummary) {
    val shape = MaterialTheme.shapes.medium
    Box(
        Modifier.size(56.dp).clip(shape).background(
            when (session.status) {
                "completed" -> MaterialTheme.colorScheme.primaryContainer
                "failed" -> MaterialTheme.colorScheme.errorContainer
                else -> MaterialTheme.colorScheme.surfaceContainerHigh
            },
        ),
        contentAlignment = Alignment.Center,
    ) {
        when (session.status) {
            "completed" -> Text(
                jsRound(session.overallScore ?: 0.0).toString(),
                style = numberStyle(24.sp),
                color = MaterialTheme.colorScheme.onPrimaryContainer,
                modifier = Modifier.semantics { contentDescription = "Score ${jsRound(session.overallScore ?: 0.0)}" },
            )
            "failed" -> Icon(Icons.Warning, contentDescription = null, tint = MaterialTheme.colorScheme.onErrorContainer)
            else -> CircularProgressIndicator(
                progress = { session.progress.toFloat().coerceIn(0.02f, 1f) },
                modifier = Modifier.size(28.dp),
                strokeWidth = 3.dp,
                trackColor = MaterialTheme.colorScheme.surfaceContainerHighest,
                gapSize = 0.dp,
            )
        }
    }
}

/** The status chip(s): the pipeline stage while it runs, "Failed", "Shared". */
@Composable
private fun StatusLine(session: SessionSummary) {
    val running = session.status !in TERMINAL
    val chips = buildList {
        if (running) add(statusLabel(session.status) to Tone.NEUTRAL)
        if (session.status == "failed") add("Failed" to Tone.CRITICAL)
        if (session.shared) add("Shared" to Tone.POSITIVE)
    }
    if (chips.isEmpty()) return
    Column(Modifier.padding(top = Space.xs), verticalArrangement = Arrangement.spacedBy(Space.xs)) {
        Row(horizontalArrangement = Arrangement.spacedBy(Space.s), verticalAlignment = Alignment.CenterVertically) {
            chips.forEach { (text, tone) -> StatusChip(text, tone = tone, icon = if (text == "Shared") Icons.Link else null) }
        }
        if (running) waitCaption(session)?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (running) ThinProgress(session.progress.toFloat(), height = 2.dp)
        if (session.status == "failed") {
            Text(
                session.errorMessage ?: "Analysis failed.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
private fun SkeletonRow() {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 72.dp).padding(horizontal = Space.l, vertical = Space.m).semantics { contentDescription = "Loading" },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(56.dp).skeleton(MaterialTheme.shapes.medium))
        Spacer(Modifier.width(Space.l))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(Space.s)) {
            SkeletonLine(0.7f, height = 16.dp)
            SkeletonLine(0.45f)
        }
    }
}

// ---------------------------------------------------------------
// Overflow menu (shared by the top-level screens)
// ---------------------------------------------------------------

data class MenuAction(val label: String, val icon: androidx.compose.ui.graphics.vector.ImageVector?, val onClick: () -> Unit, val danger: Boolean = false, val tag: String? = null)

@Composable
fun OverflowMenu(actions: List<MenuAction>, modifier: Modifier = Modifier) {
    var open by remember { mutableStateOf(false) }
    Box(modifier) {
        androidx.compose.material3.IconButton(onClick = { open = true }, modifier = Modifier.testTag("overflow")) {
            Icon(Icons.MoreVert, contentDescription = "More options")
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            actions.forEach { a ->
                val tint = if (a.danger) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface
                DropdownMenuItem(
                    text = { Text(a.label, color = tint) },
                    leadingIcon = a.icon?.let { { Icon(it, contentDescription = null, tint = if (a.danger) tint else MaterialTheme.colorScheme.onSurfaceVariant) } },
                    onClick = {
                        open = false
                        a.onClick()
                    },
                    modifier = if (a.tag != null) Modifier.testTag(a.tag) else Modifier,
                )
            }
        }
    }
}
