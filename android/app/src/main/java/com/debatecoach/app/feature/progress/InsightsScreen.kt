package com.debatecoach.app.feature.progress

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.foundation.background
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
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.LifecycleStartEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.debatecoach.app.core.model.LatestProgressReport
import com.debatecoach.app.core.util.formatNextAvailable
import com.debatecoach.app.core.util.reportCaption
import com.debatecoach.app.feature.sessions.MenuAction
import com.debatecoach.app.feature.sessions.OverflowMenu
import com.debatecoach.app.ui.components.DcCard
import com.debatecoach.app.ui.components.Icons
import com.debatecoach.app.ui.components.InlineMessage
import com.debatecoach.app.ui.components.TopLevelBar
import com.debatecoach.app.ui.components.skeleton
import com.debatecoach.app.ui.components.Tone
import com.debatecoach.app.ui.theme.Space
import com.debatecoach.app.ui.theme.numberStyle

/** The AI progress report, its own destination (the website's ProgressReportPanel). */
@Composable
fun InsightsScreen(vm: ProgressViewModel, completedCount: Int) {
    val state by vm.state.collectAsStateWithLifecycle()
    val scroll = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()

    // A report made on the website today shows up here on return, as does a newly finished session.
    LifecycleStartEffect(completedCount) {
        vm.loadLatest()
        onStopOrDispose {}
    }

    Scaffold(
        modifier = Modifier.nestedScroll(scroll.nestedScrollConnection),
        containerColor = MaterialTheme.colorScheme.surface,
        topBar = {
            TopLevelBar("Insights", scroll) {
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
            val latest = state.latest
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.TopCenter) {
                LazyColumn(
                    Modifier.widthIn(max = Space.readingWidth).fillMaxSize().testTag("insights"),
                    contentPadding = PaddingValues(start = gutter, end = gutter, top = Space.s, bottom = padding.calculateBottomPadding() + Space.xxl),
                    verticalArrangement = Arrangement.spacedBy(Space.m),
                ) {
                    when {
                        state.latestError != null -> item(key = "error") {
                            InlineMessage(state.latestError!!, tone = Tone.CRITICAL, actionLabel = "Retry", onAction = { vm.loadLatest() })
                        }
                        latest == null -> items(3, key = { "skeleton-$it" }) {
                            Box(Modifier.fillMaxWidth().height(if (it == 0) 180.dp else 88.dp).skeleton(MaterialTheme.shapes.medium).semantics { contentDescription = "Loading" })
                        }
                        else -> {
                            item(key = "status") {
                                if (latest.canGenerate) GenerateCard(state, completedCount, vm) else UsedTodayCard(latest)
                            }
                            state.generateError?.let { item(key = "generate-error") { InlineMessage(it, tone = Tone.CRITICAL) } }
                            latest.report?.let { report ->
                                item(key = "report-title") {
                                    Column(Modifier.padding(top = Space.l)) {
                                        Text(
                                            if (latest.canGenerate) "Latest report" else "Today's report",
                                            style = MaterialTheme.typography.titleLarge,
                                            modifier = Modifier.semantics { heading() },
                                        )
                                        Text(
                                            reportCaption(report.sessionCountUsed, report.reportDate),
                                            style = MaterialTheme.typography.bodySmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        )
                                    }
                                }
                                items(report.bullets.size, key = { "point-$it" }) { i -> InsightCard(i + 1, report.bullets[i]) }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun GenerateCard(state: ProgressState, completedCount: Int, vm: ProgressViewModel) {
    val haptics = LocalHapticFeedback.current
    val enough = completedCount >= 2
    DcCard(Modifier.testTag("generate-card")) {
        Text("New progress report", style = MaterialTheme.typography.titleMedium, modifier = Modifier.semantics { heading() })
        Spacer(Modifier.height(Space.xs))
        Text(
            "Compare your recent sessions and see what is improving and what still needs work. One report per day.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(Space.l))
        Text("Sessions to compare", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(Space.s))
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            SESSION_COUNT_OPTIONS.forEachIndexed { i, n ->
                SegmentedButton(
                    selected = state.count == n,
                    onClick = {
                        haptics.performHapticFeedback(HapticFeedbackType.SegmentTick)
                        vm.setCount(n)
                    },
                    enabled = !state.generating,
                    shape = SegmentedButtonDefaults.itemShape(i, SESSION_COUNT_OPTIONS.size),
                    modifier = Modifier.heightIn(min = Space.touch).testTag("count-$n"),
                    label = { Text("Last $n") },
                )
            }
        }
        Spacer(Modifier.height(Space.l))
        Button(
            onClick = {
                haptics.performHapticFeedback(HapticFeedbackType.Confirm)
                vm.generate()
            },
            enabled = !state.generating && enough,
            modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp).testTag("generate-report"),
        ) {
            if (state.generating) {
                CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = MaterialTheme.colorScheme.onPrimary)
                Spacer(Modifier.width(Space.s))
                Text("Writing your report.")
            } else {
                Icon(Icons.Insights, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(Space.s))
                Text("Generate progress report")
            }
        }
        AnimatedVisibility(!enough, enter = fadeIn() + expandVertically()) {
            Text(
                "A report compares sessions, so it needs at least 2 completed ones.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = Space.s),
            )
        }
    }
}

/** Once a day: the report is shown, and when the next one can be made. */
@Composable
private fun UsedTodayCard(latest: LatestProgressReport) {
    DcCard(Modifier.testTag("used-today")) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier.size(48.dp).clip(CircleShape).background(MaterialTheme.colorScheme.secondaryContainer),
                contentAlignment = Alignment.Center,
            ) {
                Icon(Icons.Schedule, contentDescription = null, tint = MaterialTheme.colorScheme.onSecondaryContainer)
            }
            Spacer(Modifier.width(Space.l))
            Column(Modifier.weight(1f)) {
                Text("Today's report is ready", style = MaterialTheme.typography.titleMedium, modifier = Modifier.semantics { heading() })
                latest.nextAvailableAt?.let {
                    Text(
                        "You have used today's progress report. The next one is available from ${formatNextAvailable(it)}.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

/** One point of the report: a numbered card. */
@Composable
private fun InsightCard(number: Int, text: String) {
    DcCard(Modifier.testTag("insight")) {
        Row(verticalAlignment = Alignment.Top) {
            Box(
                Modifier.size(32.dp).clip(CircleShape).background(MaterialTheme.colorScheme.primaryContainer),
                contentAlignment = Alignment.Center,
            ) {
                Text(number.toString(), style = numberStyle(16.sp), color = MaterialTheme.colorScheme.onPrimaryContainer)
            }
            Spacer(Modifier.width(Space.l))
            Text(text, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
        }
    }
}
