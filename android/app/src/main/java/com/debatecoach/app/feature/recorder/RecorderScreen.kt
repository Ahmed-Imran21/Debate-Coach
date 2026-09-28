package com.debatecoach.app.feature.recorder

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.view.PreviewView
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExposedDropdownMenuAnchorType
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.ListItemDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.ProcessLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.debatecoach.app.AppContainer
import com.debatecoach.app.BuildConfig
import com.debatecoach.app.core.model.Motion
import com.debatecoach.app.core.util.ConsentChoice
import com.debatecoach.app.core.util.formatClock
import com.debatecoach.app.ui.components.DcCard
import com.debatecoach.app.ui.components.Icons
import com.debatecoach.app.ui.components.InlineMessage
import com.debatecoach.app.ui.components.OfflineBanner
import com.debatecoach.app.ui.components.StatusChip
import com.debatecoach.app.ui.components.TextInput
import com.debatecoach.app.ui.components.ThinProgress
import com.debatecoach.app.ui.components.Tone
import com.debatecoach.app.ui.components.AudioPlayerControls
import com.debatecoach.app.ui.components.appViewModel
import com.debatecoach.app.ui.components.openInApp
import com.debatecoach.app.ui.components.rememberAudioController
import com.debatecoach.app.ui.theme.Dc
import com.debatecoach.app.ui.theme.Space
import com.debatecoach.app.ui.theme.numberStyle
import com.debatecoach.app.visual.UnavailableReason
import kotlin.math.roundToInt

@Composable
fun RecorderScreen(container: AppContainer, onClose: () -> Unit, onUploaded: (String) -> Unit) {
    val context = LocalContext.current
    val vm = appViewModel {
        RecorderViewModel(
            backend = container.backend,
            consentStore = container.consent,
            recorder = AndroidSpeechRecorder(context.applicationContext),
            interruptions = AndroidInterruptionWatcher(context.applicationContext),
            captureFactory = { AndroidVisualCapture(context.applicationContext, container.appScope) },
            uploads = container.uploads,
            recordingsDir = { container.recordingsDir },
            videoFeatureEnabled = BuildConfig.VIDEO_ANALYSIS_ENABLED,
        )
    }
    val online by container.connectivity.online.collectAsStateWithLifecycle()
    RecorderContent(vm, online, onClose, onUploaded)
}

@Composable
fun RecorderContent(vm: RecorderViewModel, online: Boolean, onClose: () -> Unit, onUploaded: (String) -> Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    val upload by vm.uploadState.collectAsStateWithLifecycle()
    val view = LocalView.current
    var confirmDiscard by rememberSaveable { mutableStateOf(false) }

    // The screen stays on while the camera or microphone is live, so a
    // recording isn't cut short by the display timing out.
    val live = state.phase == Phase.SETUP || state.phase == Phase.RECORDING
    DisposableEffect(live) {
        view.keepScreenOn = live
        onDispose { view.keepScreenOn = false }
    }

    // Leaving the app (home button, power button, another app) stops the
    // recording cleanly; what was recorded goes to review.
    DisposableEffect(vm) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP) vm.stopRecording(Interruption.BACKGROUND)
        }
        val lifecycle = ProcessLifecycleOwner.get().lifecycle
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer) }
    }

    LaunchedEffect(upload) {
        when (val u = upload) {
            is UploadState.Done -> if (state.phase == Phase.UPLOADING) {
                vm.onUploadDone()
                onUploaded(u.sessionId)
            }
            is UploadState.Failed -> if (state.phase == Phase.UPLOADING) vm.onUploadFailed(u.message)
            else -> Unit
        }
    }

    // Back during a recording stops it rather than silently discarding
    // it; back from review asks before throwing a recording away.
    BackHandler(enabled = state.phase == Phase.RECORDING) { vm.stopRecording() }
    BackHandler(enabled = state.phase == Phase.REVIEW) { confirmDiscard = true }

    AnimatedContent(
        targetState = if (state.phase == Phase.UPLOADING) Phase.REVIEW else state.phase,
        transitionSpec = { (fadeIn(tween(220, delayMillis = 60)) + scaleIn(tween(220, delayMillis = 60), initialScale = 0.97f)) togetherWith fadeOut(tween(90)) },
        label = "recorder-phase",
    ) { phase ->
        when (phase) {
            Phase.IDLE -> IdleStep(vm, state, online, onClose)
            Phase.CONSENT -> ConsentStep(onDecide = vm::decideConsent)
            Phase.SETUP -> SetupStep(vm, state, onClose)
            Phase.RECORDING -> RecordingStep(vm, state)
            Phase.REVIEW, Phase.UPLOADING -> ReviewStep(vm, state, upload, online, onDiscard = { confirmDiscard = true })
        }
    }

    if (confirmDiscard) {
        AlertDialog(
            onDismissRequest = { confirmDiscard = false },
            title = { Text("Discard this recording?") },
            text = { Text("It hasn't been sent, so it will be lost.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmDiscard = false
                        vm.discard()
                    },
                    colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error),
                    modifier = Modifier.testTag("confirm-discard"),
                ) { Text("Discard") }
            },
            dismissButton = { TextButton(onClick = { confirmDiscard = false }) { Text("Keep") } },
        )
    }
}

