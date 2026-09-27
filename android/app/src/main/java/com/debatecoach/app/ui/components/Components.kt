package com.debatecoach.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.debatecoach.app.ui.theme.Dc

/*
 * The website's classes, as composables: .btn (pine), .btn-quiet
 * (outlined), .btn-stop and [data-tone=danger] (brick), .filter (the
 * chip with aria-pressed), .note, .alert / .alert-quiet, .field, and
 * the headings. Every control is at least 48dp tall for touch.
 */

enum class Tone { NORMAL, DANGER }

private val BUTTON_MIN_HEIGHT = 48.dp

@Composable
fun PrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    tone: Tone = Tone.NORMAL,
    haptic: Boolean = false,
) {
    val c = Dc.colors
    val feedback = LocalHapticFeedback.current
    Button(
        onClick = {
            if (haptic) feedback.performHapticFeedback(HapticFeedbackType.Confirm)
            onClick()
        },
        modifier = modifier.heightIn(min = BUTTON_MIN_HEIGHT),
        enabled = enabled,
        shape = MaterialTheme.shapes.small,
        colors = ButtonDefaults.buttonColors(
            containerColor = if (tone == Tone.DANGER) c.brick else c.pine,
            contentColor = c.onPine,
            disabledContainerColor = (if (tone == Tone.DANGER) c.brick else c.pine).copy(alpha = 0.45f),
            disabledContentColor = c.onPine.copy(alpha = 0.85f),
        ),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 12.dp),
    ) {
        Text(text, style = MaterialTheme.typography.labelLarge)
    }
}

@Composable
fun QuietButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    tone: Tone = Tone.NORMAL,
) {
    val c = Dc.colors
    val ink = if (tone == Tone.DANGER) c.brick else c.ink
    OutlinedButton(
        onClick = onClick,
        modifier = modifier.heightIn(min = BUTTON_MIN_HEIGHT),
        enabled = enabled,
        shape = MaterialTheme.shapes.small,
        border = BorderStroke(1.dp, if (tone == Tone.DANGER) c.brick else c.ruleStrong),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = ink, disabledContentColor = ink.copy(alpha = 0.45f)),
        contentPadding = PaddingValues(horizontal = 18.dp, vertical = 12.dp),
    ) {
        Text(text, style = MaterialTheme.typography.labelLarge)
    }
}

@Composable
fun LinkButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    TextButton(onClick = onClick, modifier = modifier.heightIn(min = BUTTON_MIN_HEIGHT)) {
        Text(text, color = Dc.colors.pineDeep, style = MaterialTheme.typography.bodyMedium)
    }
}

