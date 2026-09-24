/**
 * Reads a JWT's `exp` without verifying it — for scheduling (when
 * to refresh, when a cookie should expire), never for trust. The
 * backend verifies every token it's actually handed.
 */
export function tokenExpiresAt(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const base64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
    const exp = JSON.parse(atob(padded)).exp;
    return typeof exp === "number" ? exp * 1000 : null;
  } catch {
    return null;
  }
}
