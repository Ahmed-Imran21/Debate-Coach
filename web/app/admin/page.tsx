"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { ReactElement } from "react";

import { ApiError, clearTokens, getAccessToken, getAdminStats } from "@/lib/api";
import SiteHeader from "@/components/SiteHeader";
import type { AdminStats } from "@/lib/types";

const POLL_MS = 30_000;

/**
 * Client-rendered, but reaching this component at all already
 * means web/middleware.ts's server-side check passed — that's
 * the real gate (see its own docstring); this page's own
 * getAccessToken()/401 handling below is the same pattern every
 * other authenticated page in this app already uses, not a
 * second security boundary.
 */
export default function AdminPage(): ReactElement {
  const router = useRouter();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const leftPageRef = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async (): Promise<void> => {
    try {
      const data = await getAdminStats();
      if (leftPageRef.current) return;
      setStats(data);
      setError(null);
    } catch (caught) {
      if (leftPageRef.current) return;

      if (caught instanceof ApiError && caught.status === 401) {
        clearTokens();
        router.replace("/login");
        return;
      }

      if (caught instanceof ApiError && caught.status === 403) {
        // Cookie-gated by middleware already, but ADMIN_EMAILS
        // could have changed between that check and this call.
        router.replace("/");
        return;
      }

      setError("Could not load admin stats. Retrying.");
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
      await load();
      if (cancelled) return;
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
            <h1 style={{ fontSize: "var(--step-4)", marginBottom: "1.5rem" }}>
              Admin
            </h1>

            {error && (
              <p className="alert alert-quiet" role="status">
                {error}
              </p>
            )}

            {stats === null && !error && <p className="note">Loading.</p>}

            {stats && (
              <>
                <div className="figures" style={{ marginBottom: "2.5rem" }}>
                  <div className="figure">
                    <b>{stats.active_users}</b>
                    <span>Active now (last 5 min)</span>
                  </div>
                  <div className="figure">
                    <b>{stats.total_signups.toLocaleString()}</b>
                    <span>Total signups</span>
                  </div>
                  <div className="figure">
                    <b>{stats.storage.used_gb.toFixed(2)} GB</b>
                    <span>
                      Storage used, of {stats.storage.quota_gb.toFixed(0)} GB soft quota
                    </span>
                  </div>
                </div>

                <h2 style={{ fontSize: "var(--step-2)", marginBottom: "1rem" }}>
                  API key usage
                </h2>

                <div style={{ marginBottom: "2.5rem" }}>
                  {stats.keys.map((key) => (
                    <div
                      key={key.key_id}
                      style={{ marginBottom: "1.5rem" }}
                    >
                      <h3
                        style={{
                          fontSize: "0.9375rem",
                          fontWeight: 600,
                          marginBottom: "0.5rem",
                        }}
                      >
                        {key.label}
                      </h3>
                      <div className="bars">
                        <UsageBarRow
                          label="Requests"
                          used={key.requests_used}
                          limit={key.requests_limit}
                        />
                        <UsageBarRow
                          label="Tokens"
                          used={key.tokens_used}
                          limit={key.tokens_limit}
                        />
                      </div>
                    </div>
                  ))}

                  {stats.keys.length === 0 && (
                    <p className="note">No API keys are currently configured.</p>
                  )}
                </div>
              </>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

function UsageBarRow({
  label,
  used,
  limit,
}: {
  label: string;
  used: number;
  limit: number;
}): ReactElement {
  const percent = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;

  return (
    <div
      className="bar-row"
      style={{ gridTemplateColumns: "6rem 1fr 10rem" }}
    >
      <span className="bar-label">{label}</span>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${percent}%` }} />
      </div>
      <span className="bar-value" style={{ whiteSpace: "nowrap" }}>
        {used.toLocaleString()} / {limit.toLocaleString()}
      </span>
    </div>
  );
}
