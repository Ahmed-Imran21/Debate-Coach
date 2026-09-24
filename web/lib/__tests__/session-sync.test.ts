/**
 * Every token change in lib/api.ts must keep the gate cookie in
 * step: login, signup and refresh sync it (and are awaited before
 * the caller continues); a failed refresh, sign-out, session expiry
 * and account deletion clear it; a page load with a pre-existing
 * session syncs once. See the sync table in app/api/session/route.ts.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type Call = { url: string; method: string; auth?: string; keepalive?: boolean };

function memoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    get length() { return data.size; },
    clear: () => data.clear(),
    getItem: (k) => data.get(k) ?? null,
    key: (i) => [...data.keys()][i] ?? null,
    removeItem: (k) => void data.delete(k),
    setItem: (k, v) => void data.set(k, String(v)),
  };
}

function jwt(expSecondsFromNow: number, tag: string): string {
  const b64 = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");
  const exp = Math.floor(Date.now() / 1000) + expSecondsFromNow;
  return `${b64({ alg: "HS256" })}.${b64({ sub: tag, exp })}.signature-for-${tag}`;
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

let calls: Call[];
let sessionAnswer: object;
let refreshOk: boolean;
const FRESH = jwt(3600, "fresh");

function installFetch(extra: (url: string, method: string) => Response | undefined = () => undefined) {
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit = {}) => {
    const method = init.method ?? "GET";
    const headers = (init.headers ?? {}) as Record<string, string>;
    calls.push({ url, method, auth: headers.Authorization, keepalive: init.keepalive });

    if (url === "/api/session") return method === "DELETE" ? new Response(null, { status: 204 }) : json(sessionAnswer);
    if (url.endsWith("/v1/auth/refresh")) {
      return refreshOk ? json({ access_token: FRESH, refresh_token: "r2" }) : json({ detail: "no" }, 401);
    }
    if (url.endsWith("/v1/auth/login") || url.endsWith("/v1/auth/signup")) {
      return json({ access_token: FRESH, refresh_token: "r1" });
    }
    return extra(url, method) ?? json({ detail: "Not Found" }, 404);
  }));
}

const sessionCalls = () => calls.filter((c) => c.url === "/api/session");
const api = () => import("../api");

beforeEach(() => {
  vi.resetModules();
  vi.stubGlobal("window", { localStorage: memoryStorage(), sessionStorage: memoryStorage() });
  calls = [];
  sessionAnswer = {};
  refreshOk = true;
  installFetch();
});

afterEach(() => vi.unstubAllGlobals());

describe("store paths sync, and are awaited", () => {
  it.each(["login", "signup"] as const)("%s syncs the new token before resolving", async (which) => {
    const { login, signup } = await api();
    if (which === "login") await login({ email: "a@test.com", password: "x" });
    else await signup({ email: "a@test.com", password: "x", first_name: "A", last_name: "B" });

    expect(sessionCalls()).toEqual([
      { url: "/api/session", method: "POST", auth: `Bearer ${FRESH}`, keepalive: undefined },
    ]);
  });

  it("a successful refresh re-syncs with the new token", async () => {
    let first = true;
    installFetch((url) => {
      if (url.endsWith("/v1/users/me")) {
        if (first) { first = false; return json({ detail: "expired" }, 401); }
        return json({ id: "u1" });
      }
    });
    window.localStorage.setItem("dc.access", jwt(3600, "old"));
    window.localStorage.setItem("dc.refresh", "r1");

    const { getCurrentUser } = await api();
    await getCurrentUser();

    const syncs = sessionCalls().filter((c) => c.method === "POST");
    expect(syncs.map((c) => c.auth)).toEqual([`Bearer ${FRESH}`]);
  });
});

describe("clear paths clear, with keepalive", () => {
  it("a failed refresh clears", async () => {
    refreshOk = false;
    installFetch((url) => (url.endsWith("/v1/users/me") ? json({ detail: "expired" }, 401) : undefined));
    window.localStorage.setItem("dc.access", jwt(3600, "old"));
    window.localStorage.setItem("dc.refresh", "r1");

    const { getCurrentUser } = await api();
    await expect(getCurrentUser()).rejects.toMatchObject({ status: 401 });

    expect(sessionCalls()).toEqual([{ url: "/api/session", method: "DELETE", auth: undefined, keepalive: true }]);
  });

  it("sign-out and account deletion (both call clearTokens) clear", async () => {
    const { clearTokens } = await api();
    clearTokens();
    expect(sessionCalls()).toEqual([{ url: "/api/session", method: "DELETE", auth: undefined, keepalive: true }]);
  });

  it("the session-expiry redirect clears", async () => {
    const { redirectToLoginAfterSessionExpiry } = await api();
    const replace = vi.fn();
    redirectToLoginAfterSessionExpiry({ replace });
    expect(sessionCalls()).toMatchObject([{ method: "DELETE", keepalive: true }]);
    expect(replace).toHaveBeenCalledWith("/login?reason=expired");
  });
});

describe("page-load sync for a pre-existing session", () => {
  it("syncs once, shared by concurrent callers, and not again after a reload in the same tab", async () => {
    const token = jwt(3600, "existing");
    window.localStorage.setItem("dc.access", token);
    sessionAnswer = { adminLink: { href: "/admin", label: "Admin" } };

    const first = await api();
    const [a, b] = await Promise.all([first.ensureServerSession(), first.getAdminLink()]);
    expect(a).toEqual(sessionAnswer);
    expect(b).toEqual({ href: "/admin", label: "Admin" });
    expect(sessionCalls()).toHaveLength(1);

    vi.resetModules(); // a reload: module state gone, sessionStorage kept
    const reloaded = await api();
    expect(await reloaded.getAdminLink()).toEqual({ href: "/admin", label: "Admin" });
    expect(sessionCalls()).toHaveLength(1);
  });

  it("refreshes an expired token first, once, then syncs the new one", async () => {
    window.localStorage.setItem("dc.access", jwt(-60, "expired"));
    window.localStorage.setItem("dc.refresh", "r1");

    const { ensureServerSession } = await api();
    await Promise.all([ensureServerSession(), ensureServerSession()]);

    expect(calls.filter((c) => c.url.endsWith("/v1/auth/refresh"))).toHaveLength(1);
    expect(sessionCalls().map((c) => c.auth)).toEqual([`Bearer ${FRESH}`]);
  });

  it("a non-admin gets no link, and clearTokens forgets the memo so the next session syncs fresh", async () => {
    window.localStorage.setItem("dc.access", jwt(3600, "someone"));
    const { getAdminLink, clearTokens, ensureServerSession } = await api();

    expect(await getAdminLink()).toBeNull();
    clearTokens();
    window.localStorage.setItem("dc.access", jwt(3600, "someone"));
    await ensureServerSession();

    expect(sessionCalls().map((c) => c.method)).toEqual(["POST", "DELETE", "POST"]);
  });

  it("does nothing without a session", async () => {
    const { ensureServerSession } = await api();
    expect(await ensureServerSession()).toEqual({});
    expect(calls).toEqual([]);
  });
});
