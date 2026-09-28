package com.debatecoach.app.ui.components

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.debatecoach.app.ui.theme.Dc
import com.debatecoach.app.ui.theme.Radius
import com.debatecoach.app.ui.theme.Space
import com.debatecoach.app.ui.theme.numberStyle
import androidx.compose.ui.unit.sp

// ---------------------------------------------------------------
// Surfaces
// ---------------------------------------------------------------

/**
 * The app's card: a sheet laid on the page, as on the website (lowest
 * container tone, a hairline outline, medium corners). Clickable when
 * [onClick] is given.
 */
@Composable
fun DcCard(
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    padding: PaddingValues = PaddingValues(Space.l),
    content: @Composable ColumnScope.() -> Unit,
) {
    val colors = CardDefaults.outlinedCardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLowest)
    val border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)
    val inner: @Composable ColumnScope.() -> Unit = { Column(Modifier.padding(padding), content = content) }
    if (onClick != null) {
        Card(onClick = onClick, modifier = modifier.fillMaxWidth(), shape = MaterialTheme.shapes.medium, colors = colors, border = border, content = inner)
    } else {
        Card(modifier = modifier.fillMaxWidth(), shape = MaterialTheme.shapes.medium, colors = colors, border = border, content = inner)
    }
}

/** A card's title row: a heading, optional supporting line, optional trailing action. */
@Composable
fun CardHeader(title: String, modifier: Modifier = Modifier, supporting: String? = null, trailing: (@Composable () -> Unit)? = null) {
    Row(modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurface, modifier = Modifier.semantics { heading() })
            if (supporting != null) {
                Text(supporting, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        trailing?.invoke()
    }
}

/** The small label above a group of list rows (settings-style). */
@Composable
fun SectionLabel(text: String, modifier: Modifier = Modifier) {
    Text(
        text,
        modifier = modifier.padding(top = Space.xl, bottom = Space.s).semantics { heading() },
        style = MaterialTheme.typography.labelLarge,
        color = MaterialTheme.colorScheme.primary,
    )
}

// ---------------------------------------------------------------
// Top app bars
// ---------------------------------------------------------------

/**
 * A top-level destination's bar: the title large in the serif, shrinking
 * into a standard bar as the content scrolls. Actions go on the right,
 * secondary ones in the overflow menu.
 */
@Composable
fun TopLevelBar(
    title: String,
    scrollBehavior: androidx.compose.material3.TopAppBarScrollBehavior,
    actions: @Composable androidx.compose.foundation.layout.RowScope.() -> Unit = {},
) {
    androidx.compose.material3.LargeTopAppBar(
        title = { Text(title, maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis, modifier = Modifier.semantics { heading() }) },
        actions = actions,
        scrollBehavior = scrollBehavior,
        colors = androidx.compose.material3.TopAppBarDefaults.topAppBarColors(
            containerColor = MaterialTheme.colorScheme.surface,
            scrolledContainerColor = MaterialTheme.colorScheme.surfaceContainer,
        ),
    )
}

// ---------------------------------------------------------------
// Status
// ---------------------------------------------------------------

enum class Tone { NEUTRAL, POSITIVE, CAUTION, CRITICAL }

private data class ToneColors(val container: Color, val content: Color)

@Composable
private fun toneColors(tone: Tone): ToneColors {
    val s = MaterialTheme.colorScheme
    return when (tone) {
        Tone.NEUTRAL -> ToneColors(s.secondaryContainer, s.onSecondaryContainer)
        Tone.POSITIVE -> ToneColors(s.primaryContainer, s.onPrimaryContainer)
        Tone.CAUTION -> ToneColors(s.tertiaryContainer, s.onTertiaryContainer)
        Tone.CRITICAL -> ToneColors(s.errorContainer, s.onErrorContainer)
    }
}

/** A small status chip (a pipeline stage, "Failed", "Shared", a confidence). Not interactive. */
@Composable
fun StatusChip(text: String, modifier: Modifier = Modifier, tone: Tone = Tone.NEUTRAL, icon: ImageVector? = null) {
    val c = toneColors(tone)
    Row(
        modifier
            .clip(MaterialTheme.shapes.small)
            .background(c.container)
            .padding(horizontal = Space.s, vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (icon != null) {
            Icon(icon, contentDescription = null, tint = c.content, modifier = Modifier.size(14.dp))
            Spacer(Modifier.width(Space.xs))
        }
        Text(text, style = MaterialTheme.typography.labelMedium, color = c.content, maxLines = 1)
    }
}

/**
 * An inline message: an icon, a line or two, an optional action. For
 * errors, the offline state and quiet notes; announced by TalkBack.
 */
@Composable
fun InlineMessage(
    text: String,
    modifier: Modifier = Modifier,
    tone: Tone = Tone.NEUTRAL,
    icon: ImageVector = if (tone == Tone.CRITICAL) Icons.Error else Icons.Info,
    actionLabel: String? = null,
    onAction: (() -> Unit)? = null,
) {
    val c = toneColors(tone)
    Row(
        modifier
            .fillMaxWidth()
            .clip(MaterialTheme.shapes.medium)
            .background(c.container)
            .padding(start = Space.l, end = if (actionLabel != null) Space.xs else Space.l, top = Space.m, bottom = Space.m)
            .semantics(mergeDescendants = actionLabel == null) { liveRegion = LiveRegionMode.Polite },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, contentDescription = null, tint = c.content, modifier = Modifier.size(20.dp))
        Spacer(Modifier.width(Space.m))
        Text(text, style = MaterialTheme.typography.bodyMedium, color = c.content, modifier = Modifier.weight(1f))
        if (actionLabel != null && onAction != null) {
            TextButton(onClick = onAction) { Text(actionLabel, color = c.content) }
        }
    }
}

/** The offline strip, shown at the top of a screen while there's no connection. */
@Composable
fun OfflineBanner(online: Boolean, modifier: Modifier = Modifier) {
    AnimatedVisibility(!online, modifier, enter = expandVertically() + fadeIn(), exit = shrinkVertically() + fadeOut()) {
        InlineMessage(OFFLINE_MESSAGE, icon = Icons.CloudOff, modifier = Modifier.testTag("offline-banner"))
    }
}

const val OFFLINE_MESSAGE = "You're offline. Debate Coach needs a connection to load and send sessions."

/** A designed empty or end state: an icon in a soft circle, a title, one line, an optional action. */
@Composable
fun EmptyState(
    icon: ImageVector,
    title: String,
    body: String?,
    modifier: Modifier = Modifier,
    action: (@Composable () -> Unit)? = null,
) {
    Column(
        modifier.fillMaxWidth().padding(horizontal = Space.xl, vertical = Space.xxl),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(
            Modifier.size(72.dp).clip(CircleShape).background(MaterialTheme.colorScheme.primaryContainer),
            contentAlignment = Alignment.Center,
        ) {
            Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.onPrimaryContainer, modifier = Modifier.size(32.dp))
        }
        Spacer(Modifier.height(Space.l))
        Text(
            title,
            style = MaterialTheme.typography.titleLarge,
            color = MaterialTheme.colorScheme.onSurface,
            textAlign = TextAlign.Center,
            modifier = Modifier.semantics { heading() },
        )
        if (body != null) {
            Spacer(Modifier.height(Space.s))
            Text(
                body,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
                modifier = Modifier.widthIn(max = 360.dp),
            )
        }
        if (action != null) {
            Spacer(Modifier.height(Space.xl))
            action()
        }
    }
}

