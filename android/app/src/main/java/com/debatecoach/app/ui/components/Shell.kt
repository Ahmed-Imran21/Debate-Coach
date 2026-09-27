package com.debatecoach.app.ui.components

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
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.debatecoach.app.ui.theme.Dc
import com.debatecoach.app.ui.theme.Serif

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
        Text("Debate Coach", fontFamily = Serif, fontSize = 20.sp, color = c.ink, style = MaterialTheme.typography.titleLarge.copy(fontSize = 20.sp))
    }
}

/** A ViewModel built from the app's container, scoped to the current destination. */
@Composable
inline fun <reified VM : ViewModel> appViewModel(key: String? = null, crossinline create: () -> VM): VM =
    viewModel(key = key, factory = viewModelFactory { initializer { create() } })
