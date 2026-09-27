package com.debatecoach.app.feature.progress

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.LifecycleStartEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.debatecoach.app.core.Backend
import com.debatecoach.app.core.model.LatestProgressReport
import com.debatecoach.app.core.model.ProgressPoint
import com.debatecoach.app.core.net.ApiException
import com.debatecoach.app.core.util.formatChartDate
import com.debatecoach.app.core.util.formatNextAvailable
import com.debatecoach.app.core.util.formatRecordedShort
import com.debatecoach.app.core.util.jsRound
import com.debatecoach.app.core.util.reportCaption
import com.debatecoach.app.ui.components.Alert
import com.debatecoach.app.ui.components.ButtonRow
import com.debatecoach.app.ui.components.ChipRow
import com.debatecoach.app.ui.components.FilterChip
import com.debatecoach.app.ui.components.Loading
import com.debatecoach.app.ui.components.Note
import com.debatecoach.app.ui.components.PrimaryButton
import com.debatecoach.app.ui.components.SectionTitle
import com.debatecoach.app.ui.theme.Dc
import com.debatecoach.app.ui.theme.Sans
import kotlin.math.hypot
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

// ---------------------------------------------------------------
// lib/progress-chart.ts
// ---------------------------------------------------------------

val METRIC_OPTIONS = listOf(
    "overall" to "All",
    "argumentation" to "Argumentation",
    "rebuttal" to "Rebuttal",
    "structure" to "Structure",
    "persuasion" to "Persuasion",
    "logic" to "Logic",
)

val RANGE_OPTIONS = listOf(
    "1d" to "Last 1 day",
    "1w" to "Last 1 week",
    "1m" to "Last 1 month",
    "5" to "Last 5 sessions",
    "10" to "Last 10 sessions",
    "15" to "Last 15 sessions",
)

val Y_TICKS = listOf(0, 25, 50, 75, 100)
const val MIN_POINTS = 2

data class PlottedPoint(val sessionId: String, val createdAt: String, val title: String?, val score: Double, val x: Float, val y: Float)

data class Chart(val enough: Boolean, val points: List<PlottedPoint>)

/**
 * buildChart(): sessions with no score are skipped, not drawn as 0;
 * points spaced evenly oldest-first; y always 0-100. x and y are
 * fractions of the plot area (0..1, y down).
 */
fun buildChart(points: List<ProgressPoint>): Chart {
    val scored = points.filter { it.score != null && it.score.isFinite() }
    if (scored.size < MIN_POINTS) return Chart(false, emptyList())
    val step = 1f / (scored.size - 1)
    return Chart(true, scored.mapIndexed { i, p ->
        val clamped = p.score!!.coerceIn(0.0, 100.0)
        PlottedPoint(p.sessionId, p.createdAt, p.title, p.score, i * step, (1 - clamped / 100).toFloat())
    })
}

fun metricLabel(metric: String) = METRIC_OPTIONS.firstOrNull { it.first == metric }?.second ?: "All"

/** The tooltip's three lines: name, date, and the score being shown. */
fun tooltipLines(point: PlottedPoint, label: String): List<String> {
    val date = formatRecordedShort(point.createdAt)
    val name = point.title?.takeIf { it.isNotEmpty() } ?: "Session of $date"
    val what = if (label == "All") "Overall" else label
    return listOf(name, date, "$what: ${jsRound(point.score)}")
}

/** The chart's text alternative, for TalkBack. */
fun describeChart(chart: Chart, label: String): String {
    if (!chart.enough) return ""
    val first = chart.points.first()
    val last = chart.points.last()
    val what = if (label == "All") "Overall" else label
    return "$what score over ${chart.points.size} sessions, from ${jsRound(first.score)} on ${formatChartDate(first.createdAt)} " +
        "to ${jsRound(last.score)} on ${formatChartDate(last.createdAt)}."
}

// ---------------------------------------------------------------
// ViewModel
// ---------------------------------------------------------------

