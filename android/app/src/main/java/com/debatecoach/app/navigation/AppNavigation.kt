package com.debatecoach.app.navigation

import android.content.Intent
import androidx.activity.ComponentActivity
import androidx.compose.animation.AnimatedContentTransitionScope
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.AnimatedVisibilityScope
import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.ExperimentalSharedTransitionApi
import androidx.compose.animation.SharedTransitionLayout
import androidx.compose.animation.SharedTransitionScope
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationRail
import androidx.compose.material3.NavigationRailItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.VerticalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.core.util.Consumer
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavBackStackEntry
import androidx.navigation.NavDestination
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.navigation
import androidx.navigation.navDeepLink
import androidx.navigation.toRoute
import com.debatecoach.app.AppContainer
import com.debatecoach.app.BuildConfig
import com.debatecoach.app.core.net.SignOutReason
import com.debatecoach.app.feature.account.AccountScreen
import com.debatecoach.app.feature.account.DeleteAccountScreen
import com.debatecoach.app.feature.auth.SignInScreen
import com.debatecoach.app.feature.auth.SignUpScreen
import com.debatecoach.app.feature.progress.InsightsScreen
import com.debatecoach.app.feature.progress.ProgressScreen
import com.debatecoach.app.feature.progress.ProgressViewModel
import com.debatecoach.app.feature.recorder.RecorderScreen
import com.debatecoach.app.feature.report.SessionScreen
import com.debatecoach.app.feature.sessions.SessionsScreen
import com.debatecoach.app.feature.sessions.SessionsViewModel
import com.debatecoach.app.ui.components.EmptyState
import com.debatecoach.app.ui.components.Icons
import com.debatecoach.app.ui.components.customTabToolbarColor
import com.debatecoach.app.ui.components.openInApp
import com.debatecoach.app.ui.components.sharedViewModel
import com.debatecoach.app.ui.theme.LocalWidthClass
import com.debatecoach.app.ui.theme.Motion
import com.debatecoach.app.ui.theme.WidthClass
import com.debatecoach.app.ui.theme.widthClassOf
import kotlinx.serialization.Serializable

// ---------------------------------------------------------------
// Routes
// ---------------------------------------------------------------

@Serializable data class SignInRoute(val reason: String? = null)
@Serializable data object SignUpRoute

/** Everything behind sign-in: its ViewModels live and die with this graph. */
@Serializable data object MainGraph
@Serializable data object SessionsRoute
@Serializable data object ProgressRoute
@Serializable data object InsightsRoute
@Serializable data object AccountRoute
@Serializable data class SessionRoute(val id: String)
@Serializable data object RecorderRoute
@Serializable data object DeleteAccountRoute

/** A top-level destination in the bottom bar (phones) or the rail (tablets). */
private data class Tab(val route: Any, val label: String, val icon: ImageVector, val selectedIcon: ImageVector, val tag: String)

private val TABS = listOf(
    Tab(SessionsRoute, "Sessions", Icons.Sessions, Icons.Sessions, "tab-sessions"),
    Tab(ProgressRoute, "Progress", Icons.Progress, Icons.Progress, "tab-progress"),
    Tab(InsightsRoute, "Insights", Icons.InsightsOutlined, Icons.Insights, "tab-insights"),
    Tab(AccountRoute, "Account", Icons.AccountOutlined, Icons.Account, "tab-account"),
)

private fun NavDestination?.isTab(): Boolean =
    this?.hierarchy?.any { d -> d.hasRoute(SessionsRoute::class) || d.hasRoute(ProgressRoute::class) || d.hasRoute(InsightsRoute::class) || d.hasRoute(AccountRoute::class) } == true

private fun NavDestination?.isRoute(tab: Tab): Boolean = this?.hierarchy?.any { it.hasRoute(tab.route::class) } == true

/** login/page.tsx's REASON_MESSAGE: fixed, friendly wording, never the raw backend text. */
fun reasonMessage(reason: String?): String? = when (reason) {
    "expired" -> "Your session expired. Please log in again."
    "deleted" -> "Your account has been deleted."
    else -> null
}

private fun SignOutReason.wire(): String? = when (this) {
    SignOutReason.EXPIRED -> "expired"
    SignOutReason.DELETED -> "deleted"
    SignOutReason.SIGNED_OUT -> null
}

private val SCHEME = BuildConfig.DEEP_LINK_SCHEME

// ---------------------------------------------------------------
// Shared-element plumbing: a session row grows into its report
// ---------------------------------------------------------------