// ---------------------------------------------------------------
// Loading
// ---------------------------------------------------------------

/** A gently pulsing placeholder tone, for skeleton layouts. */
fun Modifier.skeleton(shape: androidx.compose.ui.graphics.Shape? = null): Modifier = composed {
    val transition = rememberInfiniteTransition(label = "skeleton")
    val alpha by transition.animateFloat(
        initialValue = 0.55f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(900), RepeatMode.Reverse),
        label = "skeleton-alpha",
    )
    val tone = MaterialTheme.colorScheme.surfaceContainerHigh
    this
        .clip(shape ?: MaterialTheme.shapes.small)
        .alpha(alpha)
        .background(tone)
}

/** A skeleton line of text. */
@Composable
fun SkeletonLine(width: Float, modifier: Modifier = Modifier, height: Dp = 14.dp) {
    Box(modifier.fillMaxWidth(width).height(height).skeleton(MaterialTheme.shapes.extraSmall))
}

/** A centred spinner for a pane that's loading, labelled for TalkBack. */
@Composable
fun LoadingPane(modifier: Modifier = Modifier, label: String = "Loading") {
    Box(modifier.fillMaxWidth().padding(vertical = Space.xxxl), contentAlignment = Alignment.Center) {
        CircularProgressIndicator(Modifier.size(32.dp).semantics { contentDescription = label }, strokeWidth = 3.dp)
    }
}

