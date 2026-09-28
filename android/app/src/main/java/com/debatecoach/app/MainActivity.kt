package com.debatecoach.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import androidx.navigation.compose.rememberNavController
import com.debatecoach.app.navigation.AppNavigation
import com.debatecoach.app.ui.theme.DebateCoachTheme
import android.content.Intent
import android.net.Uri
import androidx.compose.material3.MaterialTheme
import androidx.core.content.pm.ShortcutInfoCompat
import androidx.core.content.pm.ShortcutManagerCompat
import androidx.core.graphics.drawable.IconCompat

/** The single activity. Every screen is a Compose destination in AppNavigation. */
class MainActivity : ComponentActivity() {
    private val container get() = (application as DebateCoachApp).container

    private val foreground = object : DefaultLifecycleObserver {
        // The heartbeat runs only while the app is in the foreground,
        // like the website's, which runs only while a tab is open.
        override fun onStart(owner: LifecycleOwner) {
            if (container.tokens.signedIn.value) container.heartbeat.start()
            publishShortcuts()
        }

        override fun onStop(owner: LifecycleOwner) {
            container.heartbeat.pause()
        }
    }

    /** "Record" on a long-press of the launcher icon, while signed in. */
    private fun publishShortcuts() {
        if (!container.tokens.signedIn.value) {
            ShortcutManagerCompat.removeAllDynamicShortcuts(this)
            return
        }
        val record = ShortcutInfoCompat.Builder(this, "record")
            .setShortLabel("Record")
            .setLongLabel("Record a speech")
            .setIcon(IconCompat.createWithResource(this, R.drawable.ic_shortcut_record))
            .setIntent(Intent(Intent.ACTION_VIEW, Uri.parse("${BuildConfig.DEEP_LINK_SCHEME}://record"), this, MainActivity::class.java))
            .build()
        runCatching { ShortcutManagerCompat.pushDynamicShortcut(this, record) }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.auto(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.auto(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT),
        )
        super.onCreate(savedInstanceState)
        ProcessLifecycleOwner.get().lifecycle.addObserver(foreground)
        publishShortcuts()
        setContent {
            DebateCoachTheme {
                Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.surface)) {
                    AppNavigation(container, rememberNavController())
                }
            }
        }
    }

    override fun onDestroy() {
        ProcessLifecycleOwner.get().lifecycle.removeObserver(foreground)
        super.onDestroy()
    }
}
