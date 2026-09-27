package com.debatecoach.app.feature.report

import com.debatecoach.app.core.model.CorrelatedMoment
import com.debatecoach.app.core.model.FeedbackItem
import com.debatecoach.app.core.model.MomentObservation
import com.debatecoach.app.core.model.SCORE_ORDER
import com.debatecoach.app.core.model.SEVERITY_ORDER
import com.debatecoach.app.core.model.SessionReport
import com.debatecoach.app.core.model.VisualView
import com.debatecoach.app.core.util.formatClock
import java.util.Locale
import kotlin.math.roundToInt

/*
 * The report's logic, free of Compose so it can be tested and reused by
 * the PDF export: web/components/ReportView.tsx, SpeechTrack.tsx,
 * VisualDeliverySection.tsx and KeyMomentsList.tsx, word for word.
 */

const val MOTION_NOT_APPLIED_NOTE =
    "This session's coaching couldn't use your practice prompt, so it wasn't judged against the motion."

/** lib/motions.ts motionFallbackNote. */
fun motionFallbackNote(hasMotion: Boolean, notApplied: Boolean): String? = if (hasMotion && notApplied) MOTION_NOT_APPLIED_NOTE else null

// ----- Speech timeline -----

enum class MarkKind(val label: String) {
    PAUSE("Pause over one second"),
    FILLER("Filler word"),
    STUTTER("Stutter"),
    FALLACY("Flagged fallacy"),
}

data class Mark(val at: Double, val kind: MarkKind, val span: Double? = null)

/** The owner page's marks: pauses of a second or more, fillers, stutters, fallacies. */
fun marksFor(report: SessionReport): List<Mark> = buildList {
    for (pause in report.analysis.pauses) if (pause.duration >= 1) add(Mark(pause.start, MarkKind.PAUSE, pause.duration))
    for (f in report.rawMetrics.fillers?.instances.orEmpty()) f.start?.let { add(Mark(it, MarkKind.FILLER)) }
    for (s in report.rawMetrics.stutters?.instances.orEmpty()) s.start?.let { add(Mark(it, MarkKind.STUTTER)) }
    for (seg in report.speechContent.segments) if ("logical_fallacy" in seg.labels) add(Mark(seg.start, MarkKind.FALLACY))
}

fun trackDuration(report: SessionReport): Double =
    report.analysis.totalDuration ?: report.rawMetrics.speech?.totalDuration ?: 0.0

/** Ticks every 30 s, or every minute beyond four minutes. */
fun trackTicks(duration: Double): List<Double> {
    val safe = if (duration > 0) duration else 1.0
    val step = if (safe > 240) 60.0 else 30.0
    return generateSequence(0.0) { it + step }.takeWhile { it <= safe }.toList()
}

// ----- Figures -----

data class Figure(val value: String, val label: String)

fun figuresFor(report: SessionReport): List<Figure> {
    val speech = report.rawMetrics.speech
    return listOf(
        Figure(Math.round(report.scores["overall"] ?: 0.0).toString(), "Overall, out of 100"),
        Figure(Math.round(speech?.wordsPerMinute ?: 0.0).toString(), "Words per minute"),
        Figure(formatClock(speech?.speechDuration ?: 0.0), "Time actually speaking"),
        Figure((report.rawMetrics.fillers?.count ?: 0).toString(), "Filler words"),
        Figure((report.rawMetrics.pauses?.count ?: 0).toString(), "Pauses"),
        Figure((report.rawMetrics.stutters?.count ?: 0).toString(), "Stutters"),
    )
}

// ----- Findings -----

/** Categories that actually have findings, in score order: the filter buttons after "All". */
fun presentCategories(feedback: List<FeedbackItem>): List<String> = SCORE_ORDER.filter { c -> feedback.any { it.category == c } }

fun visibleFindings(feedback: List<FeedbackItem>, filter: String): List<FeedbackItem> =
    (if (filter == "all") feedback else feedback.filter { it.category == filter })
        .sortedBy { SEVERITY_ORDER.indexOf(it.severity).let { i -> if (i < 0) SEVERITY_ORDER.size else i } }

// ----- Visual delivery -----

enum class MetricFormat { RATIO, RATE, SECONDS, DEGREES, AMPLITUDE }

data class MetricInfo(val label: String, val definition: String, val format: MetricFormat)

