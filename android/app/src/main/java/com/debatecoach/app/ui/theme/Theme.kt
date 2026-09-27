package com.debatecoach.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.debatecoach.app.R

/**
 * web/app/globals.css's tokens. Light values are the website's exactly;
 * the website has no dark mode, so the dark set is drawn from the same
 * family: paper becomes a deep green-black, ink a warm off-white, pine
 * lightened enough to keep its contrast.
 */
@Immutable
data class DcColors(
    val paper: Color,
    val paperRaised: Color,
    val well: Color,
    val rule: Color,
    val ruleStrong: Color,
    val ink: Color,
    val inkSoft: Color,
    val inkFaint: Color,
    val pine: Color,
    val pineDeep: Color,
    val brick: Color,
    val amber: Color,
    /** Text on a pine button. */
    val onPine: Color,
)

val LightTokens = DcColors(
    paper = Color(0xFFEDEFEA),
    paperRaised = Color(0xFFF5F6F3),
    well = Color(0xFFE2E5DD),
    rule = Color(0xFFC9CEC4),
    ruleStrong = Color(0xFFA8B0A3),
    ink = Color(0xFF1A1F1C),
    inkSoft = Color(0xFF55605A),
    inkFaint = Color(0xFF7D8781),
    pine = Color(0xFF2E5E4E),
    pineDeep = Color(0xFF1F4437),
    brick = Color(0xFF9A3324),
    amber = Color(0xFF8A6A12),
    onPine = Color(0xFFF5F6F3),
)

val DarkTokens = DcColors(
    paper = Color(0xFF141816),
    paperRaised = Color(0xFF1C211E),
    well = Color(0xFF262C28),
    rule = Color(0xFF333A35),
    ruleStrong = Color(0xFF4D5650),
    ink = Color(0xFFE8EBE5),
    inkSoft = Color(0xFFB4BCB5),
    inkFaint = Color(0xFF8C958F),
    pine = Color(0xFF6FA88F),
    pineDeep = Color(0xFF9CCBB6),
    brick = Color(0xFFE08A7A),
    amber = Color(0xFFD9B659),
    onPine = Color(0xFF0E1411),
)

val LocalDcColors = staticCompositionLocalOf { LightTokens }

object Dc {
    val colors: DcColors
        @Composable get() = LocalDcColors.current
}

// ---------------------------------------------------------------
// Type: Newsreader for headings and big numbers, IBM Plex Sans for
// text, both bundled (variable fonts, the website's weights).
// ---------------------------------------------------------------

val Serif = FontFamily(
    Font(R.font.newsreader, FontWeight.Normal, variationSettings = FontVariation.Settings(FontVariation.weight(400))),
    Font(R.font.newsreader, FontWeight.Medium, variationSettings = FontVariation.Settings(FontVariation.weight(500))),
)

val Sans = FontFamily(
    Font(R.font.ibm_plex_sans, FontWeight.Normal, variationSettings = FontVariation.Settings(FontVariation.weight(400))),
    Font(R.font.ibm_plex_sans, FontWeight.Medium, variationSettings = FontVariation.Settings(FontVariation.weight(500))),
    Font(R.font.ibm_plex_sans, FontWeight.SemiBold, variationSettings = FontVariation.Settings(FontVariation.weight(600))),
)

/** globals.css's type steps (--step-0 … --step-5, at 16px = 1rem). */
object Steps {
    val step0 = 16.sp
    val step1 = 19.sp
    val step2 = 23.sp
    val step3 = 29.sp
    val step4 = 38.sp
    val step5 = 49.sp
}

private fun heading(size: androidx.compose.ui.unit.TextUnit) = TextStyle(
    fontFamily = Serif,
    fontWeight = FontWeight.Medium,
    fontSize = size,
    lineHeight = size * 1.18f,
    letterSpacing = (-0.012).em,
)

private val DcTypography = Typography(
    displayLarge = heading(Steps.step5),
    displayMedium = heading(Steps.step4),
    displaySmall = heading(Steps.step3),
    headlineLarge = heading(Steps.step4),
    headlineMedium = heading(Steps.step3),
    headlineSmall = heading(Steps.step2),
    titleLarge = heading(Steps.step2),
    titleMedium = TextStyle(fontFamily = Sans, fontWeight = FontWeight.SemiBold, fontSize = Steps.step1, lineHeight = 26.sp),
    titleSmall = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Medium, fontSize = 15.sp, lineHeight = 22.sp),
    bodyLarge = TextStyle(fontFamily = Sans, fontSize = Steps.step0, lineHeight = 25.6.sp),
    bodyMedium = TextStyle(fontFamily = Sans, fontSize = 15.sp, lineHeight = 23.sp),
    bodySmall = TextStyle(fontFamily = Sans, fontSize = 14.sp, lineHeight = 21.sp),
    labelLarge = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Medium, fontSize = 15.sp, lineHeight = 20.sp),
    labelMedium = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Medium, fontSize = 14.sp, lineHeight = 18.sp),
    labelSmall = TextStyle(fontFamily = Sans, fontWeight = FontWeight.Medium, fontSize = 13.sp, lineHeight = 16.sp),
)

/** globals.css --radius is 3px: restrained, nearly square. */
private val DcShapes = Shapes(
    extraSmall = RoundedCornerShape(3.dp),
    small = RoundedCornerShape(3.dp),
    medium = RoundedCornerShape(4.dp),
    large = RoundedCornerShape(6.dp),
    extraLarge = RoundedCornerShape(8.dp),
)

private fun scheme(t: DcColors, dark: Boolean): ColorScheme {
    val base = if (dark) darkColorScheme() else lightColorScheme()
    return base.copy(
        primary = t.pine,
        onPrimary = t.onPine,
        primaryContainer = t.well,
        onPrimaryContainer = t.ink,
        secondary = t.pineDeep,
        onSecondary = t.onPine,
        secondaryContainer = t.well,
        onSecondaryContainer = t.ink,
        tertiary = t.amber,
        background = t.paper,
        onBackground = t.ink,
        surface = t.paper,
        onSurface = t.ink,
        surfaceVariant = t.well,
        onSurfaceVariant = t.inkSoft,
        surfaceContainerLowest = t.paper,
        surfaceContainerLow = t.paperRaised,
        surfaceContainer = t.paperRaised,
        surfaceContainerHigh = t.paperRaised,
        surfaceContainerHighest = t.well,
        surfaceTint = Color.Transparent,
        outline = t.ruleStrong,
        outlineVariant = t.rule,
        error = t.brick,
        onError = t.onPine,
        inverseSurface = t.ink,
        inverseOnSurface = t.paper,
        inversePrimary = t.pine,
        scrim = Color(0x8C1A1F1C),
    )
}

@Composable
fun DebateCoachTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val tokens = if (darkTheme) DarkTokens else LightTokens
    CompositionLocalProvider(LocalDcColors provides tokens) {
        MaterialTheme(
            colorScheme = scheme(tokens, darkTheme),
            typography = DcTypography,
            shapes = DcShapes,
            content = content,
        )
    }
}
