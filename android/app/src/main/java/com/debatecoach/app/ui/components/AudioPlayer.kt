package com.debatecoach.app.ui.components

import android.content.Context
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import com.debatecoach.app.core.util.formatClock
import com.debatecoach.app.ui.theme.Elevation
import com.debatecoach.app.ui.theme.Space
import kotlinx.coroutines.delay

/**
 * One ExoPlayer (Media3) for a recording, shared by everything on the
 * screen that plays it: the full player, a key moment's seek, the
 * mini-player. Released when the screen goes.
 */
@Stable
class AudioController internal constructor(context: Context, uri: Uri) {
    internal val player: ExoPlayer = ExoPlayer.Builder(context).build().apply {
        setMediaItem(MediaItem.fromUri(uri))
        prepare()
    }

    var playing by mutableStateOf(false)
        private set
    var position by mutableFloatStateOf(0f)
        internal set
    var duration by mutableFloatStateOf(0f)
        private set

    /** True once playback has been started, until dismissed: when the mini-player has something to show. */
    var active by mutableStateOf(false)
        private set

    internal var dragging = false

    private val listener = object : Player.Listener {
        override fun onIsPlayingChanged(isPlaying: Boolean) {
            playing = isPlaying
            if (isPlaying) active = true
        }

        override fun onPlaybackStateChanged(state: Int) {
            if (player.duration > 0) duration = player.duration / 1000f
            if (state == Player.STATE_ENDED) {
                player.pause()
                player.seekTo(0)
            }
        }
    }

    init {
        player.addListener(listener)
    }

    fun toggle() = if (player.isPlaying) player.pause() else player.play()

    fun seekTo(seconds: Float) {
        player.seekTo((seconds * 1000).toLong().coerceAtLeast(0))
        position = seconds
    }

    /** A key moment's "play from here". */
    fun seekAndPlay(seconds: Double) {
        seekTo(seconds.toFloat())
        player.play()
    }

    /** Closes the mini-player: stops and forgets the position. */
    fun dismiss() {
        player.pause()
        active = false
    }

    internal fun tick() {
        if (!dragging) position = player.currentPosition / 1000f
        if (player.duration > 0) duration = player.duration / 1000f
    }

    internal fun release() {
        player.removeListener(listener)
        player.release()
    }
}

@Composable
fun rememberAudioController(uri: Uri): AudioController {
    val context = LocalContext.current
    val controller = remember(uri) { AudioController(context, uri) }
    DisposableEffect(controller) { onDispose { controller.release() } }
    LaunchedEffect(controller) {
        while (true) {
            controller.tick()
            delay(200)
        }
    }
    return controller
}

/** The full player: a round play button, a seek bar, and the times. */
@Composable
fun AudioPlayerControls(audio: AudioController, modifier: Modifier = Modifier) {
    val haptics = LocalHapticFeedback.current
    var scrub by remember { mutableFloatStateOf(-1f) }
    val shown = if (scrub >= 0) scrub else audio.position
    Column(modifier.fillMaxWidth().testTag("audio-player")) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            FilledIconButton(
                onClick = {
                    haptics.performHapticFeedback(HapticFeedbackType.ContextClick)
                    audio.toggle()
                },
                modifier = Modifier.size(56.dp).semantics { stateDescription = if (audio.playing) "Playing" else "Paused" },
            ) {
                Icon(if (audio.playing) Icons.Pause else Icons.Play, contentDescription = if (audio.playing) "Pause" else "Play", modifier = Modifier.size(28.dp))
            }
            Spacer(Modifier.width(Space.m))
            Slider(
                value = if (audio.duration > 0) (shown / audio.duration).coerceIn(0f, 1f) else 0f,
                onValueChange = {
                    audio.dragging = true
                    scrub = it * audio.duration
                },
                onValueChangeFinished = {
                    audio.seekTo(scrub)
                    audio.dragging = false
                    scrub = -1f
                },
                modifier = Modifier.weight(1f).semantics { contentDescription = "Playback position" },
            )
        }
        Row(Modifier.fillMaxWidth().padding(start = 56.dp + Space.m)) {
            Text(formatClock(shown.toDouble()), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.weight(1f))
            Text(formatClock(audio.duration.toDouble()), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

/**
 * A compact player pinned to the bottom of the report while listening
 * elsewhere in it (after "play from here" on a key moment), so the user
 * keeps their place.
 */
@Composable
fun MiniPlayer(audio: AudioController, title: String, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier.fillMaxWidth().testTag("mini-player"),
        color = MaterialTheme.colorScheme.surfaceContainerHigh,
        tonalElevation = Elevation.level2,
        shadowElevation = Elevation.level2,
    ) {
        Column {
            LinearProgressIndicator(
                progress = { if (audio.duration > 0) (audio.position / audio.duration).coerceIn(0f, 1f) else 0f },
                modifier = Modifier.fillMaxWidth().heightIn(max = 2.dp),
                gapSize = 0.dp,
                drawStopIndicator = {},
            )
            Row(
                Modifier.fillMaxWidth().padding(start = Space.xs, end = Space.xs, top = Space.xs, bottom = Space.xs),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(onClick = audio::toggle, modifier = Modifier.semantics { stateDescription = if (audio.playing) "Playing" else "Paused" }) {
                    Icon(if (audio.playing) Icons.Pause else Icons.Play, contentDescription = if (audio.playing) "Pause" else "Play")
                }
                Column(Modifier.weight(1f).padding(horizontal = Space.xs), verticalArrangement = Arrangement.Center) {
                    Text(title, style = MaterialTheme.typography.titleSmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(
                        "${formatClock(audio.position.toDouble())} / ${formatClock(audio.duration.toDouble())}",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                IconButton(onClick = audio::dismiss) { Icon(Icons.Close, contentDescription = "Close player") }
            }
        }
    }
}
