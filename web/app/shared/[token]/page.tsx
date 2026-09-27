"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import type { ReactElement } from "react";

import ReportView, { type ReportViewData } from "@/components/ReportView";
import { getSharedReport } from "@/lib/api";
import { SHARED_UNAVAILABLE } from "@/lib/share";
import type { SharedReport } from "@/lib/types";

/**
 * The public, read-only copy of one report behind a share link. No
 * account needed, and no way into the app from here beyond the
 * homepage link in the footer. Every failure shows the same message,
 * never why.
 */
export default function SharedReportPage(): ReactElement {
  const params = useParams<{ token: string }>();
  const token = params.token;
  const [report, setReport] = useState<SharedReport | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    let current = true;
    getSharedReport(token)
      .then((loaded) => {
        if (current) setReport(loaded);
      })
      .catch(() => {
        if (current) setUnavailable(true);
      });
    return () => {
      current = false;
    };
  }, [token]);

  return (
    <div className="shell">
      <main>
        <section className="block-tight" style={{ paddingTop: "2.5rem" }}>
          <div className="wrap">
            {unavailable && <p className="note">{SHARED_UNAVAILABLE}</p>}
            {!unavailable && report === null && <p className="note">Loading.</p>}
            {report && <ReportView data={toView(report)} />}
          </div>
        </section>
      </main>

      <footer className="block-tight" data-print="hide" style={{ paddingBottom: "3rem" }}>
        <div className="wrap">
          <p className="note">
            <Link href="/">Practice your own speeches on Debate Coach</Link>
          </p>
        </div>
      </footer>
    </div>
  );
}

function toView(report: SharedReport): ReportViewData {
  return {
    title: report.title,
    recordedAt: report.recorded_at,
    motion: report.motion,
    scores: report.scores,
    feedback: report.feedback,
    delivery: {
      wordsPerMinute: report.delivery.words_per_minute,
      speechDuration: report.delivery.speech_duration,
      fillers: report.delivery.filler_count,
      pauses: report.delivery.pause_count,
      stutters: report.delivery.stutter_count,
    },
    visual: report,
  };
}
