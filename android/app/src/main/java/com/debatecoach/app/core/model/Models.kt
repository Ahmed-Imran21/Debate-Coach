package com.debatecoach.app.core.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

/*
 * The backend's JSON, as web/lib/types.ts describes it. Field names are
 * the wire names. Status-like values stay plain strings so a value this
 * build doesn't know yet never breaks decoding; the label maps below
 * turn them into words.
 */

@Serializable
data class Tokens(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("token_type") val tokenType: String = "bearer",
)

@Serializable
data class User(
    val id: String,
    val email: String,
    @SerialName("first_name") val firstName: String,
    @SerialName("last_name") val lastName: String,
    @SerialName("created_at") val createdAt: String,
)

@Serializable
data class SignupRequest(
    val email: String,
    val password: String,
    @SerialName("first_name") val firstName: String,
    @SerialName("last_name") val lastName: String,
    /** The two sign-up checkboxes; the backend refuses a sign-up without both. */
    @SerialName("accepted_privacy_policy") val acceptedPrivacyPolicy: Boolean,
    @SerialName("accepted_terms") val acceptedTerms: Boolean,
)

@Serializable
data class LoginRequest(val email: String, val password: String)

@Serializable
data class RefreshRequest(@SerialName("refresh_token") val refreshToken: String)

@Serializable
data class DeleteAccountRequest(val password: String)

@Serializable
data class Motion(val id: String, val title: String, val description: String)

@Serializable
data class SessionSummary(
    val id: String,
    val title: String? = null,
    val status: String,
    val shared: Boolean = false,
    val motion: Motion? = null,
    val progress: Double = 0.0,
    @SerialName("queue_wait_seconds") val queueWaitSeconds: Double? = null,
    @SerialName("overall_score") val overallScore: Double? = null,
    @SerialName("duration_seconds") val durationSeconds: Double? = null,
    @SerialName("words_per_minute") val wordsPerMinute: Double? = null,
    @SerialName("feedback_count") val feedbackCount: Int? = null,
    @SerialName("error_message") val errorMessage: String? = null,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String? = null,
    @SerialName("video_analysis_status") val videoAnalysisStatus: String = "not_requested",
    @SerialName("video_unavailable_reason") val videoUnavailableReason: String? = null,
    @SerialName("visual_coaching_status") val visualCoachingStatus: String = "not_requested",
)

@Serializable
data class SessionCreateRequest(
    @SerialName("content_type") val contentType: String,
    val title: String?,
    @SerialName("video_analysis") val videoAnalysis: String? = null,
    @SerialName("motion_id") val motionId: String? = null,
)

@Serializable
data class SessionCreated(
    val id: String,
    val status: String,
    @SerialName("upload_url") val uploadUrl: String,
    @SerialName("upload_headers") val uploadHeaders: Map<String, String>,
    @SerialName("expires_in_seconds") val expiresInSeconds: Int = 0,
    @SerialName("video_analysis_status") val videoAnalysisStatus: String = "not_requested",
)

@Serializable
data class VideoFinalize(val status: String, val reason: String? = null)

@Serializable
data class SessionStartRequest(val video: VideoFinalize)

@Serializable
data class VisualSignalsAck(val status: String, val frames: Int)

@Serializable
data class FeedbackItem(
    val category: String,
    val title: String,
    val issue: String,
    val severity: String,
    val evidence: List<String> = emptyList(),
    val explanation: String? = null,
    val recommendation: String? = null,
)

@Serializable
data class SpeechStats(
    @SerialName("total_duration") val totalDuration: Double? = null,
    @SerialName("speech_duration") val speechDuration: Double? = null,
    @SerialName("words_per_minute") val wordsPerMinute: Double? = null,
)

@Serializable
data class CountStats(val count: Int? = null)

@Serializable
data class TimedInstance(val word: String? = null, val start: Double? = null)

@Serializable
data class InstanceStats(val count: Int? = null, val instances: List<TimedInstance> = emptyList())

@Serializable
data class RawMetrics(
    val speech: SpeechStats? = null,
    val pauses: CountStats? = null,
    val fillers: InstanceStats? = null,
    val stutters: InstanceStats? = null,
)

@Serializable
data class SpeechSegment(val start: Double, val end: Double = 0.0, val text: String = "", val labels: List<String> = emptyList())

@Serializable
data class SpeechContent(val segments: List<SpeechSegment> = emptyList())

@Serializable
data class PauseSpan(val start: Double, val end: Double = 0.0, val duration: Double)

@Serializable
data class AudioAnalysis(
    @SerialName("total_duration") val totalDuration: Double? = null,
    val pauses: List<PauseSpan> = emptyList(),
)

// ----- Visual view (the subset VisualDeliverySection/KeyMomentsList read) -----

@Serializable
data class VisualMetric(val status: String, val value: Double? = null, val confidence: String? = null)

@Serializable
data class VisualContext(val setting: String = "camera_audience")

@Serializable
data class VisualQuality(val context: VisualContext = VisualContext(), val warnings: List<String> = emptyList())

@Serializable
data class VideoAnalysisView(val quality: VisualQuality = VisualQuality(), val metrics: Map<String, VisualMetric> = emptyMap())

