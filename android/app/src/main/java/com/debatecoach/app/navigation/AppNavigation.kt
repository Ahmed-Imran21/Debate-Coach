package com.debatecoach.app.navigation

import androidx.compose.animation.AnimatedContentTransitionScope
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.toRoute
import com.debatecoach.app.AppContainer
import com.debatecoach.app.BuildConfig
import com.debatecoach.app.core.net.SignOutReason
import com.debatecoach.app.feature.account.AccountScreen
import com.debatecoach.app.feature.auth.SignInScreen
import com.debatecoach.app.feature.auth.SignUpScreen
import com.debatecoach.app.feature.home.HomeScreen
import com.debatecoach.app.feature.recorder.RecorderScreen
import com.debatecoach.app.feature.report.SessionScreen
import kotlinx.serialization.Serializable

@Serializable data class SignInRoute(val reason: String? = null)
@Serializable data object SignUpRoute
@Serializable data object HomeRoute
@Serializable data object RecorderRoute
@Serializable data class SessionRoute(val id: String)
@Serializable data object AccountRoute

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

private const val DURATION = 280

@Composable
fun AppNavigation(container: AppContainer, nav: NavHostController) {
    val signedIn = container.backend.signedIn.collectAsStateWithLifecycle()
    val context = LocalContext.current

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

    NavHost(
        navController = nav,
        startDestination = if (signedIn.value) HomeRoute else SignInRoute(),
        enterTransition = { slideIntoContainer(AnimatedContentTransitionScope.SlideDirection.Start, tween(DURATION)) + fadeIn(tween(DURATION)) },
        exitTransition = { fadeOut(tween(DURATION / 2)) },
        popEnterTransition = { fadeIn(tween(DURATION)) },
        popExitTransition = { slideOutOfContainer(AnimatedContentTransitionScope.SlideDirection.End, tween(DURATION)) + fadeOut(tween(DURATION)) },
    ) {
        composable<SignInRoute> { entry ->
            val route = entry.toRoute<SignInRoute>()
            SignInScreen(
                backend = container.backend,
                message = reasonMessage(route.reason),
                onSignedIn = {
                    container.heartbeat.reset()
                    container.heartbeat.start()
                    nav.navigate(HomeRoute) { popUpTo(0) { inclusive = true } }
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
                    nav.navigate(HomeRoute) { popUpTo(0) { inclusive = true } }
                },
                onSignIn = { nav.popBackStack() },
                onOpenLink = { path -> openWebsite(context, path) },
            )
        }
        composable<HomeRoute> {
            HomeScreen(
                container = container,
                onRecord = { nav.navigate(RecorderRoute) },
                onOpenSession = { id -> nav.navigate(SessionRoute(id)) },
                onAccount = { nav.navigate(AccountRoute) },
            )
        }
        composable<RecorderRoute> {
            RecorderScreen(
                container = container,
                onClose = { nav.popBackStack() },
                onUploaded = { id ->
                    nav.navigate(SessionRoute(id)) { popUpTo<HomeRoute>() }
                },
            )
        }
        composable<SessionRoute> { entry ->
            SessionScreen(
                container = container,
                sessionId = entry.toRoute<SessionRoute>().id,
                onBack = { nav.popBackStack() },
            )
        }
        composable<AccountRoute> {
            AccountScreen(
                container = container,
                onBack = { nav.popBackStack() },
                onOpenLink = { path -> openWebsite(context, path) },
            )
        }
    }
}

/** Privacy policy, terms and shared reports stay on the website: open them in the browser. */
fun openWebsite(context: android.content.Context, path: String) {
    val url = BuildConfig.WEBSITE_URL.trimEnd('/') + path
    openUrl(context, url)
}

fun openUrl(context: android.content.Context, url: String) {
    val intent = android.content.Intent(android.content.Intent.ACTION_VIEW, android.net.Uri.parse(url))
        .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
    runCatching { context.startActivity(intent) }
}
