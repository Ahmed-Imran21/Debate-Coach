package com.debatecoach.app.feature.report

import android.content.ClipData
import android.content.Intent
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.ClipEntry
import androidx.compose.ui.platform.LocalClipboard
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.rememberTextMeasurer
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
import com.debatecoach.app.navigation.openUrl
import com.debatecoach.app.ui.components.Alert
import com.debatecoach.app.ui.components.AudioPlayer
import com.debatecoach.app.ui.components.AudioPlayerController
import com.debatecoach.app.ui.components.ButtonRow
import com.debatecoach.app.ui.components.ChipRow
import com.debatecoach.app.ui.components.Divider
import com.debatecoach.app.ui.components.FilterChip
import com.debatecoach.app.ui.components.Icons
import com.debatecoach.app.ui.components.Lede
import com.debatecoach.app.ui.components.Loading
import com.debatecoach.app.ui.components.Note
import com.debatecoach.app.ui.components.PageTitle
import com.debatecoach.app.ui.components.PrimaryButton
import com.debatecoach.app.ui.components.QuietButton
import com.debatecoach.app.ui.components.SectionTitle
import com.debatecoach.app.ui.components.StateLabel
import com.debatecoach.app.ui.components.ThinProgress
import com.debatecoach.app.ui.components.Tone
import com.debatecoach.app.ui.components.appViewModel
import com.debatecoach.app.ui.theme.Dc
import com.debatecoach.app.ui.theme.Sans
import com.debatecoach.app.ui.theme.Serif
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun SessionScreen(container: AppContainer, sessionId: String, onBack: () -> Unit) {
    val vm = appViewModel(key = "session-$sessionId") { SessionViewModel(container.backend, sessionId, BuildConfig.WEBSITE_URL) }
    SessionContent(vm, onBack)
}

@Composable
fun SessionContent(vm: SessionViewModel, onBack: () -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    val c = Dc.colors
    LifecycleStartEffect(vm) {
        vm.startPolling()
        onStopOrDispose { vm.stopPolling() }
    }

    Scaffold(
        containerColor = c.paper,
        topBar = {
            TopAppBar(
                title = { Text("Report", style = MaterialTheme.typography.titleLarge) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.Back, contentDescription = "Back to sessions") } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = c.paper),
            )
        },
    ) { padding ->
        val report = state.report
        val summary = state.summary
        // One player for "Listen back" and every key moment's "Play from here".
        val player = remember { AudioPlayerController() }
        LazyColumn(
            Modifier.fillMaxSize().padding(padding).testTag("session-screen"),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(start = 20.dp, end = 20.dp, top = 8.dp, bottom = 48.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            state.error?.let { item { Alert(it) } }
            when {
                report != null -> reportItems(report, state, vm, player)
                summary == null && state.error == null -> item { Loading() }
                summary != null && summary.status == "failed" -> item { Failed(summary) }
                summary != null -> item { Working(summary) }
            }
        }
    }
}

@Composable
private fun Working(summary: SessionSummary) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.testTag("working")) {
        PageTitle(summary.title?.takeIf { it.isNotEmpty() } ?: "Analysing your speech")
        val wait = summary.queueWaitSeconds
        Lede("${statusLabel(summary.status)}." + if (wait != null && wait > 0) " Waiting about ${jsRound(wait)} seconds for capacity." else "")
        ThinProgress(summary.progress.toFloat(), Modifier.widthIn(max = 540.dp))
        Note("This screen updates on its own. You can leave and come back to it later.")
    }
}

@Composable
private fun Failed(summary: SessionSummary) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        PageTitle("Analysis failed")
        Alert(summary.errorMessage ?: "Something went wrong while analysing this recording.")
        Note("Record the speech again from the practice screen. If it keeps failing on the same recording, the audio may be too quiet or too short to transcribe.")
    }
}

