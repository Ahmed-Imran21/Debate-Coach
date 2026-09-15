import Link from "next/link";
import type { ReactElement } from "react";

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

        <section className="block" id="measures">
          <div className="wrap">
            <h2>What it measures</h2>

            <p className="lede" style={{ margin: "0.75rem 0 2.5rem" }}>
              Two passes, kept deliberately separate. Anything countable
              is counted in plain code. Anything that takes judgment goes
              to a language model, and only that.
            </p>

            <div className="split">
              <div>
                <h3>Counted from the audio</h3>
                <p className="note" style={{ margin: "0 0 1rem" }}>
                  Arithmetic over word-level timestamps and voice
                  activity detection. The same recording always produces
                  the same numbers.
                </p>

                <dl className="defs">
                  <dt>Speaking pace</dt>
                  <dd>
                    Words per minute over speaking time, not wall clock,
                    so long pauses do not flatter the figure.
                  </dd>

                  <dt>Pauses</dt>
                  <dd>
                    Count, total, average and longest, taken from voice
                    activity rather than gaps between words.
                  </dd>

                  <dt>Filler words</dt>
                  <dd>
                    Every occurrence, broken down by word, with the
                    timestamp of each one.
                  </dd>

                  <dt>Stutters and repeats</dt>
                  <dd>
                    Immediate repetitions and partial-word restarts,
                    located in the transcript.
                  </dd>
                </dl>
              </div>

              <div>
                <h3>Read from the argument</h3>
                <p className="note" style={{ margin: "0 0 1rem" }}>
                  A language model labels each segment of the transcript,
                  then five separate checks run over those labels. It is
                  asked to work only from what you actually said.
                </p>

                <dl className="defs">
                  <dt>Argumentation</dt>
                  <dd>
                    Which claims you made, which carried reasoning, and
                    which were left standing on their own.
                  </dd>

                  <dt>Rebuttal</dt>
                  <dd>
                    Whether you engaged with the opposing case or
                    restated your own position at it.
                  </dd>

                  <dt>Structure</dt>
                  <dd>
                    How the speech was ordered, where it turned, and
                    whether it closed.
                  </dd>

                  <dt>Logic and persuasion</dt>
                  <dd>
                    Named fallacies where they appear, and how well the
                    reasoning would carry a listener.
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </section>

        <section className="block" id="session">
          <div className="wrap">
            <h2>How a session runs</h2>

            <ol className="steps" style={{ marginTop: "1.5rem" }}>
              <li>
                <div>
                  <h3>Record in the browser</h3>
                  <p>
                    No install and no upload dialog. The recording goes
                    straight to storage from your machine.
                  </p>
                </div>
              </li>
              <li>
                <div>
                  <h3>Transcription with word timings</h3>
                  <p>
                    Every word gets a start and end time. That timing is
                    what makes the rest of the analysis possible.
                  </p>
                </div>
              </li>
              <li>
                <div>
                  <h3>Delivery metrics</h3>
                  <p>
                    Pace, pauses, fillers and stutters, counted without
                    any model involved.
                  </p>
                </div>
              </li>
              <li>
                <div>
                  <h3>Argument analysis</h3>
                  <p>
                    The transcript is labelled segment by segment, then
                    checked for reasoning, rebuttal and structure.
                  </p>
                </div>
              </li>
              <li>
                <div>
                  <h3>Feedback you can act on</h3>
                  <p>
                    Each finding names the issue, quotes the moment it
                    came from, and says what to do differently.
                  </p>
                </div>
              </li>
            </ol>

            <p className="note" style={{ marginTop: "1.5rem" }}>
              A four-minute speech takes a few minutes to come back. You
              can close the tab and return to it.
            </p>
          </div>
        </section>

        <section className="block">
          <div className="wrap prose">
            <h2>What it does not do yet</h2>

            <p>
              Worth knowing before you sign up, so the first session is
              not a surprise.
            </p>

            <ul>
              <li>
                <strong>One speaker at a time.</strong> It analyses your
                speech on its own. It does not listen to a round and tell
                you how you did against an opponent, because the pipeline
                does not yet separate turns.
              </li>
              <li>
                <strong>English only.</strong> Transcription supports
                other languages, but the filler, stutter and argument
                checks are written for English and will mislead you
                elsewhere.
              </li>
              <li>
                <strong>No live coaching.</strong> Analysis runs after
                the recording finishes. Nothing listens while you speak.
              </li>
              <li>
                <strong>It can be wrong about your argument.</strong> The
                delivery numbers are arithmetic and reliable. The reading
                of your reasoning comes from a language model and should
                be treated as a second opinion, not a verdict.
              </li>
            </ul>
          </div>
        </section>

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