val SESSION_COUNT_OPTIONS = listOf(3, 5, 7)

data class ProgressState(
    val metric: String = "overall",
    val range: String = "10",
    val points: List<ProgressPoint>? = null,
    val chartError: String? = null,
    val active: Int? = null,
    val latest: LatestProgressReport? = null,
    val latestError: String? = null,
    val count: Int = 5,
    val generating: Boolean = false,
    val generateError: String? = null,
    val refreshing: Boolean = false,
)

class ProgressViewModel(private val backend: Backend) : ViewModel() {
    private val _state = MutableStateFlow(ProgressState())
    val state: StateFlow<ProgressState> = _state.asStateFlow()
    private var chartJob: Job? = null

    fun setMetric(metric: String) {
        _state.update { it.copy(metric = metric) }
        loadChart()
    }

    fun setRange(range: String) {
        _state.update { it.copy(range = range) }
        loadChart()
    }

    /**
     * A slower response for an earlier selection never overwrites the current one.
     * [quiet] keeps the current chart on screen while it reloads (a refresh, not a new selection).
     */
    fun loadChart(quiet: Boolean = false): Job {
        chartJob?.cancel()
        if (!quiet) _state.update { it.copy(points = null, chartError = null, active = null) }
        val (metric, range) = _state.value.let { it.metric to it.range }
        return viewModelScope.launch {
            try {
                val rows = backend.progress(metric, range)
                _state.update { it.copy(points = rows) }
            } catch (error: Exception) {
                if (error is kotlinx.coroutines.CancellationException) throw error
                if (!(error is ApiException && error.status == 401)) _state.update { it.copy(chartError = "Could not load your progress.") }
            }
        }.also { chartJob = it }
    }

    fun select(index: Int?) = _state.update { it.copy(active = index) }

    fun loadLatest(): Job =
        viewModelScope.launch {
            try {
                val latest = backend.latestProgressReport()
                _state.update { it.copy(latest = latest, latestError = null) }
            } catch (error: Exception) {
                if (!(error is ApiException && error.status == 401)) _state.update { it.copy(latestError = "Could not load your progress report.") }
            }
        }

    /** Pull to refresh: picks up what the website changed (a new report, a deleted session). */
    fun refresh() {
        if (_state.value.refreshing) return
        _state.update { it.copy(refreshing = true) }
        viewModelScope.launch {
            val chart = loadChart(quiet = true)
            loadLatest().join()
            chart.join()
            _state.update { it.copy(refreshing = false) }
        }
    }

    fun setCount(count: Int) = _state.update { it.copy(count = count) }

    fun generate() {
        if (_state.value.generating) return
        _state.update { it.copy(generating = true, generateError = null) }
        viewModelScope.launch {
            try {
                backend.createProgressReport(_state.value.count)
            } catch (error: Exception) {
                // Already used today (the website, say): the reload below
                // shows today's report and the next time, in local time.
                val message = when {
                    error is ApiException && error.status == 429 -> null
                    error is ApiException && error.status == 401 -> null
                    error is ApiException -> error.message
                    else -> "Could not generate the report. Try again shortly."
                }
                _state.update { it.copy(generateError = message) }
            }
            try {
                val latest = backend.latestProgressReport()
                _state.update { it.copy(latest = latest, latestError = null) }
            } catch (_: Exception) {
            }
            _state.update { it.copy(generating = false) }
        }
    }
}

// ---------------------------------------------------------------
// UI
// ---------------------------------------------------------------

