/**
 * app/api/session/route.ts and middleware.ts: the first-party gate.
 * An admin gets the cookie; a non-admin gets `{}` and never a
 * Set-Cookie of any kind; middleware lets only a backend-confirmed
 * admin through and otherwise rewrites to an ordinary not-found.
 */

import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DELETE, POST } from "../../app/api/session/route";
import { middleware } from "../../middleware";

function jwt(expSecondsFromNow: number): string {
  const b64 = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");
  const exp = Math.floor(Date.now() / 1000) + expSecondsFromNow;
  return `${b64({ alg: "HS256", typ: "JWT" })}.${b64({ sub: "u1", exp })}.sig-${expSecondsFromNow}`;
}

function backendSays(status: number) {
  const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => new Response("{}", { status }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function sessionRequest(method: "POST" | "DELETE", opts: { token?: string; gateCookie?: string } = {}) {
  const headers: Record<string, string> = {};
  if (opts.token) headers.authorization = `Bearer ${opts.token}`;
  if (opts.gateCookie) headers.cookie = `dc_gate=${opts.gateCookie}`;
  return new NextRequest("https://app.test/api/session", { method, headers });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("POST /api/session", () => {
  it("sets a first-party httpOnly cookie for an admin, expiring with the token", async () => {
    const fetchMock = backendSays(200);
    const token = jwt(3600);

    const response = await POST(sessionRequest("POST", { token }));

    expect(await response.json()).toEqual({ adminLink: { href: "/admin", label: "Admin" } });
    const cookie = response.cookies.get("dc_gate");
    expect(cookie?.value).toBe(token);
    expect(cookie?.httpOnly).toBe(true);
    expect(cookie?.sameSite).toBe("lax");
    expect(cookie?.path).toBe("/");
    const expires = new Date(cookie!.expires as Date).getTime();
    expect(Math.abs(expires - (Date.now() + 3600_000))).toBeLessThan(5_000);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/v1\/admin\/whoami$/);
    expect((init?.headers as Record<string, string>).Authorization).toBe(`Bearer ${token}`);
  });

  it("marks the cookie Secure in production", async () => {
    vi.stubEnv("NODE_ENV", "production");
    backendSays(200);

    const response = await POST(sessionRequest("POST", { token: jwt(3600) }));
    expect(response.cookies.get("dc_gate")?.secure).toBe(true);
  });

  it("gives a non-admin an empty body and no Set-Cookie at all", async () => {
    backendSays(404);

    const response = await POST(sessionRequest("POST", { token: jwt(3600) }));

    expect(await response.json()).toEqual({});
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it("clears a stale cookie when the browser holding it is no longer an admin", async () => {
    backendSays(404);

    const response = await POST(sessionRequest("POST", { token: jwt(3600), gateCookie: "old-admin-token" }));

    expect(await response.json()).toEqual({});
    const header = response.headers.get("set-cookie") ?? "";
    expect(header).toMatch(/^dc_gate=;/);
    expect(header.toLowerCase()).toContain("max-age=0");
  });

  it("never calls the backend for an expired or missing token", async () => {
    const fetchMock = backendSays(200);

    for (const request of [sessionRequest("POST", { token: jwt(-10) }), sessionRequest("POST")]) {
      const response = await POST(request);
      expect(await response.json()).toEqual({});
      expect(response.headers.get("set-cookie")).toBeNull();
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("fails closed when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("fetch failed"); }));

    const response = await POST(sessionRequest("POST", { token: jwt(3600) }));
    expect(await response.json()).toEqual({});
    expect(response.cookies.get("dc_gate")).toBeUndefined();
  });
});

describe("DELETE /api/session", () => {
  it("clears the cookie only for a browser that has one", async () => {
    const withCookie = DELETE(sessionRequest("DELETE", { gateCookie: "t" }));
    expect(withCookie.status).toBe(204);
    expect(withCookie.headers.get("set-cookie")).toMatch(/^dc_gate=;/);

    const without = DELETE(sessionRequest("DELETE"));
    expect(without.status).toBe(204);
    expect(without.headers.get("set-cookie")).toBeNull();
  });
});

describe("middleware", () => {
  const adminRequest = (cookie?: string) =>
    new NextRequest("https://app.test/admin", { headers: cookie ? { cookie: `dc_gate=${cookie}` } : {} });

  it("rewrites to a nonexistent path when there's no cookie, without asking the backend", async () => {
    const fetchMock = backendSays(200);

    const response = await middleware(adminRequest());

    expect(response.headers.get("x-middleware-rewrite")).toBe("https://app.test/__not-found");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rewrites when the backend no longer confirms the cookie's token", async () => {
    backendSays(404);
    const response = await middleware(adminRequest("stale"));
    expect(response.headers.get("x-middleware-rewrite")).toBe("https://app.test/__not-found");
  });

  it("passes every other path straight through without asking the backend", async () => {
    const fetchMock = backendSays(200);
    for (const path of ["/", "/practice", "/login", "/administrator", "/api/session"]) {
      const response = await middleware(new NextRequest(`https://app.test${path}`));
      expect(response.headers.get("x-middleware-next"), path).toBe("1");
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("gates the admin page's subpaths and alternate payloads too", async () => {
    backendSays(200);
    for (const path of ["/admin/x", "/admin.rsc"]) {
      const response = await middleware(new NextRequest(`https://app.test${path}`));
      expect(response.headers.get("x-middleware-rewrite"), path).toBe("https://app.test/__not-found");
    }
  });

  it("keeps its matcher generic, since Next.js ships it to every browser", async () => {
    const { config } = await import("../../middleware");
    expect(JSON.stringify(config)).not.toContain("admin");
  });

  it("lets a confirmed admin through", async () => {
    backendSays(200);
    const response = await middleware(adminRequest("good"));
    expect(response.headers.get("x-middleware-next")).toBe("1");
    expect(response.headers.get("x-middleware-rewrite")).toBeNull();
  });
});
