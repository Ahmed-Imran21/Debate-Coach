package com.debatecoach.app.feature.progress

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.LifecycleStartEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.debatecoach.app.core.util.formatChartDate
import com.debatecoach.app.feature.sessions.MenuAction
import com.debatecoach.app.feature.sessions.OverflowMenu
import com.debatecoach.app.ui.components.DcCard
import com.debatecoach.app.ui.components.DropdownChip
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import com.debatecoach.app.ui.components.EmptyState
import com.debatecoach.app.ui.components.Icons
import com.debatecoach.app.ui.components.InlineMessage
import com.debatecoach.app.ui.components.StatTile
import com.debatecoach.app.ui.components.TopLevelBar
import com.debatecoach.app.ui.components.skeleton
import com.debatecoach.app.ui.theme.Motion
import com.debatecoach.app.ui.theme.Sans
import com.debatecoach.app.ui.theme.Space
import kotlin.math.hypot

/** The progress graph, its own destination: the chart is the hero. */
@Composable
fun ProgressScreen(vm: ProgressViewModel, completedCount: Int, onOpenSession: (String) -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    val scroll = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()

    // A newly finished session refetches (the website's refreshKey), and
    // so does coming back to the app.
    LifecycleStartEffect(completedCount) {
        vm.loadChart(quiet = vm.state.value.points != null)
        onStopOrDispose {}
    }

    Scaffold(
        modifier = Modifier.nestedScroll(scroll.nestedScrollConnection),
        containerColor = MaterialTheme.colorScheme.surface,
        topBar = {
            TopLevelBar("Progress", scroll) {
                OverflowMenu(listOf(MenuAction("Refresh", Icons.Refresh, vm::refresh)))
            }
        },
    ) { padding ->
        PullToRefreshBox(
            isRefreshing = state.refreshing,
            onRefresh = vm::refresh,
            modifier = Modifier.fillMaxSize().padding(top = padding.calculateTopPadding()),
        ) {
            val gutter = Space.gutter
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.TopCenter) {
                LazyColumn(
                    Modifier.widthIn(max = Space.readingWidth).fillMaxSize().testTag("progress-tab"),
                    contentPadding = PaddingValues(start = gutter, end = gutter, top = Space.s, bottom = padding.calculateBottomPadding() + Space.xxl),
                    verticalArrangement = Arrangement.spacedBy(Space.l),
                ) {
                    item(key = "filters") { FilterBar(state.metric, state.range, vm::setMetric, vm::setRange) }
                    item(key = "chart") {
                        val points = state.points
                        when {
                            state.chartError != null -> InlineMessage(state.chartError!!, actionLabel = "Retry", onAction = { vm.loadChart() })
                            points == null -> ChartSkeleton()
                            else -> {
                                val chart = buildChart(points)
                                if (!chart.enough) {
                                    DcCard {
                                        EmptyState(
                                            icon = Icons.Progress,
                                            title = "Not enough sessions in this range yet.",
                                            body = "The graph needs at least two scored sessions. Try a longer range, or record another speech.",
                                        )
                                    }
                                } else {
                                    ChartCard(chart, metricLabel(state.metric), rangeLabel(state.range), state.active, vm::select, onOpenSession)
                                }
                            }
                        }
                    }
                    val summary = state.points?.let { summarize(buildChart(it)) }
                    if (summary != null && state.chartError == null) {
                        item(key = "summary") {
                            Row(horizontalArrangement = Arrangement.spacedBy(Space.s)) {
                                StatTile(summary.latest.toString(), "Latest", Modifier.weight(1f))
                                StatTile(summary.best.toString(), "Best", Modifier.weight(1f))
                                StatTile(formatChange(summary.change), "Change", Modifier.weight(1f))
                            }
                        }
                    }
                }
            }
        }
    }
}

