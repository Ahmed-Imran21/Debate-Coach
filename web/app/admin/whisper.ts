/**
 * Display helpers for the Whisper (transcription) key rows on the
 * admin dashboard. Free of React so vitest can test them.
 */

import type { WhisperKeyUsage } from "@/lib/types";

import { formatLastSeen } from "./users/logic";

/** Seconds of audio as minutes and seconds: 75 -> "1:15", 7200 -> "120:00". */
export function formatAudio(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

/** The line under a Whisper key's bars. */
export function whisperDetail(key: WhisperKeyUsage, now: number = Date.now()): string {
  return [
    `Last minute: ${key.requests_last_minute} of ${key.requests_per_minute_limit} requests.`,
    `Last hour: ${key.requests_last_hour} ${key.requests_last_hour === 1 ? "request" : "requests"}.`,
    `Failed (24 h): ${key.failed_last_24h}.`,
    `Rate-limited (24 h): ${key.rate_limited_last_24h}.`,
    `Last used: ${formatLastSeen(key.last_used_at, now)}.`,
  ].join(" ");
}
