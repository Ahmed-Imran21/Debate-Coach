import Link from "next/link";
import type { ReactElement } from "react";

import AboutSections from "@/components/AboutSections";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import SpeechTrack, { type Mark } from "@/components/SpeechTrack";

/**
 * Findings from one test recording, used to show what the
 * output looks like before someone signs up. Labelled as a
 * test recording on the page, because it is one.
 */
const SAMPLE_DURATION = 247;

const SAMPLE_MARKS: Mark[] = [
  { at: 14, kind: "filler" },
  { at: 22, kind: "pause", span: 1.4 },
  { at: 31, kind: "filler" },
  { at: 44, kind: "stutter" },
  { at: 58, kind: "pause", span: 2.1 },
  { at: 71, kind: "filler" },
  { at: 76, kind: "filler" },
  { at: 93, kind: "fallacy" },
  { at: 108, kind: "pause", span: 1.2 },
  { at: 121, kind: "filler" },
  { at: 137, kind: "stutter" },
  { at: 149, kind: "pause", span: 3.4 },
  { at: 162, kind: "filler" },
  { at: 171, kind: "filler" },
  { at: 186, kind: "fallacy" },
  { at: 199, kind: "pause", span: 1.1 },
  { at: 214, kind: "filler" },
  { at: 228, kind: "pause", span: 1.8 },
  { at: 239, kind: "filler" },
];

export default function HomePage(): ReactElement {
  return (
    <div className="shell">
      <SiteHeader />

      <main>
        <section className="block">
          <div className="wrap">
            <h1 style={{ maxWidth: "18ch" }}>
              Your speech, marked up second by second
            </h1>

            <p className="lede" style={{ margin: "1.25rem 0 2rem" }}>
              Record a practice speech in the browser. Debate Coach
              transcribes it, counts your pace, pauses and filler words
              from the audio itself, then reads the argument you made and
              tells you where it held and where it did not.
            </p>

            <div className="btn-row" style={{ marginBottom: "3rem" }}>
              <Link className="btn" href="/signup">
                Create an account
              </Link>
              <Link className="btn btn-quiet" href="/login">
                Sign in
              </Link>
            </div>

            <SpeechTrack
              duration={SAMPLE_DURATION}
              marks={SAMPLE_MARKS}
              title="Sample analysis"
              caption="One four-minute test recording, showing where each finding landed. Your own sessions render the same way."
            />
          </div>
        </section>

        <AboutSections />

        <section className="block">
          <div className="wrap">
            <h2>Start with one speech</h2>
            <p className="lede" style={{ margin: "0.75rem 0 1.75rem" }}>
              Record something you were going to practise anyway and see
              what comes back.
            </p>
            <Link className="btn" href="/signup">
              Create an account
            </Link>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
