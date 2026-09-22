import { NextRequest, NextResponse } from "next/server";

/**
 * Server-side gate for /admin. This is the piece that runs
 * before any /admin page renders — the backend's require_admin
 * (app/routes/deps.py) is the actual security boundary (every
 * /admin/* route 403s a non-admin regardless of this file), but
 * that alone would still let a non-admin's browser download and
 * run the page's own JS before finding out. This stops that.
 *
 * Can't use the normal localStorage-based session (lib/api.ts)
 * here — middleware runs on the server, localStorage doesn't
 * exist there. Reads the httpOnly admin-only cookie
 * app/routes/auth.py sets on login/signup instead (never set at
 * all for a non-admin user) and asks the backend whether it's
 * actually valid, rather than trusting the cookie's mere
 * presence — a cookie that's expired, been revoked by an
 * ADMIN_EMAILS change since it was issued, or is simply wrong
 * must not pass.
 *
 * A bare 404 on failure, not a redirect: a redirect confirms to
 * a curious non-admin that *something* lives at this path. A 404
 * makes /admin indistinguishable from a route that was never
 * built.
 */

const ADMIN_SESSION_COOKIE = "dc_admin_session";

const API_ORIGIN = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

function notFound(): NextResponse {
  return new NextResponse(null, { status: 404 });
}

export async function middleware(request: NextRequest): Promise<NextResponse> {
  const token = request.cookies.get(ADMIN_SESSION_COOKIE)?.value;

  if (!token) {
    return notFound();
  }

  let response: Response;

  try {
    response = await fetch(`${API_ORIGIN}/v1/admin/whoami`, {
      headers: { Authorization: `Bearer ${token}` },
      // This check must reflect the current admin list on every
      // request, not a stale edge/browser cache of a 200 from
      // an account later removed from ADMIN_EMAILS.
      cache: "no-store",
    });
  } catch {
    // Backend unreachable: fail closed, not open.
    return notFound();
  }

  if (!response.ok) {
    return notFound();
  }

  return NextResponse.next();
}

export const config = {
  matcher: "/admin/:path*",
};