@Composable
fun ProgressTab(vm: ProgressViewModel, completedCount: Int, contentPadding: PaddingValues) {
    val state by vm.state.collectAsStateWithLifecycle()

    // A new finished session (completedCount changes) refetches both,
    // as the website's refreshKey does; so does coming back to the app.
    LifecycleStartEffect(completedCount) {
        vm.loadChart(quiet = vm.state.value.points != null)
        vm.loadLatest()
        onStopOrDispose {}
    }

    PullToRefreshBox(isRefreshing = state.refreshing, onRefresh = vm::refresh, modifier = Modifier.fillMaxSize()) {
        LazyColumn(
            Modifier.fillMaxSize().testTag("progress-tab"),
            contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 8.dp, bottom = contentPadding.calculateBottomPadding() + 32.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            item { SectionTitle("Your progress") }
            item {
                ChipRow(label = "Score type") {
                    METRIC_OPTIONS.forEach { (value, label) -> FilterChip(label, state.metric == value, { vm.setMetric(value) }) }
                }
            }
            item {
                ChipRow(label = "Range") {
                    RANGE_OPTIONS.forEach { (value, label) -> FilterChip(label, state.range == value, { vm.setRange(value) }) }
                }
            }
            item {
                val points = state.points
                when {
                    state.chartError != null -> Alert(state.chartError!!, quiet = true)
                    points == null -> Loading()
                    else -> {
                        val chart = buildChart(points)
                        if (!chart.enough) Note("Not enough sessions in this range yet.")
                        else ProgressChartView(chart, metricLabel(state.metric), state.active, vm::select)
                    }
                }
            }
            item { SectionTitle("Progress report", Modifier.padding(top = 16.dp)) }
            item { ProgressReportPanel(state, completedCount, vm) }
        }
    }
}

@Composable
private fun ProgressChartView(chart: Chart, label: String, active: Int?, onSelect: (Int?) -> Unit) {
    val c = Dc.colors
    val measurer = rememberTextMeasurer()
    val density = LocalDensity.current
    BoxWithConstraints(
        Modifier
            .fillMaxWidth()
            .height(260.dp)
            .semantics { contentDescription = describeChart(chart, label) }
            .testTag("progress-chart"),
    ) {
        val widthPx = with(density) { maxWidth.toPx() }
        val heightPx = with(density) { maxHeight.toPx() }
        val left = with(density) { 36.dp.toPx() }
        val right = with(density) { 12.dp.toPx() }
        val top = with(density) { 12.dp.toPx() }
        val bottom = with(density) { 28.dp.toPx() }
        val innerW = widthPx - left - right
        val innerH = heightPx - top - bottom
        fun px(p: PlottedPoint) = Offset(left + p.x * innerW, top + p.y * innerH)

        Canvas(
            Modifier.fillMaxSize().pointerInput(chart) {
                detectTapGestures { tap ->
                    // Tapping anywhere that isn't a dot hides the tooltip.
                    val hit = chart.points.indexOfFirst { hypot(px(it).x - tap.x, px(it).y - tap.y) <= 24.dp.toPx() }
                    onSelect(if (hit >= 0) hit else null)
                }
            },
        ) {
            val labelStyle = TextStyle(fontFamily = Sans, fontSize = 12.sp, color = c.inkFaint)
            for (tick in Y_TICKS) {
                val y = top + (1 - tick / 100f) * innerH
                drawLine(c.rule, Offset(left, y), Offset(widthPx - right, y), strokeWidth = 1.dp.toPx())
                drawLabel(measurer, tick.toString(), Offset(0f, y - 8.sp.toPx()), labelStyle)
            }
            val path = Path()
            chart.points.forEachIndexed { i, p ->
                val o = px(p)
                if (i == 0) path.moveTo(o.x, o.y) else path.lineTo(o.x, o.y)
            }
            drawPath(path, c.pine, style = Stroke(width = 2.dp.toPx()))
            chart.points.forEachIndexed { i, p ->
                drawCircle(c.pine, radius = (if (i == active) 5.5f else 3.5f).dp.toPx(), center = px(p))
            }
            drawLabel(measurer, formatChartDate(chart.points.first().createdAt), Offset(left, heightPx - bottom + 6.dp.toPx()), labelStyle)
            val lastLabel = formatChartDate(chart.points.last().createdAt)
            val w = measurer.measure(lastLabel, labelStyle).size.width
            drawLabel(measurer, lastLabel, Offset(widthPx - right - w, heightPx - bottom + 6.dp.toPx()), labelStyle)
        }

        // One touch/TalkBack target per dot, 48dp, over the drawn dot.
        chart.points.forEachIndexed { i, p ->
            val o = px(p)
            val half = with(density) { 24.dp.toPx() }
            Box(
                Modifier
                    .offset { IntOffset((o.x - half).toInt(), (o.y - half).toInt()) }
                    .size(48.dp)
                    .semantics {
                        role = Role.Button
                        contentDescription = tooltipLines(p, label).joinToString(", ")
                    }
                    .clickable { onSelect(if (active == i) null else i) }
                    .testTag("progress-point-$i"),
            )
        }

        val point = active?.let { chart.points.getOrNull(it) }
        if (point != null) {
            val o = px(point)
            val lines = tooltipLines(point, label)
            val tooltipW = with(density) { 200.dp.toPx() }
            val tooltipH = with(density) { 74.dp.toPx() }
            val gap = with(density) { 10.dp.toPx() }
            val openLeft = o.x + gap + tooltipW > widthPx
            val openBelow = o.y - gap - tooltipH < 0
            val x = (if (openLeft) o.x - gap - tooltipW else o.x + gap).coerceIn(0f, maxOf(0f, widthPx - tooltipW))
            val y = maxOf(0f, if (openBelow) o.y + gap else o.y - gap - tooltipH)
            Column(
                Modifier
                    .offset { IntOffset(x.toInt(), y.toInt()) }
                    .widthIn(max = 200.dp)
                    .background(c.paperRaised, MaterialTheme.shapes.small)
                    .border(1.dp, c.ruleStrong, MaterialTheme.shapes.small)
                    .padding(horizontal = 10.dp, vertical = 8.dp)
                    .testTag("progress-tooltip"),
            ) {
                Text(lines[0], style = MaterialTheme.typography.labelMedium, color = c.ink)
                Text(lines[1], style = MaterialTheme.typography.bodySmall, color = c.inkSoft)
                Text(lines[2], style = MaterialTheme.typography.bodySmall, color = c.ink)
            }
        }
    }
}