@OptIn(ExperimentalSharedTransitionApi::class)
val LocalSharedTransitionScope = compositionLocalOf<SharedTransitionScope?> { null }
val LocalNavAnimatedScope = compositionLocalOf<AnimatedVisibilityScope?> { null }

/** The container transform between a session's row and its report; a no-op outside the app's NavHost (tests, two-pane). */
@OptIn(ExperimentalSharedTransitionApi::class)
@Composable
fun Modifier.sessionContainer(id: String): Modifier {
    val shared = LocalSharedTransitionScope.current ?: return this
    val animated = LocalNavAnimatedScope.current ?: return this
    return with(shared) {
        this@sessionContainer.sharedBounds(
            rememberSharedContentState("session-$id"),
            animatedVisibilityScope = animated,
            enter = fadeIn(tween(Motion.MEDIUM)),
            exit = fadeOut(tween(Motion.SHORT)),
            resizeMode = SharedTransitionScope.ResizeMode.RemeasureToBounds,
        )
    }
}

// ---------------------------------------------------------------
// Transitions
// ---------------------------------------------------------------

/** Between tabs: Material's fade through. */
private fun fadeThroughIn(): EnterTransition = fadeIn(tween(210, delayMillis = 90, easing = Motion.EmphasizedDecelerate)) + scaleIn(tween(210, delayMillis = 90), initialScale = 0.96f)
private fun fadeThroughOut(): ExitTransition = fadeOut(tween(90))

/** Into a detail screen: Material's shared axis (X). */
private fun sharedAxisIn(forward: Boolean): EnterTransition =
    slideInHorizontally(tween(Motion.MEDIUM, easing = Motion.Emphasized)) { w -> if (forward) w / 8 else -w / 8 } + fadeIn(tween(Motion.MEDIUM))
private fun sharedAxisOut(forward: Boolean): ExitTransition =
    slideOutHorizontally(tween(Motion.MEDIUM, easing = Motion.Emphasized)) { w -> if (forward) -w / 8 else w / 8 } + fadeOut(tween(Motion.SHORT))

private fun AnimatedContentTransitionScope<NavBackStackEntry>.bothTabs() = initialState.destination.isTab() && targetState.destination.isTab()

// ---------------------------------------------------------------
// The app
// ---------------------------------------------------------------