/** A thin determinate (or indeterminate, when [fraction] is null) progress bar. */
@Composable
fun ThinProgress(fraction: Float?, modifier: Modifier = Modifier, height: Dp = 4.dp) {
    val shape = MaterialTheme.shapes.extraSmall
    if (fraction == null) {
        LinearProgressIndicator(modifier.fillMaxWidth().height(height).clip(shape))
    } else {
        LinearProgressIndicator(
            progress = { fraction.coerceIn(0f, 1f) },
            modifier = modifier.fillMaxWidth().height(height).clip(shape),
            gapSize = 0.dp,
            drawStopIndicator = {},
        )
    }
}

// ---------------------------------------------------------------
// Figures
// ---------------------------------------------------------------

/** A figure: the value large in the serif, its label beneath. */
@Composable
fun StatTile(value: String, label: String, modifier: Modifier = Modifier) {
    Column(
        modifier
            .clip(MaterialTheme.shapes.medium)
            .background(MaterialTheme.colorScheme.surfaceContainer)
            .padding(horizontal = Space.l, vertical = Space.m)
            .semantics(mergeDescendants = true) {},
    ) {
        Text(value, style = numberStyle(28.sp), color = MaterialTheme.colorScheme.onSurface, maxLines = 1)
        Text(label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

/** A 0-100 bar. */
@Composable
fun ScoreBar(value: Double, modifier: Modifier = Modifier, color: Color = MaterialTheme.colorScheme.primary) {
    Box(
        modifier
            .height(6.dp)
            .clip(MaterialTheme.shapes.extraSmall)
            .background(MaterialTheme.colorScheme.surfaceContainerHighest),
    ) {
        Box(Modifier.fillMaxWidth((value / 100).toFloat().coerceIn(0f, 1f)).fillMaxHeight().clip(MaterialTheme.shapes.extraSmall).background(color))
    }
}

/** A coloured leading strip, for severity and polarity. */
@Composable
fun LeadingStrip(color: Color, modifier: Modifier = Modifier) {
    Box(modifier.width(4.dp).fillMaxHeight().clip(MaterialTheme.shapes.extraSmall).background(color))
}

// ---------------------------------------------------------------
// Fields
// ---------------------------------------------------------------

/**
 * Material's outlined text field with its floating label, the right
 * keyboard, an IME action, and a show/hide toggle for passwords.
 */
@Composable
fun TextInput(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    password: Boolean = false,
    keyboardType: KeyboardType = KeyboardType.Text,
    imeAction: ImeAction = ImeAction.Next,
    onIme: (() -> Unit)? = null,
    enabled: Boolean = true,
    supporting: String? = null,
    isError: Boolean = false,
    placeholder: String? = null,
    maxLength: Int? = null,
    tag: String? = null,
) {
    var revealed by remember { mutableStateOf(false) }
    OutlinedTextField(
        value = value,
        onValueChange = { if (maxLength == null || it.length <= maxLength) onValueChange(it) },
        modifier = modifier.fillMaxWidth().let { if (tag != null) it.testTag(tag) else it },
        enabled = enabled,
        singleLine = true,
        label = { Text(label) },
        placeholder = placeholder?.let { { Text(it) } },
        supportingText = supporting?.let { { Text(it) } },
        isError = isError,
        visualTransformation = if (password && !revealed) PasswordVisualTransformation() else VisualTransformation.None,
        keyboardOptions = KeyboardOptions(keyboardType = if (password) KeyboardType.Password else keyboardType, imeAction = imeAction),
        keyboardActions = KeyboardActions(onAny = { onIme?.invoke() }),
        trailingIcon = if (password) {
            {
                IconButton(onClick = { revealed = !revealed }) {
                    Icon(if (revealed) Icons.VisibilityOff else Icons.Visibility, contentDescription = if (revealed) "Hide password" else "Show password")
                }
            }
        } else {
            null
        },
        shape = MaterialTheme.shapes.small,
    )
}

// ---------------------------------------------------------------
// Layout helpers
// ---------------------------------------------------------------

/** Centres content at a comfortable reading width on large screens. */
@Composable
fun ReadingWidth(modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit) {
    Box(modifier.fillMaxSize(), contentAlignment = Alignment.TopCenter) {
        Box(Modifier.widthIn(max = Space.readingWidth).fillMaxSize(), content = content)
    }
}

/** A number in the serif, sized for a headline figure. */
@Composable
fun BigNumber(text: String, modifier: Modifier = Modifier, size: androidx.compose.ui.unit.TextUnit = 45.sp, color: Color = MaterialTheme.colorScheme.onSurface) {
    Text(text, modifier = modifier, style = numberStyle(size, FontWeight.Medium), color = color, maxLines = 1)
}

/** Severity colour for a finding (the website's .finding bar). */
@Composable
fun severityColor(severity: String): Color = when (severity) {
    "high" -> MaterialTheme.colorScheme.error
    "medium" -> Dc.colors.amber
    "positive" -> MaterialTheme.colorScheme.primary
    else -> MaterialTheme.colorScheme.outline
}

fun severityTone(severity: String): Tone = when (severity) {
    "high" -> Tone.CRITICAL
    "medium" -> Tone.CAUTION
    "positive" -> Tone.POSITIVE
    else -> Tone.NEUTRAL
}

/** Radius helper for code that wants a raw shape. */
val CardShape get() = androidx.compose.foundation.shape.RoundedCornerShape(Radius.m)

// ---------------------------------------------------------------
// Dropdown (Material's exposed dropdown menu)
// ---------------------------------------------------------------

/** A read-only field that opens a menu of [options] (value to label). */
@Composable
fun DropdownField(
    label: String,
    options: List<Pair<String, String>>,
    value: String,
    onSelect: (String) -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    tag: String? = null,
) {
    var expanded by remember { mutableStateOf(false) }
    val haptics = androidx.compose.ui.platform.LocalHapticFeedback.current
    val shown = options.firstOrNull { it.first == value }?.second ?: value
    androidx.compose.material3.ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { if (enabled) expanded = it }, modifier = modifier) {
        OutlinedTextField(
            value = shown,
            onValueChange = {},
            readOnly = true,
            enabled = enabled,
            singleLine = true,
            label = { Text(label) },
            trailingIcon = { androidx.compose.material3.ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
            modifier = Modifier
                .fillMaxWidth()
                .menuAnchor(androidx.compose.material3.ExposedDropdownMenuAnchorType.PrimaryNotEditable, enabled)
                .let { if (tag != null) it.testTag(tag) else it },
            shape = MaterialTheme.shapes.small,
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { (v, l) ->
                androidx.compose.material3.DropdownMenuItem(
                    text = { Text(l) },
                    trailingIcon = if (v == value) {
                        { Icon(Icons.Check, contentDescription = "Selected", tint = MaterialTheme.colorScheme.primary) }
                    } else {
                        null
                    },
                    onClick = {
                        expanded = false
                        if (v != value) haptics.performHapticFeedback(androidx.compose.ui.hapticfeedback.HapticFeedbackType.SegmentTick)
                        onSelect(v)
                    },
                    contentPadding = androidx.compose.material3.ExposedDropdownMenuDefaults.ItemContentPadding,
                    modifier = if (tag != null) Modifier.testTag("$tag-$v") else Modifier,
                )
            }
        }
    }
}

/**
 * A filter chip that opens a menu of [options]: a compact, tappable
 * summary of the current choice ("All scores ▾"), for filter bars.
 */
@Composable
fun DropdownChip(
    label: String,
    options: List<Pair<String, String>>,
    value: String,
    onSelect: (String) -> Unit,
    modifier: Modifier = Modifier,
    display: (String) -> String = { v -> options.firstOrNull { it.first == v }?.second ?: v },
    tag: String? = null,
) {
    var expanded by remember { mutableStateOf(false) }
    val haptics = androidx.compose.ui.platform.LocalHapticFeedback.current
    Box(modifier) {
        androidx.compose.material3.FilterChip(
            selected = true,
            onClick = { expanded = true },
            label = { Text(display(value)) },
            trailingIcon = { Icon(Icons.ExpandMore, contentDescription = null, modifier = Modifier.size(18.dp)) },
            modifier = Modifier
                .heightIn(min = Space.touch)
                .semantics { contentDescription = "$label: ${display(value)}" }
                .let { if (tag != null) it.testTag(tag) else it },
        )
        androidx.compose.material3.DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { (v, l) ->
                androidx.compose.material3.DropdownMenuItem(
                    text = { Text(l) },
                    trailingIcon = if (v == value) {
                        { Icon(Icons.Check, contentDescription = "Selected", tint = MaterialTheme.colorScheme.primary) }
                    } else {
                        null
                    },
                    onClick = {
                        expanded = false
                        if (v != value) haptics.performHapticFeedback(androidx.compose.ui.hapticfeedback.HapticFeedbackType.SegmentTick)
                        onSelect(v)
                    },
                    modifier = if (tag != null) Modifier.testTag("$tag-$v") else Modifier,
                )
            }
        }
    }
}
