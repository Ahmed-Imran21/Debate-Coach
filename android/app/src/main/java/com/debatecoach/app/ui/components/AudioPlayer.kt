package com.debatecoach.app.ui.components

import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.size
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import com.debatecoach.app.core.util.formatClock
import com.debatecoach.app.ui.theme.Dc
import kotlinx.coroutines.delay

/** Lets a parent seek the player (a key moment's "Play from here"). */
@Stable
class AudioPlayerController {
    internal var player: ExoPlayer? = null

    fun seekAndPlay(seconds: Double) {
        val p = player ?: return
        p.seekTo((seconds * 1000).toLong().coerceAtLeast(0))
        p.play()
    }
}

/**
 * ExoPlayer (Media3) with restrained controls: play/pause, a seek bar,
 * and the time. Released when it leaves the screen.
 */
@Composable
fun AudioPlayer(uri: Uri, modifier: Modifier = Modifier, controller: AudioPlayerController = remember { AudioPlayerController() }) {
    val context = LocalContext.current
    val c = Dc.colors
    val player = remember(uri) {
        ExoPlayer.Builder(context).build().apply {
            setMediaItem(MediaItem.fromUri(uri))
            prepare()
        }
    }
    var playing by remember { mutableStateOf(false) }
    var position by remember { mutableFloatStateOf(0f) }
    var duration by remember { mutableFloatStateOf(0f) }
    var dragging by remember { mutableStateOf(false) }

    DisposableEffect(player) {
        controller.player = player
        val listener = object : Player.Listener {
            override fun onIsPlayingChanged(isPlaying: Boolean) {
                playing = isPlaying
            }

            override fun onPlaybackStateChanged(state: Int) {
                if (player.duration > 0) duration = player.duration / 1000f
                if (state == Player.STATE_ENDED) {
                    player.pause()
                    player.seekTo(0)
                }
            }
        }
        player.addListener(listener)
        onDispose {
            player.removeListener(listener)
            controller.player = null
            player.release()
        }
    }

    LaunchedEffect(player) {
        while (true) {
            if (!dragging) position = player.currentPosition / 1000f
            if (player.duration > 0) duration = player.duration / 1000f
            delay(200)
        }
    }

    Column(modifier.fillMaxWidth().testTag("audio-player"), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            FilledIconButton(
                onClick = { if (player.isPlaying) player.pause() else player.play() },
                modifier = Modifier.size(48.dp).semantics { stateDescription = if (playing) "Playing" else "Paused" },
                colors = IconButtonDefaults.filledIconButtonColors(containerColor = c.pine, contentColor = c.onPine),
            ) {
                Icon(if (playing) Icons.Pause else Icons.Play, contentDescription = if (playing) "Pause" else "Play")
            }
            Slider(
                value = if (duration > 0) (position / duration).coerceIn(0f, 1f) else 0f,
                onValueChange = {
                    dragging = true
                    position = it * duration
                },
                onValueChangeFinished = {
                    player.seekTo((position * 1000).toLong())
                    dragging = false
                },
                modifier = Modifier.weight(1f).semantics { contentDescription = "Playback position" },
                colors = SliderDefaults.colors(thumbColor = c.pine, activeTrackColor = c.pine, inactiveTrackColor = c.well),
            )
        }
        Text(
            "${formatClock(position.toDouble())} / ${formatClock(duration.toDouble())}",
            style = MaterialTheme.typography.bodySmall,
            color = c.inkSoft,
        )
    }
}
