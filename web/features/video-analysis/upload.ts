/**
 * Serializes and uploads a built VisualSignalTrack (task doc
 * §4.11.2/4.11.4). Retries with exponential backoff; on final
 * failure the caller finalizes the session with
 * video.status = "unavailable", reason "upload_failed" — the
 * audio session must proceed regardless.
 */

import { ApiError, uploadVisualSignals } from "@/lib/api";

import { UPLOAD_RETRY_DELAYS_MS } from "./config";
import type { VisualSignalTrack } from "./types";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Whether a failed upload attempt is worth retrying.
 *
 * Confirmed bug (2026-09-19): a manifest field the backend's strict
 * schema rejects (see extractor.ts's toModelProvenance()) made every
 * upload fail with the same 422 every time. The old unconditional
 * retry loop sent the identical, already-proven-invalid payload
 * four more times before reporting failure — turning an instant,
 * deterministic rejection into a ~15s wait for the same outcome.
 * request()/ApiError only exists for a response the server actually
 * sent, so this only needs to decide by status code.
 */
function isRetryable(error: unknown): boolean {
  // Not an ApiError: fetch() itself rejected (DNS, connection
  // refused, dropped mid-request) rather than the server responding
  // at all. Exactly the transient case retries exist for.
  if (!(error instanceof ApiError)) return true;

  // 408 Request Timeout and 429 Too Many Requests are the only 4xx
  // statuses that mean "try again," not "this request is wrong."
  if (error.status === 408 || error.status === 429) return true;

  // Every other 4xx means the server is telling us the request
  // itself is invalid (bad schema, session-state conflict, payload
  // too large) — an identical retry produces an identical rejection.
  if (error.status >= 400 && error.status < 500) return false;

  // 5xx and anything else: presume transient (restart, overload).
  return true;
}

/** gzip via CompressionStream when the browser has it, else plain JSON. */
async function encode(track: VisualSignalTrack): Promise<{ body: BodyInit; contentEncoding: "gzip" | null }> {
  const json = JSON.stringify(track);

  if (typeof CompressionStream === "undefined") {
    return { body: json, contentEncoding: null };
  }

  const bytes = new TextEncoder().encode(json);
  const stream = new Blob([bytes]).stream().pipeThrough(new CompressionStream("gzip"));
  const compressed = await new Response(stream).blob();
  return { body: compressed, contentEncoding: "gzip" };
}

export class VisualSignalUploadError extends Error {
  constructor(message: string, readonly cause?: unknown) {
    super(message);
    this.name = "VisualSignalUploadError";
  }
}

/**
 * Uploads with retry. Resolves with the frame count the server
 * acknowledged, or throws VisualSignalUploadError once retries are
 * exhausted — or immediately, without ever sleeping, on the first
 * non-retryable failure (see isRetryable()).
 */
export async function uploadTrackWithRetry(
  sessionId: string,
  track: VisualSignalTrack,
  delaysMs: readonly number[] = UPLOAD_RETRY_DELAYS_MS,
): Promise<number> {
  const { body, contentEncoding } = await encode(track);

  let lastError: unknown;
  let attempts = 0;

  for (let attempt = 0; attempt <= delaysMs.length; attempt++) {
    attempts += 1;
    try {
      const result = await uploadVisualSignals(sessionId, body, contentEncoding);
      return result.frames;
    } catch (error) {
      lastError = error;
      if (!isRetryable(error)) break;
      if (attempt < delaysMs.length) {
        await sleep(delaysMs[attempt]);
      }
    }
  }

  throw new VisualSignalUploadError(
    `Visual signal upload failed after ${attempts} attempt${attempts === 1 ? "" : "s"}.`,
    lastError,
  );
}
