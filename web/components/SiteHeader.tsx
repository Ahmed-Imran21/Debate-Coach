"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { ReactElement } from "react";

import { isCurrentUserAdmin } from "@/lib/api";

interface Props {
  /** The practice area gets a reduced nav, since the marketing
   *  sections are not relevant once someone is signed in. */
  variant?: "site" | "app";
}

export default function SiteHeader({
  variant = "site",
}: Props): ReactElement {
  // Only ever checked for the signed-in nav — "site" is shown to
  // a visitor regardless of actual auth state (see the /about
  // comment below), so there is no signed-in user to check here.
  // isCurrentUserAdmin() is memoized per access token (lib/api.ts),
  // so this component re-mounting on every page navigation costs
  // one shared network round trip total, not one per page — a
  // non-admin's browser makes exactly one cheap, silently-failing
  // request for the whole session and never shows the link.
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    if (variant !== "app") return;

    let cancelled = false;
    isCurrentUserAdmin().then((admin) => {
      if (!cancelled) setIsAdmin(admin);
    });

    return () => {
      cancelled = true;
    };
  }, [variant]);

  return (
    <header className="masthead">
      <div className="wrap masthead-inner">
        <Link
          className="wordmark"
          href={variant === "app" ? "/practice" : "/"}
        >
          <svg
            width="18"
            height="20"
            viewBox="0 0 18 20"
            aria-hidden="true"
            fill="none"
          >
            <rect x="0" y="6" width="2" height="8" fill="var(--rule-strong)" />
            <rect x="5" y="2" width="2" height="16" fill="var(--pine)" />
            <rect x="10" y="7" width="2" height="6" fill="var(--rule-strong)" />
            <rect x="15" y="4" width="2" height="12" fill="var(--pine)" />
          </svg>
          Debate Coach
        </Link>

        <nav className="nav">
          {variant === "site" ? (
            <>
              <Link href="/#measures">What it measures</Link>
              <Link href="/#session">How a session runs</Link>
              <Link href="/login">Sign in</Link>
            </>
          ) : (
            <>
              <Link href="/practice">Sessions</Link>
              {/* /about, not /: the landing page hands a signed-in
                  reader a "Sign in" link and no way back to their
                  sessions. */}
              <Link href="/about">About</Link>
              {/* Absent, not disabled/greyed, for a non-admin —
                  same "don't reveal the route exists" principle
                  middleware.ts already applies to the page itself. */}
              {isAdmin && <Link href="/admin">Admin</Link>}
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
