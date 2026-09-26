/**
 * Practice motions on the frontend: the picker's value mapping, the
 * motions API call, and above all that "No prompt" sends exactly the
 * session-create request this app always sent.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { getMotions, uploadAndStart } from "../api";
import { NO_PROMPT, findMotion, toMotionId } from "../motions";
import type { Motion } from "../types";

afterEach(() => {
  vi.unstubAllGlobals();
});

const MOTIONS: Motion[] = [
  { id: "carbon-tax", title: "Climate policy", description: "This house would introduce a carbon tax." },
  { id: "space-funding", title: "Space exploration", description: "This house believes that governments should stop funding space exploration." },
];

describe("picker values", () => {
  it("maps the No prompt option to null and anything else to its id", () => {
    expect(toMotionId(NO_PROMPT)).toBeNull();
    expect(toMotionId("carbon-tax")).toBe("carbon-tax");
  });

  it("finds the chosen motion, and nothing for No prompt or an unknown id", () => {
    expect(findMotion(MOTIONS, "space-funding")?.title).toBe("Space exploration");
    expect(findMotion(MOTIONS, null)).toBeNull();
    expect(findMotion(MOTIONS, "gone")).toBeNull();
  });
});

function fakeBackend() {
  const calls: { url: string; method: string; body?: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const path = url.replace(/^https?:\/\/[^/]+/, "");
      const method = init.method ?? "GET";
      calls.push({ url: path, method, body: typeof init.body === "string" ? JSON.parse(init.body) : undefined });
      if (path === "/v1/motions") return new Response(JSON.stringify(MOTIONS), { status: 200 });
      if (path === "/v1/sessions" && method === "POST") {
        return new Response(
          JSON.stringify({ id: "s1", status: "created", upload_url: "https://upload.test/x", upload_headers: {}, expires_in_seconds: 900 }),
          { status: 201 },
        );
      }
      if (method === "PUT") return new Response(null, { status: 200 });
      return new Response(JSON.stringify({ id: "s1", status: "queued" }), { status: 202 });
    }),
  );
  return calls;
}

describe("motions API", () => {
  it("reads the list from the backend", async () => {
    const calls = fakeBackend();
    await expect(getMotions()).resolves.toEqual(MOTIONS);
    expect(calls[0]).toMatchObject({ url: "/v1/motions", method: "GET" });
  });

  it("sends the chosen motion id when creating the session", async () => {
    const calls = fakeBackend();
    await uploadAndStart(new Blob(["x"], { type: "audio/webm" }), "My speech", "carbon-tax");

    const create = calls.find((c) => c.url === "/v1/sessions" && c.method === "POST");
    expect(create?.body).toEqual({ content_type: "audio/webm", title: "My speech", motion_id: "carbon-tax" });
  });

  it("with No prompt, sends exactly the request it always sent (no motion_id key at all)", async () => {
    const calls = fakeBackend();
    await uploadAndStart(new Blob(["x"], { type: "audio/webm" }), null, null);
    await uploadAndStart(new Blob(["x"], { type: "audio/webm" }), null);

    const creates = calls.filter((c) => c.url === "/v1/sessions" && c.method === "POST");
    expect(creates.map((c) => c.body)).toEqual([
      { content_type: "audio/webm", title: null },
      { content_type: "audio/webm", title: null },
    ]);
  });
});
