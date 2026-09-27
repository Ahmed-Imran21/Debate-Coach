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
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ExposedDropdownMenuAnchorType
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.RadioButton
import androidx.compose.material3.RadioButtonDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
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
import com.debatecoach.app.feature.home.OfflineBanner
import com.debatecoach.app.navigation.openUrl
import com.debatecoach.app.ui.components.Alert
import com.debatecoach.app.ui.components.AudioPlayer
import com.debatecoach.app.ui.components.ButtonRow
import com.debatecoach.app.ui.components.Field
import com.debatecoach.app.ui.components.FilterChip
import com.debatecoach.app.ui.components.Icons
import com.debatecoach.app.ui.components.LinkButton
import com.debatecoach.app.ui.components.Note
import com.debatecoach.app.ui.components.Panel
import com.debatecoach.app.ui.components.PrimaryButton
import com.debatecoach.app.ui.components.QuietButton
import com.debatecoach.app.ui.components.SectionTitle
import com.debatecoach.app.ui.components.ThinProgress
import com.debatecoach.app.ui.components.Tone
import com.debatecoach.app.ui.components.appViewModel
import com.debatecoach.app.ui.theme.Dc
import com.debatecoach.app.ui.theme.Serif
import com.debatecoach.app.visual.UnavailableReason

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
    val c = Dc.colors
    val view = LocalView.current

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

    // Back during a recording stops it rather than silently discarding it.
    BackHandler(enabled = state.phase == Phase.RECORDING) { vm.stopRecording() }

    Scaffold(
        containerColor = c.paper,
        topBar = {
            TopAppBar(
                title = { Text("Record", style = MaterialTheme.typography.titleLarge) },
                navigationIcon = {
                    IconButton(onClick = { if (state.phase == Phase.RECORDING) vm.stopRecording() else onClose() }) {
                        Icon(Icons.Back, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = c.paper),
            )
        },
    ) { padding ->
        Column(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .imePadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp, vertical = 8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Column(Modifier.widthIn(max = 560.dp).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                OfflineBanner(online)
                state.error?.let { Alert(it, Modifier.testTag("recorder-error")) }
                AnimatedContent(
                    targetState = state.phase,
                    transitionSpec = { fadeIn() togetherWith fadeOut() },
                    label = "phase",
                ) { phase ->
                    when (phase) {
                        Phase.IDLE -> IdlePanel(vm, state)
                        Phase.CONSENT -> ConsentPanel(onDecide = vm::decideConsent)
                        Phase.SETUP -> SetupPanel(vm, state)
                        Phase.RECORDING -> RecordingPanel(vm, state)
                        Phase.REVIEW, Phase.UPLOADING -> ReviewPanel(vm, state, upload)
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------
// Idle
// ---------------------------------------------------------------

private enum class Ask { NONE, MIC_WHY, MIC_BLOCKED, CAMERA_WHY }

@Composable
private fun IdlePanel(vm: RecorderViewModel, state: RecorderState) {
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

    Panel {
        SectionTitle("Record a speech")
        Note(
            buildString {
                append("Speak as you would in a round. Debate Coach will ask for microphone access the first time.")
                if (state.videoFeatureEnabled && state.consent == ConsentChoice.IN) append(" Visual feedback is on.")
                if (state.videoFeatureEnabled && state.consent == ConsentChoice.OUT) append(" Visual feedback is off.")
            },
        )
        MotionPicker(state.motions, state.motionId, vm::setMotion, loadFailed = state.motionsFailed)
        if (ask == Ask.MIC_BLOCKED) {
            Alert("Microphone access was blocked. Allow it for Debate Coach in your phone's settings, then try again.")
            if (micPermanentlyDenied) QuietButton("Open settings", { openAppSettings(context) })
        }
        ButtonRow {
            PrimaryButton(
                "Start recording",
                onClick = {
                    if (granted(context, Manifest.permission.RECORD_AUDIO)) afterMic() else ask = Ask.MIC_WHY
                },
                modifier = Modifier.testTag("start-recording"),
            )
            if (state.videoFeatureEnabled && state.consent != null) {
                QuietButton("Change visual feedback setting", vm::changeConsent)
            }
        }
    }

    when (ask) {
        Ask.MIC_WHY -> PermissionDialog(
            title = "Microphone",
            text = "Debate Coach records your speech with the microphone, then sends the recording for analysis. It only listens while you are recording.",
            onContinue = {
                ask = Ask.NONE
                micLauncher.launch(Manifest.permission.RECORD_AUDIO)
            },
            onCancel = { ask = Ask.NONE },
        )
        Ask.CAMERA_WHY -> PermissionDialog(
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

@Composable
private fun PermissionDialog(title: String, text: String, onContinue: () -> Unit, onCancel: () -> Unit) {
    AlertDialog(
        onDismissRequest = onCancel,
        title = { Text(title) },
        text = { Text(text) },
        confirmButton = { PrimaryButton("Continue", onContinue, modifier = Modifier.testTag("permission-continue")) },
        dismissButton = { QuietButton("Not now", onCancel) },
        containerColor = Dc.colors.paperRaised,
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

/** components/MotionPicker.tsx: "No prompt" by default, the motion's wording underneath. */
@Composable
fun MotionPicker(motions: List<Motion>, value: String?, onChange: (String?) -> Unit, enabled: Boolean = true, loadFailed: Boolean = false) {
    val c = Dc.colors
    var expanded by remember { mutableStateOf(false) }
    val chosen = motions.firstOrNull { it.id == value }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("Practice prompt (optional)", style = MaterialTheme.typography.labelMedium, color = c.ink)
        ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { if (enabled) expanded = it }) {
            OutlinedTextField(
                value = chosen?.title ?: "No prompt",
                onValueChange = {},
                readOnly = true,
                enabled = enabled,
                trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                modifier = Modifier
                    .fillMaxWidth()
                    .menuAnchor(ExposedDropdownMenuAnchorType.PrimaryNotEditable, enabled)
                    .semantics { contentDescription = "Practice prompt: ${chosen?.title ?: "No prompt"}" }
                    .testTag("motion-picker"),
                shape = MaterialTheme.shapes.small,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = c.pine,
                    unfocusedBorderColor = c.ruleStrong,
                    focusedContainerColor = c.paperRaised,
                    unfocusedContainerColor = c.paperRaised,
                ),
            )
            ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }, containerColor = c.paperRaised) {
                DropdownMenuItem(text = { Text("No prompt") }, onClick = { onChange(null); expanded = false })
                motions.forEach { m ->
                    DropdownMenuItem(text = { Text(m.title) }, onClick = { onChange(m.id); expanded = false }, modifier = Modifier.testTag("motion-${m.id}"))
                }
            }
        }
        if (chosen != null) {
            Note("${chosen.description} Your coaching will also judge how well you address it.")
        } else if (loadFailed) {
            Note("Practice prompts could not be loaded. You can still record without one.")
        }
    }
}

// ---------------------------------------------------------------
// Consent (components/video-analysis/ConsentPanel.tsx)
// ---------------------------------------------------------------

@Composable
fun ConsentPanel(onDecide: (ConsentChoice) -> Unit) {
    val context = LocalContext.current
    Panel {
        SectionTitle("Visual feedback (optional)")
        Note("Debate Coach can also look at your camera while you record, in addition to your audio.")
        Definition("What is measured", "Which way your head faces, whether you're facing the camera, and where your hands are and how much they move.")
        Definition("What is not done", "No video is recorded, uploaded, or saved. No identity recognition. No emotion detection.")
        Definition("What leaves this device", "Numbers describing movement over time, plus your audio, the same as it does today.")
        Definition("One more thing", "The on-device vision library this uses (Google MediaPipe) sends its own usage and performance statistics to Google. See MediaPipe's privacy notice.")
        LinkButton("MediaPipe's privacy notice", { openUrl(context, "https://goo.gle/mediapipe-privacy") })
        ButtonRow {
            PrimaryButton("Turn on visual feedback", { onDecide(ConsentChoice.IN) }, modifier = Modifier.testTag("consent-in"))
            QuietButton("Continue with audio only", { onDecide(ConsentChoice.OUT) }, modifier = Modifier.testTag("consent-out"))
        }
    }
}

@Composable
fun Definition(term: String, definition: String) {
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(term, style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.SemiBold), color = Dc.colors.ink)
        Text(definition, style = MaterialTheme.typography.bodyMedium, color = Dc.colors.inkSoft)
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
    val capture = vm.capture as? AndroidVisualCapture ?: return
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
            .clip(MaterialTheme.shapes.small)
            .background(Dc.colors.well)
            .semantics { contentDescription = "Camera preview" },
    )
}

@Composable
private fun SetupPanel(vm: RecorderViewModel, state: RecorderState) {
    val setup = state.setup
    val capture = vm.capture
    val framing = capture?.framing?.collectAsStateWithLifecycle()?.value
    val hands = capture?.handsInView?.collectAsStateWithLifecycle()?.value ?: false
    val haptics = LocalHapticFeedback.current

    Panel {
        if (setup.step == SetupStep.UNAVAILABLE) {
            Note(unavailableMessage(setup.unavailable))
            PrimaryButton("Continue with audio only", vm::continueAudioOnly, modifier = Modifier.testTag("audio-only"))
            return@Panel
        }

        if (capture != null) CameraPreview(vm, Modifier.fillMaxWidth().aspectRatio(3f / 4f).heightIn(max = 420.dp))

        when (setup.step) {
            SetupStep.STARTING -> Note("Starting the camera.")
            SetupStep.FRAMING -> {
                val f = framing
                SectionTitle("Framing")
                Definition("Face", if (f?.faceVisible == true) "Visible" else "Not clearly visible yet")
                Definition("Distance", if (f?.distance == "ok") "Good" else DISTANCE_HINT[f?.distance ?: "too_far"].orEmpty())
                Definition("Lighting", if (f == null || f.lighting == "ok") "Good" else LIGHTING_HINT[f.lighting].orEmpty())
                Definition("Hands", if (hands) "Both in view" else "Raise both hands to check they're in the frame")
                val ready = f != null && f.faceVisible && f.distance == "ok" && f.lighting == "ok"
                ButtonRow {
                    PrimaryButton("Continue", vm::framingContinue, enabled = ready, modifier = Modifier.testTag("framing-continue"))
                    QuietButton("Skip visual feedback", { vm.skipVisual() })
                }
            }
            SetupStep.BENCHMARK -> {
                SectionTitle("Checking this device")
                Note(
                    "A brief check to see how much analysis this device can keep up with." +
                        if (setup.benchmarkFps > 0) " Last run: ~${setup.benchmarkFps.toInt()} frames/sec." else "",
                )
                ButtonRow {
                    PrimaryButton(if (setup.busy) "Checking." else "Run check", vm::runBenchmark, enabled = !setup.busy)
                    QuietButton("Skip visual feedback", { vm.skipVisual() }, enabled = !setup.busy)
                }
            }
            SetupStep.CALIBRATE_GAZE -> {
                SectionTitle(setup.deviceTier?.let { "Device ready (${it.replace("_", " ")} tracking)" } ?: "Look at the camera")
                Note("Look directly at your camera lens, not the screen, for three seconds. This sets the baseline for \"facing the camera\" during your speech.")
                ButtonRow {
                    PrimaryButton(if (setup.busy) "Reading." else "Start", vm::runGazeCalibration, enabled = !setup.busy)
                    QuietButton("Skip", vm::skipGazeCalibration, enabled = !setup.busy)
                }
            }
            SetupStep.CALIBRATE_HAND -> {
                SectionTitle("Raise your right hand")
                Note("Just for a couple of seconds, so gestures get attributed to the right side.")
                ButtonRow {
                    PrimaryButton(if (setup.busy) "Checking." else "Start", vm::runRightHandCheck, enabled = !setup.busy)
                    QuietButton("Skip", vm::skipCalibration, enabled = !setup.busy)
                }
            }
            SetupStep.CONTEXT -> {
                SectionTitle("A couple of questions")
                Note("Where will your audience be?")
                Choice("Watching this camera (online or recorded)", setup.setting == "camera_audience") { vm.setSetting("camera_audience") }
                Choice("In the room with me", setup.setting == "in_room_practice") { vm.setSetting("in_room_practice") }
                Row(
                    Modifier
                        .fillMaxWidth()
                        .heightIn(min = 48.dp)
                        .toggleable(value = setup.usesNotes, role = Role.Checkbox, onValueChange = vm::setUsesNotes),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Checkbox(checked = setup.usesNotes, onCheckedChange = null, colors = CheckboxDefaults.colors(checkedColor = Dc.colors.pine))
                    Text("I'm using notes", style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(start = 8.dp))
                }
                PrimaryButton("Continue", vm::contextContinue)
            }
            SetupStep.READY -> {
                SectionTitle("Ready")
                Note(
                    (if (setup.calibration.performed) "Calibration complete. " else "Recording without calibration; gaze tracking will be less precise. ") +
                        "You can start whenever you're ready.",
                )
                PrimaryButton(
                    "Start recording",
                    {
                        haptics.performHapticFeedback(HapticFeedbackType.Confirm)
                        vm.setupReady()
                    },
                    modifier = Modifier.testTag("setup-start"),
                )
            }
            SetupStep.UNAVAILABLE -> Unit
        }
    }
}

@Composable
private fun Choice(label: String, selected: Boolean, onSelect: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 48.dp).selectable(selected = selected, role = Role.RadioButton, onClick = onSelect),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        RadioButton(selected = selected, onClick = null, colors = RadioButtonDefaults.colors(selectedColor = Dc.colors.pine))
        Text(label, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.padding(start = 8.dp))
    }
}

// ---------------------------------------------------------------
// Recording
// ---------------------------------------------------------------

@Composable
private fun RecordingPanel(vm: RecorderViewModel, state: RecorderState) {
    val c = Dc.colors
    val haptics = LocalHapticFeedback.current
    val faceMissing = vm.capture?.faceMissingSeconds?.collectAsStateWithLifecycle()?.value ?: 0.0
    Panel {
        state.chosenMotion?.let { Note(it.description, color = c.inkSoft) }
        Text(
            formatClock(state.elapsedSeconds.toDouble()),
            fontFamily = Serif,
            style = MaterialTheme.typography.displayMedium,
            color = c.ink,
            modifier = Modifier.semantics { contentDescription = "Recording, ${state.elapsedSeconds} seconds" }.testTag("timer"),
        )
        // The level meter: confirms the microphone is actually hearing you.
        Box(
            Modifier
                .fillMaxWidth()
                .height(6.dp)
                .clip(MaterialTheme.shapes.extraSmall)
                .background(c.well)
                .semantics { progressBarRangeInfo = ProgressBarRangeInfo(state.level / 100f, 0f..1f); contentDescription = "Microphone level" },
        ) {
            Box(Modifier.fillMaxWidth(state.level / 100f).height(6.dp).background(c.pine))
        }
        Text("Recording in progress.", modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }, style = MaterialTheme.typography.bodySmall, color = c.inkFaint)
        if (state.usingVideo && faceMissing > 0) Note("Your face isn't in view.")
        if (state.usingVideo) {
            FilterChip(if (state.showPreview) "Hide camera preview" else "Show camera preview", state.showPreview, vm::togglePreview)
            if (state.showPreview) CameraPreview(vm, Modifier.fillMaxWidth(0.45f).aspectRatio(3f / 4f))
        }
        PrimaryButton(
            "Stop recording",
            {
                haptics.performHapticFeedback(HapticFeedbackType.Confirm)
                vm.stopRecording()
            },
            tone = Tone.DANGER,
            modifier = Modifier.fillMaxWidth().testTag("stop-recording"),
        )
    }
}

// ---------------------------------------------------------------
// Review and upload
// ---------------------------------------------------------------

@Composable
private fun ReviewPanel(vm: RecorderViewModel, state: RecorderState, upload: UploadState) {
    val uploading = state.phase == Phase.UPLOADING
    val haptics = LocalHapticFeedback.current
    Panel {
        SectionTitle("Recording of ${formatClock(state.recordedSeconds)}")
        state.interruption?.let { Alert(it.message(), quiet = true) }
        state.recordingFile?.let { AudioPlayer(Uri.fromFile(it)) }
        MotionPicker(state.motions, state.motionId, vm::setMotion, enabled = !uploading, loadFailed = state.motionsFailed)
        Field(
            "Name this session (optional)",
            state.title,
            vm::setTitle,
            placeholder = "Second constructive, nuclear energy",
            enabled = !uploading,
            maxLength = 200,
        )
        if (uploading && upload is UploadState.Running) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite }) {
                Note("${upload.step.label}.")
                ThinProgress(upload.progress)
            }
        }
        ButtonRow {
            PrimaryButton(
                if (uploading) "Sending" else "Analyse this speech",
                {
                    haptics.performHapticFeedback(HapticFeedbackType.Confirm)
                    vm.submit()
                },
                enabled = !uploading,
                modifier = Modifier.testTag("submit-recording"),
            )
            QuietButton("Record again", vm::discard, enabled = !uploading, modifier = Modifier.testTag("discard-recording"))
        }
    }
}
