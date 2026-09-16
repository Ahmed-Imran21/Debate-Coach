"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactElement } from "react";

import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import SpeechTrack, {
  formatClock,
  type Mark,
} from "@/components/SpeechTrack";
import {
  ApiError,
  clearTokens,
  getAccessToken,
  getReport,
  getSession,
} from "@/lib/api";
import {
  CATEGORY_LABEL,
  STATUS_LABEL,
  type Category,
  type FeedbackItem,
  type SessionReport,
  type SessionSummary,
  type Severity,
} from "@/lib/types";

const POLL_MS = 4000;

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

export default function SessionPage(): ReactElement {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;

  const [summary, setSummary] = useState<SessionSummary | null>(null);
  const [report, setReport] = useState<SessionReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // A poll can still be in flight when the user navigates away, and
  // fetch here is not abortable. Without this, a 401 landing after
  // the move redirects them off whatever page they just opened,
  // which reads as "clicking About signed me out".
  const leftPageRef = useRef(false);

  const load = useCallback(async (): Promise<boolean> => {
    try {
      const current = await getSession(id);
      setSummary(current);

      if (current.status === "completed") {
        setReport(await getReport(id));
        return false;
      }

      return current.status !== "failed";
    } catch (caught) {
      if (leftPageRef.current) return false;

      if (caught instanceof ApiError) {
        if (caught.status === 401) {
          clearTokens();
          router.replace("/login");
          return false;
        }

        if (caught.status === 404) {
          setError("That session does not exist.");
          return false;
        }
      }

      setError("Could not load this session. Retrying.");
      return true;
    }
  }, [id, router]);

  useEffect(() => {
    leftPageRef.current = false;

    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }

    let cancelled = false;

    const run = async () => {
      const keepGoing = await load();
      if (cancelled || !keepGoing) return;
      timerRef.current = setTimeout(run, POLL_MS);
    };

    void run();

    return () => {
      cancelled = true;
      leftPageRef.current = true;
      if (timerRef.current !== null) clearTimeout(timerRef.current);
    };
  }, [load, router]);

  return (
    <div className="shell">
      <SiteHeader variant="app" />

      <main>
        <section className="block-tight" style={{ paddingTop: "2.5rem" }}>
          <div className="wrap">
            <p className="note" style={{ marginBottom: "0.75rem" }}>
              <Link href="/practice">Back to sessions</Link>
            </p>

            {error && (
              <p className="alert" role="alert">
                {error}
              </p>
            )}

            {!error && summary === null && <p className="note">Loading.</p>}

            {summary && summary.status === "failed" && (
              <>
                <h1 style={{ fontSize: "var(--step-4)" }}>
                  Analysis failed
                </h1>
                <p className="alert" style={{ marginTop: "1rem" }}>
                  {summary.error_message ??
                    "Something went wrong while analysing this recording."}
                </p>
                <p className="note">
                  Record the speech again from the practice page. If it
                  keeps failing on the same recording, the audio may be
                  too quiet or too short to transcribe.
                </p>
              </>
            )}

            {summary &&
              summary.status !== "failed" &&
              summary.status !== "completed" && (
                <Working summary={summary} />
              )}

            {report && <Report report={report} />}
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}

/* ---------------------------------------------------------- */

