/**
 * The admin user-management page's logic (app/admin/users/logic.ts)
 * and API calls (app/admin/admin-api.ts): debounced search, cursor
 * paging with stale responses dropped, relative "last seen", and the
 * typed-email gate on the delete button.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { deleteUser, listUsers } from "../../app/admin/admin-api";
import {
  canConfirmDelete,
  createDebouncer,
  deleteButtonEnabled,
  formatLastSeen,
  initialListState,
  listReducer,
  type ListState,
} from "../../app/admin/users/logic";
import { ApiError } from "../api";
import type { AdminUser, AdminUserPage } from "../types";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const user = (n: number): AdminUser => ({
  id: `id-${n}`,
  email: `u${n}@test.com`,
  first_name: "F",
  last_name: "L",
  created_at: "2026-09-01T00:00:00Z",
  last_seen_at: null,
  session_count: 0,
  is_admin: false,
});

const page = (ns: number[], next: string | null): AdminUserPage => ({ users: ns.map(user), next_cursor: next });

describe("createDebouncer", () => {
  it("fires once, with the latest value, after typing pauses", () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const d = createDebouncer(fn, 300);

    d.call("a");
    vi.advanceTimersByTime(200);
    d.call("al");
    vi.advanceTimersByTime(200);
    d.call("ali");
    expect(fn).not.toHaveBeenCalled();

    vi.advanceTimersByTime(300);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith("ali");
  });

  it("fires again for a later pause, and cancel drops a pending call", () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const d = createDebouncer(fn, 300);

    d.call("x");
    vi.advanceTimersByTime(300);
    d.call("y");
    vi.advanceTimersByTime(300);
    d.call("z");
    d.cancel();
    vi.advanceTimersByTime(1000);

    expect(fn.mock.calls).toEqual([["x"], ["y"]]);
  });
});

describe("formatLastSeen", () => {
  const now = Date.parse("2026-09-24T12:00:00Z");
  const ago = (s: number) => new Date(now - s * 1000).toISOString();

  it.each([
    [null, "never"],
    [ago(0), "just now"],
    [ago(59), "just now"],
    [ago(-30), "just now"],
    [ago(60), "1 minute ago"],
    [ago(5 * 60), "5 minutes ago"],
    [ago(3600), "1 hour ago"],
    [ago(23 * 3600), "23 hours ago"],
    [ago(3 * 86400), "3 days ago"],
    [ago(29 * 86400), "29 days ago"],
    [ago(60 * 86400), "2 months ago"],
    [ago(400 * 86400), "1 year ago"],
  ])("%s -> %s", (iso, expected) => {
    expect(formatLastSeen(iso, now)).toBe(expected);
  });
});

describe("delete confirmation gate", () => {
  const email = "target@test.com";

  it("needs the exact email", () => {
    expect(canConfirmDelete("target@test.com", email)).toBe(true);
    expect(canConfirmDelete("  target@test.com ", email)).toBe(true);
    for (const typed of ["", "target", "target@test.co", "TARGET@test.com", "target@test.comx"]) {
      expect(canConfirmDelete(typed, email), typed).toBe(false);
      expect(deleteButtonEnabled(typed, email, "pw", false), typed).toBe(false);
    }
  });

  it("needs the exact email AND a non-empty password, never while in flight", () => {
    expect(deleteButtonEnabled(email, email, "pw", false)).toBe(true);
    expect(deleteButtonEnabled(email, email, "", false)).toBe(false);
    expect(deleteButtonEnabled("wrong@test.com", email, "pw", false)).toBe(false);
    expect(deleteButtonEnabled(email, email, "pw", true)).toBe(false);
    expect(deleteButtonEnabled(email, undefined, "pw", false)).toBe(false);
  });
});

describe("listReducer", () => {
  const started = (requestId: number): ListState =>
    listReducer(initialListState, { type: "start", requestId, search: "", sort: "newest" });

  it("walks cursor pages by appending, with no duplicates", () => {
    let s = started(1);
    s = listReducer(s, { type: "loaded", requestId: 1, page: page([1, 2], "c1"), append: false });
    s = listReducer(s, { type: "more", requestId: 2 });
    expect(s.status).toBe("loading-more");
    s = listReducer(s, { type: "loaded", requestId: 2, page: page([2, 3], "c2"), append: true });
    s = listReducer(s, { type: "more", requestId: 3 });
    s = listReducer(s, { type: "loaded", requestId: 3, page: page([4], null), append: true });

    expect(s.users.map((u) => u.id)).toEqual(["id-1", "id-2", "id-3", "id-4"]);
    expect(s.nextCursor).toBeNull();
    expect(s.status).toBe("idle");
  });

  it("drops a slow response for an old search that lands after a newer one", () => {
    let s = started(1); // search "a"
    s = listReducer(s, { type: "start", requestId: 2, search: "ab", sort: "newest" });
    s = listReducer(s, { type: "loaded", requestId: 2, page: page([7], null), append: false });
    s = listReducer(s, { type: "loaded", requestId: 1, page: page([1, 2, 3], "old"), append: false });
    s = listReducer(s, { type: "failed", requestId: 1, message: "stale" });

    expect(s.users.map((u) => u.id)).toEqual(["id-7"]);
    expect(s.search).toBe("ab");
    expect(s.error).toBeNull();
  });

  it("a new search or sort clears the list and cursor", () => {
    let s = started(1);
    s = listReducer(s, { type: "loaded", requestId: 1, page: page([1, 2], "c1"), append: false });
    s = listReducer(s, { type: "start", requestId: 2, search: "", sort: "last_seen" });
    expect(s).toMatchObject({ users: [], nextCursor: null, status: "loading", sort: "last_seen" });
  });

  it("removes a deleted user without touching the cursor", () => {
    let s = started(1);
    s = listReducer(s, { type: "loaded", requestId: 1, page: page([1, 2, 3], "c1"), append: false });
    s = listReducer(s, { type: "removed", id: "id-2" });
    expect(s.users.map((u) => u.id)).toEqual(["id-1", "id-3"]);
    expect(s.nextCursor).toBe("c1");
  });
});

describe("admin-api", () => {
  function captureFetch(respond: () => Response) {
    const calls: { url: string; method: string; body?: BodyInit | null }[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit = {}) => {
      calls.push({ url, method: init.method ?? "GET", body: init.body });
      return respond();
    }));
    return calls;
  }

  it("builds the list query: trimmed search, default sort omitted, cursor encoded", async () => {
    const calls = captureFetch(() => new Response(JSON.stringify(page([], null)), { status: 200 }));

    await listUsers({});
    await listUsers({ search: "  Jane Doe ", sort: "last_seen", cursor: "abc+/=", limit: 50 });
    await listUsers({ search: "   ", sort: "newest" });

    expect(calls.map((c) => c.url.replace(/^https?:\/\/[^/]+/, ""))).toEqual([
      "/v1/admin/users",
      "/v1/admin/users?search=Jane+Doe&sort=last_seen&cursor=abc%2B%2F%3D&limit=50",
      "/v1/admin/users",
    ]);
  });

  it("deletes by id with the admin's password in the body, and surfaces the refusal", async () => {
    const calls = captureFetch(
      () => new Response(JSON.stringify({ detail: "This account is an admin." }), { status: 409 }),
    );

    await expect(deleteUser("id/1", "AdminPass123")).rejects.toEqual(new ApiError(409, "This account is an admin."));
    expect(calls[0]).toMatchObject({ method: "DELETE" });
    expect(calls[0].url).toMatch(/\/v1\/admin\/users\/id%2F1$/);
    expect(JSON.parse(String(calls[0].body))).toEqual({ password: "AdminPass123" });
  });

  it("surfaces a wrong password as its own 401, distinct from an expired session", async () => {
    captureFetch(() => new Response(JSON.stringify({ detail: "Incorrect password." }), { status: 401 }));
    await expect(deleteUser("id-1", "nope")).rejects.toEqual(new ApiError(401, "Incorrect password."));
  });
});
