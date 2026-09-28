package com.debatecoach.app.feature.progress

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.debatecoach.app.core.Backend
import com.debatecoach.app.core.model.LatestProgressReport
import com.debatecoach.app.core.model.ProgressPoint
import com.debatecoach.app.core.net.ApiException
import com.debatecoach.app.core.util.formatChartDate
import com.debatecoach.app.core.util.formatRecordedShort
import com.debatecoach.app.core.util.jsRound
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
// The figures under the chart
// ---------------------------------------------------------------

data class ChartSummary(val latest: Long, val best: Long, val change: Long)

/** Latest, best and change across the plotted range; null without a chart. */
fun summarize(chart: Chart): ChartSummary? {
    if (!chart.enough) return null
    val first = jsRound(chart.points.first().score)
    val last = jsRound(chart.points.last().score)
    return ChartSummary(latest = last, best = chart.points.maxOf { jsRound(it.score) }, change = last - first)
}

/** "+6", "−4" (a real minus sign), or "0". */
fun formatChange(change: Long): String = when {
    change > 0 -> "+$change"
    change < 0 -> "−${-change}"
    else -> "0"
}

fun rangeLabel(range: String): String = RANGE_OPTIONS.firstOrNull { it.first == range }?.second ?: range
