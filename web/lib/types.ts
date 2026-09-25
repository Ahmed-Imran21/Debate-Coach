export type SessionStatus =
  | "created"
  | "queued"
  | "converting"
  | "transcribing"
  | "analyzing_audio"
  | "calculating_metrics"
  | "analyzing_speech"
  | "coaching"
  | "completed"
  | "failed";

export type Severity = "high" | "medium" | "low" | "positive";

export type Category =
  | "quantitative"
  | "argumentation"
  | "rebuttal"
  | "structure"
  | "persuasion"
  | "logic";

export interface Tokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  created_at: string;
}

/** video_analysis_status values (app/models/video_analysis.py); "not_requested" when the session never asked for it. */
export type VideoAnalysisStatus =
  | "not_requested"
  | "awaiting_upload"
  | "received"
  | "processing"
  | "processed"
  | "partial"
  | "insufficient_data"
  | "unavailable"
  | "failed";

export type VisualCoachingStatus = "not_requested" | "pending" | "completed" | "failed";

/** visual_analysis/metrics.py's status enum. When not "ok", value/confidence are null. */
export type VisualMetricStatus =
  | "ok"
  | "insufficient_coverage"
  | "not_measured"
  | "disabled_by_tier";

export type VisualConfidence = "high" | "medium" | "low";

/** One row of the 11-metric table (visual_analysis/metrics.py), keyed by metric name in VideoAnalysisResult.metrics. */
export interface VisualMetric {
  key: string;
  value: number | null;
  unit: string;
  basis: string;
  coverage: number | null;
  confidence: VisualConfidence | null;
  status: VisualMetricStatus;
  definition_version: string;
  note?: string;
}

export type VisualEventType =
  | "gaze_away"
  | "head_down"
  | "gesture"
  | "hands_still"
  | "face_lost"
  | "second_person"
  | "analysis_degraded";

/** visual_analysis/events.py's event shape. */
export interface VisualEvent {
  id: string;
  type: VisualEventType;
  start: number;
  end: number;
  confidence: VisualConfidence;
  attributes: Record<string, unknown>;
}

/** visual_analysis/pipeline.py's quality summary. */
export interface VideoAnalysisQuality {
  analyzed_duration_s: number;
  speaking_duration_s: number;
  face_tracked_ratio: number | null;
  hands_visible_ratio: {
    any: number | null;
    left: number | null;
    right: number | null;
  };
  effective_fps: { face_median: number; hands_median: number };
  second_person_ratio: number | null;
  calibration: {
    performed: boolean;
    stability: number;
    right_hand_check: string;
  };
  context: {
    setting: "camera_audience" | "in_room_practice";
    uses_notes: boolean;
  };
  clock_uncertainty_ms: number;
  warnings: string[];
}

/** video_analysis.json: visual_analysis/pipeline.py's VideoAnalysisResult.to_dict(). */
export interface VideoAnalysisResult {
  schema: string;
  schema_version: string;
  metrics_version: string;
  session_id: string;
  computed_at: string;
  source_summary: {
    platform: string;
    runtime_version: string;
    delegate: string;
    device_tier: string;
  };
  status: "complete" | "partial" | "insufficient_data" | "unavailable" | "failed";
  unavailable_reason: string | null;
  quality: VideoAnalysisQuality;
  /** Keyed by metric name, e.g. metrics.camera_facing_ratio. */
  metrics: Record<string, VisualMetric>;
  events: VisualEvent[];
  series: {
    resolution_s: number;
    camera_facing: Array<number | null>;
    hand_activity: Array<number | null>;
    head_motion: Array<number | null>;
  };
}

/** One observation inside a CorrelatedMoment (session_timeline/correlation.py). */
export interface MomentObservation {
  id: string;
  kind: "event" | "metric";
  // kind: "event"
  event_ref?: string;
  type?: string;
  duration_s?: number;
  direction?: string;
  // kind: "metric"
  metric?: string;
  unit_value?: number;
  session_value?: number | null;
}

/** session_timeline/correlation.py's moment shape. */
export interface CorrelatedMoment {
  id: string;
  rule_id: string;
  polarity: "improve" | "strength";
  anchor: { argument_unit_id: string; type: string };
  start: number;
  end: number;
  excerpt_word_range: [number, number] | null;
  excerpt_text: string;
  observations: MomentObservation[];
  salience: number;
}

/** One item of the LLM's visual_feedback output (visual_coaching/validator.py). */
export interface VisualFeedbackItem {
  id: string;
  category: "gaze" | "gestures" | "head" | "integration" | "coverage";
  polarity: "strength" | "improve" | "neutral";
  moment_id: string | null;
  metric_keys: string[];
  observation_ids: string[];
  coaching: string;
}

/** visual_feedback.json, as stored by visual_coaching/service.py. */
export interface VisualFeedbackDocument {
  schema_version: string;
  metrics_version: string;
  prompt_version: string;
  model: string;
  generated_at: string;
  correlated_moments: CorrelatedMoment[];
  visual_feedback: VisualFeedbackItem[];
  summary: string;
  validation: { retried: boolean; dropped_items: number };
}

