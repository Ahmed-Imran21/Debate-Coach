package com.debatecoach.app.ui.theme

import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.TextUnit
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.debatecoach.app.R

/*
 * The design system. The website's brand (web/app/globals.css: paper,
 * ink, pine, brick, amber; Newsreader and IBM Plex Sans; a calm,
 * serious tone) mapped onto Material 3's roles, so every Material
 * component picks it up the native way, in light and dark.
 *
 * Screens use MaterialTheme.colorScheme / typography / shapes plus the
 * scales below (Space, Radius, Elevation, Motion). DcColors keeps the
 * brand's named colours for the few places that mean something by
 * colour (severity, timeline marks, the chart).
 */

// ---------------------------------------------------------------
// Brand palette (named, for meaning-by-colour)
// ---------------------------------------------------------------

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
    /** Text on a pine surface. */
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
    inkFaint = Color(0xFF6E7872),
    pine = Color(0xFF2E5E4E),
    pineDeep = Color(0xFF1F4437),
    brick = Color(0xFF9A3324),
    amber = Color(0xFF8A6A12),
    onPine = Color(0xFFFFFFFF),
)

val DarkTokens = DcColors(
    paper = Color(0xFF121614),
    paperRaised = Color(0xFF1A1E1C),
    well = Color(0xFF262B28),
    rule = Color(0xFF3A413C),
    ruleStrong = Color(0xFF59625C),
    ink = Color(0xFFE3E7E1),
    inkSoft = Color(0xFFBEC7C0),
    inkFaint = Color(0xFF9AA39C),
    pine = Color(0xFF8FCBB1),
    pineDeep = Color(0xFFB3E3CD),
    brick = Color(0xFFFFB4A6),
    amber = Color(0xFFE3C46B),
    onPine = Color(0xFF00382A),
)

val LocalDcColors = staticCompositionLocalOf { LightTokens }

object Dc {
    val colors: DcColors
        @Composable get() = LocalDcColors.current
}

// ---------------------------------------------------------------
// Material 3 colour roles
// ---------------------------------------------------------------

/**
 * Light: paper is the app's surface, paper-raised the lowest container
 * (cards read as a sheet laid on the page, as on the website), and the
 * containers above it step down through the well tones. Text colours
 * keep AA contrast on every surface: secondary text is ink-soft, never
 * ink-faint.
 */
private val LightScheme: ColorScheme = lightColorScheme(
    primary = Color(0xFF2E5E4E),
    onPrimary = Color(0xFFFFFFFF),
    primaryContainer = Color(0xFFCDE7DA),
    onPrimaryContainer = Color(0xFF0B2A1F),
    inversePrimary = Color(0xFF8FCBB1),
    secondary = Color(0xFF4D6158),
    onSecondary = Color(0xFFFFFFFF),
    secondaryContainer = Color(0xFFD9E4DD),
    onSecondaryContainer = Color(0xFF1A1F1C),
    tertiary = Color(0xFF7A5D0C),
    onTertiary = Color(0xFFFFFFFF),
    tertiaryContainer = Color(0xFFF4E2B0),
    onTertiaryContainer = Color(0xFF261A00),
    error = Color(0xFF9A3324),
    onError = Color(0xFFFFFFFF),
    errorContainer = Color(0xFFF7DAD4),
    onErrorContainer = Color(0xFF3C0A04),
    background = Color(0xFFEDEFEA),
    onBackground = Color(0xFF1A1F1C),
    surface = Color(0xFFEDEFEA),
    onSurface = Color(0xFF1A1F1C),
    surfaceVariant = Color(0xFFE2E5DD),
    onSurfaceVariant = Color(0xFF4F5A54),
    surfaceTint = Color(0xFF2E5E4E),
    inverseSurface = Color(0xFF2E3430),
    inverseOnSurface = Color(0xFFEEF1EC),
    outline = Color(0xFF737D77),
    outlineVariant = Color(0xFFC9CEC4),
    scrim = Color(0xFF000000),
    surfaceBright = Color(0xFFF5F6F3),
    surfaceDim = Color(0xFFD9DDD5),
    surfaceContainerLowest = Color(0xFFFAFBF8),
    surfaceContainerLow = Color(0xFFF5F6F3),
    surfaceContainer = Color(0xFFE8EBE4),
    surfaceContainerHigh = Color(0xFFE2E5DD),
    surfaceContainerHighest = Color(0xFFDCE0D7),
)