// ---------------------------------------------------------------
// Shared scaffolding: a focused screen with a bottom action area
// ---------------------------------------------------------------

@Composable
private fun StepScaffold(
    title: String,
    navigationIcon: ImageVector?,
    onNavigate: () -> Unit,
    navigationLabel: String,
    bottom: @Composable ColumnScope.() -> Unit,
    content: @Composable ColumnScope.() -> Unit,
) {
    Scaffold(
        containerColor = MaterialTheme.colorScheme.surface,
        topBar = {
            TopAppBar(
                title = { Text(title) },
                navigationIcon = {
                    if (navigationIcon != null) IconButton(onClick = onNavigate) { Icon(navigationIcon, contentDescription = navigationLabel) }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface),
            )
        },
        bottomBar = {
            Surface(color = MaterialTheme.colorScheme.surface) {
                Column(
                    Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = Space.xl, vertical = Space.l),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(Space.s),
                    content = bottom,
                )
            }
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding).imePadding(), contentAlignment = Alignment.TopCenter) {
            Column(
                Modifier.widthIn(max = 560.dp).fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = Space.xl, vertical = Space.s),
                verticalArrangement = Arrangement.spacedBy(Space.l),
                content = content,
            )
        }
    }
}

// ---------------------------------------------------------------
// Idle: choose a prompt, check the setting, start
// ---------------------------------------------------------------

private enum class Ask { NONE, MIC_WHY, MIC_BLOCKED, CAMERA_WHY }

@Composable
private fun IdleStep(vm: RecorderViewModel, state: RecorderState, online: Boolean, onClose: () -> Unit) {
    val context = LocalContext.current
    val haptics = LocalHapticFeedback.current
    var ask by remember { mutableStateOf(Ask.NONE) }
    var micPermanentlyDenied by remember { mutableStateOf(false) }
    val visualOn = state.videoFeatureEnabled && state.consent == ConsentChoice.IN

    fun begin(cameraGranted: Boolean) {
        haptics.performHapticFeedback(HapticFeedbackType.Confirm)
        vm.startRecording(cameraGranted)
    }

    val cameraLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted -> begin(granted) }

    fun afterMic() {
        if (visualOn && !granted(context, Manifest.permission.CAMERA)) ask = Ask.CAMERA_WHY else begin(granted(context, Manifest.permission.CAMERA))
    }

    val micLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) {
            afterMic()
        } else {
            micPermanentlyDenied = context.findActivity()?.shouldShowRequestPermissionRationale(Manifest.permission.RECORD_AUDIO) == false
            ask = Ask.MIC_BLOCKED
        }
    }

    StepScaffold(
        title = "",
        navigationIcon = Icons.Close,
        onNavigate = onClose,
        navigationLabel = "Close",
        bottom = {
            RoundActionButton(
                icon = Icons.Mic,
                label = "Start recording",
                color = MaterialTheme.colorScheme.error,
                contentColor = MaterialTheme.colorScheme.onError,
                onClick = { if (granted(context, Manifest.permission.RECORD_AUDIO)) afterMic() else ask = Ask.MIC_WHY },
                tag = "start-recording",
            )
        },
    ) {
        OfflineBanner(online)
        state.error?.let { InlineMessage(it, tone = Tone.CRITICAL, modifier = Modifier.testTag("recorder-error")) }
        Text("Record a speech", style = MaterialTheme.typography.headlineMedium, modifier = Modifier.semantics { heading() })
        Text(
            "Speak as you would in a round. Debate Coach will ask for microphone access the first time.",
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        MotionPicker(state.motions, state.motionId, vm::setMotion, loadFailed = state.motionsFailed)
        if (state.videoFeatureEnabled) {
            DcCard(padding = androidx.compose.foundation.layout.PaddingValues(0.dp)) {
                ListItem(
                    headlineContent = { Text("Visual feedback") },
                    supportingContent = {
                        Text(
                            when (state.consent) {
                                ConsentChoice.IN -> "Visual feedback is on."
                                ConsentChoice.OUT -> "Visual feedback is off."
                                null -> "You'll be asked when you start."
                            },
                        )
                    },
                    leadingContent = { Icon(Icons.Camera, contentDescription = null) },
                    trailingContent = if (state.consent != null) {
                        { TextButton(onClick = vm::changeConsent, modifier = Modifier.testTag("change-consent")) { Text("Change") } }
                    } else {
                        null
                    },
                    colors = ListItemDefaults.colors(containerColor = Color.Transparent),
                )
            }
        }
        if (ask == Ask.MIC_BLOCKED) {
            InlineMessage(
                "Microphone access was blocked. Allow it for Debate Coach in your phone's settings, then try again.",
                tone = Tone.CRITICAL,
                actionLabel = if (micPermanentlyDenied) "Settings" else null,
                onAction = if (micPermanentlyDenied) ({ openAppSettings(context) }) else null,
            )
        }
    }

    when (ask) {
        Ask.MIC_WHY -> PermissionDialog(
            icon = Icons.Mic,
            title = "Microphone",
            text = "Debate Coach records your speech with the microphone, then sends the recording for analysis. It only listens while you are recording.",
            onContinue = {
                ask = Ask.NONE
                micLauncher.launch(Manifest.permission.RECORD_AUDIO)
            },
            onCancel = { ask = Ask.NONE },
        )
        Ask.CAMERA_WHY -> PermissionDialog(
            icon = Icons.Camera,
            title = "Camera",
            text = "Visual feedback looks at your camera while you record. Only numbers describing movement leave this phone; no video is recorded, uploaded or saved. If you say no, the session records audio only.",
            onContinue = {
                ask = Ask.NONE
                cameraLauncher.launch(Manifest.permission.CAMERA)
            },
            onCancel = {
                ask = Ask.NONE
                begin(false)
            },
        )
        else -> Unit
    }
}

