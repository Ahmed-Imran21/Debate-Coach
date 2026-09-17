/**
 * Serializes and uploads a built VisualSignalTrack (task doc
 * §4.11.2/4.11.4). Retries with exponential backoff; on final
 * failure the caller finalizes the session with
 * video.status = "unavailable", reason "upload_failed" — the
 * audio session must proceed regardless.
 */

import { uploadVisualSignals } from "@/lib/api";

import { UPLOAD_RETRY_DELAYS_MS } from "./config";
import type { VisualSignalTrack } from "./types";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
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
 * acknowledged, or throws VisualSignalUploadError once every
 * retry is exhausted.
 */
export async function uploadTrackWithRetry(
  sessionId: string,
  track: VisualSignalTrack,
  delaysMs: readonly number[] = UPLOAD_RETRY_DELAYS_MS,
): Promise<number> {
  const { body, contentEncoding } = await encode(track);

  let lastError: unknown;

  for (let attempt = 0; attempt <= delaysMs.length; attempt++) {
    try {
      const result = await uploadVisualSignals(sessionId, body, contentEncoding);
      return result.frames;
    } catch (error) {
      lastError = error;
      if (attempt < delaysMs.length) {
        await sleep(delaysMs[attempt]);
      }
    }
  }

  throw new VisualSignalUploadError(
    `Visual signal upload failed after ${delaysMs.length + 1} attempts.`,
    lastError,
  );
}
