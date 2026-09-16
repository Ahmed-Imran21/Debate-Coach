import Link from "next/link";
import type { ReactElement } from "react";

interface Props {
  /** The practice area gets a reduced nav, since the marketing
   *  sections are not relevant once someone is signed in. */
  variant?: "site" | "app";
}

export default function SiteHeader({
  variant = "site",
}: Props): ReactElement {
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
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