/** A large round action (record, stop), labelled underneath. */
@Composable
private fun RoundActionButton(icon: ImageVector, label: String, color: Color, contentColor: Color, onClick: () -> Unit, tag: String, square: Boolean = false) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Surface(
            onClick = onClick,
            shape = CircleShape,
            color = color,
            contentColor = contentColor,
            shadowElevation = 2.dp,
            modifier = Modifier.size(80.dp).semantics { contentDescription = label }.testTag(tag),
        ) {
            Box(contentAlignment = Alignment.Center) {
                if (square) {
                    Box(Modifier.size(26.dp).clip(MaterialTheme.shapes.extraSmall).background(contentColor))
                } else {
                    Icon(icon, contentDescription = null, modifier = Modifier.size(34.dp))
                }
            }
        }
        Spacer(Modifier.height(Space.s))
        Text(label, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun PermissionDialog(icon: ImageVector, title: String, text: String, onContinue: () -> Unit, onCancel: () -> Unit) {
    AlertDialog(
        onDismissRequest = onCancel,
        icon = { Icon(icon, contentDescription = null) },
        title = { Text(title) },
        text = { Text(text) },
        confirmButton = { TextButton(onClick = onContinue, modifier = Modifier.testTag("permission-continue")) { Text("Continue") } },
        dismissButton = { TextButton(onClick = onCancel) { Text("Not now") } },
    )
}

fun granted(context: Context, permission: String): Boolean =
    ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED

fun Context.findActivity(): Activity? {
    var c: Context? = this
    while (c is ContextWrapper) {
        if (c is Activity) return c
        c = c.baseContext
    }
    return null
}

fun openAppSettings(context: Context) {
    val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.fromParts("package", context.packageName, null))
        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    runCatching { context.startActivity(intent) }
}