private fun androidx.compose.ui.graphics.drawscope.DrawScope.drawLabel(measurer: TextMeasurer, text: String, at: Offset, style: TextStyle) {
    drawText(measurer, text, topLeft = at, style = style)
}

@Composable
private fun ProgressReportPanel(state: ProgressState, completedCount: Int, vm: ProgressViewModel) {
    val latest = state.latest
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        when {
            state.latestError != null -> Alert(state.latestError, quiet = true)
            latest == null -> Loading()
            else -> {
                val enough = completedCount >= 2
                if (latest.canGenerate) {
                    Note("Compare your recent sessions and see what is improving and what still needs work. One report per day.")
                    ChipRow(label = "Sessions to compare") {
                        SESSION_COUNT_OPTIONS.forEach { n ->
                            FilterChip("Last $n sessions", state.count == n, { vm.setCount(n) }, enabled = !state.generating)
                        }
                    }
                    ButtonRow {
                        PrimaryButton(
                            if (state.generating) "Writing your report." else "Generate progress report",
                            onClick = vm::generate,
                            enabled = !state.generating && enough,
                            haptic = true,
                            modifier = Modifier.testTag("generate-report"),
                        )
                    }
                    if (!enough) Note("A report compares sessions, so it needs at least 2 completed ones.")
                } else if (latest.nextAvailableAt != null) {
                    Note("You have used today's progress report. The next one is available from ${formatNextAvailable(latest.nextAvailableAt)}.")
                }
                state.generateError?.let { Alert(it, quiet = true) }
                latest.report?.let { report ->
                    Note(reportCaption(report.sessionCountUsed, report.reportDate))
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        report.bullets.forEach { bullet ->
                            Text("•  $bullet", style = MaterialTheme.typography.bodyLarge, color = Dc.colors.ink)
                        }
                    }
                }
            }
        }
    }
}