private fun LazyListScope.reportItems(report: SessionReport, state: SessionUiState, vm: SessionViewModel, player: AudioPlayerController) {
    item { ReportHeader(report) }
    item { ShareSection(state, vm) }
    item { FiguresGrid(figuresFor(report)) }
    // The timeline and audio player are the owner's only, as on the web.
    val duration = trackDuration(report)
    if (duration > 0) item { SpeechTrack(duration, marksFor(report), "Where each finding landed") }
    report.audioUrl?.let { url ->
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                SectionTitle("Listen back")
                AudioPlayer(Uri.parse(url), controller = player)
            }
        }
    }
    item { VisualDelivery(report) }
    item { KeyMoments(report, onSeek = if (report.audioUrl != null) { s -> player.seekAndPlay(maxOf(0.0, s - 1)) } else null) }
    item { ScoresSection(report) }
    item { FindingsHeader(report.feedback, state.filter, vm::setFilter) }
    val findings = visibleFindings(report.feedback, state.filter)
    items(findings.size, key = { "finding-$it-${state.filter}" }) { i -> Finding(findings[i]) }
}

@Composable
private fun ReportHeader(report: SessionReport) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var exported by remember { mutableStateOf<File?>(null) }
    var exporting by remember { mutableStateOf(false) }
    var exportError by remember { mutableStateOf<String?>(null) }
    val recorded = formatRecordedLong(report.createdAt)

    val saveLauncher = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/pdf")) { uri ->
        val file = exported
        if (uri != null && file != null) {
            scope.launch(Dispatchers.IO) {
                runCatching { context.contentResolver.openOutputStream(uri)?.use { out -> file.inputStream().use { it.copyTo(out) } } }
            }
        }
        exported = null
    }

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        PageTitle(report.title?.takeIf { it.isNotEmpty() } ?: "Session of $recorded")
        val lines = buildList {
            add("Recorded $recorded")
            report.motion?.let { add("Motion: ${it.description}") }
            motionFallbackNote(report.motion != null, report.motionNotApplied)?.let { add(it) }
        }
        Note(lines.joinToString("\n"), Modifier.testTag("report-meta"))
        exportError?.let { Alert(it, quiet = true) }
        QuietButton(
            if (exporting) "Preparing PDF." else "Export as PDF",
            {
                exporting = true
                exportError = null
                scope.launch {
                    val file = withContext(Dispatchers.Default) { runCatching { ReportPdf.write(context, report) }.getOrNull() }
                    exporting = false
                    if (file == null) exportError = "Could not create the PDF. Try again." else exported = file
                }
            },
            enabled = !exporting,
            modifier = Modifier.testTag("export-pdf"),
        )
    }

    exported?.let { file ->
        AlertDialog(
            onDismissRequest = { exported = null },
            title = { Text("Your PDF is ready") },
            text = { Text("An A4 PDF of this report. Share it, or save it to your device.") },
            confirmButton = {
                PrimaryButton("Share", {
                    val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
                    val send = Intent(Intent.ACTION_SEND).setType("application/pdf").putExtra(Intent.EXTRA_STREAM, uri)
                        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    context.startActivity(Intent.createChooser(send, "Share the report"))
                    exported = null
                })
            },
            dismissButton = { QuietButton("Save to device", { saveLauncher.launch(file.name) }) },
            containerColor = Dc.colors.paperRaised,
        )
    }
}

// ---------------------------------------------------------------
// Share (components/ShareSection.tsx)
// ---------------------------------------------------------------