/** .filter with aria-pressed: a toggle chip. */
@Composable
fun FilterChip(text: String, selected: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    val c = Dc.colors
    val shape = MaterialTheme.shapes.small
    Box(
        modifier = modifier
            .heightIn(min = BUTTON_MIN_HEIGHT)
            .semantics {
                role = Role.Tab
                this.selected = selected
                stateDescription = if (selected) "Selected" else "Not selected"
            },
        contentAlignment = Alignment.Center,
    ) {
        TextButton(
            onClick = onClick,
            enabled = enabled,
            shape = shape,
            border = BorderStroke(1.dp, if (selected) c.ink else c.ruleStrong),
            colors = ButtonDefaults.textButtonColors(
                containerColor = if (selected) c.ink else Color.Transparent,
                contentColor = if (selected) c.paper else c.inkSoft,
            ),
            contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp),
            modifier = Modifier.heightIn(min = 40.dp),
        ) {
            Text(text, style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.Normal))
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ChipRow(modifier: Modifier = Modifier, label: String? = null, content: @Composable () -> Unit) {
    FlowRow(
        modifier = modifier.semantics { if (label != null) contentDescription = label },
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) { content() }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ButtonRow(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    FlowRow(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) { content() }
}

// ---------------------------------------------------------------
// Text
// ---------------------------------------------------------------

@Composable
fun PageTitle(text: String, modifier: Modifier = Modifier) {
    Text(text, modifier = modifier.semantics { heading() }, style = MaterialTheme.typography.headlineLarge, color = Dc.colors.ink)
}

@Composable
fun SectionTitle(text: String, modifier: Modifier = Modifier) {
    Text(text, modifier = modifier.semantics { heading() }, style = MaterialTheme.typography.headlineSmall, color = Dc.colors.ink)
}

@Composable
fun Note(text: String, modifier: Modifier = Modifier, color: Color? = null) {
    Text(text, modifier = modifier, style = MaterialTheme.typography.bodySmall, color = color ?: Dc.colors.inkFaint)
}

@Composable
fun Lede(text: String, modifier: Modifier = Modifier) {
    Text(text, modifier = modifier, style = MaterialTheme.typography.bodyLarge.copy(fontSize = 19.sp, lineHeight = 29.sp), color = Dc.colors.inkSoft)
}

/** .alert (brick bar) or .alert-quiet (grey bar). Announced by TalkBack. */
@Composable
fun Alert(text: String, modifier: Modifier = Modifier, quiet: Boolean = false) {
    val c = Dc.colors
    Row(
        modifier = modifier
            .fillMaxWidth()
            .height(IntrinsicSize.Min)
            .background(c.paperRaised)
            .semantics { liveRegion = LiveRegionMode.Polite },
    ) {
        Box(Modifier.width(3.dp).fillMaxHeight().background(if (quiet) c.ruleStrong else c.brick))
        Text(
            text,
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
            style = MaterialTheme.typography.bodyMedium,
            color = if (quiet) c.inkSoft else c.ink,
        )
    }
}

/** .state: a small bordered label (Shared, Failed, a status). */
@Composable
fun StateLabel(text: String, tone: String? = null, modifier: Modifier = Modifier) {
    val c = Dc.colors
    val color = when (tone) {
        "failed" -> c.brick
        "done" -> c.pineDeep
        else -> c.inkSoft
    }
    val border = when (tone) {
        "failed" -> c.brick
        "done" -> c.pine
        else -> c.ruleStrong
    }
    Text(
        text,
        modifier = modifier
            .border(1.dp, border, RoundedCornerShape(3.dp))
            .padding(horizontal = 8.dp, vertical = 2.dp),
        style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Normal),
        color = color,
    )
}

// ---------------------------------------------------------------
// Fields
// ---------------------------------------------------------------

@Composable
fun Field(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    password: Boolean = false,
    keyboardType: KeyboardType = KeyboardType.Text,
    enabled: Boolean = true,
    placeholder: String? = null,
    supporting: String? = null,
    maxLength: Int? = null,
    singleLine: Boolean = true,
) {
    val c = Dc.colors
    Column(modifier.fillMaxWidth()) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = c.ink, modifier = Modifier.padding(bottom = 6.dp))
        OutlinedTextField(
            value = value,
            onValueChange = { if (maxLength == null || it.length <= maxLength) onValueChange(it) },
            modifier = Modifier.fillMaxWidth().semantics { contentDescription = label },
            enabled = enabled,
            singleLine = singleLine,
            placeholder = placeholder?.let { { Text(it, color = c.inkFaint) } },
            visualTransformation = if (password) PasswordVisualTransformation() else VisualTransformation.None,
            keyboardOptions = KeyboardOptions(keyboardType = if (password) KeyboardType.Password else keyboardType),
            shape = MaterialTheme.shapes.small,
            textStyle = MaterialTheme.typography.bodyLarge.copy(color = c.ink),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = c.pine,
                unfocusedBorderColor = c.ruleStrong,
                focusedContainerColor = c.paperRaised,
                unfocusedContainerColor = c.paperRaised,
                disabledContainerColor = c.paperRaised,
                cursorColor = c.pine,
            ),
        )
        if (supporting != null) Note(supporting, Modifier.padding(top = 6.dp))
    }
}

// ---------------------------------------------------------------
// Loading / progress
// ---------------------------------------------------------------

/** The website's "Loading." note, with a small spinner. */
@Composable
fun Loading(modifier: Modifier = Modifier, text: String = "Loading.") {
    Row(modifier.padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        CircularProgressIndicator(Modifier.width(16.dp).height(16.dp), strokeWidth = 2.dp, color = Dc.colors.pine)
        Spacer(Modifier.width(10.dp))
        Note(text)
    }
}

/** .progress: the thin pine bar. */
@Composable
fun ThinProgress(fraction: Float?, modifier: Modifier = Modifier, height: Dp = 4.dp) {
    val c = Dc.colors
    val shape = RoundedCornerShape(1.dp)
    if (fraction == null) {
        LinearProgressIndicator(modifier.fillMaxWidth().height(height).clip(shape), color = c.pine, trackColor = c.well)
    } else {
        LinearProgressIndicator(
            progress = { fraction.coerceIn(0f, 1f) },
            modifier = modifier.fillMaxWidth().height(height).clip(shape),
            color = c.pine,
            trackColor = c.well,
            drawStopIndicator = {},
            gapSize = 0.dp,
        )
    }
}

/** .form-panel / .recorder: a raised, ruled box. */
@Composable
fun Panel(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    val c = Dc.colors
    Column(
        modifier
            .fillMaxWidth()
            .clip(MaterialTheme.shapes.small)
            .border(1.dp, c.rule, MaterialTheme.shapes.small)
            .background(c.paperRaised)
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) { content() }
}

@Composable
fun Divider(modifier: Modifier = Modifier) {
    Box(modifier.fillMaxWidth().height(1.dp).background(Dc.colors.rule))
}

val NumberStyle: TextStyle
    @Composable get() = MaterialTheme.typography.headlineMedium
