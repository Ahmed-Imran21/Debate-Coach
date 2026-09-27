package com.debatecoach.app.core.util

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import com.debatecoach.app.core.auth.KeyValueStore
import com.debatecoach.app.core.auth.isLive
import com.debatecoach.app.core.net.ApiException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

// ---------------------------------------------------------------
// Visual feedback consent (web: features/video-analysis/consent.ts)
// ---------------------------------------------------------------

enum class ConsentChoice(val wire: String) { IN("in"), OUT("out") }

/** Remembers whether the user opted in to visual feedback. Not sensitive; a plain preference. */
class ConsentStore(private val kv: KeyValueStore) {
    private val _choice = MutableStateFlow(read())
    val choice: StateFlow<ConsentChoice?> = _choice.asStateFlow()

    private fun read(): ConsentChoice? = when (kv.get(KEY)) {
        "in" -> ConsentChoice.IN
        "out" -> ConsentChoice.OUT
        else -> null
    }

    fun set(choice: ConsentChoice) {
        kv.put(mapOf(KEY to choice.wire))
        _choice.value = choice
    }

    private companion object {
        const val KEY = "dc.videoAnalysisOptIn"
    }
}

// ---------------------------------------------------------------
// Connectivity
// ---------------------------------------------------------------

interface Connectivity {
    val online: StateFlow<Boolean>
}

class AndroidConnectivity(context: Context) : Connectivity {
    private val manager = context.getSystemService(ConnectivityManager::class.java)
    private val _online = MutableStateFlow(current())
    override val online: StateFlow<Boolean> = _online.asStateFlow()

    init {
        manager.registerDefaultNetworkCallback(object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                _online.value = true
            }

            override fun onLost(network: Network) {
                _online.value = current()
            }

            override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) {
                _online.value = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            }
        })
    }

    private fun current(): Boolean {
        val caps = manager.activeNetwork?.let { manager.getNetworkCapabilities(it) } ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }
}

// ---------------------------------------------------------------
// Heartbeat (web: lib/heartbeat.ts)
// ---------------------------------------------------------------

const val HEARTBEAT_INTERVAL_MS = 60_000L

/**
 * Pings POST /v1/users/heartbeat every 60s while the app is in the
 * foreground with a live access token, so the admin dashboard's
 * "active now" counts an open app. Never sends with an expired token,
 * never refreshes one (the request doesn't retry on 401), and stops for
 * good after a 401, exactly like the website.
 */
class Heartbeat(
    private val scope: CoroutineScope,
    private val getToken: () -> String?,
    private val send: suspend () -> Unit,
    private val now: () -> Long = System::currentTimeMillis,
) {
    private var job: Job? = null
    private var stopped = false

    val running: Boolean get() = job?.isActive == true

    fun start() {
        if (stopped || running || !isLive(getToken(), now())) return
        job = scope.launch {
            while (isActive && !stopped) {
                if (!isLive(getToken(), now())) break
                try {
                    send()
                } catch (error: ApiException) {
                    if (error.status == 401) {
                        stop()
                        break
                    }
                } catch (_: Exception) {
                    // A missed heartbeat isn't worth surfacing.
                }
                delay(HEARTBEAT_INTERVAL_MS)
            }
        }
    }

    /** Pause (app in background). Can start again. */
    fun pause() {
        job?.cancel()
        job = null
    }

    /** Stop for good (a 401, or signed out). */
    fun stop() {
        stopped = true
        job?.cancel()
        job = null
    }

    /** A new sign-in: allowed to run again. */
    fun reset() {
        stop()
        stopped = false
    }
}