export interface SessionSummary {
  id: string;
  title: string | null;
  status: SessionStatus;
  progress: number;
  queue_wait_seconds: number | null;
  overall_score: number | null;
  duration_seconds: number | null;
  words_per_minute: number | null;
  feedback_count: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  video_analysis_status: VideoAnalysisStatus;
  video_unavailable_reason: string | null;
  visual_coaching_status: VisualCoachingStatus;
}

export interface SessionCreated {
  id: string;
  status: SessionStatus;
  upload_url: string;
  upload_headers: Record<string, string>;
  expires_in_seconds: number;
}

export interface FeedbackItem {
  category: Category;
  title: string;
  issue: string;
  severity: Severity;
  evidence: string[];
  explanation: string | null;
  recommendation: string | null;
  metadata: Record<string, unknown>;
}

/** Shape written by raw_metrics/metrics.py. */
export interface RawMetrics {
  session_id?: string;
  speech?: {
    total_duration: number;
    speech_duration: number;
    silence_duration: number;
    speech_percentage: number;
    word_count: number;
    words_per_minute: number;
  };
  pauses?: {
    count: number;
    total_duration: number;
    average_duration: number;
    longest_duration: number;
  };
  fillers?: {
    count: number;
    words: Record<string, number>;
    instances: Array<{ word?: string; start?: number }>;
  };
  stutters?: {
    count: number;
    instances: Array<{ word?: string; start?: number }>;
  };
}

/** Shape written by speech_analysis/. */
export interface SpeechSegment {
  start: number;
  end: number;
  text: string;
  labels: string[];
  fallacy_type: string | null;
}

export interface SpeechContent {
  session_id?: string;
  segments?: SpeechSegment[];
}

/** Shape written by audio/audio_analyzer.py. */
export interface AudioAnalysis {
  total_duration?: number;
  speech_duration?: number;
  silence_duration?: number;
  speech_percentage?: number;
  pauses?: Array<{ start: number; end: number; duration: number }>;
}

export interface SessionReport {
  id: string;
  title: string | null;
  status: SessionStatus;
  created_at: string;
  /** A category is null when it wasn't scored — rebuttal, for a speech with nothing to rebut. */
  scores: Partial<Record<Category | "overall", number | null>>;
  feedback: FeedbackItem[];
  raw_metrics: RawMetrics;
  speech_content: SpeechContent;
  analysis: AudioAnalysis;
  audio_url: string | null;
  video_analysis_status: VideoAnalysisStatus;
  video_unavailable_reason: string | null;
  visual_coaching_status: VisualCoachingStatus;
  video_analysis: VideoAnalysisResult | null;
  correlated_moments: CorrelatedMoment[] | null;
  /** The whole stored feedback document (not just its items list) -- see app/routes/sessions.py's report.visual_feedback = feedback_doc. */
  visual_feedback: VisualFeedbackDocument | null;
}

export const STATUS_LABEL: Record<SessionStatus, string> = {
  created: "Waiting for a recording",
  queued: "Queued",
  converting: "Preparing audio",
  transcribing: "Transcribing",
  analyzing_audio: "Measuring pauses",
  calculating_metrics: "Counting delivery metrics",
  analyzing_speech: "Reading the argument",
  coaching: "Writing feedback",
  completed: "Ready",
  failed: "Failed",
};

export const CATEGORY_LABEL: Record<Category, string> = {
  quantitative: "Delivery",
  argumentation: "Argumentation",
  rebuttal: "Rebuttal",
  structure: "Structure",
  persuasion: "Persuasion",
  logic: "Logic",
};

export const TERMINAL: SessionStatus[] = ["completed", "failed"];

/* ------------------------------------------------------------
   Visual delivery (Phase 7 report UI)
   ------------------------------------------------------------ */

export type VisualMetricFormat = "ratio" | "rate" | "seconds" | "degrees" | "amplitude";

/**
 * Plain label/definition/format per metric key. Wording here is not
 * given verbatim by the task document beyond one worked example
 * (camera_facing_ratio); written to match that example's style.
 */
export const VISUAL_METRIC_INFO: Record<
  string,
  { label: string; definition: string; format: VisualMetricFormat }