/** components/MotionPicker.tsx as a native dropdown: "No prompt" by default, the motion's wording underneath. */
@Composable
fun MotionPicker(motions: List<Motion>, value: String?, onChange: (String?) -> Unit, enabled: Boolean = true, loadFailed: Boolean = false) {
    var expanded by remember { mutableStateOf(false) }
    val chosen = motions.firstOrNull { it.id == value }
    Column(verticalArrangement = Arrangement.spacedBy(Space.s)) {
        ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { if (enabled) expanded = it }) {
            OutlinedTextField(
                value = chosen?.title ?: "No prompt",
                onValueChange = {},
                readOnly = true,
                enabled = enabled,
                singleLine = true,
                label = { Text("Practice prompt (optional)") },
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                modifier = Modifier
                    .fillMaxWidth()
                    .menuAnchor(ExposedDropdownMenuAnchorType.PrimaryNotEditable, enabled)
                    .testTag("motion-picker"),
                shape = MaterialTheme.shapes.small,
            )
            ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                DropdownMenuItem(text = { Text("No prompt") }, onClick = { onChange(null); expanded = false }, contentPadding = ExposedDropdownMenuDefaults.ItemContentPadding)
                motions.forEach { m ->
                    DropdownMenuItem(
                        text = { Text(m.title) },
                        onClick = { onChange(m.id); expanded = false },
                        contentPadding = ExposedDropdownMenuDefaults.ItemContentPadding,
                        modifier = Modifier.testTag("motion-${m.id}"),
                    )
                }
            }
        }
        if (chosen != null) {
            MotionCard(chosen, "Your coaching will also judge how well you address it.")
        } else if (loadFailed) {
            Text("Practice prompts could not be loaded. You can still record without one.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

/** The motion's wording as a card, kept on screen while recording. */
@Composable
private fun MotionCard(motion: Motion, note: String? = null) {
    Column(
        Modifier.fillMaxWidth().clip(MaterialTheme.shapes.medium).background(MaterialTheme.colorScheme.secondaryContainer).padding(Space.l),
        verticalArrangement = Arrangement.spacedBy(Space.xs),
    ) {
        Text("Motion", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSecondaryContainer)
        Text(motion.description, style = MaterialTheme.typography.titleLarge, color = MaterialTheme.colorScheme.onSecondaryContainer)
        if (note != null) Text(note, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSecondaryContainer)
    }
}

// ---------------------------------------------------------------
// Consent (components/video-analysis/ConsentPanel.tsx)
// ---------------------------------------------------------------

@Composable
fun ConsentStep(onDecide: (ConsentChoice) -> Unit) {
    val context = LocalContext.current
    val toolbar = com.debatecoach.app.ui.components.customTabToolbarColor()
    StepScaffold(
        title = "",
        navigationIcon = null,
        onNavigate = {},
        navigationLabel = "",
        bottom = {
            Button(
                onClick = { onDecide(ConsentChoice.IN) },
                modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp).testTag("consent-in"),
            ) { Text("Turn on visual feedback") }
            TextButton(onClick = { onDecide(ConsentChoice.OUT) }, modifier = Modifier.fillMaxWidth().heightIn(min = Space.touch).testTag("consent-out")) {
                Text("Continue with audio only")
            }
        },
    ) {
        Box(
            Modifier.size(56.dp).clip(CircleShape).background(MaterialTheme.colorScheme.primaryContainer),
            contentAlignment = Alignment.Center,
        ) { Icon(Icons.Camera, contentDescription = null, tint = MaterialTheme.colorScheme.onPrimaryContainer) }
        Text("Visual feedback (optional)", style = MaterialTheme.typography.headlineMedium, modifier = Modifier.semantics { heading() })
        Text(
            "Debate Coach can also look at your camera while you record, in addition to your audio.",
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Column(verticalArrangement = Arrangement.spacedBy(Space.xs)) {
            Definition(Icons.Waveform, "What is measured", "Which way your head faces, whether you're facing the camera, and where your hands are and how much they move.")
            Definition(Icons.Lock, "What is not done", "No video is recorded, uploaded, or saved. No identity recognition. No emotion detection.")
            Definition(Icons.Share, "What leaves this device", "Numbers describing movement over time, plus your audio, the same as it does today.")
            Definition(Icons.Info, "One more thing", "The on-device vision library this uses (Google MediaPipe) sends its own usage and performance statistics to Google. See MediaPipe's privacy notice.")
        }
        ListItem(
            headlineContent = { Text("MediaPipe's privacy notice", color = MaterialTheme.colorScheme.primary) },
            trailingContent = { Icon(Icons.OpenInNew, contentDescription = null, tint = MaterialTheme.colorScheme.primary) },
            colors = ListItemDefaults.colors(containerColor = Color.Transparent),
            modifier = Modifier.clip(MaterialTheme.shapes.small).clickable { openInApp(context, "https://goo.gle/mediapipe-privacy", toolbar) },
        )
    }
}

@Composable
private fun Definition(icon: ImageVector, term: String, definition: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = Space.s).semantics(mergeDescendants = true) {}, verticalAlignment = Alignment.Top) {
        Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.padding(top = 2.dp).size(20.dp))
        Spacer(Modifier.width(Space.l))
        Column {
            Text(term, style = MaterialTheme.typography.titleSmall)
            Text(definition, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

// ---------------------------------------------------------------
// Setup (components/video-analysis/SetupScreen.tsx)
// ---------------------------------------------------------------

private val LIGHTING_HINT = mapOf(
    "dim" to "The room looks dim. More light on your face will help.",
    "backlit" to "There's a lot of light behind you. Try facing a window or lamp instead.",
)

private val DISTANCE_HINT = mapOf(
    "too_close" to "Move back a little so your hands fit in the frame.",
    "too_far" to "Move a bit closer so your face is easy to track.",
)

fun unavailableMessage(reason: UnavailableReason?): String = when (reason) {
    UnavailableReason.CAMERA_DENIED -> "Camera access was blocked. You can still record with audio only."
    UnavailableReason.DEVICE_TOO_SLOW -> "This device can't keep up with visual analysis right now. Continuing with audio only."
    UnavailableReason.MODEL_LOAD_FAILED -> "Visual analysis couldn't start. Continuing with audio only."
    else -> "Visual analysis isn't available here. Continuing with audio only."
}

@Composable
private fun CameraPreview(vm: RecorderViewModel, modifier: Modifier) {
    val capture = vm.capture as? AndroidVisualCapture
    if (capture == null) {
        Box(modifier.clip(MaterialTheme.shapes.large).background(MaterialTheme.colorScheme.surfaceContainerHighest))
        return
    }
    val context = LocalContext.current
    val previewView = remember {
        PreviewView(context).apply {
            implementationMode = PreviewView.ImplementationMode.COMPATIBLE
            scaleType = PreviewView.ScaleType.FILL_CENTER
        }
    }
    DisposableEffect(capture) {
        capture.attachPreview(previewView)
        onDispose { capture.attachPreview(null) }
    }
    AndroidView(
        factory = { previewView },
        modifier = modifier
            .clip(MaterialTheme.shapes.large)
            .background(MaterialTheme.colorScheme.surfaceContainerHighest)
            .semantics { contentDescription = "Camera preview" },
    )
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SetupStep(vm: RecorderViewModel, state: RecorderState, onClose: () -> Unit) {
    val setup = state.setup
    val capture = vm.capture
    val framing = capture?.framing?.collectAsStateWithLifecycle()?.value
    val hands = capture?.handsInView?.collectAsStateWithLifecycle()?.value ?: false
    val haptics = LocalHapticFeedback.current

    if (setup.step == SetupStep.UNAVAILABLE) {
        StepScaffold(
            title = "",
            navigationIcon = Icons.Close,
            onNavigate = onClose,
            navigationLabel = "Close",
            bottom = {
                Button(onClick = vm::continueAudioOnly, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp).testTag("audio-only")) { Text("Continue with audio only") }
            },
        ) {
            com.debatecoach.app.ui.components.EmptyState(Icons.Camera, "Audio only this time", unavailableMessage(setup.unavailable))
        }
        return
    }

    val ready = framing != null && framing.faceVisible && framing.distance == "ok" && framing.lighting == "ok"
    StepScaffold(
        title = "Set up the camera",
        navigationIcon = Icons.Close,
        onNavigate = { vm.skipVisual() },
        navigationLabel = "Skip visual feedback",
        bottom = {
            when (setup.step) {
                SetupStep.FRAMING -> SetupActions("Continue", vm::framingContinue, enabled = ready, tag = "framing-continue", skip = "Skip visual feedback" to { vm.skipVisual() })
                SetupStep.BENCHMARK -> SetupActions(if (setup.busy) "Checking." else "Run check", vm::runBenchmark, enabled = !setup.busy, skip = "Skip visual feedback" to { vm.skipVisual() }, skipEnabled = !setup.busy)
                SetupStep.CALIBRATE_GAZE -> SetupActions(if (setup.busy) "Reading." else "Start", vm::runGazeCalibration, enabled = !setup.busy, skip = "Skip" to vm::skipGazeCalibration, skipEnabled = !setup.busy)
                SetupStep.CALIBRATE_HAND -> SetupActions(if (setup.busy) "Checking." else "Start", vm::runRightHandCheck, enabled = !setup.busy, skip = "Skip" to vm::skipCalibration, skipEnabled = !setup.busy)
                SetupStep.CONTEXT -> SetupActions("Continue", vm::contextContinue)
                SetupStep.READY -> RoundActionButton(
                    icon = Icons.Mic,
                    label = "Start recording",
                    color = MaterialTheme.colorScheme.error,
                    contentColor = MaterialTheme.colorScheme.onError,
                    onClick = {
                        haptics.performHapticFeedback(HapticFeedbackType.Confirm)
                        vm.setupReady()
                    },
                    tag = "setup-start",
                )
                else -> Unit
            }
        },
    ) {
        if (capture != null) {
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.BottomCenter) {
                CameraPreview(vm, Modifier.fillMaxWidth().aspectRatio(3f / 4f).heightIn(max = 460.dp))
                if (setup.step == SetupStep.FRAMING) {
                    FlowRow(
                        Modifier.fillMaxWidth().padding(Space.m),
                        horizontalArrangement = Arrangement.spacedBy(Space.s, Alignment.CenterHorizontally),
                        verticalArrangement = Arrangement.spacedBy(Space.s),
                    ) {
                        CheckChip("Face", framing?.faceVisible == true)
                        CheckChip("Distance", framing?.distance == "ok")
                        CheckChip("Lighting", framing == null || framing.lighting == "ok")
                        CheckChip("Hands", hands)
                    }
                }
            }
        }
        when (setup.step) {
            SetupStep.STARTING -> StepText("Starting the camera", null)
            SetupStep.FRAMING -> {
                val f = framing
                val hint = when {
                    f == null || !f.faceVisible -> "Centre your face in the frame."
                    f.distance != "ok" -> DISTANCE_HINT[f.distance].orEmpty()
                    f.lighting != "ok" -> LIGHTING_HINT[f.lighting].orEmpty()
                    !hands -> "Raise both hands to check they're in the frame."
                    else -> "Looking good."
                }
                StepText("Framing", hint)
            }
            SetupStep.BENCHMARK -> StepText(
                "Checking this device",
                "A brief check to see how much analysis this device can keep up with." +
                    if (setup.benchmarkFps > 0) " Last run: ~${setup.benchmarkFps.toInt()} frames/sec." else "",
            )
            SetupStep.CALIBRATE_GAZE -> StepText(
                setup.deviceTier?.let { "Device ready (${it.replace("_", " ")} tracking)" } ?: "Look at the camera",
                "Look directly at your camera lens, not the screen, for three seconds. This sets the baseline for \"facing the camera\" during your speech.",
            )
            SetupStep.CALIBRATE_HAND -> StepText("Raise your right hand", "Just for a couple of seconds, so gestures get attributed to the right side.")
            SetupStep.CONTEXT -> {
                StepText("A couple of questions", "Where will your audience be?")
                Column {
                    Choice("Watching this camera (online or recorded)", setup.setting == "camera_audience") { vm.setSetting("camera_audience") }
                    Choice("In the room with me", setup.setting == "in_room_practice") { vm.setSetting("in_room_practice") }
                    Row(
                        Modifier.fillMaxWidth().heightIn(min = Space.touch).clip(MaterialTheme.shapes.small)
                            .toggleable(value = setup.usesNotes, role = Role.Checkbox, onValueChange = vm::setUsesNotes),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Checkbox(checked = setup.usesNotes, onCheckedChange = null)
                        Spacer(Modifier.width(Space.m))
                        Text("I'm using notes", style = MaterialTheme.typography.bodyLarge)
                    }
                }
            }
            SetupStep.READY -> StepText(
                "Ready",
                (if (setup.calibration.performed) "Calibration complete. " else "Recording without calibration; gaze tracking will be less precise. ") +
                    "You can start whenever you're ready.",
            )
            SetupStep.UNAVAILABLE -> Unit
        }
    }
}

@Composable
private fun StepText(title: String, body: String?) {
    Column(verticalArrangement = Arrangement.spacedBy(Space.xs), modifier = Modifier.semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite }) {
        Text(title, style = MaterialTheme.typography.headlineSmall, modifier = Modifier.semantics { heading() })
        if (body != null) Text(body, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun ColumnScope.SetupActions(
    label: String,
    onClick: () -> Unit,
    enabled: Boolean = true,
    tag: String? = null,
    skip: Pair<String, () -> Unit>? = null,
    skipEnabled: Boolean = true,
) {
    Button(onClick = onClick, enabled = enabled, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp).let { if (tag != null) it.testTag(tag) else it }) { Text(label) }
    if (skip != null) {
        TextButton(onClick = skip.second, enabled = skipEnabled, modifier = Modifier.fillMaxWidth().heightIn(min = Space.touch)) { Text(skip.first) }
    }
}

/** A framing check over the camera preview: a tick when it's right. */
@Composable
private fun CheckChip(label: String, ok: Boolean) {
    Row(
        Modifier
            .clip(MaterialTheme.shapes.small)
            .background(if (ok) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.inverseSurface.copy(alpha = 0.78f))
            .padding(horizontal = Space.m, vertical = Space.xs)
            .semantics(mergeDescendants = true) { contentDescription = "$label: ${if (ok) "good" else "not yet"}" },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            if (ok) Icons.Check else Icons.Info,
            contentDescription = null,
            tint = if (ok) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.inverseOnSurface,
            modifier = Modifier.size(16.dp),
        )
        Spacer(Modifier.width(Space.xs))
        Text(label, style = MaterialTheme.typography.labelLarge, color = if (ok) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.inverseOnSurface)
    }
}

@Composable
private fun Choice(label: String, selected: Boolean, onSelect: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = Space.touch).clip(MaterialTheme.shapes.small).selectable(selected = selected, role = Role.RadioButton, onClick = onSelect),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        RadioButton(selected = selected, onClick = null)
        Spacer(Modifier.width(Space.m))
        Text(label, style = MaterialTheme.typography.bodyLarge)
    }
}

