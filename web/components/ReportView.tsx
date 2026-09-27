"use client";

import { useMemo, useState } from "react";
import type { ReactElement, ReactNode } from "react";
import { flushSync } from "react-dom";

import KeyMomentsList from "@/components/KeyMomentsList";
import { formatClock } from "@/components/SpeechTrack";
import VisualDeliverySection from "@/components/VisualDeliverySection";
import { motionFallbackNote } from "@/lib/motions";
import {
  CATEGORY_LABEL,
  type Category,
  type FeedbackItem,
  type Severity,
  type VisualView,
} from "@/lib/types";

const SEVERITY_ORDER: Severity[] = ["high", "medium", "low", "positive"];

const SEVERITY_LABEL: Record<Severity, string> = {
  high: "Needs work",
  medium: "Worth fixing",
  low: "Minor",
  positive: "Working well",
};

const SCORE_ORDER: Category[] = [
  "quantitative",
  "argumentation",
  "rebuttal",
  "structure",
  "persuasion",
  "logic",
];

export type FindingView = Pick<
  FeedbackItem,
  "category" | "title" | "issue" | "severity" | "evidence" | "explanation" | "recommendation"
>;

export interface ReportViewData {
  title: string | null;
  /** When the speech was recorded (ISO). */
  recordedAt: string;
  motion: { description: string } | null;
  /** Coaching fell back and couldn't use the motion. */
  motionNotApplied?: boolean;
  scores: Partial<Record<Category | "overall", number | null>>;
  feedback: FindingView[];
  delivery: {
    wordsPerMinute: number | null;
    speechDuration: number | null;
    fillers: number | null;
    pauses: number | null;
    stutters: number | null;
  };
  visual: VisualView;
}

/**
 * One report, as the owner's page (/practice/[id]) and the public
 * shared page (/shared/[token]) both show it. The owner page adds its
 * own parts through the two slots: `belowTitle` (the share section)
 * and `afterFigures` (the speech timeline and audio player), which
 * the shared page leaves empty.
 */
export default function ReportView({
  data,
  belowTitle,
  afterFigures,
  onSeek,
}: {
  data: ReportViewData;
  belowTitle?: ReactNode;
  afterFigures?: ReactNode;
  onSeek?: (seconds: number) => void;
}): ReactElement {
  const [filter, setFilter] = useState<Category | "all">("all");

  const grouped = useMemo(() => {
    const items = filter === "all" ? data.feedback : data.feedback.filter((item) => item.category === filter);
    return [...items].sort((a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity));
  }, [data.feedback, filter]);

  const recorded = new Date(data.recordedAt).toLocaleDateString(undefined, {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  const present = useMemo(
    () => SCORE_ORDER.filter((category) => data.feedback.some((item) => item.category === category)),
    [data.feedback],
  );

  // The PDF is the print layout: show every finding first (not just
  // the current filter), then open the browser's print dialog.
  function exportPdf(): void {
    flushSync(() => setFilter("all"));
    window.print();
  }

  const { delivery } = data;
  const fallbackNote = motionFallbackNote(data.motion, data.motionNotApplied);

  return (
    <>
      <h1 style={{ fontSize: "var(--step-4)" }}>{data.title || `Session of ${recorded}`}</h1>

      <p className="note" style={{ margin: "0.5rem 0 1.25rem" }}>
        Recorded {recorded}
        {data.motion && (
          <>
            <br />
            Motion: {data.motion.description}
          </>
        )}
        {fallbackNote && (
          <>
            <br />
            {fallbackNote}
          </>
        )}
      </p>

      <div className="btn-row" data-print="hide" style={{ marginBottom: "2rem" }}>
        <button className="btn btn-quiet btn-sm" type="button" onClick={exportPdf}>
          Export as PDF
        </button>
      </div>

      {belowTitle}

      <div className="figures" style={{ marginBottom: "2rem" }}>
        <div className="figure">
          <b>{Math.round(data.scores.overall ?? 0)}</b>
          <span>Overall, out of 100</span>
        </div>
        <div className="figure">
          <b>{Math.round(delivery.wordsPerMinute ?? 0)}</b>
          <span>Words per minute</span>
        </div>
        <div className="figure">
          <b>{formatClock(delivery.speechDuration ?? 0)}</b>
          <span>Time actually speaking</span>
        </div>
        <div className="figure">
          <b>{delivery.fillers ?? 0}</b>
          <span>Filler words</span>
        </div>
        <div className="figure">
          <b>{delivery.pauses ?? 0}</b>
          <span>Pauses</span>
        </div>
        <div className="figure">
          <b>{delivery.stutters ?? 0}</b>
          <span>Stutters</span>
        </div>
      </div>

      {afterFigures}

      <VisualDeliverySection report={data.visual} />
      <KeyMomentsList report={data.visual} onSeek={onSeek} />

      <h2 style={{ fontSize: "var(--step-2)", marginBottom: "1rem" }}>Scores by category</h2>

      <div className="bars" style={{ marginBottom: "2.5rem" }}>
        {SCORE_ORDER.map((category) => {
          const raw = data.scores[category];
          // null: not scored (rebuttal for a speech with nothing to
          // rebut), left out of the overall. Absent: an older report.
          const notScored = raw === null;
          const value = raw ?? 0;

          return (
            <div className="bar-row" key={category}>
              <span className="bar-label">{CATEGORY_LABEL[category]}</span>
              {notScored ? (
                // Spans the track and value columns: the value column
                // is sized for a number, not a phrase.
                <span className="note" style={{ gridColumn: "2 / 4", margin: 0 }}>
                  Not scored: nothing to rebut
                </span>
              ) : (
                <>
                  <div className="bar-track">
                    <div className="bar-fill" style={{ width: `${Math.min(100, value)}%` }} />
                  </div>
                  <span className="bar-value">{Math.round(value)}</span>
                </>
              )}
            </div>
          );
        })}
      </div>

      <p className="note" style={{ maxWidth: "58ch" }}>
        Delivery is arithmetic over the audio. The other five come from a language model reading the
        transcript, so treat them as a second opinion rather than a mark. Rebuttal isn&apos;t scored when
        there was nothing to rebut, and doesn&apos;t count toward the overall.
      </p>

      <h2 style={{ fontSize: "var(--step-2)", margin: "2.5rem 0 1rem" }}>Findings</h2>

      <div className="filters" data-print="hide">
        <button className="filter" type="button" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>
          All {data.feedback.length}
        </button>

        {present.map((category) => (
          <button
            key={category}
            className="filter"
            type="button"
            aria-pressed={filter === category}
            onClick={() => setFilter(category)}
          >
            {CATEGORY_LABEL[category]}
          </button>
        ))}
      </div>

      <ul className="findings">
        {grouped.map((item, index) => (
          <Finding key={`${item.category}-${index}`} item={item} />
        ))}
      </ul>
    </>
  );
}

function Finding({ item }: { item: FindingView }): ReactElement {
  return (
    <li className="finding" data-severity={item.severity}>
      <div>
        <h3>{item.title}</h3>

        <p className="finding-meta">
          {CATEGORY_LABEL[item.category] ?? item.category}. {SEVERITY_LABEL[item.severity] ?? item.severity}.
        </p>

        <p>{item.issue}</p>

        {item.evidence.map((quote, index) => (
          <blockquote key={index}>{quote}</blockquote>
        ))}

        {item.explanation && <p>{item.explanation}</p>}

        {item.recommendation && <p className="rec">{item.recommendation}</p>}
      </div>
    </li>
  );
}
