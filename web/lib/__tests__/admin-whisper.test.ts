/**
 * Whisper (transcription) key rows on the admin dashboard: audio shown
 * as minutes and seconds, and the detail line under the bars.
 */

import { describe, expect, it } from "vitest";

import { formatAudio, whisperDetail } from "../../app/admin/whisper";
import type { WhisperKeyUsage } from "../types";

describe("formatAudio", () => {
  it.each([
    [0, "0:00"],
    [5, "0:05"],
    [75, "1:15"],
    [59.6, "1:00"],
    [7200, "120:00"],
    [28800, "480:00"],
    [-3, "0:00"],
  ])("%s seconds -> %s", (seconds, text) => {
    expect(formatAudio(seconds)).toBe(text);
  });
});

describe("whisperDetail", () => {
  const key: WhisperKeyUsage = {
    key_id: "groq_whisper_large_v3_1",
    label: "Whisper large-v3 — Key 1 (transcription)",
    requests_last_minute: 2,
    requests_last_hour: 1,
    requests_last_24h: 9,
    requests_per_minute_limit: 20,
    requests_per_day_limit: 2000,
    audio_seconds_last_hour: 75,
    audio_seconds_last_24h: 450,
    audio_seconds_per_hour_limit: 7200,
    audio_seconds_per_day_limit: 28800,
    failed_last_24h: 1,
    rate_limited_last_24h: 3,
    last_used_at: "2026-09-27T11:55:00Z",
  };

  it("summarises the short window, failures, rate limits and last use", () => {
    expect(whisperDetail(key, Date.parse("2026-09-27T12:00:00Z"))).toBe(
      "Last minute: 2 of 20 requests. Last hour: 1 request. Failed (24 h): 1. Rate-limited (24 h): 3. Last used: 5 minutes ago.",
    );
  });

  it("says never for an unused key, and never mentions tokens", () => {
    const text = whisperDetail({ ...key, last_used_at: null, requests_last_hour: 0 });
    expect(text).toContain("Last hour: 0 requests.");
    expect(text).toContain("Last used: never.");
    expect(text.toLowerCase()).not.toContain("token");
  });
});