> = {
  face_tracked_ratio: {
    label: "Face visible",
    definition: "Share of your speaking time your face was visible to the camera.",
    format: "ratio",
  },
  camera_facing_ratio: {
    label: "Facing the camera",
    definition: "Share of your speaking time spent facing the camera, measured from head direction and eye position.",
    format: "ratio",
  },
  gaze_away_events_per_min: {
    label: "Looking away",
    definition: "How often you looked away from the camera, per minute of speaking.",
    format: "rate",
  },
  longest_gaze_away_s: {
    label: "Longest look away",
    definition: "The longest single stretch you looked away from the camera.",
    format: "seconds",
  },
  head_down_ratio: {
    label: "Head down",
    definition: "Share of your speaking time your head was tilted down.",
    format: "ratio",
  },
  head_motion_median_deg_s: {
    label: "Head movement",
    definition: "Your typical head movement speed.",
    format: "degrees",
  },
  hands_visible_ratio: {
    label: "Hands visible",
    definition: "Share of your speaking time your hands were visible on camera.",
    format: "ratio",
  },
  gesture_rate_per_min: {
    label: "Gesture rate",
    definition: "How often you made a hand gesture, per minute of speaking.",
    format: "rate",
  },
  gesture_amplitude_median: {
    label: "Gesture size",
    definition: "The typical size of your hand gestures.",
    format: "amplitude",
  },
  hands_still_longest_s: {
    label: "Longest still stretch",
    definition: "The longest stretch your hands stayed still.",
    format: "seconds",
  },
  hands_still_ratio: {
    label: "Hands still",
    definition: "Share of your speaking time your hands stayed still.",
    format: "ratio",
  },
};

/** Table row order, independent of the metrics dict's own key order. */
export const VISUAL_METRIC_ORDER: string[] = [
  "face_tracked_ratio",
  "camera_facing_ratio",
  "gaze_away_events_per_min",
  "longest_gaze_away_s",
  "head_down_ratio",
  "head_motion_median_deg_s",
  "hands_visible_ratio",
  "gesture_rate_per_min",
  "gesture_amplitude_median",
  "hands_still_longest_s",
  "hands_still_ratio",
];

/** Metrics built from the camera-facing cone; hidden in in_room_practice context. */
export const CAMERA_FACING_METRIC_KEYS: ReadonlySet<string> = new Set([
  "camera_facing_ratio",
  "gaze_away_events_per_min",
  "longest_gaze_away_s",
]);

export const CONFIDENCE_LABEL: Record<VisualConfidence, string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

export const VISUAL_WARNING_LABEL: Record<string, string> = {
  hands_mostly_out_of_frame: "Your hands were out of frame for most of the speech.",
  face_often_out_of_frame: "Your face was out of frame for a large part of the speech.",
  calibration_skipped: "Camera calibration was skipped, so facing measurements are less certain.",
  calibration_unstable: "Camera calibration was unstable, so facing measurements are less certain.",
  second_person_detected: "Another person was visible on camera for part of the speech.",
  analysis_degraded: "Analysis quality dropped partway through, likely because your device slowed down.",
  high_clock_uncertainty: "Timing between audio and video was less precise than usual for part of this session.",
  in_room_context: "This session was marked as practising with someone in the room, so camera-facing isn't shown.",
};

export const VIDEO_UNAVAILABLE_REASON_LABEL: Record<string, string> = {
  camera_denied: "Camera access was denied.",
  unsupported: "Your browser or device doesn't support visual analysis.",
  model_load_failed: "The on-device vision models couldn't be loaded.",
  device_too_slow: "Your device couldn't keep up with visual analysis.",
  user_opted_out: "Visual analysis wasn't turned on for this session.",
  upload_failed: "The captured visual data couldn't be uploaded.",
  face_not_found: "Your face couldn't be found during setup.",
  duration_mismatch: "The captured visual data didn't match the length of the recording.",
};

/* ---------------------------------------------------------- */
/* Admin (app/schemas/admin.py)                                */
/* ---------------------------------------------------------- */

export interface KeyUsage {
  key_id: string;
  label: string;
  provider: string;

  requests_used: number;
  requests_limit: number;
  requests_remaining: number;

  prompt_tokens: number;
  completion_tokens: number;
  tokens_used: number;
  tokens_limit: number;
  tokens_remaining: number;

  window_reset_at: string | null;
  last_rate_limit_headers: Record<string, string> | null;
}

export interface StorageUsage {
  used_bytes: number;
  used_gb: number;
  quota_gb: number;
  remaining_gb: number;
}

export interface AdminStats {
  active_users: number;
  total_signups: number;
  keys: KeyUsage[];
  storage: StorageUsage;
}

export type AdminUserSort = "newest" | "last_seen";

export interface AdminUser {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  created_at: string;
  last_seen_at: string | null;
  session_count: number;
  /** In ADMIN_EMAILS: the backend refuses to force-delete these. */
  is_admin: boolean;
}

export interface AdminUserPage {
  users: AdminUser[];
  /** Pass back as `cursor` for the next page; null on the last page. */
  next_cursor: string | null;
}

/* ---------------------------------------------------------- */
/* Progress graph (GET /v1/sessions/progress)                  */
/* ---------------------------------------------------------- */

/** "overall" is the chart's "All". */
export type ProgressMetric =
  | "overall"
  | "argumentation"
  | "rebuttal"
  | "structure"
  | "persuasion"
  | "logic";

/** Rolling 24h / 7d / 30d windows, or the newest 5 / 10 / 15 sessions. */
export type ProgressRange = "1d" | "1w" | "1m" | "5" | "10" | "15";

export interface ProgressPoint {
  session_id: string;
  created_at: string;
  /** null when the session has no score for this metric (rebuttal with nothing to rebut). */
  score: number | null;
}