val VISUAL_METRIC_INFO = mapOf(
    "face_tracked_ratio" to MetricInfo("Face visible", "Share of your speaking time your face was visible to the camera.", MetricFormat.RATIO),
    "camera_facing_ratio" to MetricInfo("Facing the camera", "Share of your speaking time spent facing the camera, measured from head direction and eye position.", MetricFormat.RATIO),
    "gaze_away_events_per_min" to MetricInfo("Looking away", "How often you looked away from the camera, per minute of speaking.", MetricFormat.RATE),
    "longest_gaze_away_s" to MetricInfo("Longest look away", "The longest single stretch you looked away from the camera.", MetricFormat.SECONDS),
    "head_down_ratio" to MetricInfo("Head down", "Share of your speaking time your head was tilted down.", MetricFormat.RATIO),
    "head_motion_median_deg_s" to MetricInfo("Head movement", "Your typical head movement speed.", MetricFormat.DEGREES),
    "hands_visible_ratio" to MetricInfo("Hands visible", "Share of your speaking time your hands were visible on camera.", MetricFormat.RATIO),
    "gesture_rate_per_min" to MetricInfo("Gesture rate", "How often you made a hand gesture, per minute of speaking.", MetricFormat.RATE),
    "gesture_amplitude_median" to MetricInfo("Gesture size", "The typical size of your hand gestures.", MetricFormat.AMPLITUDE),
    "hands_still_longest_s" to MetricInfo("Longest still stretch", "The longest stretch your hands stayed still.", MetricFormat.SECONDS),
    "hands_still_ratio" to MetricInfo("Hands still", "Share of your speaking time your hands stayed still.", MetricFormat.RATIO),
)

val VISUAL_METRIC_ORDER = listOf(
    "face_tracked_ratio", "camera_facing_ratio", "gaze_away_events_per_min", "longest_gaze_away_s", "head_down_ratio",
    "head_motion_median_deg_s", "hands_visible_ratio", "gesture_rate_per_min", "gesture_amplitude_median",
    "hands_still_longest_s", "hands_still_ratio",
)

val CAMERA_FACING_METRIC_KEYS = setOf("camera_facing_ratio", "gaze_away_events_per_min", "longest_gaze_away_s")
private val FACE_GATED_KEYS = setOf("camera_facing_ratio", "gaze_away_events_per_min", "longest_gaze_away_s", "head_down_ratio", "head_motion_median_deg_s")
private val HAND_GATED_KEYS = setOf("gesture_rate_per_min", "gesture_amplitude_median", "hands_still_longest_s", "hands_still_ratio")

val CONFIDENCE_LABEL = mapOf("high" to "High confidence", "medium" to "Medium confidence", "low" to "Low confidence")

val VISUAL_WARNING_LABEL = mapOf(
    "hands_mostly_out_of_frame" to "Your hands were out of frame for most of the speech.",
    "face_often_out_of_frame" to "Your face was out of frame for a large part of the speech.",
    "calibration_skipped" to "Camera calibration was skipped, so facing measurements are less certain.",
    "calibration_unstable" to "Camera calibration was unstable, so facing measurements are less certain.",
    "second_person_detected" to "Another person was visible on camera for part of the speech.",
    "analysis_degraded" to "Analysis quality dropped partway through, likely because your device slowed down.",
    "high_clock_uncertainty" to "Timing between audio and video was less precise than usual for part of this session.",
    "in_room_context" to "This session was marked as practising with someone in the room, so camera-facing isn't shown.",
)

val VIDEO_UNAVAILABLE_REASON_LABEL = mapOf(
    "camera_denied" to "Camera access was denied.",
    "unsupported" to "Your browser or device doesn't support visual analysis.",
    "model_load_failed" to "The on-device vision models couldn't be loaded.",
    "device_too_slow" to "Your device couldn't keep up with visual analysis.",
    "user_opted_out" to "Visual analysis wasn't turned on for this session.",
    "upload_failed" to "The captured visual data couldn't be uploaded.",
    "face_not_found" to "Your face couldn't be found during setup.",
    "duration_mismatch" to "The captured visual data didn't match the length of the recording.",
)

fun formatMetric(value: Double, format: MetricFormat): String = when (format) {
    MetricFormat.RATIO -> "${Math.round(value * 100)}%"
    MetricFormat.RATE -> "${"%.1f".format(Locale.US, value)}/min"
    MetricFormat.SECONDS -> "${"%.1f".format(Locale.US, value)}s"
    MetricFormat.DEGREES -> "${"%.1f".format(Locale.US, value)}°/s"
    MetricFormat.AMPLITUDE -> "%.2f".format(Locale.US, value)
}

data class MetricRow(val label: String, val value: String, val confidence: String?, val highConfidence: Boolean, val definition: String)

sealed interface VisualSection {
    data object Hidden : VisualSection
    data class Message(val text: String) : VisualSection
    data class Metrics(
        val rows: List<MetricRow>,
        val faceMessage: String?,
        val handsMessage: String?,
        val warnings: List<String>,
        val coachingFailed: Boolean,
        val sessionFeedback: List<Pair<String, String?>>,
    ) : VisualSection
}

private fun unavailableMessage(group: String, status: String): String {
    if (group == "hands") {
        if (status == "disabled_by_tier") return "Hand tracking was turned off for this session because your device couldn't keep up, so gesture metrics aren't available."
        if (status == "not_measured") return "There wasn't enough usable video to measure your gestures for this session."
        return "Gestures could not be assessed because your hands were out of frame for most of the speech. Sit a little further back next time."
    }
    if (status == "not_measured") return "There wasn't enough usable video to measure camera-facing and head position for this session."
    return "Your face wasn't visible enough of the time to measure camera-facing and head position. Try sitting a little closer or improving the lighting next time."
}