/** Dark: a deep green-black paper, warm off-white ink, pine lifted for contrast. */
private val DarkScheme: ColorScheme = darkColorScheme(
    primary = Color(0xFF8FCBB1),
    onPrimary = Color(0xFF00382A),
    primaryContainer = Color(0xFF1F4C3D),
    onPrimaryContainer = Color(0xFFB3E9D0),
    inversePrimary = Color(0xFF2E5E4E),
    secondary = Color(0xFFB3CCBF),
    onSecondary = Color(0xFF1E352B),
    secondaryContainer = Color(0xFF354B41),
    onSecondaryContainer = Color(0xFFD0E8DA),
    tertiary = Color(0xFFE3C46B),
    onTertiary = Color(0xFF3D2F00),
    tertiaryContainer = Color(0xFF584400),
    onTertiaryContainer = Color(0xFFFFE08F),
    error = Color(0xFFFFB4A6),
    onError = Color(0xFF561E14),
    errorContainer = Color(0xFF73332A),
    onErrorContainer = Color(0xFFFFDAD4),
    background = Color(0xFF121614),
    onBackground = Color(0xFFE3E7E1),
    surface = Color(0xFF121614),
    onSurface = Color(0xFFE3E7E1),
    surfaceVariant = Color(0xFF3F4843),
    onSurfaceVariant = Color(0xFFBEC7C0),
    surfaceTint = Color(0xFF8FCBB1),
    inverseSurface = Color(0xFFE3E7E1),
    inverseOnSurface = Color(0xFF2E3430),
    outline = Color(0xFF89928B),
    outlineVariant = Color(0xFF3F4843),
    scrim = Color(0xFF000000),
    surfaceBright = Color(0xFF383D3A),
    surfaceDim = Color(0xFF121614),
    surfaceContainerLowest = Color(0xFF0D100E),
    surfaceContainerLow = Color(0xFF1A1E1C),
    surfaceContainer = Color(0xFF1E2320),
    surfaceContainerHigh = Color(0xFF282D2A),
    surfaceContainerHighest = Color(0xFF333835),
)

// ---------------------------------------------------------------
// Type: Newsreader for display, headlines and big numbers; IBM Plex
// Sans for everything read or tapped. Material 3's scale and rhythm.
// ---------------------------------------------------------------

val Serif = FontFamily(
    Font(R.font.newsreader, FontWeight.Normal, variationSettings = FontVariation.Settings(FontVariation.weight(400))),
    Font(R.font.newsreader, FontWeight.Medium, variationSettings = FontVariation.Settings(FontVariation.weight(500))),
    Font(R.font.newsreader, FontWeight.SemiBold, variationSettings = FontVariation.Settings(FontVariation.weight(600))),
)

val Sans = FontFamily(
    Font(R.font.ibm_plex_sans, FontWeight.Normal, variationSettings = FontVariation.Settings(FontVariation.weight(400))),
    Font(R.font.ibm_plex_sans, FontWeight.Medium, variationSettings = FontVariation.Settings(FontVariation.weight(500))),
    Font(R.font.ibm_plex_sans, FontWeight.SemiBold, variationSettings = FontVariation.Settings(FontVariation.weight(600))),
)

private fun serif(size: TextUnit, line: TextUnit, weight: FontWeight = FontWeight.Medium) = TextStyle(
    fontFamily = Serif,
    fontWeight = weight,
    fontSize = size,
    lineHeight = line,
    letterSpacing = (-0.01).em,
)

private fun sans(size: TextUnit, line: TextUnit, weight: FontWeight = FontWeight.Normal, tracking: Float = 0f) = TextStyle(
    fontFamily = Sans,
    fontWeight = weight,
    fontSize = size,
    lineHeight = line,
    letterSpacing = tracking.em,
)