@Composable
private fun ShareSection(state: SessionUiState, vm: SessionViewModel) {
    val context = LocalContext.current
    val clipboard = LocalClipboard.current
    val scope = rememberCoroutineScope()
    Column(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.testTag("share-section")) {
        SectionTitle("Share")
        when (val share = state.share) {
            ShareUi.Loading -> Note("Loading.")
            ShareUi.Private -> {
                Note("Only you can see this report.")
                PrimaryButton("Create share link", vm::createShareLink, enabled = !state.shareBusy, modifier = Modifier.testTag("create-share"))
            }
            is ShareUi.Shared -> {
                if (share.link != null) {
                    Text("Anyone with this link can view this report", style = MaterialTheme.typography.labelMedium, color = Dc.colors.ink)
                    SelectionContainer {
                        Text(
                            share.link,
                            style = MaterialTheme.typography.bodyMedium,
                            color = Dc.colors.ink,
                            modifier = Modifier
                                .fillMaxWidth()
                                .border(1.dp, Dc.colors.ruleStrong, MaterialTheme.shapes.small)
                                .background(Dc.colors.paperRaised)
                                .padding(12.dp)
                                .testTag("share-link"),
                        )
                    }
                    ButtonRow {
                        PrimaryButton(if (state.copied) "Copied" else "Copy link", {
                            scope.launch { clipboard.setClipEntry(ClipEntry(ClipData.newPlainText("Debate Coach report", share.link))) }
                            vm.markCopied()
                        }, enabled = !state.shareBusy)
                        QuietButton("Share", {
                            val send = Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, share.link)
                            context.startActivity(Intent.createChooser(send, "Share the report link"))
                        })
                        QuietButton("Open", { openUrl(context, share.link) })
                        QuietButton("Create new link", vm::createShareLink, enabled = !state.shareBusy)
                        QuietButton("Stop sharing", vm::stopSharing, enabled = !state.shareBusy, tone = Tone.DANGER, modifier = Modifier.testTag("stop-share"))
                    }
                } else {
                    Note("Sharing is on. For security, a link is only shown when it's created. To copy it again, create a new link; the current one will stop working.")
                    ButtonRow {
                        PrimaryButton("Create new link", vm::createShareLink, enabled = !state.shareBusy)
                        QuietButton("Stop sharing", vm::stopSharing, enabled = !state.shareBusy, tone = Tone.DANGER, modifier = Modifier.testTag("stop-share"))
                    }
                }
                Note("Creating a new link or stopping sharing turns the old link off straight away.")
            }
        }
        state.shareError?.let { Alert(it, quiet = true) }
    }
}

// ---------------------------------------------------------------
// Figures, timeline, audio, visual sections
// ---------------------------------------------------------------

@Composable
private fun FiguresGrid(figures: List<Figure>) {
    val c = Dc.colors
    BoxWithConstraints(Modifier.fillMaxWidth()) {
        val columns = if (maxWidth > 520.dp) 3 else 2
        Column(Modifier.border(1.dp, c.rule, MaterialTheme.shapes.small).background(c.rule)) {
            figures.chunked(columns).forEach { row ->
                Row(Modifier.height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(1.dp)) {
                    row.forEach { f ->
                        Column(
                            Modifier.weight(1f).fillMaxHeight().background(c.paperRaised).padding(horizontal = 14.dp, vertical = 12.dp)
                                .semantics(mergeDescendants = true) {},
                        ) {
                            Text(f.value, fontFamily = Serif, style = MaterialTheme.typography.headlineMedium, color = c.ink)
                            Text(f.label, style = MaterialTheme.typography.bodySmall, color = c.inkSoft)
                        }
                    }
                    repeat(columns - row.size) { Spacer(Modifier.weight(1f).background(c.paperRaised)) }
                }
                Spacer(Modifier.height(1.dp))
            }
        }
    }
}

private fun markColor(kind: MarkKind, c: com.debatecoach.app.ui.theme.DcColors): Color = when (kind) {
    MarkKind.PAUSE -> c.ruleStrong
    MarkKind.FILLER -> c.amber
    MarkKind.STUTTER -> c.inkFaint
    MarkKind.FALLACY -> c.brick
}

