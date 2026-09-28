package com.debatecoach.app.feature.report

import android.content.ClipData
import android.content.Intent
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.PrimaryScrollableTabRow
import androidx.compose.material3.PrimaryTabRow
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.TopAppBarScrollBehavior
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.layout.Layout
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.ClipEntry
import androidx.compose.ui.platform.LocalClipboard
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.LifecycleStartEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.debatecoach.app.AppContainer
import com.debatecoach.app.BuildConfig
import com.debatecoach.app.core.model.CATEGORY_LABEL
import com.debatecoach.app.core.model.FeedbackItem
import com.debatecoach.app.core.model.SCORE_ORDER
import com.debatecoach.app.core.model.SEVERITY_LABEL
import com.debatecoach.app.core.model.SessionReport
import com.debatecoach.app.core.model.SessionSummary
import com.debatecoach.app.core.model.statusLabel
import com.debatecoach.app.core.util.formatClock
import com.debatecoach.app.core.util.formatRecordedLong
import com.debatecoach.app.core.util.jsRound
import com.debatecoach.app.core.util.sessionName
import com.debatecoach.app.navigation.sessionContainer
import com.debatecoach.app.ui.components.AudioController
import com.debatecoach.app.ui.components.AudioPlayerControls
import com.debatecoach.app.ui.components.BigNumber
import com.debatecoach.app.ui.components.CardHeader
import com.debatecoach.app.ui.components.DcCard
import com.debatecoach.app.ui.components.EmptyState
import com.debatecoach.app.ui.components.Icons
import com.debatecoach.app.ui.components.InlineMessage
import com.debatecoach.app.ui.components.LeadingStrip
import com.debatecoach.app.ui.components.MiniPlayer
import com.debatecoach.app.ui.components.ScoreBar
import com.debatecoach.app.ui.components.SkeletonLine
import com.debatecoach.app.ui.components.StatTile
import com.debatecoach.app.ui.components.StatusChip
import com.debatecoach.app.ui.components.ThinProgress
import com.debatecoach.app.ui.components.Tone
import com.debatecoach.app.ui.components.appViewModel
import com.debatecoach.app.ui.components.openUrl
import com.debatecoach.app.ui.components.rememberAudioController
import com.debatecoach.app.ui.components.severityColor
import com.debatecoach.app.ui.components.severityTone
import com.debatecoach.app.ui.components.skeleton
import com.debatecoach.app.ui.theme.Dc
import com.debatecoach.app.ui.theme.DcColors
import com.debatecoach.app.ui.theme.Sans
import com.debatecoach.app.ui.theme.Serif
import com.debatecoach.app.ui.theme.Space
import com.debatecoach.app.feature.sessions.MenuAction
import com.debatecoach.app.feature.sessions.OverflowMenu
import java.io.File
import kotlin.math.roundToInt
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun SessionScreen(
    container: AppContainer,
    sessionId: String,
    onBack: (() -> Unit)?,
    onDeleted: () -> Unit,
    onRecordAgain: () -> Unit,
) {
    val vm = appViewModel(key = "session-$sessionId") { SessionViewModel(container.backend, sessionId, BuildConfig.WEBSITE_URL) }
    SessionContent(vm, onBack, onDeleted, onRecordAgain, Modifier.sessionContainer(sessionId))
}

private enum class ReportTab(val label: String) { OVERVIEW("Overview"), FINDINGS("Findings"), VISUAL("Visual") }

private enum class Sheet { SHARE, PDF, SCORES_INFO }

/** Visual gets its own tab only when there's visual data to show. */
private fun tabsFor(report: SessionReport): List<ReportTab> {
    val visual = visualSection(report)
    val hasVisual = visual is VisualSection.Metrics || keyMoments(report).isNotEmpty() ||
        (visual is VisualSection.Message && report.videoAnalysisStatus in setOf("awaiting_upload", "received", "processing"))
    return listOfNotNull(ReportTab.OVERVIEW, ReportTab.FINDINGS, ReportTab.VISUAL.takeIf { hasVisual })
}

