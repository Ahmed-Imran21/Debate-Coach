"use client";

import { useEffect } from "react";

import { ensureServerSession, getAccessToken, heartbeat } from "@/lib/api";

const INTERVAL_MS = 60_000;

/**
 * Mounted once, in the root layout, for every page. Pings
 * POST /v1/users/heartbeat every ~60s while a tab is open and a
 * session token exists in localStorage — the fallback
 * LastSeenMiddleware (app/core/last_seen.py) itself documents:
 * that middleware only fires on requests that hit some other
 * endpoint, so a tab sitting on a page that makes no other API
 * calls (e.g. the report page, after it's loaded) would
 * otherwise look inactive within a few minutes even with the tab
 * genuinely open. Renders nothing.
 */
export default function Heartbeat(): null {
  useEffect(() => {
    if (!getAccessToken()) return;

    // A page load is real activity, so this is where a session that
    // predates this tab (or whose gate cookie expired with its access
    // token) gets synced — refreshing first if the token has expired.
    // The first heartbeat waits for it so it goes out with a live
    // token; the interval below never refreshes (see heartbeat()).
    void ensureServerSession()
      .catch(() => {})
      .finally(() => heartbeat().catch(() => {}));

    const id = setInterval(() => {
      if (!getAccessToken()) return;
      void heartbeat().catch(() => {});
    }, INTERVAL_MS);

    return () => clearInterval(id);
  }, []);

  return null;
}