/** components/SpeechTrack.tsx: the speech as a stretch of time, each finding where it happened. */
@Composable
fun SpeechTrack(duration: Double, marks: List<Mark>, title: String) {
    val c = Dc.colors
    val measurer = rememberTextMeasurer()
    val safe = if (duration > 0) duration else 1.0
    Column(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.testTag("speech-track")) {
        Row(verticalAlignment = Alignment.Bottom) {
            Text(title, style = MaterialTheme.typography.titleSmall, color = c.ink, modifier = Modifier.weight(1f))
            Note("Length ${formatClock(safe)}")
        }
        Canvas(
            Modifier
                .fillMaxWidth()
                .height(96.dp)
                .semantics { contentDescription = "$title. ${marks.size} findings across ${formatClock(safe)}." },
        ) {
            val pad = 8.dp.toPx()
            val usable = size.width - pad * 2
            val base = 64.dp.toPx()
            fun x(t: Double) = pad + (t.coerceIn(0.0, safe) / safe).toFloat() * usable
            drawRect(c.well, Offset(pad, 28.dp.toPx()), Size(usable, 16.dp.toPx()))
            for (m in marks) {
                val left = x(m.at)
                val width = m.span?.let { maxOf(2.dp.toPx(), x(m.at + it) - left) } ?: 2.dp.toPx()
                val pause = m.kind == MarkKind.PAUSE
                drawRect(markColor(m.kind, c), Offset(left, (if (pause) 28 else 20).dp.toPx()), Size(width, (if (pause) 16 else 32).dp.toPx()))
            }
            drawLine(c.ruleStrong, Offset(pad, base), Offset(size.width - pad, base), 1.dp.toPx())
            val labelStyle = TextStyle(fontFamily = Sans, fontSize = 12.sp, color = c.inkFaint)
            for (t in trackTicks(safe)) {
                val minute = t % 60.0 == 0.0
                drawLine(c.ruleStrong, Offset(x(t), base), Offset(x(t), base + (if (minute) 8 else 4).dp.toPx()), 1.dp.toPx())
                if (minute) {
                    val text = formatClock(t)
                    val w = measurer.measure(text, labelStyle).size.width
                    val left = if (t == 0.0) x(t) else (x(t) - w / 2f).coerceAtMost(size.width - w)
                    drawText(measurer, text, Offset(left, base + 12.dp.toPx()), labelStyle)
                }
            }
        }
        val present = marks.map { it.kind }.distinct()
        if (present.isNotEmpty()) {
            ChipRow {
                present.forEach { kind ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(10.dp).background(markColor(kind, c)))
                        Spacer(Modifier.width(6.dp))
                        Text(kind.label, style = MaterialTheme.typography.bodySmall, color = c.inkSoft)
                    }
                }
            }
        }
    }
}

@Composable
private fun VisualDelivery(report: SessionReport) {
    val c = Dc.colors
    when (val section = visualSection(report)) {
        VisualSection.Hidden -> Unit
        is VisualSection.Message -> Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            SectionTitle("Visual delivery")
            Alert(section.text, quiet = true)
        }
        is VisualSection.Metrics -> Column(verticalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.testTag("visual-delivery")) {
            SectionTitle("Visual delivery")
            section.rows.forEach { row ->
                Column(verticalArrangement = Arrangement.spacedBy(2.dp), modifier = Modifier.semantics(mergeDescendants = true) {}) {
                    Text(row.label, style = MaterialTheme.typography.labelMedium, color = c.inkSoft)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(row.value, style = MaterialTheme.typography.titleSmall, color = c.ink)
                        row.confidence?.let {
                            Spacer(Modifier.width(10.dp))
                            StateLabel(it, tone = if (row.highConfidence) "done" else null)
                        }
                    }
                    Text(row.definition, style = MaterialTheme.typography.bodySmall, color = c.inkSoft)
                }
            }
            section.faceMessage?.let { Note(it) }
            section.handsMessage?.let { Note(it) }
            section.warnings.forEach { Note(it) }
            if (section.coachingFailed) Note("Coaching notes for your visual delivery couldn’t be generated for this session. The measurements above are unaffected.")
            section.sessionFeedback.forEach { (text, polarity) ->
                Marker(color = when (polarity) { "strength" -> c.pine; "improve" -> c.amber; else -> c.ruleStrong }) {
                    Text(text, style = MaterialTheme.typography.bodyMedium, color = c.inkSoft)
                }
            }
        }
    }
}

@Composable
private fun KeyMoments(report: SessionReport, onSeek: ((Double) -> Unit)?) {
    val entries = keyMoments(report)
    if (entries.isEmpty()) return
    val c = Dc.colors
    Column(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.testTag("key-moments")) {
        SectionTitle("Key moments")
        entries.forEach { e ->
            Divider()
            Marker(color = if (e.positive) c.pine else c.amber) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(e.meta, style = MaterialTheme.typography.bodySmall, color = c.inkFaint, modifier = Modifier.weight(1f))
                        if (onSeek != null) {
                            FilterChip("Play from here", false, { onSeek(e.moment.start) }, modifier = Modifier.testTag("seek-${e.key}"))
                        }
                    }
                    if (e.moment.excerptText.isNotEmpty()) Quote(e.moment.excerptText)
                    e.facts.forEach { Text("• $it", style = MaterialTheme.typography.bodyMedium, color = c.inkSoft) }
                    e.coaching?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = c.ink) }
                }
            }
        }
    }
}

// ---------------------------------------------------------------
// Scores and findings
// ---------------------------------------------------------------