@Composable
fun SessionContent(
    vm: SessionViewModel,
    onBack: (() -> Unit)?,
    onDeleted: () -> Unit = {},
    onRecordAgain: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val state by vm.state.collectAsStateWithLifecycle()
    val haptics = LocalHapticFeedback.current
    val snackbar = remember { SnackbarHostState() }
    val scroll = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    var sheet by rememberSaveable { mutableStateOf<Sheet?>(null) }
    var confirmDelete by rememberSaveable { mutableStateOf(false) }

    LifecycleStartEffect(vm) {
        vm.startPolling()
        onStopOrDispose { vm.stopPolling() }
    }
    LaunchedEffect(state.deleted) { if (state.deleted) onDeleted() }
    LaunchedEffect(state.deleteError) { state.deleteError?.let { snackbar.showSnackbar(it) } }

    val report = state.report
    val summary = state.summary
    val name = report?.let { sessionName(it.title, it.createdAt) } ?: summary?.let { sessionName(it.title, it.createdAt) }
    val audio = report?.audioUrl?.let { rememberAudioController(Uri.parse(it)) }
    val tabs = report?.let(::tabsFor) ?: emptyList()
    val pager = rememberPagerState { tabs.size }
    val scope = rememberCoroutineScope()

    Scaffold(
        modifier = modifier.nestedScroll(scroll.nestedScrollConnection).testTag("session-screen"),
        containerColor = MaterialTheme.colorScheme.surface,
        topBar = {
            ReportTopBar(
                name = name,
                score = report?.let { jsRound(it.scores["overall"] ?: 0.0) },
                recorded = (report?.createdAt ?: summary?.createdAt)?.let { "Recorded ${formatRecordedLong(it)}" },
                scroll = scroll,
                onBack = onBack,
                actions = {
                    if (report != null) {
                        IconButton(onClick = { sheet = Sheet.SHARE }, modifier = Modifier.testTag("share-button")) {
                            Icon(Icons.Share, contentDescription = "Share")
                        }
                        OverflowMenu(
                            listOf(
                                MenuAction("Export as PDF", Icons.Document, { sheet = Sheet.PDF }, tag = "export-pdf"),
                                MenuAction("Delete session", Icons.DeleteOutlined, { confirmDelete = true }, danger = true, tag = "delete-session"),
                            ),
                        )
                    } else if (summary != null && summary.status == "failed") {
                        OverflowMenu(listOf(MenuAction("Delete session", Icons.DeleteOutlined, { confirmDelete = true }, danger = true, tag = "delete-session")))
                    }
                },
            )
        },
        bottomBar = {
            val overviewShowing = tabs.getOrNull(pager.currentPage) == ReportTab.OVERVIEW
            AnimatedVisibility(
                audio != null && audio.active && !overviewShowing,
                enter = slideInVertically { it } + fadeIn(),
                exit = slideOutVertically { it } + fadeOut(),
            ) {
                if (audio != null && name != null) {
                    Box(Modifier.background(MaterialTheme.colorScheme.surfaceContainerHigh).windowInsetsPadding(WindowInsets.navigationBars)) {
                        MiniPlayer(audio, name)
                    }
                }
            }
        },
        snackbarHost = { SnackbarHost(snackbar) },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(top = padding.calculateTopPadding())) {
            when {
                report != null -> Column(Modifier.fillMaxSize()) {
                    val selectedTab = pager.currentPage.coerceIn(0, (tabs.size - 1).coerceAtLeast(0))
                    val tabItems: @Composable () -> Unit = {
                        tabs.forEachIndexed { i, tab ->
                            Tab(
                                selected = pager.currentPage == i,
                                onClick = {
                                    haptics.performHapticFeedback(HapticFeedbackType.SegmentTick)
                                    scope.launch { pager.animateScrollToPage(i) }
                                },
                                text = { Text(if (tab == ReportTab.FINDINGS) "${tab.label} (${report.feedback.size})" else tab.label, maxLines = 1) },
                                selectedContentColor = MaterialTheme.colorScheme.primary,
                                unselectedContentColor = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.testTag("tab-${tab.name.lowercase()}"),
                            )
                        }
                    }
                    // Large text: the tabs scroll rather than clip.
                    Box(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface), contentAlignment = Alignment.TopCenter) {
                        Box(Modifier.widthIn(max = Space.readingWidth)) {
                            if (LocalDensity.current.fontScale >= 1.3f) {
                                PrimaryScrollableTabRow(selectedTabIndex = selectedTab, containerColor = MaterialTheme.colorScheme.surface, edgePadding = Space.l, tabs = tabItems)
                            } else {
                                PrimaryTabRow(selectedTabIndex = selectedTab, containerColor = MaterialTheme.colorScheme.surface, tabs = tabItems)
                            }
                        }
                    }
                    HorizontalPager(pager, Modifier.fillMaxSize(), beyondViewportPageCount = 1, key = { tabs[it].name }) { page ->
                        val bottom = padding.calculateBottomPadding() + Space.xxl
                        when (tabs[page]) {
                            ReportTab.OVERVIEW -> OverviewTab(report, audio, bottom, onScoresInfo = { sheet = Sheet.SCORES_INFO })
                            ReportTab.FINDINGS -> FindingsTab(report.feedback, state.filter, vm::setFilter, bottom)
                            ReportTab.VISUAL -> VisualTab(report, audio, bottom)
                        }
                    }
                }
                state.error != null && summary == null -> EmptyState(
                    icon = Icons.Error,
                    title = state.error!!,
                    body = null,
                    action = onBack?.let { back -> { FilledTonalButton(onClick = back) { Text("Back to sessions") } } },
                )
                summary == null -> ReportSkeleton()
                summary.status == "failed" -> Failed(summary, onRecordAgain)
                else -> Working(summary, state.error)
            }
        }
    }

    // Sheets and dialogs
    if (report != null) {
        when (sheet) {
            Sheet.SHARE -> ShareSheet(state, vm, onDismiss = { sheet = null })
            Sheet.PDF -> PdfSheet(report, onDismiss = { sheet = null })
            Sheet.SCORES_INFO -> InfoSheet(
                "About these scores",
                "Delivery is arithmetic over the audio. The other five come from a language model reading the transcript, so treat them as a second opinion rather than a mark. Rebuttal isn't scored when there was nothing to rebut, and doesn't count toward the overall.",
                onDismiss = { sheet = null },
            )
            null -> Unit
        }
    }
    if (confirmDelete && name != null) {
        AlertDialog(
            onDismissRequest = { confirmDelete = false },
            icon = { Icon(Icons.DeleteOutlined, contentDescription = null) },
            title = { Text("Delete this session?") },
            text = { Text("“$name” will be deleted from your account on the website and in the app. This cannot be undone.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmDelete = false
                        haptics.performHapticFeedback(HapticFeedbackType.Confirm)
                        vm.delete()
                    },
                    colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error),
                    modifier = Modifier.testTag("confirm-delete"),
                ) { Text("Delete") }
            },
            dismissButton = { TextButton(onClick = { confirmDelete = false }) { Text("Cancel") } },
        )
    }
}

