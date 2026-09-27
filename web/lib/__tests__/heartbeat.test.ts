/**
 * The heartbeat (lib/heartbeat.ts): a forgotten tab whose session has
 * expired must go quiet instead of getting a 401 every minute, and the
 * heartbeat must never refresh a session.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HEARTBEAT_INTERVAL_MS, createHeartbeat, isLive } from "../heartbeat";

function jwt(secondsFromNow: number): string {
  const payload = btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + secondsFromNow }))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  return `h.${payload}.s`;
}

class Unauthorized extends Error {
  status = 401;
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-27T12:00:00Z"));
});

afterEach(() => {
  vi.useRealTimers();
});

async function flush(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

describe("isLive", () => {
  it("is true only for a present, readable, unexpired token", () => {
    expect(isLive(jwt(600))).toBe(true);
    expect(isLive(jwt(-1))).toBe(false);
    expect(isLive(null)).toBe(false);
    expect(isLive("not-a-jwt")).toBe(false);
  });
});

describe("createHeartbeat", () => {
  it("beats every minute while the session is live", () => {
    const send = vi.fn(async () => {});
    const beat = createHeartbeat({ getToken: () => jwt(3600), send });

    beat.start();
    vi.advanceTimersByTime(HEARTBEAT_INTERVAL_MS * 3);

    expect(send).toHaveBeenCalledTimes(4); // once at start, then each minute
    expect(beat.running).toBe(true);
  });

  it("stops for good after a 401, and sends nothing more", async () => {
    const send = vi.fn(async () => {
      throw new Unauthorized();
    });
    const beat = createHeartbeat({ getToken: () => jwt(3600), send });

    beat.start();
    await flush();
    vi.advanceTimersByTime(HEARTBEAT_INTERVAL_MS * 10);

    expect(send).toHaveBeenCalledTimes(1);
    expect(beat.running).toBe(false);
    beat.start(); // and it won't come back on this page load
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("keeps going after other failures (a network blip is not a 401)", async () => {
    const send = vi.fn(async () => {
      throw Object.assign(new Error("offline"), { status: 0 });
    });
    const beat = createHeartbeat({ getToken: () => jwt(3600), send });

    beat.start();
    await flush();
    vi.advanceTimersByTime(HEARTBEAT_INTERVAL_MS * 2);

    expect(send).toHaveBeenCalledTimes(3);
    expect(beat.running).toBe(true);
  });

  it("never starts while the stored token is expired", () => {
    const send = vi.fn(async () => {});
    const beat = createHeartbeat({ getToken: () => jwt(-60), send });

    beat.start();
    vi.advanceTimersByTime(HEARTBEAT_INTERVAL_MS * 5);

    expect(send).not.toHaveBeenCalled();
    expect(beat.running).toBe(false);
  });

  it("sends nothing once the token expires mid-way", () => {
    let token = jwt(90); // expires between the first and second minute
    const send = vi.fn(async () => {});
    const beat = createHeartbeat({ getToken: () => token, send });

    beat.start();
    vi.advanceTimersByTime(HEARTBEAT_INTERVAL_MS * 5);
    expect(send).toHaveBeenCalledTimes(2); // at start and at 1:00; not at 2:00+

    token = "";
    vi.advanceTimersByTime(HEARTBEAT_INTERVAL_MS);
    expect(send).toHaveBeenCalledTimes(2);
  });

  it("stop() ends the timer", () => {
    const send = vi.fn(async () => {});
    const beat = createHeartbeat({ getToken: () => jwt(3600), send });

    beat.start();
    beat.stop();
    vi.advanceTimersByTime(HEARTBEAT_INTERVAL_MS * 3);

    expect(send).toHaveBeenCalledTimes(1);
  });
});

describe("heartbeat() in api.ts", () => {
  it("never refreshes a session: a 401 is final, with no call to /auth/refresh", async () => {
    vi.useRealTimers();
    vi.resetModules();
    const store = new Map<string, string>([["dc.access", jwt(-60)], ["dc.refresh", "r1"]]);
    const storage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
      key: () => null,
      length: 0,
    };
    vi.stubGlobal("window", { localStorage: storage, sessionStorage: storage });
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        urls.push(url.replace(/^https?:\/\/[^/]+/, ""));
        return new Response(JSON.stringify({ detail: "expired" }), { status: 401 });
      }),
    );

    const { heartbeat } = await import("../api");
    await expect(heartbeat()).rejects.toMatchObject({ status: 401 });

    expect(urls).toEqual(["/v1/users/heartbeat"]);
    vi.unstubAllGlobals();
  });
});
