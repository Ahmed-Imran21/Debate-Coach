"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactElement } from "react";

import ReportView, { type ReportViewData } from "@/components/ReportView";
import ShareSection from "@/components/ShareSection";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import SpeechTrack, { type Mark } from "@/components/SpeechTrack";
import {
  ApiError,
  getAccessToken,
  getReport,
  getSession,
  redirectToLoginAfterSessionExpiry,
} from "@/lib/api";
import {
  STATUS_LABEL,
  type SessionReport,
  type SessionSummary,
} from "@/lib/types";

const POLL_MS = 4000;

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
          redirectToLoginAfterSessionExpiry(router);
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
            <p className="note" data-print="hide" style={{ marginBottom: "0.75rem" }}>
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
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const seekAudio = useCallback((seconds: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = seconds;
    void audio.play();
  }, []);

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

  const data: ReportViewData = {
    title: report.title,
    recordedAt: report.created_at,
    motion: report.motion ?? null,
    motionNotApplied: report.motion_not_applied,
    scores: report.scores,
    feedback: report.feedback,
    delivery: {
      wordsPerMinute: speech?.words_per_minute ?? null,
      speechDuration: speech?.speech_duration ?? null,
      fillers: fillers?.count ?? null,
      pauses: pauses?.count ?? null,
      stutters: stutters?.count ?? null,
    },
    visual: report,
  };

  // The timeline and audio player are the owner's only: they're built
  // from the transcript and the recording, neither of which a shared
  // link exposes. Both are left out of the printed report.
  const ownerExtras = (
    <>
      {duration > 0 && (
        <div data-print="hide" style={{ marginBottom: "2.5rem" }}>
          <SpeechTrack
            duration={duration}
            marks={marks}
            title="Where each finding landed"
          />
        </div>
      )}

      {report.audio_url && (
        <div data-print="hide" style={{ marginBottom: "2.5rem" }}>
          <h2 style={{ fontSize: "var(--step-2)", marginBottom: "0.75rem" }}>
            Listen back
          </h2>
          <audio
            ref={audioRef}
            controls
            src={report.audio_url}
            style={{ width: "100%", maxWidth: "34rem" }}
          />
        </div>
      )}
    </>
  );

  return (
    <ReportView
      data={data}
      belowTitle={<ShareSection sessionId={report.id} />}
      afterFigures={ownerExtras}
      onSeek={report.audio_url ? seekAudio : undefined}
    />
  );
}