// ---------------------------------------------------------------
// The collapsing header
// ---------------------------------------------------------------

/**
 * Large at first (the session's name, when it was recorded, and the
 * overall score big in the serif), shrinking into a standard bar that
 * keeps the name and score as the report scrolls.
 */
@Composable
private fun ReportTopBar(
    name: String?,
    score: Long?,
    recorded: String?,
    scroll: TopAppBarScrollBehavior,
    onBack: (() -> Unit)?,
    actions: @Composable () -> Unit,
) {
    var expandedHeight by remember { mutableFloatStateOf(0f) }
    SideEffect {
        if (scroll.state.heightOffsetLimit != -expandedHeight) scroll.state.heightOffsetLimit = -expandedHeight
    }
    val fraction = scroll.state.collapsedFraction.coerceIn(0f, 1f)
    val colors = MaterialTheme.colorScheme
    Surface(color = lerp(colors.surface, colors.surfaceContainer, fraction)) {
        Column(Modifier.windowInsetsPadding(TopAppBarDefaults.windowInsets)) {
            Row(Modifier.fillMaxWidth().height(64.dp).padding(horizontal = Space.xs), verticalAlignment = Alignment.CenterVertically) {
                if (onBack != null) {
                    IconButton(onClick = onBack) { Icon(Icons.Back, contentDescription = "Back to sessions") }
                } else {
                    Spacer(Modifier.width(Space.m))
                }
                Row(
                    Modifier.weight(1f).padding(horizontal = Space.xs).graphicsLayer { alpha = ((fraction - 0.5f) * 2f).coerceIn(0f, 1f) },
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    if (name != null) {
                        Text(name, style = MaterialTheme.typography.titleLarge, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                    }
                    if (score != null) {
                        Spacer(Modifier.width(Space.s))
                        StatusChip(score.toString(), tone = Tone.POSITIVE)
                    }
                }
                actions()
            }
            // The expanded block: measured at its natural height (so large
            // fonts never clip), then shown as much as the scroll allows.
            Layout(
                content = {
                    // Aligned with the report's reading column on wide screens.
                    Box(Modifier.fillMaxWidth().onSizeChanged { expandedHeight = it.height.toFloat() }, contentAlignment = Alignment.TopCenter) {
                        Box(Modifier.widthIn(max = Space.readingWidth).fillMaxWidth()) { ExpandedHeader(name, score, recorded) }
                    }
                },
                modifier = Modifier.clipToBounds().graphicsLayer { alpha = (1f - fraction * 1.6f).coerceIn(0f, 1f) },
            ) { measurables, constraints ->
                val p = measurables.first().measure(constraints.copy(minHeight = 0, maxHeight = Constraints.Infinity))
                val h = (p.height + scroll.state.heightOffset).roundToInt().coerceIn(0, p.height)
                layout(constraints.maxWidth, h) { p.place(0, h - p.height) }
            }
        }
    }
}

@Composable
private fun ExpandedHeader(name: String?, score: Long?, recorded: String?) {
    Column(Modifier.fillMaxWidth().padding(start = Space.gutter, end = Space.gutter, bottom = Space.l)) {
        if (name == null) {
            SkeletonLine(0.7f, height = 28.dp)
            Spacer(Modifier.height(Space.s))
            SkeletonLine(0.4f)
            return@Column
        }
        Text(name, style = MaterialTheme.typography.headlineMedium, maxLines = 3, overflow = TextOverflow.Ellipsis, modifier = Modifier.semantics { heading() })
        if (recorded != null) {
            Text(recorded, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (score != null) {
            Spacer(Modifier.height(Space.m))
            Row(verticalAlignment = Alignment.Bottom, modifier = Modifier.semantics(mergeDescendants = true) { contentDescription = "Overall score $score out of 100" }) {
                BigNumber(score.toString(), size = 57.sp, color = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.width(Space.s))
                Column(Modifier.padding(bottom = Space.s)) {
                    Text("Overall", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurface)
                    Text("out of 100", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

// ---------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------

@Composable
private fun TabList(bottom: androidx.compose.ui.unit.Dp, tag: String, content: LazyListScope.() -> Unit) {
    val gutter = Space.gutter
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.TopCenter) {
        LazyColumn(
            Modifier.widthIn(max = Space.readingWidth).fillMaxSize().testTag(tag),
            contentPadding = PaddingValues(start = gutter, end = gutter, top = Space.l, bottom = bottom),
            verticalArrangement = Arrangement.spacedBy(Space.l),
            content = content,
        )
    }
}

@Composable
private fun OverviewTab(report: SessionReport, audio: AudioController?, bottom: androidx.compose.ui.unit.Dp, onScoresInfo: () -> Unit) {
    TabList(bottom, "overview") {
        report.motion?.let { motion ->
            item(key = "motion") {
                DcCard(Modifier.testTag("report-meta")) {
                    Text("Practice prompt", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.height(Space.xs))
                    Text("Motion: ${motion.description}", style = MaterialTheme.typography.bodyLarge)
                    motionFallbackNote(true, report.motionNotApplied)?.let {
                        Spacer(Modifier.height(Space.m))
                        InlineMessage(it, tone = Tone.CAUTION, icon = Icons.Warning)
                    }
                }
            }
        }
        item(key = "scores") { ScoresCard(report, onScoresInfo) }
        item(key = "figures") { DeliveryCard(report) }
        val duration = trackDuration(report)
        if (duration > 0) item(key = "track") { DcCard { SpeechTrack(duration, marksFor(report), "Where each finding landed") } }
        if (audio != null) {
            item(key = "audio") {
                DcCard {
                    CardHeader("Listen back")
                    Spacer(Modifier.height(Space.m))
                    AudioPlayerControls(audio)
                }
            }
        }
        // A visual status with no tab of its own (unavailable, failed, not enough video).
        val visual = visualSection(report)
        if (visual is VisualSection.Message && ReportTab.VISUAL !in tabsFor(report)) {
            item(key = "visual-note") { InlineMessage(visual.text, icon = Icons.Camera) }
        }
    }
}

@Composable
private fun ScoresCard(report: SessionReport, onInfo: () -> Unit) {
    DcCard(Modifier.testTag("scores")) {
        CardHeader("Scores by category") {
            IconButton(onClick = onInfo) { Icon(Icons.Info, contentDescription = "About these scores", tint = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
        Spacer(Modifier.height(Space.s))
        SCORE_ORDER.forEachIndexed { i, category ->
            val raw = report.scores[category]
            // null: not scored (rebuttal with nothing to rebut). Absent: an older report.
            val notScored = report.scores.containsKey(category) && raw == null
            val label = CATEGORY_LABEL[category].orEmpty()
            Column(
                Modifier.fillMaxWidth().heightIn(min = Space.touch).padding(vertical = Space.s).semantics(mergeDescendants = true) {
                    contentDescription = "$label: " + if (notScored) "Not scored: nothing to rebut" else "${jsRound(raw ?: 0.0)} out of 100"
                },
                verticalArrangement = Arrangement.spacedBy(Space.s),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(label, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
                    if (!notScored) Text(jsRound(raw ?: 0.0).toString(), style = MaterialTheme.typography.titleMedium)
                }
                if (notScored) {
                    Text("Not scored: nothing to rebut", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                } else {
                    ScoreBar(raw ?: 0.0, Modifier.fillMaxWidth())
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DeliveryCard(report: SessionReport) {
    // Overall is in the header; the rest of the website's figures here.
    val figures = figuresFor(report).drop(1)
    DcCard {
        CardHeader("Delivery")
        Spacer(Modifier.height(Space.m))
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            val columns = if (maxWidth > 520.dp) 3 else 2
            val gap = Space.s
            // A hair under the exact share, so rounding never wraps the last tile.
            val cell = (maxWidth - gap * (columns - 1)) / columns - 0.5.dp
            FlowRow(horizontalArrangement = Arrangement.spacedBy(gap), verticalArrangement = Arrangement.spacedBy(gap)) {
                figures.forEach { StatTile(it.value, it.label, Modifier.width(cell)) }
            }
        }
    }
}

@Composable
private fun FindingsTab(feedback: List<FeedbackItem>, filter: String, onFilter: (String) -> Unit, bottom: androidx.compose.ui.unit.Dp) {
    val haptics = LocalHapticFeedback.current
    val findings = visibleFindings(feedback, filter)
    Column(Modifier.fillMaxSize()) {
        LazyRow(
            Modifier.fillMaxWidth().semantics { contentDescription = "Filter findings" },
            contentPadding = PaddingValues(horizontal = Space.gutter, vertical = Space.s),
            horizontalArrangement = Arrangement.spacedBy(Space.s),
        ) {
            val options = listOf("all" to "All ${feedback.size}") + presentCategories(feedback).map { it to CATEGORY_LABEL[it].orEmpty() }
            items(options, key = { it.first }) { (value, label) ->
                FilterChip(
                    selected = filter == value,
                    onClick = {
                        haptics.performHapticFeedback(HapticFeedbackType.SegmentTick)
                        onFilter(value)
                    },
                    label = { Text(label) },
                    leadingIcon = if (filter == value) {
                        { Icon(Icons.Check, contentDescription = null, modifier = Modifier.size(FilterChipDefaults.IconSize)) }
                    } else {
                        null
                    },
                    modifier = Modifier.heightIn(min = Space.touch).testTag("filter-$value"),
                )
            }
        }
        TabList(bottom, "findings") {
            if (findings.isEmpty()) {
                item { EmptyState(Icons.CheckCircle, "No findings here", "Nothing was flagged in this category.") }
            }
            items(findings.size, key = { "finding-${findings[it].category}-${findings[it].title}-$it" }) { i -> FindingCard(findings[i]) }
        }
    }
}

@Composable
private fun FindingCard(item: FeedbackItem) {
    var expanded by rememberSaveable(item.title, item.category) { mutableStateOf(false) }
    val rotation by animateFloatAsState(if (expanded) 180f else 0f, label = "chevron")
    val category = CATEGORY_LABEL[item.category] ?: item.category
    val severity = SEVERITY_LABEL[item.severity] ?: item.severity
    DcCard(
        Modifier.testTag("finding").semantics { stateDescription = if (expanded) "Expanded" else "Collapsed" },
        onClick = { expanded = !expanded },
        padding = PaddingValues(0.dp),
    ) {
        Row(Modifier.height(IntrinsicSize.Min)) {
            LeadingStrip(severityColor(item.severity), Modifier.padding(vertical = Space.m))
            Column(Modifier.weight(1f).padding(Space.l).animateContentSize(), verticalArrangement = Arrangement.spacedBy(Space.s)) {
                Row(verticalAlignment = Alignment.Top) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(Space.xs)) {
                        Text(item.title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.semantics { heading() })
                        Row(horizontalArrangement = Arrangement.spacedBy(Space.s), verticalAlignment = Alignment.CenterVertically) {
                            StatusChip(severity, tone = severityTone(item.severity))
                            Text(category, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    Icon(Icons.ExpandMore, contentDescription = null, modifier = Modifier.rotate(rotation), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Text(
                    item.issue,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = if (expanded) Int.MAX_VALUE else 2,
                    overflow = TextOverflow.Ellipsis,
                )
                if (expanded) {
                    item.evidence.forEach { Quote(it) }
                    item.explanation?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                    item.recommendation?.let {
                        Column(
                            Modifier.fillMaxWidth().clip(MaterialTheme.shapes.small).background(MaterialTheme.colorScheme.secondaryContainer).padding(Space.m),
                        ) {
                            Text("What to try", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSecondaryContainer)
                            Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSecondaryContainer)
                        }
                    }
                }
            }
        }
    }
}

/** An evidence quote, in the serif. */
@Composable
private fun Quote(text: String) {
    Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min)) {
        Box(Modifier.width(2.dp).fillMaxHeight().background(MaterialTheme.colorScheme.outline))
        Spacer(Modifier.width(Space.m))
        Text(text, fontFamily = Serif, style = MaterialTheme.typography.bodyLarge.copy(fontFamily = Serif), color = MaterialTheme.colorScheme.onSurface)
    }
}

@Composable
private fun VisualTab(report: SessionReport, audio: AudioController?, bottom: androidx.compose.ui.unit.Dp) {
    val section = visualSection(report)
    val moments = keyMoments(report)
    TabList(bottom, "visual") {
        when (section) {
            is VisualSection.Message -> item(key = "visual-message") { InlineMessage(section.text, icon = Icons.Camera) }
            is VisualSection.Metrics -> {
                item(key = "visual-metrics") { VisualMetricsCard(section) }
                val notes = listOfNotNull(section.faceMessage, section.handsMessage) + section.warnings +
                    listOfNotNull("Coaching notes for your visual delivery couldn’t be generated for this session. The measurements above are unaffected.".takeIf { section.coachingFailed })
                items(notes, key = { "note-$it" }) { InlineMessage(it) }
                items(section.sessionFeedback.size, key = { "coach-$it" }) { i ->
                    val (text, polarity) = section.sessionFeedback[i]
                    CoachingCard(text, polarity)
                }
            }
            VisualSection.Hidden -> Unit
        }
        if (moments.isNotEmpty()) {
            item(key = "moments-title") {
                Text("Key moments", style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(top = Space.s).semantics { heading() })
            }
            items(moments, key = { "moment-${it.key}" }) { e ->
                KeyMomentCard(e, onPlay = audio?.let { a -> { a.seekAndPlay(maxOf(0.0, e.moment.start - 1)) } })
            }
        }
    }
}

@Composable
private fun VisualMetricsCard(section: VisualSection.Metrics) {
    DcCard(Modifier.testTag("visual-delivery")) {
        CardHeader("Visual delivery")
        section.rows.forEachIndexed { i, row ->
            if (i > 0) HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            Column(Modifier.fillMaxWidth().padding(vertical = Space.m).semantics(mergeDescendants = true) {}, verticalArrangement = Arrangement.spacedBy(Space.xs)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(row.label, style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
                    Text(row.value, style = MaterialTheme.typography.titleMedium)
                }
                Text(row.definition, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                row.confidence?.let { StatusChip(it, tone = if (row.highConfidence) Tone.POSITIVE else Tone.NEUTRAL) }
            }
        }
    }
}

@Composable
private fun CoachingCard(text: String, polarity: String?) {
    val color = when (polarity) {
        "strength" -> MaterialTheme.colorScheme.primary
        "improve" -> Dc.colors.amber
        else -> MaterialTheme.colorScheme.outline
    }
    DcCard(padding = PaddingValues(0.dp)) {
        Row(Modifier.height(IntrinsicSize.Min)) {
            LeadingStrip(color, Modifier.padding(vertical = Space.m))
            Text(text, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(Space.l))
        }
    }
}

@Composable
private fun KeyMomentCard(e: MomentEntry, onPlay: (() -> Unit)?) {
    val haptics = LocalHapticFeedback.current
    DcCard(Modifier.testTag("key-moment"), padding = PaddingValues(0.dp)) {
        Row(Modifier.height(IntrinsicSize.Min)) {
            LeadingStrip(if (e.positive) MaterialTheme.colorScheme.primary else Dc.colors.amber, Modifier.padding(vertical = Space.m))
            Column(Modifier.weight(1f).padding(Space.l), verticalArrangement = Arrangement.spacedBy(Space.s)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(e.meta, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.weight(1f))
                    if (onPlay != null) {
                        FilledTonalButton(
                            onClick = {
                                haptics.performHapticFeedback(HapticFeedbackType.ContextClick)
                                onPlay()
                            },
                            contentPadding = PaddingValues(horizontal = Space.m),
                            modifier = Modifier.heightIn(min = Space.touch).testTag("seek-${e.key}"),
                        ) {
                            Icon(Icons.Play, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(Modifier.width(Space.xs))
                            Text("Play from here")
                        }
                    }
                }
                if (e.moment.excerptText.isNotEmpty()) Quote(e.moment.excerptText)
                e.facts.forEach { Text("•  $it", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                e.coaching?.let { Text(it, style = MaterialTheme.typography.bodyLarge) }
            }
        }
    }
}

// ---------------------------------------------------------------
// Speech timeline (components/SpeechTrack.tsx)
// ---------------------------------------------------------------

private fun markColor(kind: MarkKind, c: DcColors, outline: Color, error: Color): Color = when (kind) {
    MarkKind.PAUSE -> outline
    MarkKind.FILLER -> c.amber
    MarkKind.STUTTER -> c.inkSoft
    MarkKind.FALLACY -> error
}

/** The speech as a stretch of time, each finding where it happened. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SpeechTrack(duration: Double, marks: List<Mark>, title: String) {
    val c = Dc.colors
    val scheme = MaterialTheme.colorScheme
    val measurer = rememberTextMeasurer()
    val safe = if (duration > 0) duration else 1.0
    Column(verticalArrangement = Arrangement.spacedBy(Space.s), modifier = Modifier.testTag("speech-track")) {
        CardHeader(title, supporting = "Length ${formatClock(safe)}")
        Canvas(
            Modifier
                .fillMaxWidth()
                .height(88.dp)
                .semantics { contentDescription = "$title. ${marks.size} findings across ${formatClock(safe)}." },
        ) {
            val usable = size.width
            val base = 60.dp.toPx()
            fun x(t: Double) = (t.coerceIn(0.0, safe) / safe).toFloat() * usable
            drawRoundRect(scheme.surfaceContainerHighest, Offset(0f, 22.dp.toPx()), Size(usable, 20.dp.toPx()), androidx.compose.ui.geometry.CornerRadius(4.dp.toPx()))
            for (m in marks) {
                val left = x(m.at)
                val width = m.span?.let { maxOf(3.dp.toPx(), x(m.at + it) - left) } ?: 3.dp.toPx()
                val pause = m.kind == MarkKind.PAUSE
                drawRect(markColor(m.kind, c, scheme.outline, scheme.error), Offset(left, (if (pause) 22 else 14).dp.toPx()), Size(width, (if (pause) 20 else 36).dp.toPx()))
            }
            drawLine(scheme.outlineVariant, Offset(0f, base), Offset(size.width, base), 1.dp.toPx())
            val labelStyle = TextStyle(fontFamily = Sans, fontSize = 11.sp, color = scheme.onSurfaceVariant)
            for (t in trackTicks(safe)) {
                val minute = t % 60.0 == 0.0
                drawLine(scheme.outline, Offset(x(t), base), Offset(x(t), base + (if (minute) 6 else 3).dp.toPx()), 1.dp.toPx())
                if (minute) {
                    val text = formatClock(t)
                    val w = measurer.measure(text, labelStyle).size.width
                    val left = if (t == 0.0) x(t) else (x(t) - w / 2f).coerceAtMost(size.width - w)
                    drawText(measurer, text, Offset(left, base + 10.dp.toPx()), labelStyle)
                }
            }
        }
        val present = marks.map { it.kind }.distinct()
        if (present.isNotEmpty()) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(Space.l), verticalArrangement = Arrangement.spacedBy(Space.xs)) {
                present.forEach { kind ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(10.dp).clip(MaterialTheme.shapes.extraSmall).background(markColor(kind, c, scheme.outline, scheme.error)))
                        Spacer(Modifier.width(6.dp))
                        Text(kind.label, style = MaterialTheme.typography.bodySmall, color = scheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------
// Not finished yet / failed / loading
// ---------------------------------------------------------------

@Composable
private fun Working(summary: SessionSummary, error: String?) {
    Column(
        Modifier.fillMaxSize().padding(horizontal = Space.gutter).testTag("working"),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Box(contentAlignment = Alignment.Center) {
            CircularProgressIndicator(
                progress = { summary.progress.toFloat().coerceIn(0.02f, 1f) },
                modifier = Modifier.size(96.dp),
                strokeWidth = 6.dp,
                trackColor = MaterialTheme.colorScheme.surfaceContainerHighest,
                gapSize = 0.dp,
            )
            Text("${(summary.progress * 100).roundToInt()}%", style = MaterialTheme.typography.titleLarge)
        }
        Spacer(Modifier.height(Space.xl))
        Text(statusLabel(summary.status), style = MaterialTheme.typography.headlineSmall, modifier = Modifier.semantics { heading() })
        val wait = summary.queueWaitSeconds
        if (wait != null && wait > 0) {
            Spacer(Modifier.height(Space.xs))
            Text("Waiting about ${jsRound(wait)} seconds for capacity.", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Spacer(Modifier.height(Space.l))
        Text(
            "This screen updates on its own. You can leave and come back to it later.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.widthIn(max = 360.dp),
            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
        )
        if (error != null) {
            Spacer(Modifier.height(Space.l))
            InlineMessage(error)
        }
    }
}

@Composable
private fun Failed(summary: SessionSummary, onRecordAgain: () -> Unit) {
    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.Center) {
        EmptyState(
            icon = Icons.Warning,
            title = "Analysis failed",
            body = (summary.errorMessage ?: "Something went wrong while analysing this recording.") +
                " If it keeps failing on the same recording, the audio may be too quiet or too short to transcribe.",
            action = { Button(onClick = onRecordAgain, modifier = Modifier.heightIn(min = Space.touch)) { Text("Record again") } },
        )
    }
}

@Composable
private fun ReportSkeleton() {
    Column(Modifier.fillMaxSize().padding(Space.gutter).semantics { contentDescription = "Loading" }, verticalArrangement = Arrangement.spacedBy(Space.l)) {
        Box(Modifier.fillMaxWidth().height(48.dp).skeleton())
        repeat(3) { Box(Modifier.fillMaxWidth().height(120.dp).skeleton(MaterialTheme.shapes.medium)) }
    }
}

// ---------------------------------------------------------------
// Sheets: sharing, PDF, info
// ---------------------------------------------------------------

@Composable
private fun SheetTitle(text: String) {
    Text(text, style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(horizontal = Space.xl, vertical = Space.s).semantics { heading() })
}

@Composable
private fun SheetRow(label: String, icon: androidx.compose.ui.graphics.vector.ImageVector, onClick: () -> Unit, enabled: Boolean = true, danger: Boolean = false, trailing: String? = null, tag: String? = null) {
    val tint = if (danger) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface
    ListItem(
        headlineContent = { Text(label, color = tint) },
        leadingContent = { Icon(icon, contentDescription = null, tint = if (danger) tint else MaterialTheme.colorScheme.onSurfaceVariant) },
        trailingContent = trailing?.let { { Text(it, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary) } },
        colors = ListItemDefaults.colors(containerColor = Color.Transparent),
        modifier = Modifier
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = Space.s)
            .graphicsLayer { alpha = if (enabled) 1f else 0.5f }
            .let { if (tag != null) it.testTag(tag) else it },
    )
}

/** components/ShareSection.tsx, as a bottom sheet: same behaviour, same words. */
@Composable
private fun ShareSheet(state: SessionUiState, vm: SessionViewModel, onDismiss: () -> Unit) {
    val context = LocalContext.current
    val clipboard = LocalClipboard.current
    val haptics = LocalHapticFeedback.current
    val scope = rememberCoroutineScope()
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(Modifier.fillMaxWidth().padding(bottom = Space.l).testTag("share-section")) {
            AnimatedVisibility(state.shareBusy, enter = expandVertically(), exit = shrinkVertically()) {
                LinearProgressIndicator(Modifier.fillMaxWidth().padding(horizontal = Space.xl))
            }
            SheetTitle("Share this report")
            when (val share = state.share) {
                ShareUi.Loading -> Box(Modifier.fillMaxWidth().padding(Space.xl), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                ShareUi.Private -> {
                    Text("Only you can see this report.", style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = Space.xl))
                    Spacer(Modifier.height(Space.l))
                    Button(
                        onClick = {
                            haptics.performHapticFeedback(HapticFeedbackType.Confirm)
                            vm.createShareLink()
                        },
                        enabled = !state.shareBusy,
                        modifier = Modifier.fillMaxWidth().padding(horizontal = Space.xl).heightIn(min = 52.dp).testTag("create-share"),
                    ) {
                        Icon(Icons.Link, contentDescription = null)
                        Spacer(Modifier.width(Space.s))
                        Text("Create share link")
                    }
                }
                is ShareUi.Shared -> {
                    if (share.link != null) {
                        Text("Anyone with this link can view this report", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = Space.xl))
                        Spacer(Modifier.height(Space.s))
                        SelectionContainer {
                            Text(
                                share.link,
                                style = MaterialTheme.typography.bodyMedium,
                                modifier = Modifier
                                    .padding(horizontal = Space.xl)
                                    .fillMaxWidth()
                                    .clip(MaterialTheme.shapes.small)
                                    .background(MaterialTheme.colorScheme.surfaceContainerHighest)
                                    .padding(Space.m)
                                    .testTag("share-link"),
                            )
                        }
                        Spacer(Modifier.height(Space.s))
                        SheetRow(
                            if (state.copied) "Copied" else "Copy link",
                            if (state.copied) Icons.Check else Icons.Copy,
                            {
                                haptics.performHapticFeedback(HapticFeedbackType.Confirm)
                                scope.launch { clipboard.setClipEntry(ClipEntry(ClipData.newPlainText("Debate Coach report", share.link))) }
                                vm.markCopied()
                            },
                            enabled = !state.shareBusy,
                        )
                        SheetRow("Share via…", Icons.Share, {
                            val send = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, share.link)
                            context.startActivity(Intent.createChooser(send, "Share the report link"))
                        })
                        SheetRow("Open in browser", Icons.OpenInNew, { openUrl(context, share.link) })
                    } else {
                        Text(
                            "Sharing is on. For security, a link is only shown when it's created. To copy it again, create a new link; the current one will stop working.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(horizontal = Space.xl),
                        )
                        Spacer(Modifier.height(Space.s))
                    }
                    SheetRow("Create new link", Icons.Refresh, vm::createShareLink, enabled = !state.shareBusy, tag = "new-share")
                    SheetRow("Stop sharing", Icons.LinkOff, vm::stopSharing, enabled = !state.shareBusy, danger = true, tag = "stop-share")
                    Text(
                        "Creating a new link or stopping sharing turns the old link off straight away.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(horizontal = Space.xl, vertical = Space.s),
                    )
                }
            }
            state.shareError?.let {
                Spacer(Modifier.height(Space.s))
                InlineMessage(it, tone = Tone.CRITICAL, modifier = Modifier.padding(horizontal = Space.xl))
            }
        }
    }
}

/** Export as PDF: prepares the A4 PDF, then offers Share or Save to device. */
@Composable
private fun PdfSheet(report: SessionReport, onDismiss: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var file by remember { mutableStateOf<File?>(null) }
    var failed by remember { mutableStateOf(false) }
    LaunchedEffect(report.id) {
        val made = withContext(Dispatchers.Default) { runCatching { ReportPdf.write(context, report) }.getOrNull() }
        if (made == null) failed = true else file = made
    }
    val saveLauncher = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/pdf")) { uri ->
        val f = file
        if (uri != null && f != null) {
            scope.launch(Dispatchers.IO) {
                runCatching { context.contentResolver.openOutputStream(uri)?.use { out -> f.inputStream().use { it.copyTo(out) } } }
            }
            onDismiss()
        }
    }
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.fillMaxWidth().padding(bottom = Space.l).testTag("pdf-sheet")) {
            val ready = file
            when {
                failed -> {
                    SheetTitle("Export as PDF")
                    InlineMessage("Could not create the PDF. Try again.", tone = Tone.CRITICAL, modifier = Modifier.padding(horizontal = Space.xl))
                }
                ready == null -> {
                    SheetTitle("Preparing PDF")
                    LinearProgressIndicator(Modifier.fillMaxWidth().padding(horizontal = Space.xl, vertical = Space.l))
                }
                else -> {
                    SheetTitle("Your PDF is ready")
                    Text("An A4 PDF of this report. Share it, or save it to your device.", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = Space.xl))
                    Spacer(Modifier.height(Space.s))
                    SheetRow("Share", Icons.Share, {
                        val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", ready)
                        val send = Intent(Intent.ACTION_SEND).setType("application/pdf").putExtra(Intent.EXTRA_STREAM, uri)
                            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                        context.startActivity(Intent.createChooser(send, "Share the report"))
                        onDismiss()
                    })
                    SheetRow("Save to device", Icons.Download, { saveLauncher.launch(ready.name) })
                }
            }
        }
    }
}

@Composable
private fun InfoSheet(title: String, body: String, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.fillMaxWidth().padding(bottom = Space.xl)) {
            SheetTitle(title)
            Text(body, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(horizontal = Space.xl))
        }
    }
}
