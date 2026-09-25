"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";

import DeleteAccountModal from "@/components/DeleteAccountModal";
import Recorder from "@/components/Recorder";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import { formatClock } from "@/components/SpeechTrack";
import ProgressChart from "./ProgressChart";
import {
  ApiError,
  clearTokens,
  deleteSession,
  getAccessToken,
  listSessions,
  redirectToLoginAfterSessionExpiry,
} from "@/lib/api";
import {
  STATUS_LABEL,
  TERMINAL,
  type SessionSummary,
} from "@/lib/types";

const POLL_MS = 4000;

export default function PracticePage(): ReactElement {
  const router = useRouter();

  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // A poll can still be in flight when the user navigates away, and
  // fetch here is not abortable. Without this, a 401 landing after
  // the move redirects them off whatever page they just opened,
  // which reads as "clicking About signed me out".
  const leftPageRef = useRef(false);

  const load = useCallback(async (): Promise<boolean> => {
    try {
      const rows = await listSessions();
      setSessions(rows);
      setError(null);

      // Keep polling only while something is still moving.
      return rows.some((row) => !TERMINAL.includes(row.status));
    } catch (caught) {
      if (leftPageRef.current) return false;

      if (caught instanceof ApiError && caught.status === 401) {
        redirectToLoginAfterSessionExpiry(router);
        return false;
      }

      setError("Could not load your sessions. Retrying.");
      return true;
    }
  }, [router]);

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

  const handleDeleted = useCallback((id: string): void => {
    setSessions((current) =>
      current === null ? null : current.filter((row) => row.id !== id),
    );
  }, []);

  // Changes when a session finishes, so the chart refetches.
  const completedCount =
    sessions?.filter((row) => row.status === "completed").length ?? 0;

  function signOut(): void {
    clearTokens();
    router.replace("/");
  }

  return (
    <div className="shell">
      <SiteHeader variant="app" />

      <main>
        <section className="block-tight" style={{ paddingTop: "2.5rem" }}>
          <div className="wrap">
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                gap: "1rem",
                flexWrap: "wrap",
                marginBottom: "1.5rem",
              }}
            >
              <h1 style={{ fontSize: "var(--step-4)" }}>Practice</h1>
              <div className="btn-row">
                <button
                  className="btn btn-quiet btn-sm"
                  type="button"
                  data-tone="danger"
                  onClick={() => setDeleteModalOpen(true)}
                >
                  Delete account
                </button>
                <button className="filter" type="button" onClick={signOut}>
                  Sign out
                </button>
              </div>
            </div>

            <DeleteAccountModal
              open={deleteModalOpen}
              onClose={() => setDeleteModalOpen(false)}
            />

            <div style={{ maxWidth: "34rem" }}>
              <Recorder />
            </div>
          </div>
        </section>

        <section className="block-tight">
          <div className="wrap">
            <h2 style={{ fontSize: "var(--step-2)", marginBottom: "1rem" }}>
              Your progress
            </h2>
            <ProgressChart refreshKey={completedCount} />
          </div>
        </section>

        <section className="block-tight" style={{ paddingBottom: "4rem" }}>
          <div className="wrap">
            <h2 style={{ fontSize: "var(--step-2)", marginBottom: "1rem" }}>
              Your sessions
            </h2>

            {error && (
              <p className="alert alert-quiet" role="status">
                {error}
              </p>
            )}

            {sessions === null && <p className="note">Loading.</p>}

            {sessions !== null && sessions.length === 0 && (
              <p className="note" style={{ maxWidth: "48ch" }}>
                Nothing here yet. Record a speech above and it will appear
                in this list while it is being analysed.
              </p>
            )}

            {sessions !== null && sessions.length > 0 && (
              <ul className="rows">
                {sessions.map((session) => (
                  <SessionRow
                    key={session.id}
                    session={session}
                    onDeleted={handleDeleted}
                  />
                ))}
              </ul>
            )}
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}

function SessionRow({
  session,
  onDeleted,
}: {
  session: SessionSummary;
  onDeleted: (id: string) => void;
}): ReactElement {
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const done = session.status === "completed";
  const failed = session.status === "failed";

  const recorded = new Date(session.created_at).toLocaleDateString(
    undefined,
    { day: "numeric", month: "short", year: "numeric" },
  );

  const name = session.title || `Session of ${recorded}`;

  const body = (
    <>
      <div>
        <div className="row-title">{name}</div>

        <div className="row-meta">
          {done ? (
            <>
              {recorded}. {formatClock(session.duration_seconds ?? 0)} of
              speech at {Math.round(session.words_per_minute ?? 0)} words
              per minute.{" "}
              {session.feedback_count ?? 0} findings.
            </>
          ) : failed ? (
            <>{session.error_message ?? "Analysis failed."}</>
          ) : (
            <>
              {STATUS_LABEL[session.status]}
              {session.queue_wait_seconds
                ? `. Waiting about ${Math.round(
                    session.queue_wait_seconds,
                  )} seconds for capacity.`
                : "."}
            </>
          )}
        </div>

        {!done && !failed && (
          <div className="progress" aria-hidden="true">
            <div
              className="progress-fill"
              style={{ width: `${Math.round(session.progress * 100)}%` }}
            />
          </div>
        )}
      </div>

      <div>
        {done ? (
          <span className="row-score">
            {Math.round(session.overall_score ?? 0)}
          </span>
        ) : (
          <span
            className="state"
            data-tone={failed ? "failed" : undefined}
          >
            {failed ? "Failed" : STATUS_LABEL[session.status]}
          </span>
        )}
      </div>
    </>
  );

  async function handleDelete(): Promise<void> {
    if (
      !window.confirm("Delete this session? This cannot be undone.")
    ) {
      return;
    }

    setDeleting(true);
    setDeleteError(null);

    try {
      await deleteSession(session.id);
      // Parent drops the row, unmounting this component, so
      // nothing is set on state after this point.
      onDeleted(session.id);
    } catch (caught) {
      setDeleteError(
        caught instanceof ApiError && caught.status === 404
          ? "That session was already gone."
          : "Could not delete that session. Try again.",
      );
      setDeleting(false);
    }
  }

  return (
    <li className="row">
      {done ? (
        <Link href={`/practice/${session.id}`}>{body}</Link>
      ) : (
        <div>{body}</div>
      )}

      {/* Sibling of the link, never inside it: a button nested in
          an anchor is invalid and the click would also navigate. */}
      <button
        type="button"
        className="btn btn-quiet btn-sm"
        data-tone="danger"
        onClick={handleDelete}
        disabled={deleting}
        aria-label={`Delete ${name}`}
      >
        {deleting ? "Deleting." : "Delete"}
      </button>

      {deleteError && (
        <p
          className="alert alert-quiet"
          role="status"
          style={{ flexBasis: "100%", marginBottom: "1rem" }}
        >
          {deleteError}
        </p>
      )}
    </li>
  );
}