/** VisualDeliverySection: which state to show, with its wording. */
fun visualSection(report: VisualView): VisualSection {
    when (val status = report.videoAnalysisStatus) {
        "not_requested" -> return VisualSection.Hidden
        "awaiting_upload", "received", "processing" -> return VisualSection.Message("Visual analysis in progress.")
        "unavailable" -> {
            val reason = report.videoUnavailableReason?.let { VIDEO_UNAVAILABLE_REASON_LABEL[it] } ?: "Visual analysis wasn't available for this session."
            return VisualSection.Message("$reason Turn on visual feedback before your next recording to see it here.")
        }
        "failed" -> return VisualSection.Message("Visual analysis couldn't be completed for this session. Your speech feedback is unaffected.")
        "insufficient_data" -> return VisualSection.Message("There wasn't enough usable video from this session to measure delivery. Your speech feedback is unaffected.")
        else -> if (status != "processed" && status != "partial") return VisualSection.Hidden
    }
    val analysis = report.videoAnalysis ?: return VisualSection.Hidden
    val inRoom = analysis.quality.context.setting == "in_room_practice"
    val metrics = analysis.metrics
    val rows = VISUAL_METRIC_ORDER.filter { key -> !(inRoom && key in CAMERA_FACING_METRIC_KEYS) && key in metrics }
    val faceBlocked = rows.firstOrNull { it in FACE_GATED_KEYS && metrics.getValue(it).status != "ok" }
    val handsBlocked = rows.firstOrNull { it in HAND_GATED_KEYS && metrics.getValue(it).status != "ok" }
    val okRows = rows.filter { metrics.getValue(it).status == "ok" }.mapNotNull { key ->
        val metric = metrics.getValue(key)
        val info = VISUAL_METRIC_INFO[key] ?: return@mapNotNull null
        val value = metric.value ?: return@mapNotNull null
        MetricRow(info.label, formatMetric(value, info.format), metric.confidence?.let { CONFIDENCE_LABEL[it] }, metric.confidence == "high", info.definition)
    }
    return VisualSection.Metrics(
        rows = okRows,
        faceMessage = faceBlocked?.let { unavailableMessage("face", metrics.getValue(it).status) },
        handsMessage = handsBlocked?.let { unavailableMessage("hands", metrics.getValue(it).status) },
        warnings = analysis.quality.warnings.map { VISUAL_WARNING_LABEL[it] ?: it },
        coachingFailed = report.visualCoachingStatus == "failed",
        sessionFeedback = report.visualFeedback?.items.orEmpty().filter { it.momentId == null }.map { it.coaching to it.polarity },
    )
}

// ----- Key moments -----

private val UNIT_TYPE_LABEL = mapOf("claim" to "Claim", "rebuttal" to "Rebuttal", "conclusion" to "Conclusion")

fun describeObservation(obs: MomentObservation): String? {
    if (obs.kind == "event" && obs.type == "gaze_away") {
        return "Looked ${obs.direction ?: "away"} for ${"%.1f".format(Locale.US, obs.durationS ?: 0.0)}s"
    }
    val unit = obs.unitValue
    if (obs.metric == "camera_facing_ratio" && unit != null) {
        val u = Math.round(unit * 100)
        val session = obs.sessionValue?.let { Math.round(it * 100) }
        return if (session != null) "Facing the camera $u% of this part, versus $session% across the whole session" else "Facing the camera $u% of this part"
    }
    if (obs.metric == "head_down_fraction" && unit != null) return "Head down for ${Math.round(unit * 100)}% of this part"
    if (obs.metric == "hands_still_fraction" && unit != null) return "Hands still for ${Math.round(unit * 100)}% of this part"
    if (obs.metric == "hand_activity_ratio" && unit != null) return "Hand movement ${"%.1f".format(Locale.US, unit)}× your typical pace"
    return null
}

data class MomentEntry(val moment: CorrelatedMoment, val coaching: String?, val key: String) {
    /** "0:42–1:05. Claim" */
    val meta: String
        get() = "${formatClock(moment.start)}–${formatClock(moment.end)}" +
            (moment.anchor.type?.let { UNIT_TYPE_LABEL[it] }?.let { ". $it" } ?: "")
    val facts: List<String> get() = moment.observations.mapNotNull(::describeObservation)
    val positive: Boolean get() = moment.polarity == "strength"
}

/** Coached moments when coaching succeeded; otherwise the raw moments by salience. */
fun keyMoments(report: VisualView): List<MomentEntry> {
    val moments = report.correlatedMoments.orEmpty()
    if (moments.isEmpty()) return emptyList()
    val byId = moments.associateBy { it.id }
    val items = report.visualFeedback?.items.orEmpty()
    val coachingById = items.filter { it.momentId != null }.associateBy { it.momentId!! }
    val showRaw = report.visualCoachingStatus != "completed" || coachingById.isEmpty()
    return if (showRaw) {
        moments.sortedByDescending { it.salience }.map { MomentEntry(it, null, it.id) }
    } else {
        items.filter { it.momentId != null && it.momentId in byId }.map { MomentEntry(byId.getValue(it.momentId!!), it.coaching, it.id) }
    }
}

fun percent(value: Double): Int = (value * 100).roundToInt()
