/**
 * putToSignedUrl (the audio-blob PUT to a GCS signed URL) and
 * request()'s own fetch() call previously had no timeout at all —
 * a stalled connection just hung forever with no feedback. These
 * test the classification logic added to fix that: a real
 * AbortSignal.timeout()-shaped rejection becomes a specific
 * "timed out" ApiError, a genuine network failure gets its own
 * distinct message, and a normal failed/successful response is
 * unaffected.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, getCurrentUser, putToSignedUrl } from "../api";

function timeoutRejection(): DOMException {
  return new DOMException("The operation was aborted due to timeout", "TimeoutError");
}

describe("putToSignedUrl", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("resolves on a successful PUT and passes an AbortSignal to fetch", async () => {
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      expect(init.signal).toBeInstanceOf(AbortSignal);
      return new Response(null, { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      putToSignedUrl("https://storage.test/upload", { "Content-Type": "audio/webm" }, new Blob(["x"])),
    ).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("throws a distinct 'timed out' ApiError when the request stalls past its deadline", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw timeoutRejection();
    }));

    await expect(putToSignedUrl("https://storage.test/upload", {}, new Blob(["x"]))).rejects.toMatchObject({
      status: 408,
      message: "The upload timed out. Check your connection and try again.",
    });
  });

  it("throws a generic upload-failed ApiError on a real network failure (not a timeout)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }));

    await expect(putToSignedUrl("https://storage.test/upload", {}, new Blob(["x"]))).rejects.toMatchObject({
      status: 0,
      message: "The recording could not be uploaded. Check your connection and try again.",
    });
  });

  it("throws with the real status when GCS responds but rejects the upload", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 403 })));

    await expect(putToSignedUrl("https://storage.test/upload", {}, new Blob(["x"]))).rejects.toMatchObject({
      status: 403,
      message: "The recording could not be uploaded. Check your connection and try again.",
    });
  });

  it("is a real ApiError instance in every failure case, not a raw DOMException/TypeError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw timeoutRejection();
    }));

    await expect(putToSignedUrl("https://storage.test/upload", {}, new Blob(["x"]))).rejects.toBeInstanceOf(
      ApiError,
    );
  });
});

describe("request() (via getCurrentUser)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("converts a stalled request into ApiError(408, timed-out message)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw timeoutRejection();
    }));

    await expect(getCurrentUser()).rejects.toMatchObject({
      status: 408,
      message: "The request timed out. Check your connection and try again.",
    });
  });

  it("still resolves normally when the response arrives in time", async () => {
    const user = { id: "u1", email: "a@test.com", first_name: "A", last_name: "B", created_at: "2026-01-01" };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(user), { status: 200 })),
    );

    await expect(getCurrentUser()).resolves.toEqual(user);
  });

  it("lets a genuine (non-timeout) network failure propagate as-is, not relabeled as a timeout", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );

    await expect(getCurrentUser()).rejects.toThrow("Failed to fetch");
    await expect(getCurrentUser()).rejects.not.toBeInstanceOf(ApiError);
  });
});
