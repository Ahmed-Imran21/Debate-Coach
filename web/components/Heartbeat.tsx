"use client";

import { useEffect } from "react";

import { getAccessToken, heartbeat } from "@/lib/api";

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

    // Fire once immediately rather than waiting a full interval
    // for the first tick, then on the regular cadence.
    void heartbeat().catch(() => {});

    const id = setInterval(() => {
      if (!getAccessToken()) return;
      void heartbeat().catch(() => {});
    }, INTERVAL_MS);

    return () => clearInterval(id);
  }, []);

  return null;
}
