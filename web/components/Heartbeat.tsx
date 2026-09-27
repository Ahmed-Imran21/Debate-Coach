"use client";

import { useEffect } from "react";

import { ensureServerSession, getAccessToken, heartbeat } from "@/lib/api";
import { createHeartbeat } from "@/lib/heartbeat";

/**
 * Mounted once, in the root layout, for every page. Pings
 * POST /v1/users/heartbeat every ~60s while a tab is open with a live
 * session token in localStorage: the fallback LastSeenMiddleware
 * (app/core/last_seen.py) itself documents. That middleware only
 * fires on requests that hit some other endpoint, so a tab sitting on
 * a page that makes no other API calls (e.g. the report page, after
 * it's loaded) would otherwise look inactive within a few minutes
 * even with the tab genuinely open. Renders nothing.
 *
 * It stops for good on a 401, and never sends while the stored token
 * is past its exp, so a forgotten tab with an expired session goes
 * quiet instead of failing every minute (lib/heartbeat.ts).
 */
export default function Heartbeat(): null {
  useEffect(() => {
    if (!getAccessToken()) return;

    const beat = createHeartbeat({ getToken: getAccessToken, send: heartbeat });

    // A page load is real activity, so this is where a session that
    // predates this tab (or whose gate cookie expired with its access
    // token) gets synced, refreshing first if the token has expired.
    // The heartbeat starts only after that, and only with a live token;
    // it never refreshes anything itself (see heartbeat() in api.ts).
    void ensureServerSession()
      .catch(() => {})
      .finally(() => beat.start());

    return () => beat.stop();
  }, []);

  return null;
}