// ---------------------------------------------------------------
// Recording: focused, immersive
// ---------------------------------------------------------------

@Composable
private fun RecordingStep(vm: RecorderViewModel, state: RecorderState) {
    val haptics = LocalHapticFeedback.current
    val faceMissing = vm.capture?.faceMissingSeconds?.collectAsStateWithLifecycle()?.value ?: 0.0
    Scaffold(containerColor = MaterialTheme.colorScheme.surface) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            Column(
                Modifier.fillMaxSize().statusBarsPadding().padding(horizontal = Space.xl, vertical = Space.l),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                // The status line: a pulsing dot, and the camera toggle.
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    RecordingDot()
                    Spacer(Modifier.width(Space.s))
                    Text(
                        "Recording in progress.",
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.weight(1f).semantics { liveRegion = LiveRegionMode.Polite },
                    )
                    if (state.usingVideo) {
                        IconButton(onClick = vm::togglePreview, modifier = Modifier.testTag("toggle-preview")) {
                            Icon(Icons.Camera, contentDescription = if (state.showPreview) "Hide camera preview" else "Show camera preview")
                        }
                    }
                }
                state.chosenMotion?.let {
                    Spacer(Modifier.height(Space.l))
                    MotionCard(it)
                }
                Spacer(Modifier.weight(1f))
                Text(
                    formatClock(state.elapsedSeconds.toDouble()),
                    style = numberStyle(80.sp),
                    color = MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier.semantics { contentDescription = "Recording, ${state.elapsedSeconds} seconds" }.testTag("timer"),
                )
                Spacer(Modifier.height(Space.xl))
                LevelMeter(state.level)
                AnimatedVisibility(state.usingVideo && faceMissing > 0) {
                    StatusChip("Your face isn't in view.", tone = Tone.CAUTION, icon = Icons.Warning, modifier = Modifier.padding(top = Space.l))
                }
                Spacer(Modifier.weight(1f))
                RoundActionButton(
                    icon = Icons.Stop,
                    label = "Stop recording",
                    color = MaterialTheme.colorScheme.error,
                    contentColor = MaterialTheme.colorScheme.onError,
                    onClick = {
                        haptics.performHapticFeedback(HapticFeedbackType.Confirm)
                        vm.stopRecording()
                    },
                    tag = "stop-recording",
                    square = true,
                )
                Spacer(Modifier.navigationBarsPadding())
            }
            // The camera, picture-in-picture, when visual feedback is on.
            AnimatedVisibility(
                state.usingVideo && state.showPreview,
                modifier = Modifier.align(Alignment.TopEnd).statusBarsPadding().padding(top = 64.dp, end = Space.l),
                enter = fadeIn() + scaleIn(initialScale = 0.9f),
                exit = fadeOut(),
            ) {
                CameraPreview(vm, Modifier.width(112.dp).aspectRatio(3f / 4f).border(2.dp, MaterialTheme.colorScheme.surface, MaterialTheme.shapes.large))
            }
        }
    }
}

