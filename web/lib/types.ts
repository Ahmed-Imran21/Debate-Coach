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
  scores: Partial<Record<Category | "overall", number>>;
  feedback: FeedbackItem[];
  raw_metrics: RawMetrics;
  speech_content: SpeechContent;
  analysis: AudioAnalysis;
  audio_url: string | null;
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