@Serializable
data class MomentObservation(
    val id: String,
    val kind: String,
    val type: String? = null,
    @SerialName("duration_s") val durationS: Double? = null,
    val direction: String? = null,
    val metric: String? = null,
    @SerialName("unit_value") val unitValue: Double? = null,
    @SerialName("session_value") val sessionValue: Double? = null,
)

@Serializable
data class MomentAnchor(val type: String? = null)

@Serializable
data class CorrelatedMoment(
    val id: String,
    val polarity: String,
    val anchor: MomentAnchor = MomentAnchor(),
    val start: Double,
    val end: Double,
    @SerialName("excerpt_text") val excerptText: String = "",
    val observations: List<MomentObservation> = emptyList(),
    val salience: Double = 0.0,
)

@Serializable
data class VisualFeedbackItem(
    val id: String,
    val category: String = "",
    val polarity: String,
    @SerialName("moment_id") val momentId: String? = null,
    val coaching: String,
)

@Serializable
data class VisualFeedbackDocument(@SerialName("visual_feedback") val items: List<VisualFeedbackItem> = emptyList())

/** What the visual components read; the owner's report and the shared report both carry it. */
interface VisualView {
    val videoAnalysisStatus: String
    val videoUnavailableReason: String?
    val visualCoachingStatus: String
    val videoAnalysis: VideoAnalysisView?
    val correlatedMoments: List<CorrelatedMoment>?
    val visualFeedback: VisualFeedbackDocument?
}

@Serializable
data class SessionReport(
    val id: String,
    val title: String? = null,
    val status: String,
    val motion: Motion? = null,
    @SerialName("motion_not_applied") val motionNotApplied: Boolean = false,
    @SerialName("created_at") val createdAt: String,
    /** A category is null when it wasn't scored: rebuttal with nothing to rebut. */
    val scores: Map<String, Double?> = emptyMap(),
    val feedback: List<FeedbackItem> = emptyList(),
    @SerialName("raw_metrics") val rawMetrics: RawMetrics = RawMetrics(),
    @SerialName("speech_content") val speechContent: SpeechContent = SpeechContent(),
    val analysis: AudioAnalysis = AudioAnalysis(),
    @SerialName("audio_url") val audioUrl: String? = null,
    @SerialName("video_analysis_status") override val videoAnalysisStatus: String = "not_requested",
    @SerialName("video_unavailable_reason") override val videoUnavailableReason: String? = null,
    @SerialName("visual_coaching_status") override val visualCoachingStatus: String = "not_requested",
    @SerialName("video_analysis") override val videoAnalysis: VideoAnalysisView? = null,
    @SerialName("correlated_moments") override val correlatedMoments: List<CorrelatedMoment>? = null,
    @SerialName("visual_feedback") override val visualFeedback: VisualFeedbackDocument? = null,
) : VisualView

// ----- Progress -----

@Serializable
data class ProgressPoint(
    @SerialName("session_id") val sessionId: String,
    @SerialName("created_at") val createdAt: String,
    val title: String? = null,
    val score: Double? = null,
)

@Serializable
data class ProgressReportCreate(@SerialName("session_count") val sessionCount: Int)

@Serializable
data class ProgressReport(
    val id: String,
    @SerialName("report_date") val reportDate: String,
    @SerialName("created_at") val createdAt: String,
    @SerialName("session_count_requested") val sessionCountRequested: Int,
    @SerialName("session_count_used") val sessionCountUsed: Int,
    val bullets: List<String>,
)

@Serializable
data class LatestProgressReport(
    val report: ProgressReport? = null,
    @SerialName("can_generate") val canGenerate: Boolean,
    @SerialName("next_available_at") val nextAvailableAt: String? = null,
)

// ----- Sharing -----

@Serializable
data class ShareStatus(val sharing: Boolean, @SerialName("created_at") val createdAt: String? = null)

@Serializable
data class ShareCreated(val token: String, @SerialName("created_at") val createdAt: String)

@Serializable
data class ErrorBody(val detail: JsonElement? = null)

// ---------------------------------------------------------------
// Labels (web/lib/types.ts)
// ---------------------------------------------------------------

val STATUS_LABEL: Map<String, String> = mapOf(
    "created" to "Waiting for a recording",
    "queued" to "Queued",
    "converting" to "Preparing audio",
    "transcribing" to "Transcribing",
    "analyzing_audio" to "Measuring pauses",
    "calculating_metrics" to "Counting delivery metrics",
    "analyzing_speech" to "Reading the argument",
    "coaching" to "Writing feedback",
    "completed" to "Ready",
    "failed" to "Failed",
)

fun statusLabel(status: String): String = STATUS_LABEL[status] ?: status

val TERMINAL = setOf("completed", "failed")

val CATEGORY_LABEL: Map<String, String> = linkedMapOf(
    "quantitative" to "Delivery",
    "argumentation" to "Argumentation",
    "rebuttal" to "Rebuttal",
    "structure" to "Structure",
    "persuasion" to "Persuasion",
    "logic" to "Logic",
)

val SCORE_ORDER = listOf("quantitative", "argumentation", "rebuttal", "structure", "persuasion", "logic")

val SEVERITY_ORDER = listOf("high", "medium", "low", "positive")

val SEVERITY_LABEL = mapOf(
    "high" to "Needs work",
    "medium" to "Worth fixing",
    "low" to "Minor",
    "positive" to "Working well",
)