@Composable
private fun RecordingDot() {
    val transition = rememberInfiniteTransition(label = "rec")
    val alpha by transition.animateFloat(1f, 0.25f, infiniteRepeatable(tween(800), RepeatMode.Reverse), label = "rec-alpha")
    val color = MaterialTheme.colorScheme.error
    Canvas(Modifier.size(12.dp)) { drawCircle(color.copy(alpha = alpha)) }
}

/**
 * The live level meter: recent levels as bars, newest on the right, so
 * you can see the microphone hearing you. Announced as a progress bar.
 */
@Composable
private fun LevelMeter(level: Int) {
    val history = remember { mutableStateListOf<Float>().apply { repeat(BARS) { add(0f) } } }
    LaunchedEffect(level) {
        history.removeAt(0)
        history.add(level / 100f)
    }
    val color = MaterialTheme.colorScheme.primary
    val track = MaterialTheme.colorScheme.surfaceContainerHighest
    Canvas(
        Modifier
            .fillMaxWidth()
            .widthIn(max = 360.dp)
            .height(56.dp)
            .semantics {
                progressBarRangeInfo = ProgressBarRangeInfo(level / 100f, 0f..1f)
                contentDescription = "Microphone level"
            }
            .testTag("level-meter"),
    ) {
        val gap = 3.dp.toPx()
        val w = (size.width - gap * (BARS - 1)) / BARS
        history.forEachIndexed { i, v ->
            val h = (size.height * (0.08f + 0.92f * v.coerceIn(0f, 1f)))
            val x = i * (w + gap)
            drawRoundRect(track, Offset(x, 0f), Size(w, size.height), CornerRadius(w / 2))
            drawRoundRect(color, Offset(x, (size.height - h) / 2), Size(w, h), CornerRadius(w / 2))
        }
    }
}

