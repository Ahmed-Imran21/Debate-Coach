package com.debatecoach.app.ui.components

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.browser.customtabs.CustomTabColorSchemeParams
import androidx.browser.customtabs.CustomTabsIntent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.debatecoach.app.ui.theme.Dc

/** The website's wordmark (SiteHeader.tsx): four bars and "Debate Coach". */
@Composable
fun Wordmark(modifier: Modifier = Modifier) {
    val c = Dc.colors
    Row(modifier.clearAndSetSemantics { contentDescription = "Debate Coach" }, verticalAlignment = Alignment.CenterVertically) {
        Canvas(Modifier.size(18.dp, 20.dp)) {
            val u = size.width / 18f
            fun bar(x: Float, y: Float, h: Float, color: androidx.compose.ui.graphics.Color) =
                drawRect(color, Offset(x * u, y * u), Size(2 * u, h * u))
            bar(0f, 6f, 8f, c.ruleStrong)
            bar(5f, 2f, 16f, c.pine)
            bar(10f, 7f, 6f, c.ruleStrong)
            bar(15f, 4f, 12f, c.pine)
        }
        Spacer(Modifier.width(10.dp))
        Text("Debate Coach", style = MaterialTheme.typography.titleLarge.copy(fontSize = 20.sp), color = MaterialTheme.colorScheme.onSurface)
    }
}

/** A ViewModel built from the app's container, scoped to the current destination. */
@Composable
inline fun <reified VM : ViewModel> appViewModel(key: String? = null, crossinline create: () -> VM): VM =
    viewModel(key = key, factory = viewModelFactory { initializer { create() } })

/** The same, scoped to [owner] (the signed-in graph), so several screens share one instance. */
@Composable
inline fun <reified VM : ViewModel> sharedViewModel(owner: ViewModelStoreOwner, key: String? = null, crossinline create: () -> VM): VM =
    viewModel(viewModelStoreOwner = owner, key = key, factory = viewModelFactory { initializer { create() } })

/**
 * Opens a web page in an in-app browser (a Chrome Custom Tab) themed to
 * the app, so closing it returns exactly where the user was. Falls back
 * to the default browser when no browser supports Custom Tabs.
 */
fun openInApp(context: Context, url: String, toolbarColor: Int? = null) {
    val uri = Uri.parse(url)
    val builder = CustomTabsIntent.Builder()
        .setShowTitle(true)
        .setShareState(CustomTabsIntent.SHARE_STATE_ON)
    if (toolbarColor != null) {
        builder.setDefaultColorSchemeParams(CustomTabColorSchemeParams.Builder().setToolbarColor(toolbarColor).build())
    }
    try {
        builder.build().launchUrl(context, uri)
    } catch (_: ActivityNotFoundException) {
        openUrl(context, url)
    } catch (_: SecurityException) {
        openUrl(context, url)
    }
}

/** A page for the user's default browser (a shared report). */
fun openUrl(context: Context, url: String) {
    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    runCatching { context.startActivity(intent) }
}

/** The theme's surface colour, for a Custom Tab's toolbar. */
@Composable
fun customTabToolbarColor(): Int = MaterialTheme.colorScheme.surface.toArgb()
