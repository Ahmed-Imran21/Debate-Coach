/**
 * Server-side only: imported by middleware.ts and
 * app/api/session/route.ts, never by client code, so the admin
 * path and the admin API route below never ship to the browser.
 * (Checked after every build: grep .next/static for "admin".)
 *
 * The gate cookie is first-party to the frontend's own domain. It
 * can't come from the backend: production runs the API on
 * *.run.app and this app on *.vercel.app, both public suffixes, so
 * a cookie set by one can never be read by the other.
 */

export const GATE_COOKIE = "dc_gate";

export const ADMIN_LINK = { href: "/admin", label: "Admin" } as const;

const API_ORIGIN = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

/**
 * True only on a 200 from the backend's admin check. The backend
 * answers every non-admin, bad token or wrong method with a plain
 * 404, so anything else — including the backend being unreachable —
 * is "not an admin". Fails closed.
 */
export async function isAdminToken(token: string): Promise<boolean> {
  try {
    const response = await fetch(`${API_ORIGIN}/v1/admin/whoami`, {
      headers: { Authorization: `Bearer ${token}` },
      // Must reflect the admin list as of this request, not a
      // cached 200 from before someone was removed from it.
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    return response.ok;
  } catch {
    return false;
  }
}