@OptIn(ExperimentalSharedTransitionApi::class)
@Composable
fun AppNavigation(container: AppContainer, nav: NavHostController) {
    // Decided once, at launch. Later sign-outs are routed by the
    // signedOut event below, which carries the reason to show; a start
    // destination that followed the signed-in state would reset the
    // graph and lose that message.
    val start: Any = remember { if (container.backend.signedIn.value) MainGraph else SignInRoute() }
    val context = LocalContext.current
    val toolbar = customTabToolbarColor()
    val haptics = LocalHapticFeedback.current
    val openWebsite: (String) -> Unit = { path -> openInApp(context, BuildConfig.WEBSITE_URL.trimEnd('/') + path, toolbar) }

    // An expired session, a deleted account or a sign-out, from any
    // screen: back to sign-in, with nothing left on the back stack.
    LaunchedEffect(Unit) {
        container.backend.signedOut.collect { reason ->
            container.heartbeat.stop()
            container.uploads.reset()
            nav.navigate(SignInRoute(reason.wire())) {
                popUpTo(0) { inclusive = true }
                launchSingleTop = true
            }
        }
    }

    // A deep link while the app is already open (the activity is single-top).
    DisposableEffect(nav) {
        val activity = context as? ComponentActivity
        val listener = Consumer<Intent> { intent -> nav.handleDeepLink(intent) }
        activity?.addOnNewIntentListener(listener)
        onDispose { activity?.removeOnNewIntentListener(listener) }
    }

    BoxWithConstraints(Modifier.fillMaxSize()) {
        val widthClass = widthClassOf(maxWidth)
        CompositionLocalProvider(LocalWidthClass provides widthClass) {
            val entry by nav.currentBackStackEntryAsState()
            val destination = entry?.destination
            val onTab = destination.isTab()
            val rail = widthClass != WidthClass.COMPACT

            fun openTab(tab: Tab) {
                if (destination.isRoute(tab)) return
                haptics.performHapticFeedback(HapticFeedbackType.SegmentTick)
                nav.navigate(tab.route) {
                    popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                    launchSingleTop = true
                    restoreState = true
                }
            }
            val openRecorder = {
                haptics.performHapticFeedback(HapticFeedbackType.Confirm)
                nav.navigate(RecorderRoute)
            }

            Scaffold(
                contentWindowInsets = WindowInsets(0, 0, 0, 0),
                bottomBar = {
                    AnimatedVisibility(onTab && !rail, enter = expandVertically(expandFrom = androidx.compose.ui.Alignment.Top), exit = shrinkVertically(shrinkTowards = androidx.compose.ui.Alignment.Top)) {
                        NavigationBar(containerColor = MaterialTheme.colorScheme.surfaceContainer) {
                            TABS.forEach { tab ->
                                val selected = destination.isRoute(tab)
                                NavigationBarItem(
                                    selected = selected,
                                    onClick = { openTab(tab) },
                                    icon = { Icon(if (selected) tab.selectedIcon else tab.icon, contentDescription = null) },
                                    label = { Text(tab.label, maxLines = 1) },
                                    modifier = Modifier.testTag(tab.tag),
                                )
                            }
                        }
                    }
                },
            ) { padding ->
                Row(Modifier.fillMaxSize().padding(padding).consumeWindowInsets(padding)) {
                    if (rail && onTab) {
                        NavigationRail(
                            containerColor = MaterialTheme.colorScheme.surfaceContainer,
                            header = {
                                FloatingActionButton(
                                    onClick = openRecorder,
                                    containerColor = MaterialTheme.colorScheme.primary,
                                    contentColor = MaterialTheme.colorScheme.onPrimary,
                                    modifier = Modifier.padding(vertical = 12.dp).semantics { contentDescription = "Record a speech" }.testTag("rail-record"),
                                ) { Icon(Icons.Mic, contentDescription = null) }
                            },
                        ) {
                            Spacer(Modifier.height(8.dp))
                            TABS.forEach { tab ->
                                val selected = destination.isRoute(tab)
                                NavigationRailItem(
                                    selected = selected,
                                    onClick = { openTab(tab) },
                                    icon = { Icon(if (selected) tab.selectedIcon else tab.icon, contentDescription = null) },
                                    label = { Text(tab.label, maxLines = 1) },
                                    modifier = Modifier.testTag(tab.tag),
                                )
                            }
                        }
                    }
                    SharedTransitionLayout(Modifier.weight(1f).fillMaxHeight()) {
                        CompositionLocalProvider(LocalSharedTransitionScope provides this) {
                            NavHost(
                                navController = nav,
                                startDestination = start,
                                modifier = Modifier.fillMaxSize(),
                                enterTransition = { if (bothTabs()) fadeThroughIn() else sharedAxisIn(forward = true) },
                                exitTransition = { if (bothTabs()) fadeThroughOut() else sharedAxisOut(forward = true) },
                                popEnterTransition = { if (bothTabs()) fadeThroughIn() else sharedAxisIn(forward = false) },
                                popExitTransition = { if (bothTabs()) fadeThroughOut() else sharedAxisOut(forward = false) },
                            ) {
                                composable<SignInRoute> { e ->
                                    SignInScreen(
                                        backend = container.backend,
                                        message = reasonMessage(e.toRoute<SignInRoute>().reason),
                                        onSignedIn = {
                                            container.heartbeat.reset()
                                            container.heartbeat.start()
                                            nav.navigate(MainGraph) { popUpTo(0) { inclusive = true } }
                                        },
                                        onCreateAccount = { nav.navigate(SignUpRoute) },
                                    )
                                }
                                composable<SignUpRoute> {
                                    SignUpScreen(
                                        backend = container.backend,
                                        onSignedUp = {
                                            container.heartbeat.reset()
                                            container.heartbeat.start()
                                            nav.navigate(MainGraph) { popUpTo(0) { inclusive = true } }
                                        },
                                        onSignIn = { nav.popBackStack() },
                                        onOpenLink = openWebsite,
                                    )
                                }
                                mainGraph(container, nav, openWebsite, openRecorder, rail, widthClass)
                            }
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalSharedTransitionApi::class)
private fun androidx.navigation.NavGraphBuilder.mainGraph(
    container: AppContainer,
    nav: NavHostController,
    openWebsite: (String) -> Unit,
    openRecorder: () -> Unit,
    rail: Boolean,
    widthClass: WidthClass,
) {
    navigation<MainGraph>(startDestination = SessionsRoute) {
        composable<SessionsRoute>(deepLinks = listOf(navDeepLink { uriPattern = "$SCHEME://sessions" })) { e ->
            val (sessions, _) = graphViewModels(container, nav, e)
            val online by container.connectivity.online.collectAsStateWithLifecycle()
            CompositionLocalProvider(LocalNavAnimatedScope provides this) {
                if (widthClass == WidthClass.EXPANDED) {
                    // List and report side by side on large screens.
                    var selected by rememberSaveable { mutableStateOf<String?>(null) }
                    Row(Modifier.fillMaxSize()) {
                        Box(Modifier.width(400.dp).fillMaxHeight()) {
                            SessionsScreen(sessions, online, onOpenSession = { selected = it }, onRecord = openRecorder, showFab = !rail, selectedId = selected)
                        }
                        VerticalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                        Box(Modifier.weight(1f).fillMaxHeight()) {
                            val id = selected
                            if (id == null) {
                                EmptyState(Icons.Document, "Select a session", "Its report opens here.", Modifier.fillMaxSize().padding(top = 120.dp))
                            } else {
                                androidx.compose.runtime.key(id) {
                                    CompositionLocalProvider(LocalNavAnimatedScope provides null) {
                                        SessionScreen(container, id, onBack = null, onDeleted = { selected = null }, onRecordAgain = openRecorder)
                                    }
                                }
                            }
                        }
                    }
                } else {
                    SessionsScreen(sessions, online, onOpenSession = { nav.navigate(SessionRoute(it)) }, onRecord = openRecorder, showFab = !rail)
                }
            }
        }
        composable<ProgressRoute>(deepLinks = listOf(navDeepLink { uriPattern = "$SCHEME://progress" })) { e ->
            val (sessions, progress) = graphViewModels(container, nav, e)
            val state by sessions.state.collectAsStateWithLifecycle()
            LaunchedEffect(Unit) { sessions.ensureLoaded() }
            ProgressScreen(progress, state.completedCount, onOpenSession = { nav.navigate(SessionRoute(it)) })
        }
        composable<InsightsRoute>(deepLinks = listOf(navDeepLink { uriPattern = "$SCHEME://insights" })) { e ->
            val (sessions, progress) = graphViewModels(container, nav, e)
            val state by sessions.state.collectAsStateWithLifecycle()
            LaunchedEffect(Unit) { sessions.ensureLoaded() }
            InsightsScreen(progress, state.completedCount)
        }
        composable<AccountRoute>(deepLinks = listOf(navDeepLink { uriPattern = "$SCHEME://account" })) {
            AccountScreen(container, onOpenLink = openWebsite, onDeleteAccount = { nav.navigate(DeleteAccountRoute) })
        }
        composable<SessionRoute>(deepLinks = listOf(navDeepLink<SessionRoute>(basePath = "$SCHEME://session"))) { e ->
            CompositionLocalProvider(LocalNavAnimatedScope provides this) {
                SessionScreen(
                    container,
                    e.toRoute<SessionRoute>().id,
                    onBack = { nav.popBackStack() },
                    onDeleted = { nav.popBackStack() },
                    onRecordAgain = { nav.navigate(RecorderRoute) { popUpTo<SessionsRoute>() } },
                )
            }
        }
        composable<RecorderRoute>(
            deepLinks = listOf(navDeepLink { uriPattern = "$SCHEME://record" }),
            // The recorder rises from the bottom, like a sheet, and falls back down.
            enterTransition = { slideInVertically(tween(Motion.MEDIUM, easing = Motion.EmphasizedDecelerate)) { it / 3 } + fadeIn(tween(Motion.MEDIUM)) },
            exitTransition = { fadeOut(tween(Motion.SHORT)) },
            popEnterTransition = { fadeIn(tween(Motion.MEDIUM)) },
            popExitTransition = { slideOutVertically(tween(Motion.MEDIUM, easing = Motion.EmphasizedAccelerate)) { it / 3 } + fadeOut(tween(Motion.MEDIUM)) },
        ) {
            RecorderScreen(
                container = container,
                onClose = { nav.popBackStack() },
                onUploaded = { id -> nav.navigate(SessionRoute(id)) { popUpTo<SessionsRoute>() } },
            )
        }
        composable<DeleteAccountRoute> {
            DeleteAccountScreen(container, onClose = { nav.popBackStack() })
        }
    }
}

/** The sessions and progress ViewModels, shared by every screen in the signed-in graph. */
@Composable
private fun graphViewModels(container: AppContainer, nav: NavHostController, entry: NavBackStackEntry): Pair<SessionsViewModel, ProgressViewModel> {
    val parent = remember(entry) { nav.getBackStackEntry<MainGraph>() }
    val sessions = sharedViewModel(parent) { SessionsViewModel(container.backend) }
    val progress = sharedViewModel(parent) { ProgressViewModel(container.backend) }
    return sessions to progress
}
