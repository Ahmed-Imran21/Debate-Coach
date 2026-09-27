package com.debatecoach.app

import android.content.Context
import com.debatecoach.app.core.Backend
import com.debatecoach.app.core.RemoteBackend
import com.debatecoach.app.core.auth.SharedPreferencesStore
import com.debatecoach.app.core.auth.TokenStore
import com.debatecoach.app.core.net.ApiClient
import com.debatecoach.app.core.net.AppJson
import com.debatecoach.app.core.net.ColdStartTracker
import com.debatecoach.app.core.net.Network
import com.debatecoach.app.core.net.SignedUploader
import com.debatecoach.app.core.util.AndroidConnectivity
import com.debatecoach.app.core.util.ConsentStore
import com.debatecoach.app.core.util.Connectivity
import com.debatecoach.app.core.util.Heartbeat
import com.debatecoach.app.feature.recorder.AudioUploader
import com.debatecoach.app.feature.recorder.TrackUploader
import com.debatecoach.app.feature.recorder.UploadManager
import com.debatecoach.app.visual.SignalUploader
import com.debatecoach.app.visual.VisualSignalTrack
import java.io.File
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

/** The app's long-lived services, created once in [DebateCoachApp]. */
class AppContainer(val context: Context) {
    val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    val tokens: TokenStore = TokenStore.create(context)
    private val okHttp = Network.okHttp(tokens)
    val api = ApiClient(
        service = Network.service(BuildConfig.API_BASE_URL, okHttp),
        tokens = tokens,
        coldStart = ColdStartTracker(System::currentTimeMillis),
        json = AppJson,
        scope = appScope,
    )
    val backend: Backend = RemoteBackend(api, tokens)

    val connectivity: Connectivity = AndroidConnectivity(context)
    val consent = ConsentStore(SharedPreferencesStore(context.getSharedPreferences("dc.prefs", Context.MODE_PRIVATE)))

    private val signedUploader = SignedUploader(okHttp)
    private val signalUploader = SignalUploader(api)

    val uploads = UploadManager(
        backend = backend,
        audioUploader = object : AudioUploader {
            override suspend fun put(url: String, headers: Map<String, String>, file: File, onProgress: (Long, Long) -> Unit) =
                signedUploader.put(url, headers, file, onProgress)
        },
        trackUploader = object : TrackUploader {
            override suspend fun upload(sessionId: String, track: VisualSignalTrack): Int = signalUploader.uploadWithRetry(sessionId, track)
        },
        connectivity = connectivity,
        scope = appScope,
    )

    val heartbeat = Heartbeat(appScope, getToken = { tokens.accessToken }, send = { backend.heartbeat() })

    /** Where recordings wait between Stop and a finished upload. Cleared on each new recording. */
    val recordingsDir: File get() = File(context.cacheDir, "recordings").apply { mkdirs() }

    fun onAppStart() {
        // Fire-and-forget: a cold backend starts while the first screen loads.
        api.warmUp()
    }
}