function Working({
  summary,
}: {
  summary: SessionSummary;
}): ReactElement {
  return (
    <>
      <h1 style={{ fontSize: "var(--step-4)" }}>
        {summary.title || "Analysing your speech"}
      </h1>

      <p className="lede" style={{ margin: "0.75rem 0 1rem" }}>
        {STATUS_LABEL[summary.status]}.
        {summary.queue_wait_seconds
          ? ` Waiting about ${Math.round(
              summary.queue_wait_seconds,
            )} seconds for capacity.`
          : ""}
      </p>

      <div
        className="progress"
        role="progressbar"
        aria-valuenow={Math.round(summary.progress * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        style={{ maxWidth: "34rem" }}
      >
        <div
          className="progress-fill"
          style={{ width: `${Math.round(summary.progress * 100)}%` }}
        />
      </div>

      <p className="note">
        This page updates on its own. You can close the tab and come
        back to it later.
      </p>
    </>
  );
}

/* ---------------------------------------------------------- */

function Report({ report }: { report: SessionReport }): ReactElement {
  const [filter, setFilter] = useState<Category | "all">("all");

  const speech = report.raw_metrics.speech;
  const pauses = report.raw_metrics.pauses;
  const fillers = report.raw_metrics.fillers;
  const stutters = report.raw_metrics.stutters;

  const duration =
    report.analysis.total_duration ?? speech?.total_duration ?? 0;

  const marks: Mark[] = useMemo(() => {
    const collected: Mark[] = [];

    for (const pause of report.analysis.pauses ?? []) {
      if (pause.duration >= 1) {
        collected.push({
          at: pause.start,
          kind: "pause",
          span: pause.duration,
        });
      }
    }

    for (const filler of fillers?.instances ?? []) {
      if (typeof filler.start === "number") {
        collected.push({ at: filler.start, kind: "filler" });
      }
    }

    for (const stutter of stutters?.instances ?? []) {
      if (typeof stutter.start === "number") {
        collected.push({ at: stutter.start, kind: "stutter" });
      }
    }

    for (const segment of report.speech_content.segments ?? []) {
      if (segment.labels?.includes("logical_fallacy")) {
        collected.push({ at: segment.start, kind: "fallacy" });
      }
    }

    return collected;
  }, [report, fillers, stutters]);

  const grouped = useMemo(() => {
    const items =
      filter === "all"
        ? report.feedback
        : report.feedback.filter((item) => item.category === filter);

    return [...items].sort(
      (a, b) =>
        SEVERITY_ORDER.indexOf(a.severity) -
        SEVERITY_ORDER.indexOf(b.severity),
    );
  }, [report.feedback, filter]);

  const recorded = new Date(report.created_at).toLocaleDateString(
    undefined,
    { day: "numeric", month: "long", year: "numeric" },
  );

  const present = useMemo(
    () =>
      SCORE_ORDER.filter((category) =>
        report.feedback.some((item) => item.category === category),
      ),
    [report.feedback],
  );

  return (
    <>
      <h1 style={{ fontSize: "var(--step-4)" }}>
        {report.title || `Session of ${recorded}`}
      </h1>

      <p className="note" style={{ margin: "0.5rem 0 2rem" }}>
        Recorded {recorded}
      </p>

      <div className="figures" style={{ marginBottom: "2rem" }}>
        <div className="figure">
          <b>{Math.round(report.scores.overall ?? 0)}</b>
          <span>Overall, out of 100</span>
        </div>
        <div className="figure">
          <b>{Math.round(speech?.words_per_minute ?? 0)}</b>
          <span>Words per minute</span>
        </div>
        <div className="figure">
          <b>{formatClock(speech?.speech_duration ?? 0)}</b>
          <span>Time actually speaking</span>
        </div>
        <div className="figure">
          <b>{fillers?.count ?? 0}</b>
          <span>Filler words</span>
        </div>
        <div className="figure">
          <b>{pauses?.count ?? 0}</b>
          <span>Pauses</span>
        </div>
        <div className="figure">
          <b>{stutters?.count ?? 0}</b>
          <span>Stutters</span>
        </div>
      </div>

      {duration > 0 && (
        <div style={{ marginBottom: "2.5rem" }}>
          <SpeechTrack
            duration={duration}
            marks={marks}
            title="Where each finding landed"
          />
        </div>
      )}

      {report.audio_url && (
        <div style={{ marginBottom: "2.5rem" }}>
          <h2 style={{ fontSize: "var(--step-2)", marginBottom: "0.75rem" }}>
            Listen back
          </h2>
          <audio
            controls
            src={report.audio_url}
            style={{ width: "100%", maxWidth: "34rem" }}
          />
        </div>
      )}

      <h2 style={{ fontSize: "var(--step-2)", marginBottom: "1rem" }}>
        Scores by category
      </h2>

      <div className="bars" style={{ marginBottom: "2.5rem" }}>
        {SCORE_ORDER.map((category) => {
          const value = report.scores[category] ?? 0;

          return (
            <div className="bar-row" key={category}>
              <span className="bar-label">
                {CATEGORY_LABEL[category]}
              </span>
              <div className="bar-track">
                <div
                  className="bar-fill"
                  style={{ width: `${Math.min(100, value)}%` }}
                />
              </div>
              <span className="bar-value">{Math.round(value)}</span>
            </div>
          );
        })}
      </div>

      <p className="note" style={{ maxWidth: "58ch" }}>
        Delivery is arithmetic over the audio. The other five come from a
        language model reading your transcript, so treat them as a second
        opinion rather than a mark.
      </p>

      <h2 style={{ fontSize: "var(--step-2)", margin: "2.5rem 0 1rem" }}>
        Findings
      </h2>

      <div className="filters">
        <button
          className="filter"
          type="button"
          aria-pressed={filter === "all"}
          onClick={() => setFilter("all")}
        >
          All {report.feedback.length}
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

/* ---------------------------------------------------------- */

function Finding({ item }: { item: FeedbackItem }): ReactElement {
  return (
    <li className="finding" data-severity={item.severity}>
      <div>
        <h3>{item.title}</h3>

        <p className="finding-meta">
          {CATEGORY_LABEL[item.category] ?? item.category}.{" "}
          {SEVERITY_LABEL[item.severity] ?? item.severity}.
        </p>

        <p>{item.issue}</p>

        {item.evidence.map((quote, index) => (
          <blockquote key={index}>{quote}</blockquote>
        ))}

        {item.explanation && <p>{item.explanation}</p>}

        {item.recommendation && (
          <p className="rec">{item.recommendation}</p>
        )}
      </div>
    </li>
  );
}
