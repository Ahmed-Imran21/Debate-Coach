import type { Metadata } from "next";
import type { ReactElement } from "react";

import AboutSections from "@/components/AboutSections";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";

export const metadata: Metadata = {
  title: "About",
};

/**
 * The same explanatory content as the landing page, but under the
 * app header so a signed-in reader keeps their way back to
 * Sessions instead of being handed a "Sign in" link.
 */
export default function AboutPage(): ReactElement {
  return (
    <div className="shell">
      <SiteHeader variant="app" />

      <main>
        <section className="block-tight" style={{ paddingTop: "2.5rem" }}>
          <div className="wrap">
            <h1 style={{ fontSize: "var(--step-4)" }}>About</h1>
            <p className="lede" style={{ margin: "1rem 0 0", maxWidth: "60ch" }}>
              What Debate Coach measures, how a session runs, and what
              it does not do yet.
            </p>
          </div>
        </section>

        <AboutSections />
      </main>

      <SiteFooter />
    </div>
  );
}
