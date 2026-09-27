import type { Metadata } from "next";
import type { ReactNode } from "react";

// A shared report is reachable by anyone with its link, but it's
// never meant to be found: no indexing, no following, and the link
// (which is the credential) is never sent on as a Referer. The same
// rules are also sent as response headers (next.config.mjs), and the
// backend sends them on the data itself (app/routes/shared.py).
export const metadata: Metadata = {
  title: "Shared report",
  robots: { index: false, follow: false, nocache: true, googleBot: { index: false, follow: false } },
  referrer: "no-referrer",
};

export default function SharedLayout({ children }: { children: ReactNode }): ReactNode {
  return children;
}