@Composable
private fun ScoresSection(report: SessionReport) {
    val c = Dc.colors
    Column(verticalArrangement = Arrangement.spacedBy(0.dp), modifier = Modifier.testTag("scores")) {
        SectionTitle("Scores by category", Modifier.padding(bottom = 12.dp))
        SCORE_ORDER.forEachIndexed { i, category ->
            if (i > 0) Divider()
            val raw = report.scores[category]
            // null: not scored (rebuttal with nothing to rebut). Absent: an older report.
            val notScored = report.scores.containsKey(category) && raw == null
            Row(
                Modifier.fillMaxWidth().heightIn(min = 44.dp).padding(vertical = 8.dp).semantics(mergeDescendants = true) {
                    contentDescription = "${CATEGORY_LABEL[category]}: " + if (notScored) "Not scored: nothing to rebut" else "${jsRound(raw ?: 0.0)} out of 100"
                },
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(CATEGORY_LABEL[category].orEmpty(), style = MaterialTheme.typography.bodyMedium, color = c.ink, modifier = Modifier.width(120.dp))
                if (notScored) {
                    Note("Not scored: nothing to rebut", Modifier.weight(1f))
                } else {
                    val value = raw ?: 0.0
                    Box(Modifier.weight(1f).height(8.dp).background(c.well)) {
                        Box(Modifier.fillMaxWidth((value / 100).toFloat().coerceIn(0f, 1f)).fillMaxHeight().background(c.pine))
                    }
                    Text(jsRound(value).toString(), style = MaterialTheme.typography.bodyMedium, color = c.inkSoft, modifier = Modifier.width(44.dp).padding(start = 12.dp))
                }
            }
        }
        Note(
            "Delivery is arithmetic over the audio. The other five come from a language model reading the transcript, so treat them as a second opinion rather than a mark. Rebuttal isn't scored when there was nothing to rebut, and doesn't count toward the overall.",
            Modifier.padding(top = 12.dp),
        )
    }
}

@Composable
private fun FindingsHeader(feedback: List<FeedbackItem>, filter: String, onFilter: (String) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionTitle("Findings", Modifier.padding(top = 16.dp))
        ChipRow(label = "Filter findings") {
            FilterChip("All ${feedback.size}", filter == "all", { onFilter("all") }, modifier = Modifier.testTag("filter-all"))
            presentCategories(feedback).forEach { category ->
                FilterChip(CATEGORY_LABEL[category].orEmpty(), filter == category, { onFilter(category) }, modifier = Modifier.testTag("filter-$category"))
            }
        }
    }
}

@Composable
private fun Finding(item: FeedbackItem) {
    val c = Dc.colors
    val color = when (item.severity) {
        "high" -> c.brick
        "medium" -> c.amber
        "positive" -> c.pine
        else -> c.ruleStrong
    }
    Column(Modifier.testTag("finding")) {
        Divider()
        Marker(color, Modifier.padding(vertical = 14.dp)) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(item.title, style = MaterialTheme.typography.titleSmall, color = c.ink, modifier = Modifier.semantics { heading() })
                Text(
                    "${CATEGORY_LABEL[item.category] ?: item.category}. ${SEVERITY_LABEL[item.severity] ?: item.severity}.",
                    style = MaterialTheme.typography.bodySmall,
                    color = c.inkFaint,
                )
                Text(item.issue, style = MaterialTheme.typography.bodyMedium, color = c.inkSoft)
                item.evidence.forEach { Quote(it) }
                item.explanation?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = c.inkSoft) }
                item.recommendation?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = c.ink) }
            }
        }
    }
}

/** .finding's left severity bar. */
@Composable
private fun Marker(color: Color, modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Row(modifier.fillMaxWidth().height(IntrinsicSize.Min)) {
        Box(Modifier.width(6.dp).fillMaxHeight().background(color))
        Spacer(Modifier.width(16.dp))
        Box(Modifier.weight(1f)) { content() }
    }
}

/** .finding blockquote: an evidence quote, in the serif. */
@Composable
private fun Quote(text: String) {
    val c = Dc.colors
    Row(Modifier.height(IntrinsicSize.Min)) {
        Box(Modifier.width(1.dp).fillMaxHeight().background(c.ruleStrong))
        Spacer(Modifier.width(14.dp))
        Text(text, fontFamily = Serif, style = MaterialTheme.typography.bodyLarge, color = c.ink)
    }
}
