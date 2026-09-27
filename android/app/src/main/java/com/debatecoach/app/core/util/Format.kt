package com.debatecoach.app.core.util

import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale
import kotlin.math.roundToLong

/** components/SpeechTrack.tsx formatClock: "m:ss". */
fun formatClock(seconds: Double): String {
    val safe = maxOf(0L, jsRound(seconds))
    return "${safe / 60}:${(safe % 60).toString().padStart(2, '0')}"
}

/** Math.round (ties toward +infinity). */
fun jsRound(x: Double): Long = if (x.isNaN()) 0 else Math.round(x)

fun parseInstant(iso: String): Instant? = try {
    Instant.parse(iso)
} catch (_: Exception) {
    try {
        java.time.OffsetDateTime.parse(iso).toInstant()
    } catch (_: Exception) {
        try {
            java.time.LocalDateTime.parse(iso).toInstant(ZoneOffset.UTC)
        } catch (_: Exception) {
            null
        }
    }
}

private fun localDate(iso: String, zone: ZoneId): LocalDate? = parseInstant(iso)?.atZone(zone)?.toLocalDate()

/** toLocaleDateString(undefined, {day: "numeric", month: "short", year: "numeric"}): the session list's date. */
fun formatRecordedShort(iso: String, locale: Locale = Locale.getDefault(), zone: ZoneId = ZoneId.systemDefault()): String =
    localDate(iso, zone)?.format(DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM).withLocale(locale)) ?: iso

/** toLocaleDateString(undefined, {day: "numeric", month: "long", year: "numeric"}): the report's date. */
fun formatRecordedLong(iso: String, locale: Locale = Locale.getDefault(), zone: ZoneId = ZoneId.systemDefault()): String =
    localDate(iso, zone)?.format(DateTimeFormatter.ofLocalizedDate(FormatStyle.LONG).withLocale(locale)) ?: iso

/** "Session of <date>", the session list's fallback name. */
fun sessionName(title: String?, createdAt: String): String =
    title?.takeIf { it.isNotEmpty() } ?: "Session of ${formatRecordedShort(createdAt)}"

// ----- lib/progress-report.ts (en-GB, fixed) -----

/** "Sun 27 Sept, 05:00": the next UTC midnight, in local time. */
fun formatNextAvailable(iso: String, zone: ZoneId = ZoneId.systemDefault()): String =
    parseInstant(iso)?.atZone(zone)?.format(DateTimeFormatter.ofPattern("EEE d MMM, HH:mm", Locale.UK)) ?: iso

/** A report's UTC day, "26 Sept 2026". */
fun formatReportDate(reportDate: String): String = try {
    LocalDate.parse(reportDate).format(DateTimeFormatter.ofPattern("d MMM yyyy", Locale.UK))
} catch (_: Exception) {
    reportDate
}

fun isFromToday(reportDate: String, now: Instant = Instant.now()): Boolean =
    reportDate == now.atZone(ZoneOffset.UTC).toLocalDate().toString()

/** "Compares your last N sessions. Generated today." */
fun reportCaption(used: Int, reportDate: String, now: Instant = Instant.now()): String {
    val whenText = if (isFromToday(reportDate, now)) "today" else "on ${formatReportDate(reportDate)}"
    return "Compares your last $used sessions. Generated $whenText."
}

// ----- lib/progress-chart.ts -----

/** en-GB "26 Sept". */
fun formatChartDate(iso: String, zone: ZoneId = ZoneId.systemDefault()): String =
    localDate(iso, zone)?.format(DateTimeFormatter.ofPattern("d MMM", Locale.UK)) ?: iso

fun roundScore(score: Double?): Long = if (score == null) 0 else score.roundToLong().let { jsRound(score) }