val DcTypography = Typography(
    displayLarge = serif(57.sp, 64.sp),
    displayMedium = serif(45.sp, 52.sp),
    displaySmall = serif(36.sp, 44.sp),
    headlineLarge = serif(32.sp, 40.sp),
    headlineMedium = serif(28.sp, 36.sp),
    headlineSmall = serif(24.sp, 32.sp),
    titleLarge = serif(22.sp, 28.sp),
    titleMedium = sans(16.sp, 24.sp, FontWeight.Medium, 0.01f),
    titleSmall = sans(14.sp, 20.sp, FontWeight.Medium, 0.006f),
    bodyLarge = sans(16.sp, 24.sp),
    bodyMedium = sans(14.sp, 20.sp, tracking = 0.01f),
    bodySmall = sans(12.sp, 16.sp, tracking = 0.02f),
    labelLarge = sans(14.sp, 20.sp, FontWeight.Medium, 0.006f),
    labelMedium = sans(12.sp, 16.sp, FontWeight.Medium, 0.03f),
    labelSmall = sans(11.sp, 16.sp, FontWeight.Medium, 0.04f),
)

/** A big number (a score, a figure) in the serif, at any size. */
fun numberStyle(size: TextUnit, weight: FontWeight = FontWeight.Medium) =
    TextStyle(fontFamily = Serif, fontWeight = weight, fontSize = size, lineHeight = size * 1.1f, letterSpacing = (-0.02).em)

// ---------------------------------------------------------------
// Scales: one spacing, radius, elevation and motion system
// ---------------------------------------------------------------

/** 4dp grid. */
object Space {
    val xxs: Dp = 2.dp
    val xs: Dp = 4.dp
    val s: Dp = 8.dp
    val m: Dp = 12.dp
    val l: Dp = 16.dp
    val xl: Dp = 24.dp
    val xxl: Dp = 32.dp
    val xxxl: Dp = 48.dp

    /** Screen edge margin: 16dp on phones, 24dp from medium width up. */
    val gutter: Dp
        @Composable get() = if (LocalWidthClass.current == WidthClass.COMPACT) l else xl

    /** Minimum touch target. */
    val touch: Dp = 48.dp

    /** Reading width for single-column content on wide screens. */
    val readingWidth: Dp = 720.dp
}

/** Corner radii: restrained, a notch tighter than Material's defaults, as the website's 3px corners suggest. */
object Radius {
    val xs: Dp = 4.dp
    val s: Dp = 8.dp
    val m: Dp = 12.dp
    val l: Dp = 16.dp
    val xl: Dp = 24.dp
}

val DcShapes = Shapes(
    extraSmall = RoundedCornerShape(Radius.xs),
    small = RoundedCornerShape(Radius.s),
    medium = RoundedCornerShape(Radius.m),
    large = RoundedCornerShape(Radius.l),
    extraLarge = RoundedCornerShape(Radius.xl),
)

/** Tonal elevation levels (Material 3): surfaces lift by tone, rarely by shadow. */
object Elevation {
    val level0: Dp = 0.dp
    val level1: Dp = 1.dp
    val level2: Dp = 3.dp
    val level3: Dp = 6.dp
}

/** Material 3 motion: durations and the emphasized easing curves. */
object Motion {
    const val SHORT = 150
    const val MEDIUM = 300
    const val LONG = 450
    val Emphasized = CubicBezierEasing(0.2f, 0f, 0f, 1f)
    val EmphasizedDecelerate = CubicBezierEasing(0.05f, 0.7f, 0.1f, 1f)
    val EmphasizedAccelerate = CubicBezierEasing(0.3f, 0f, 0.8f, 0.15f)
}

// ---------------------------------------------------------------
// Window size classes (Material's breakpoints: 600dp, 840dp)
// ---------------------------------------------------------------

enum class WidthClass { COMPACT, MEDIUM, EXPANDED }

fun widthClassOf(width: Dp): WidthClass = when {
    width < 600.dp -> WidthClass.COMPACT
    width < 840.dp -> WidthClass.MEDIUM
    else -> WidthClass.EXPANDED
}

val LocalWidthClass = compositionLocalOf { WidthClass.COMPACT }

@Composable
fun DebateCoachTheme(darkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalDcColors provides if (darkTheme) DarkTokens else LightTokens) {
        MaterialTheme(
            colorScheme = if (darkTheme) DarkScheme else LightScheme,
            typography = DcTypography,
            shapes = DcShapes,
            content = content,
        )
    }
}