/** Score type and range: a compact bar of two dropdown chips (Material's filter chip with a menu). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun FilterBar(metric: String, range: String, onMetric: (String) -> Unit, onRange: (String) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(Space.s), verticalArrangement = Arrangement.spacedBy(Space.s)) {
        DropdownChip("Score type", METRIC_OPTIONS, metric, onMetric, display = { if (it == "overall") "All scores" else metricLabel(it) }, tag = "metric")
        DropdownChip("Range", RANGE_OPTIONS, range, onRange, tag = "range")
    }
}

@Composable
private fun ChartSkeleton() {
    Box(Modifier.fillMaxWidth().height(chartHeight() + 72.dp).skeleton(MaterialTheme.shapes.medium).semantics { contentDescription = "Loading" })
}

/** Tall enough to read on a phone, never taller than a good share of the screen. */
@Composable
private fun chartHeight() = (LocalConfiguration.current.screenHeightDp * 0.38f).dp.coerceIn(220.dp, 360.dp)

@Composable
private fun ChartCard(chart: Chart, label: String, range: String, active: Int?, onSelect: (Int?) -> Unit, onOpen: (String) -> Unit) {
    val what = if (label == "All") "Overall" else label
    DcCard(padding = PaddingValues(start = Space.l, end = Space.l, top = Space.l, bottom = Space.m)) {
        Text("$what score", style = MaterialTheme.typography.titleMedium)
        Text(range, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(Space.m))
        ProgressChart(chart, label, active, onSelect, onOpen)
        Spacer(Modifier.height(Space.xs))
        Text(
            if (active == null) "Tap a point for details." else "Tap the card to open that session.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun ProgressChart(chart: Chart, label: String, active: Int?, onSelect: (Int?) -> Unit, onOpen: (String) -> Unit) {
    val scheme = MaterialTheme.colorScheme
    val measurer = rememberTextMeasurer()
    val density = LocalDensity.current
    val haptics = LocalHapticFeedback.current
    val reveal = remember(chart) { Animatable(0f) }
    LaunchedEffect(chart) { reveal.animateTo(1f, tween(700, easing = Motion.EmphasizedDecelerate)) }

    BoxWithConstraints(
        Modifier
            .fillMaxWidth()
            .height(chartHeight())
            .semantics { contentDescription = describeChart(chart, label) }
            .testTag("progress-chart"),
    ) {
        val widthPx = with(density) { maxWidth.toPx() }
        val heightPx = with(density) { maxHeight.toPx() }
        val left = with(density) { 32.dp.toPx() }
        val right = with(density) { 16.dp.toPx() }
        val top = with(density) { 10.dp.toPx() }
        val bottom = with(density) { 26.dp.toPx() }
        val innerW = widthPx - left - right
        val innerH = heightPx - top - bottom
        fun px(p: PlottedPoint) = Offset(left + p.x * innerW, top + p.y * innerH)

        fun select(i: Int?) {
            if (i != null && i == active) {
                onOpen(chart.points[i].sessionId)
            } else {
                if (i != null) haptics.performHapticFeedback(HapticFeedbackType.SegmentTick)
                onSelect(i)
            }
        }

        Canvas(
            Modifier.fillMaxSize().pointerInput(chart, active) {
                detectTapGestures { tap ->
                    // Tapping anywhere that isn't a point hides the card.
                    val hit = chart.points.indexOfFirst { hypot(px(it).x - tap.x, px(it).y - tap.y) <= 24.dp.toPx() }
                    select(if (hit >= 0) hit else null)
                }
            },
        ) {
            val labelStyle = TextStyle(fontFamily = Sans, fontSize = 11.sp, color = scheme.onSurfaceVariant)
            for (tick in Y_TICKS) {
                val y = top + (1 - tick / 100f) * innerH
                drawLine(
                    scheme.outlineVariant,
                    Offset(left, y),
                    Offset(widthPx - right, y),
                    strokeWidth = 1.dp.toPx(),
                    pathEffect = if (tick == 0) null else PathEffect.dashPathEffect(floatArrayOf(4.dp.toPx(), 4.dp.toPx())),
                )
                drawText(measurer, tick.toString(), Offset(0f, y - 7.sp.toPx()), labelStyle)
            }

            val line = Path()
            chart.points.forEachIndexed { i, p ->
                val o = px(p)
                if (i == 0) line.moveTo(o.x, o.y) else line.lineTo(o.x, o.y)
            }
            val area = Path().apply {
                addPath(line)
                lineTo(px(chart.points.last()).x, top + innerH)
                lineTo(px(chart.points.first()).x, top + innerH)
                close()
            }
            clipRect(right = left + innerW * reveal.value + 8.dp.toPx()) {
                drawPath(area, Brush.verticalGradient(listOf(scheme.primary.copy(alpha = 0.18f), scheme.primary.copy(alpha = 0f)), startY = top, endY = top + innerH))
                drawPath(line, scheme.primary, style = Stroke(width = 2.5.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
                chart.points.forEachIndexed { i, p ->
                    val o = px(p)
                    if (i == active) {
                        drawLine(scheme.outline, Offset(o.x, top), Offset(o.x, top + innerH), 1.dp.toPx())
                        drawCircle(scheme.primary.copy(alpha = 0.18f), radius = 12.dp.toPx(), center = o)
                        drawCircle(scheme.primary, radius = 6.dp.toPx(), center = o)
                        drawCircle(scheme.surfaceContainerLowest, radius = 2.5.dp.toPx(), center = o)
                    } else {
                        drawCircle(scheme.surfaceContainerLowest, radius = 5.dp.toPx(), center = o)
                        drawCircle(scheme.primary, radius = 3.5.dp.toPx(), center = o)
                    }
                }
            }
            val firstLabel = formatChartDate(chart.points.first().createdAt)
            drawText(measurer, firstLabel, Offset(left, heightPx - bottom + 8.dp.toPx()), labelStyle)
            val lastLabel = formatChartDate(chart.points.last().createdAt)
            val w = measurer.measure(lastLabel, labelStyle).size.width
            drawText(measurer, lastLabel, Offset(widthPx - right - w, heightPx - bottom + 8.dp.toPx()), labelStyle)
        }

        // One 48dp touch and TalkBack target over each point.
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
                        customActions = listOf(CustomAccessibilityAction("Open this session") { onOpen(p.sessionId); true })
                    }
                    .clickable { select(i) }
                    .testTag("progress-point-$i"),
            )
        }

        val point = active?.let { chart.points.getOrNull(it) }
        AnimatedVisibility(point != null, enter = fadeIn() + scaleIn(initialScale = 0.9f), exit = fadeOut() + scaleOut(targetScale = 0.9f)) {
            if (point != null) {
                val o = px(point)
                val lines = tooltipLines(point, label)
                val cardW = with(density) { 216.dp.toPx() }
                val cardH = with(density) { 96.dp.toPx() }
                val gap = with(density) { 14.dp.toPx() }
                val x = (o.x - cardW / 2).coerceIn(0f, maxOf(0f, widthPx - cardW))
                val y = if (o.y - gap - cardH >= 0) o.y - gap - cardH else o.y + gap
                Surface(
                    onClick = { onOpen(point.sessionId) },
                    modifier = Modifier
                        .offset { IntOffset(x.toInt(), y.toInt()) }
                        .widthIn(max = 216.dp)
                        .testTag("progress-tooltip"),
                    shape = MaterialTheme.shapes.medium,
                    color = MaterialTheme.colorScheme.inverseSurface,
                    contentColor = MaterialTheme.colorScheme.inverseOnSurface,
                    shadowElevation = 3.dp,
                ) {
                    Row(Modifier.padding(start = Space.m, top = Space.s, bottom = Space.s, end = Space.xs), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f, fill = false)) {
                            Text(lines[0], style = MaterialTheme.typography.titleSmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
                            Text(lines[1], style = MaterialTheme.typography.bodySmall)
                            Text(lines[2], style = MaterialTheme.typography.labelLarge)
                        }
                        Spacer(Modifier.width(Space.xs))
                        Icon(Icons.ChevronRight, contentDescription = "Open")
                    }
                }
            }
        }
    }
}
