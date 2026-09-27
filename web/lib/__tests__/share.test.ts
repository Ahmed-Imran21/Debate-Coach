/**
 * Share links on the frontend: the public URL, the owner's API calls,
 * and above all that the public report is fetched with no
 * credentials, even when the viewer happens to be signed in.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SHARED_UNAVAILABLE, shareUrl } from "../share";

function memoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    clear: () => data.clear(),
    getItem: (k: string) => data.get(k) ?? null,
    key: (i: number) => [...data.keys()][i] ?? null,
    removeItem: (k: string) => void data.delete(k),
    setItem: (k: string, v: string) => void data.set(k, v),
  };
}

let calls: { url: string; method: string; auth?: string }[] = [];

beforeEach(() => {
  vi.resetModules();
  vi.stubGlobal("window", { localStorage: memoryStorage(), sessionStorage: memoryStorage() });
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const headers = (init.headers ?? {}) as Record<string, string>;
      calls.push({ url: url.replace(/^https?:\/\/[^/]+/, ""), method: init.method ?? "GET", auth: headers.Authorization });
      if ((init.method ?? "GET") === "DELETE") return new Response(null, { status: 204 });
      return new Response(JSON.stringify({ token: "t".repeat(43), created_at: "2026-09-27T00:00:00Z", sharing: true }), { status: 200 });
    }),
  );
});

afterEach(() => vi.unstubAllGlobals());

const api = () => import("../api");

describe("shareUrl", () => {
  it("builds the public link on this site's origin", () => {
    expect(shareUrl("https://web-debate-coach1.vercel.app", "abc_DEF-123")).toBe(
      "https://web-debate-coach1.vercel.app/shared/abc_DEF-123",
    );
    expect(shareUrl("http://localhost:3000/", "x")).toBe("http://localhost:3000/shared/x");
  });
});

describe("the public report", () => {
  it("is fetched with no Authorization header even when the viewer is signed in", async () => {
    window.localStorage.setItem("dc.access", "a-real-looking-access-token");
    const { getSharedReport } = await api();

    await getSharedReport("t".repeat(43));

    expect(calls).toEqual([{ url: `/v1/shared/${"t".repeat(43)}`, method: "GET", auth: undefined }]);
  });

  it("shows one message for every failure", () => {
    expect(SHARED_UNAVAILABLE).toBe("This report isn't available.");
  });
});

describe("owner share controls", () => {
  it("call the owner-only endpoints, signed in", async () => {
    window.localStorage.setItem("dc.access", "owner-token");
    const { createShareLink, getShareStatus, stopSharing } = await api();

    await getShareStatus("s1");
    await createShareLink("s1");
    await stopSharing("s1");

    expect(calls).toEqual([
      { url: "/v1/sessions/s1/share", method: "GET", auth: "Bearer owner-token" },
      { url: "/v1/sessions/s1/share", method: "POST", auth: "Bearer owner-token" },
      { url: "/v1/sessions/s1/share", method: "DELETE", auth: "Bearer owner-token" },
    ]);
  });
});
