import { NextRequest, NextResponse } from "next/server";

import { ADMIN_LINK, GATE_COOKIE, isAdminToken } from "./lib/admin-gate";
import { SHARED_PAGE_HEADERS } from "./lib/shared-headers.mjs";

/**
 * Server-side gate for /admin. The backend's require_admin is the
 * real security boundary (every /v1/admin route answers a plain 404
 * to anyone else); this keeps a non-admin from ever receiving the
 * admin page or learning it exists.
 *
 * Reads the first-party gate cookie app/api/session/route.ts sets,
 * then re-checks it with the backend on every request rather than
 * trusting its presence — so an expired token, or an account since
 * removed from ADMIN_EMAILS, is turned away immediately.
 *
 * Refusal is a rewrite to a path that doesn't exist, so the response
 * is the app's ordinary not-found page: same status and byte-for-byte
 * body as any unknown URL. A bare 404 or a redirect would each be
 * distinguishable. (`next start` also adds an x-middleware-rewrite
 * header; a gate in app/admin/layout.tsx calling notFound() was tried
 * instead and differs far more — body, headers, and a reference to
 * the admin chunk.)
 */

const NOT_FOUND_PATH = "/__not-found";

function isAdminPath(pathname: string): boolean {
  const base = ADMIN_LINK.href;
  // "/admin.rsc" and similar are the same page's alternate payloads.
  return pathname === base || pathname.startsWith(`${base}/`) || pathname.startsWith(`${base}.`);
}

function isSharedPath(pathname: string): boolean {
  return pathname === "/shared" || pathname.startsWith("/shared/");
}

export async function middleware(request: NextRequest): Promise<NextResponse> {
  // Public shared reports: explicitly allowed with no sign-in (the
  // backend decides what a token can see), with their no-index,
  // no-store, no-referrer headers. This touches nothing else: every
  // other path is handled exactly as before.
  if (isSharedPath(request.nextUrl.pathname)) {
    const response = NextResponse.next();
    for (const { key, value } of SHARED_PAGE_HEADERS) response.headers.set(key, value);
    return response;
  }

  if (!isAdminPath(request.nextUrl.pathname)) {
    return NextResponse.next();
  }

  const token = request.cookies.get(GATE_COOKIE)?.value;

  if (token && (await isAdminToken(token))) {
    return NextResponse.next();
  }

  return NextResponse.rewrite(new URL(NOT_FOUND_PATH, request.url));
}

// Deliberately generic: Next.js copies this matcher into its public
// client runtime (window.__MIDDLEWARE_MATCHERS), so "/admin/:path*"
// here would name the admin page to every visitor. The real check is
// isAdminPath() above, which stays server-side. Every other path
// returns immediately, with no backend call.
export const config = {
  matcher: "/((?!_next/static|_next/image).*)",
};
