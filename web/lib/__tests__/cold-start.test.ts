/**
 * Cold starts (lib/api.ts): the backend scales to zero, and the first
 * request after that can take ~27s. While it may be cold, a request
 * gets a longer timeout and a GET that times out is retried once, so
 * the user sees a delay at worst, never an error. warmUpBackend()
 * wakes it on page load.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const timeoutError = () => new DOMException("The operation timed out.", "TimeoutError");
let calls: { url: string; method: string; mode?: string }[] = [];
let script: Array<"timeout" | "ok">;
let timeouts: number[];

beforeEach(() => {
  vi.resetModules();
  const memory = new Map<string, string>();
  const storage = {
    getItem: (k: string) => memory.get(k) ?? null,
    setItem: (k: string, v: string) => void memory.set(k, v),
    removeItem: (k: string) => void memory.delete(k),
    clear: () => memory.clear(),
    key: () => null,
    length: 0,
  };
  vi.stubGlobal("window", { localStorage: storage, sessionStorage: storage });
  calls = [];
  script = [];
  timeouts = [];
  vi.spyOn(AbortSignal, "timeout").mockImplementation((ms: number) => {
    timeouts.push(ms);
    return new AbortController().signal;
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      calls.push({ url: url.replace(/^https?:\/\/[^/]+/, ""), method: init.method ?? "GET", mode: init.mode });
      if (script.shift() === "timeout") throw timeoutError();
      return new Response(JSON.stringify([]), { status: 200 });
    }),
  );
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const api = () => import("../api");

describe("while the backend may be cold", () => {
  it("gives the first request a longer timeout", async () => {
    const { listSessions } = await api();
    await listSessions();
    expect(timeouts).toEqual([60_000]);
  });

  it("retries a GET that times out once, so the user gets data instead of an error", async () => {
    script = ["timeout", "ok"];
    const { listSessions } = await api();

    await expect(listSessions()).resolves.toEqual([]);
    expect(calls.map((c) => c.url)).toEqual(["/v1/sessions", "/v1/sessions"]);
  });

  it("gives up after the one retry", async () => {
    script = ["timeout", "timeout", "ok"];
    const { listSessions } = await api();

    await expect(listSessions()).rejects.toMatchObject({ status: 408 });
    expect(calls).toHaveLength(2);
  });

  it("retries only a timeout, not a network error", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      calls.push({ url, method: "GET" });
      throw new TypeError("Failed to fetch");
    }));
    const { listSessions } = await api();

    await expect(listSessions()).rejects.toThrow();
    expect(calls).toHaveLength(1);
  });

  it("doesn't retry a POST (it could double up) but still waits longer", async () => {
    script = ["timeout"];
    const { createSession } = await api();

    await expect(createSession({ content_type: "audio/webm", title: null })).rejects.toMatchObject({ status: 408 });
    expect(calls).toHaveLength(1);
    expect(timeouts).toEqual([60_000]);
  });

  it("keeps a longer timeout a call already asked for", async () => {
    const { createProgressReport, PROGRESS_REPORT_TIMEOUT_MS } = await api();
    await createProgressReport(3).catch(() => {});
    expect(timeouts).toEqual([PROGRESS_REPORT_TIMEOUT_MS]);
  });
});

describe("once the backend has answered", () => {
  it("goes back to the normal timeout and doesn't retry", async () => {
    const { listSessions } = await api();
    await listSessions();
    script = ["timeout"];

    await expect(listSessions()).rejects.toMatchObject({ status: 408 });
    expect(timeouts).toEqual([60_000, 30_000]);
    expect(calls).toHaveLength(2);
  });

  it("treats it as cold again after ten idle minutes", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-09-27T12:00:00Z"));
    const { listSessions } = await api();
    await listSessions();

    vi.setSystemTime(new Date("2026-09-27T12:09:00Z"));
    await listSessions();
    vi.setSystemTime(new Date("2026-09-27T12:20:00Z"));
    await listSessions();

    expect(timeouts).toEqual([60_000, 30_000, 60_000]);
  });
});

describe("warmUpBackend", () => {
  it("sends a fire-and-forget GET /health, and a request after it uses the normal timeout", async () => {
    const { warmUpBackend, listSessions } = await api();
    warmUpBackend();
    await new Promise((resolve) => setTimeout(resolve, 0));
    await listSessions();

    expect(calls[0]).toEqual({ url: "/health", method: "GET", mode: "no-cors" });
    expect(timeouts).toEqual([30_000]);
  });

  it("never throws, even when the network fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("network down");
    }));
    const { warmUpBackend } = await api();
    expect(() => warmUpBackend()).not.toThrow();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
});
