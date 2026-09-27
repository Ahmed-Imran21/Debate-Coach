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
import com.debatecoach.app.ui.theme.Dc

/** The single activity. Every screen is a Compose destination in AppNavigation. */
class MainActivity : ComponentActivity() {
    private val container get() = (application as DebateCoachApp).container

    private val foreground = object : DefaultLifecycleObserver {
        // The heartbeat runs only while the app is in the foreground,
        // like the website's, which runs only while a tab is open.
        override fun onStart(owner: LifecycleOwner) {
            if (container.tokens.signedIn.value) container.heartbeat.start()
        }

        override fun onStop(owner: LifecycleOwner) {
            container.heartbeat.pause()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.auto(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.auto(android.graphics.Color.TRANSPARENT, android.graphics.Color.TRANSPARENT),
        )
        super.onCreate(savedInstanceState)
        ProcessLifecycleOwner.get().lifecycle.addObserver(foreground)
        setContent {
            DebateCoachTheme {
                Box(Modifier.fillMaxSize().background(Dc.colors.paper)) {
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
