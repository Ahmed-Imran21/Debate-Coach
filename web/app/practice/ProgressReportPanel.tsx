"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";

import {
  ApiError,
  createProgressReport,
  getLatestProgressReport,
  redirectToLoginAfterSessionExpiry,
} from "@/lib/api";
import {
  SESSION_COUNT_OPTIONS,
  formatNextAvailable,
  reportCaption,
} from "@/lib/progress-report";
import type { LatestProgressReport, ReportSessionCount } from "@/lib/types";

/**
 * AI progress report: compares the last 3, 5 or 7 completed
 * sessions. One per day (reset at midnight UTC), enforced by the
 * backend; this only reflects what /latest says.
 */
export default function ProgressReportPanel({
  completedCount,
}: {
  completedCount: number;
}): ReactElement {
  const router = useRouter();
  const [latest, setLatest] = useState<LatestProgressReport | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [count, setCount] = useState<ReportSessionCount>(5);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  const handleAuth = useCallback(
    (caught: unknown): boolean => {
      if (caught instanceof ApiError && caught.status === 401) {
        redirectToLoginAfterSessionExpiry(router);
        return true;
      }
      return false;
    },
    [router],
  );

  const load = useCallback(async (): Promise<void> => {
    try {
      setLatest(await getLatestProgressReport());
      setLoadError(null);
    } catch (caught) {
      if (!handleAuth(caught)) setLoadError("Could not load your progress report.");
    }
  }, [handleAuth]);

  useEffect(() => {
    void load();
  }, [load]);

  async function generate(): Promise<void> {
    setGenerating(true);
    setGenerateError(null);
    try {
      await createProgressReport(count);
    } catch (caught) {
      if (handleAuth(caught)) return;
      // Already used today (another tab, say): the reload below shows
      // today's report and the next time in local time, which says it
      // better than the backend's UTC message.
      if (!(caught instanceof ApiError && caught.status === 429)) {
        setGenerateError(
          caught instanceof ApiError ? caught.message : "Could not generate the report. Try again shortly.",
        );
      }
    } finally {
      setGenerating(false);
    }
    // Success or a 429 (already used today): either way /latest now
    // has the report and when the next one is allowed.
    await load();
  }

  if (loadError) {
    return (
      <p className="alert alert-quiet" role="status">
        {loadError}
      </p>
    );
  }

  if (latest === null) return <p className="note">Loading.</p>;

  const enoughSessions = completedCount >= 2;

  return (
    <div>
      {latest.can_generate ? (
        <>
          <p className="note" style={{ maxWidth: "52ch" }}>
            Compare your recent sessions and see what is improving and what still needs work.
            One report per day.
          </p>

          <div className="filters" role="group" aria-label="Sessions to compare">
            {SESSION_COUNT_OPTIONS.map((n) => (
              <button
                key={n}
                className="filter"
                type="button"
                aria-pressed={count === n}
                onClick={() => setCount(n)}
                disabled={generating}
              >
                Last {n} sessions
              </button>
            ))}
          </div>

          <div className="btn-row" style={{ marginTop: "0.75rem" }}>
            <button
              className="btn"
              type="button"
              onClick={() => void generate()}
              disabled={generating || !enoughSessions}
            >
              {generating ? "Writing your report." : "Generate progress report"}
            </button>
          </div>

          {!enoughSessions && (
            <p className="note">A report compares sessions, so it needs at least 2 completed ones.</p>
          )}
        </>
      ) : (
        latest.next_available_at && (
          <p className="note" style={{ maxWidth: "52ch" }}>
            You have used today&apos;s progress report. The next one is available from{" "}
            {formatNextAvailable(latest.next_available_at)}.
          </p>
        )
      )}

      {generateError && (
        <p className="alert alert-quiet" role="status" style={{ marginTop: "0.75rem" }}>
          {generateError}
        </p>
      )}

      {latest.report && (
        <div style={{ marginTop: "1rem" }}>
          <p className="note" style={{ margin: 0 }}>
            {reportCaption(latest.report.session_count_used, latest.report.report_date)}
          </p>
          <div className="prose">
            <ul>
              {latest.report.bullets.map((bullet) => (
                <li key={bullet}>{bullet}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