private const val BARS = 28

// ---------------------------------------------------------------
// Review and upload
// ---------------------------------------------------------------

@Composable
private fun ReviewStep(vm: RecorderViewModel, state: RecorderState, upload: UploadState, online: Boolean, onDiscard: () -> Unit) {
    val uploading = state.phase == Phase.UPLOADING
    val haptics = LocalHapticFeedback.current
    StepScaffold(
        title = "Review",
        navigationIcon = Icons.Close,
        onNavigate = { if (!uploading) onDiscard() },
        navigationLabel = "Discard",
        bottom = {
            if (uploading && upload is UploadState.Running) {
                Column(Modifier.fillMaxWidth().semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite }, verticalArrangement = Arrangement.spacedBy(Space.s)) {
                    Row {
                        Text("${upload.step.label}.", style = MaterialTheme.typography.labelLarge, modifier = Modifier.weight(1f))
                        upload.progress?.let { Text("${(it * 100).roundToInt()}%", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                    }
                    ThinProgress(upload.progress)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(Space.m), modifier = Modifier.fillMaxWidth()) {
                OutlinedButton(
                    onClick = onDiscard,
                    enabled = !uploading,
                    modifier = Modifier.weight(1f).heightIn(min = 52.dp).testTag("discard-recording"),
                ) { Text("Discard") }
                Button(
                    onClick = {
                        haptics.performHapticFeedback(HapticFeedbackType.Confirm)
                        vm.submit()
                    },
                    enabled = !uploading,
                    modifier = Modifier.weight(1f).heightIn(min = 52.dp).testTag("submit-recording"),
                ) { Text(if (uploading) "Uploading" else "Upload") }
            }
        },
    ) {
        OfflineBanner(online)
        state.error?.let { InlineMessage(it, tone = Tone.CRITICAL, modifier = Modifier.testTag("recorder-error")) }
        Text("Recording of ${formatClock(state.recordedSeconds)}", style = MaterialTheme.typography.headlineMedium, modifier = Modifier.semantics { heading() })
        state.interruption?.let { InlineMessage(it.message()) }
        state.recordingFile?.let { file ->
            val audio = rememberAudioController(Uri.fromFile(file))
            DcCard { AudioPlayerControls(audio) }
        }
        TextInput(
            "Name this session (optional)",
            state.title,
            vm::setTitle,
            placeholder = "Second constructive, nuclear energy",
            enabled = !uploading,
            maxLength = 200,
            tag = "title-field",
        )
        MotionPicker(state.motions, state.motionId, vm::setMotion, enabled = !uploading, loadFailed = state.motionsFailed)
    }
}

