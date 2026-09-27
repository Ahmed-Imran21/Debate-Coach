package com.debatecoach.app.feature.home

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.Crossfade
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.debatecoach.app.AppContainer
import com.debatecoach.app.feature.progress.ProgressTab
import com.debatecoach.app.feature.progress.ProgressViewModel
import com.debatecoach.app.feature.sessions.SessionsTab
import com.debatecoach.app.feature.sessions.SessionsViewModel
import com.debatecoach.app.ui.components.Alert
import com.debatecoach.app.ui.components.Icons
import com.debatecoach.app.ui.components.Wordmark
import com.debatecoach.app.ui.components.appViewModel
import com.debatecoach.app.ui.theme.Dc

const val OFFLINE_MESSAGE = "You're offline. Debate Coach needs a connection to load and send sessions."

@Composable
fun OfflineBanner(online: Boolean, modifier: Modifier = Modifier) {
    AnimatedVisibility(!online, modifier) {
        Alert(OFFLINE_MESSAGE, quiet = true, modifier = Modifier.testTag("offline-banner"))
    }
}

@Composable
fun HomeScreen(container: AppContainer, onRecord: () -> Unit, onOpenSession: (String) -> Unit, onAccount: () -> Unit) {
    var tab by rememberSaveable { mutableIntStateOf(0) }
    val sessionsVm = appViewModel { SessionsViewModel(container.backend) }
    val progressVm = appViewModel { ProgressViewModel(container.backend) }
    val online by container.connectivity.online.collectAsStateWithLifecycle()
    val sessionsState by sessionsVm.state.collectAsStateWithLifecycle()
    val haptics = LocalHapticFeedback.current
    val c = Dc.colors

    Scaffold(
        containerColor = c.paper,
        topBar = {
            TopAppBar(
                title = { Wordmark() },
                actions = {
                    IconButton(onClick = onAccount, modifier = Modifier.testTag("account-button")) {
                        Icon(Icons.Person, contentDescription = "Account", tint = c.ink)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = c.paper, scrolledContainerColor = c.paperRaised),
            )
        },
        bottomBar = {
            NavigationBar(containerColor = c.paperRaised) {
                val itemColors = NavigationBarItemDefaults.colors(
                    selectedIconColor = c.pineDeep,
                    selectedTextColor = c.ink,
                    indicatorColor = c.well,
                    unselectedIconColor = c.inkSoft,
                    unselectedTextColor = c.inkSoft,
                )
                NavigationBarItem(
                    selected = tab == 0,
                    onClick = { tab = 0 },
                    icon = { Icon(Icons.List, contentDescription = null) },
                    label = { Text("Practice") },
                    colors = itemColors,
                    modifier = Modifier.testTag("tab-practice"),
                )
                NavigationBarItem(
                    selected = tab == 1,
                    onClick = { tab = 1 },
                    icon = { Icon(Icons.Chart, contentDescription = null) },
                    label = { Text("Progress") },
                    colors = itemColors,
                    modifier = Modifier.testTag("tab-progress"),
                )
            }
        },
        floatingActionButton = {
            if (tab == 0) {
                ExtendedFloatingActionButton(
                    onClick = {
                        haptics.performHapticFeedback(HapticFeedbackType.Confirm)
                        onRecord()
                    },
                    icon = { Icon(Icons.Mic, contentDescription = null, modifier = Modifier.size(22.dp)) },
                    text = { Text("Record") },
                    containerColor = c.pine,
                    contentColor = c.onPine,
                    modifier = Modifier.testTag("record-button"),
                )
            }
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(top = padding.calculateTopPadding())) {
            OfflineBanner(online, Modifier.padding(horizontal = 20.dp, vertical = 4.dp))
            Box(Modifier.weight(1f)) {
                Crossfade(targetState = tab, label = "tab") { current ->
                    val inner = PaddingValues(bottom = padding.calculateBottomPadding())
                    when (current) {
                        0 -> SessionsTab(sessionsVm, onOpenSession, inner)
                        else -> ProgressTab(progressVm, sessionsState.completedCount, inner)
                    }
                }
            }
        }
    }
}
