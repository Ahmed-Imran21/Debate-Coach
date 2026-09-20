/**
 * uploadTrackWithRetry()'s retry/fail-fast classification. Real
 * timers, kept fast by passing tiny custom delaysMs (the function
 * already accepts an override for exactly this).
 *
 * @/lib/api is mocked because it reaches out to fetch()/BASE, which
 * this suite (environment: "node", see vitest.config.ts) has none
 * of. ApiError is reimplemented identically in the mock rather than
 * imported from the real module, so instanceof checks inside
 * upload.ts's isRetryable() work against the same class identity
 * the test constructs errors with.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

const { uploadVisualSignals } = vi.hoisted(() => ({ uploadVisualSignals: vi.fn() }));

vi.mock("@/lib/api", () => {
  class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.name = "ApiError";
      this.status = status;
    }
  }
  return { ApiError, uploadVisualSignals };
});

import { ApiError } from "@/lib/api";

import { uploadTrackWithRetry, VisualSignalUploadError } from "../upload";
import type { VisualSignalTrack } from "../types";

// Only reaches JSON.stringify() inside encode() — shape doesn't
// matter beyond being serializable.
const TRACK = {} as VisualSignalTrack;

const FAST_DELAYS = [1, 1, 1]; // 4 attempts total, ~4ms of real waiting

beforeEach(() => {
  uploadVisualSignals.mockReset();
});

describe("uploadTrackWithRetry — fail-fast on non-retryable 4xx", () => {
  it("does not retry a 422 (deterministic schema mismatch) — one attempt, immediate failure", async () => {
    uploadVisualSignals.mockRejectedValue(new ApiError(422, "invalid_schema"));

    await expect(uploadTrackWithRetry("s1", TRACK, FAST_DELAYS)).rejects.toThrow(VisualSignalUploadError);

    expect(uploadVisualSignals).toHaveBeenCalledTimes(1);
  });

  it("does not retry a 409 (session-state conflict) — one attempt", async () => {
    uploadVisualSignals.mockRejectedValue(new ApiError(409, "already started"));

    await expect(uploadTrackWithRetry("s1", TRACK, FAST_DELAYS)).rejects.toThrow(VisualSignalUploadError);

    expect(uploadVisualSignals).toHaveBeenCalledTimes(1);
  });

  it("does not retry a 413 (payload too large) — one attempt", async () => {
    uploadVisualSignals.mockRejectedValue(new ApiError(413, "too large"));

    await expect(uploadTrackWithRetry("s1", TRACK, FAST_DELAYS)).rejects.toThrow(VisualSignalUploadError);

    expect(uploadVisualSignals).toHaveBeenCalledTimes(1);
  });

  it("the resulting error names the real attempt count, not the schedule length", async () => {
    uploadVisualSignals.mockRejectedValue(new ApiError(422, "invalid_schema"));

    await expect(uploadTrackWithRetry("s1", TRACK, FAST_DELAYS)).rejects.toThrow(/after 1 attempt\.$/);
  });
});

describe("uploadTrackWithRetry — still retries genuinely transient failures", () => {
  it("retries 429 (Too Many Requests) through the full schedule", async () => {
    uploadVisualSignals.mockRejectedValue(new ApiError(429, "rate limited"));

    await expect(uploadTrackWithRetry("s1", TRACK, FAST_DELAYS)).rejects.toThrow(VisualSignalUploadError);

    expect(uploadVisualSignals).toHaveBeenCalledTimes(FAST_DELAYS.length + 1);
  });

  it("retries 408 (Request Timeout) through the full schedule", async () => {
    uploadVisualSignals.mockRejectedValue(new ApiError(408, "timed out"));

    await expect(uploadTrackWithRetry("s1", TRACK, FAST_DELAYS)).rejects.toThrow(VisualSignalUploadError);

    expect(uploadVisualSignals).toHaveBeenCalledTimes(FAST_DELAYS.length + 1);
  });

  it("retries a 500 through the full schedule", async () => {
    uploadVisualSignals.mockRejectedValue(new ApiError(500, "server error"));

    await expect(uploadTrackWithRetry("s1", TRACK, FAST_DELAYS)).rejects.toThrow(VisualSignalUploadError);

    expect(uploadVisualSignals).toHaveBeenCalledTimes(FAST_DELAYS.length + 1);
  });

  it("retries a plain network failure (not an ApiError at all) through the full schedule", async () => {
    uploadVisualSignals.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(uploadTrackWithRetry("s1", TRACK, FAST_DELAYS)).rejects.toThrow(VisualSignalUploadError);

    expect(uploadVisualSignals).toHaveBeenCalledTimes(FAST_DELAYS.length + 1);
  });

  it("succeeds on a later attempt without exhausting the schedule", async () => {
    uploadVisualSignals
      .mockRejectedValueOnce(new ApiError(500, "server error"))
      .mockRejectedValueOnce(new ApiError(500, "server error"))
      .mockResolvedValueOnce({ status: "received", frames: 42 });

    await expect(uploadTrackWithRetry("s1", TRACK, FAST_DELAYS)).resolves.toBe(42);

    expect(uploadVisualSignals).toHaveBeenCalledTimes(3);
  });
});
