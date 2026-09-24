"use client";

import type { ReactElement } from "react";

import { setVideoAnalysisConsent } from "@/features/video-analysis/consent";

interface Props {
  onDecide: (choice: "in" | "out") => void;
}

/**
 * Shown before ever requesting camera permission (task doc §4.3).
 * Plain copy: what's measured, what isn't done, what leaves the
 * device, and that MediaPipe itself reports usage statistics to
 * Google.
 */
export default function ConsentPanel({ onDecide }: Props): ReactElement {
  function choose(choice: "in" | "out"): void {
    setVideoAnalysisConsent(choice);
    onDecide(choice);
  }

  return (
    <div className="form-panel" style={{ maxWidth: "34rem" }}>
      <h2 style={{ fontSize: "var(--step-2)", marginBottom: "0.75rem" }}>
        Visual feedback (optional)
      </h2>

      <p className="note" style={{ marginBottom: "1.25rem" }}>
        Debate Coach can also look at your camera while you record, in
        addition to your audio.
      </p>

      <dl className="defs" style={{ marginBottom: "1.25rem" }}>
        <dt>What is measured</dt>
        <dd>
          Which way your head faces, whether you&apos;re facing the
          camera, and where your hands are and how much they move.
        </dd>

        <dt>What is not done</dt>
        <dd>
          No video is recorded, uploaded, or saved. No identity
          recognition. No emotion detection.
        </dd>

        <dt>What leaves this device</dt>
        <dd>
          Numbers describing movement over time, plus your audio, the
          same as it does today.
        </dd>

        <dt>One more thing</dt>
        <dd>
          The on-device vision library this uses (Google MediaPipe)
          sends its own usage and performance statistics to Google.
          See{" "}
          <a
            href="https://goo.gle/mediapipe-privacy"
            target="_blank"
            rel="noreferrer"
          >
            MediaPipe&apos;s privacy notice
          </a>
          .
        </dd>
      </dl>

      <div className="btn-row">
        <button className="btn" type="button" onClick={() => choose("in")}>
          Turn on visual feedback
        </button>
        <button
          className="btn btn-quiet"
          type="button"
          onClick={() => choose("out")}
        >
          Continue with audio only
        </button>
      </div>
    </div>
  );
}
