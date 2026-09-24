import { NextRequest, NextResponse } from "next/server";

import { ADMIN_LINK, GATE_COOKIE, isAdminToken } from "../../../lib/admin-gate";
import { tokenExpiresAt } from "../../../lib/jwt";

/**
 * Keeps the first-party gate cookie that middleware.ts checks in
 * step with the client's session. lib/api.ts calls POST whenever
 * tokens are stored (login, signup, refresh, page load) and DELETE
 * whenever they're cleared (sign-out, expiry, account deletion).
 *
 * A non-admin must learn nothing here: they get `{}` and no
 * Set-Cookie at all. The only clearing header ever sent goes to a
 * browser that already holds the cookie.
 */

function bearer(request: NextRequest): string | null {
  const match = /^Bearer\s+(\S+)$/i.exec(request.headers.get("authorization") ?? "");
  return match ? match[1] : null;
}

function cookieBase() {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    // First-party now, so Lax is enough: the cookie only needs to
    // ride along on this site's own page loads.
    sameSite: "lax" as const,
    path: "/",
  };
}

function clearIfPresent(request: NextRequest, response: NextResponse): NextResponse {
  if (request.cookies.has(GATE_COOKIE)) {
    response.cookies.set(GATE_COOKIE, "", { ...cookieBase(), maxAge: 0 });
  }
  return response;
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const token = bearer(request);
  const expiresAt = token ? tokenExpiresAt(token) : null;

  if (token && expiresAt !== null && expiresAt > Date.now() && (await isAdminToken(token))) {
    const response = NextResponse.json({ adminLink: ADMIN_LINK });
    // Expires with the access token it carries; lib/api.ts re-syncs
    // on every refresh, so an active admin always has a live one.
    response.cookies.set(GATE_COOKIE, token, { ...cookieBase(), expires: new Date(expiresAt) });
    return response;
  }

  return clearIfPresent(request, NextResponse.json({}));
}

export function DELETE(request: NextRequest): NextResponse {
  return clearIfPresent(request, new NextResponse(null, { status: 204 }));
}
