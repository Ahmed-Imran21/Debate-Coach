"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { ReactElement } from "react";

import { ApiError, getProgress, redirectToLoginAfterSessionExpiry } from "@/lib/api";
import {
  METRIC_OPTIONS,
  RANGE_OPTIONS,
  buildChart,
  describeChart,
  formatDate,
} from "@/lib/progress-chart";
import type { ProgressMetric, ProgressPoint, ProgressRange } from "@/lib/types";

/**
 * The user's score trend. `refreshKey` changes when a session
 * finishes (the dashboard passes its completed count), so a new
 * speech appears here without a reload.
 */
export default function ProgressChart({ refreshKey }: { refreshKey: number }): ReactElement {
  const router = useRouter();
  const [metric, setMetric] = useState<ProgressMetric>("overall");
  const [range, setRange] = useState<ProgressRange>("10");
  const [points, setPoints] = useState<ProgressPoint[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // A slower response for an earlier selection must never
    // overwrite the current one.
    let current = true;
    setPoints(null);
    setError(null);

    getProgress(metric, range)
      .then((rows) => {
        if (current) setPoints(rows);
      })
      .catch((caught: unknown) => {
        if (!current) return;
        if (caught instanceof ApiError && caught.status === 401) {
          redirectToLoginAfterSessionExpiry(router);
          return;
        }
        setError("Could not load your progress.");
      });

    return () => {
      current = false;
    };
  }, [metric, range, refreshKey, router]);

  const metricLabel = METRIC_OPTIONS.find((o) => o.value === metric)?.label ?? "All";
  const chart = points === null ? null : buildChart(points);

  return (
    <div>
      <div className="filters" role="group" aria-label="Score type">
        {METRIC_OPTIONS.map((option) => (
          <button
            key={option.value}
            className="filter"
            type="button"
            aria-pressed={metric === option.value}
            onClick={() => setMetric(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div className="filters" role="group" aria-label="Range">
        {RANGE_OPTIONS.map((option) => (
          <button
            key={option.value}
            className="filter"
            type="button"
            aria-pressed={range === option.value}
            onClick={() => setRange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div style={{ marginTop: "1rem" }}>
        {error && (
          <p className="alert alert-quiet" role="status">
            {error}
          </p>
        )}

        {!error && chart === null && <p className="note">Loading.</p>}

        {!error && chart !== null && !chart.enough && (
          <p className="note">Not enough sessions in this range yet.</p>
        )}

        {!error && chart !== null && chart.enough && (
          <svg
            viewBox={`0 0 ${chart.box.width} ${chart.box.height}`}
            width="100%"
            role="img"
            aria-label={describeChart(chart, metricLabel)}
            style={{ display: "block", maxWidth: "40rem", height: "auto", overflow: "visible" }}
          >
            {chart.ticks.map((tick) => (
              <g key={tick.value}>
                <line
                  x1={chart.box.left}
                  x2={chart.box.width - chart.box.right}
                  y1={tick.y}
                  y2={tick.y}
                  stroke="var(--rule)"
                  strokeWidth={1}
                />
                <text
                  x={chart.box.left - 8}
                  y={tick.y}
                  textAnchor="end"
                  dominantBaseline="middle"
                  fontSize={12}
                  fill="var(--ink-faint)"
                >
                  {tick.value}
                </text>
              </g>
            ))}

            <path d={chart.path} fill="none" stroke="var(--pine)" strokeWidth={2} strokeLinejoin="round" />

            {chart.points.map((p) => (
              <circle key={p.sessionId} cx={p.x} cy={p.y} r={3.5} fill="var(--pine)">
                <title>{`${formatDate(p.createdAt)}: ${Math.round(p.score)}`}</title>
              </circle>
            ))}

            <text
              x={chart.points[0].x}
              y={chart.box.height - 6}
              textAnchor="start"
              fontSize={12}
              fill="var(--ink-soft)"
            >
              {formatDate(chart.points[0].createdAt)}
            </text>
            <text
              x={chart.points[chart.points.length - 1].x}
              y={chart.box.height - 6}
              textAnchor="end"
              fontSize={12}
              fill="var(--ink-soft)"
            >
              {formatDate(chart.points[chart.points.length - 1].createdAt)}
            </text>
          </svg>
        )}
      </div>
    </div>
  );
}
