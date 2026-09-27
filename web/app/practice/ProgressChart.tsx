"use client";

import { useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ReactElement } from "react";

import { ApiError, getProgress, redirectToLoginAfterSessionExpiry } from "@/lib/api";
import {
  METRIC_OPTIONS,
  RANGE_OPTIONS,
  buildChart,
  describeChart,
  formatDate,
  placeTooltip,
  tooltipLines,
  type PlottedPoint,
} from "@/lib/progress-chart";
import type { ProgressMetric, ProgressPoint, ProgressRange } from "@/lib/types";

const DOT_RADIUS = 3.5;
const ACTIVE_DOT_RADIUS = 5.5;
// Invisible target around each dot, in chart units, so it's easy to
// hover or tap.
const HIT_RADIUS = 13;

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
  // Index into chart.points of the dot whose tooltip is showing.
  const [active, setActive] = useState<number | null>(null);

  useEffect(() => {
    // A slower response for an earlier selection must never
    // overwrite the current one.
    let current = true;
    setPoints(null);
    setError(null);
    setActive(null); // switching score type or range hides any tooltip

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

  // Tapping anywhere that isn't a dot hides the tooltip (phones).
  useEffect(() => {
    if (active === null) return;
    function onPointerDown(event: PointerEvent): void {
      const target = event.target as Element | null;
      if (!target?.closest?.("[data-progress-point]")) setActive(null);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [active]);

  const metricLabel = METRIC_OPTIONS.find((o) => o.value === metric)?.label ?? "All";
  const chart = points === null ? null : buildChart(points);
  const activePoint = chart?.enough && active !== null ? chart.points[active] ?? null : null;

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
          <div style={{ position: "relative", maxWidth: "40rem" }}>
            <svg
              viewBox={`0 0 ${chart.box.width} ${chart.box.height}`}
              width="100%"
              // "group", not "img": an img is one opaque picture to a
              // screen reader, which would hide the focusable dots.
              role="group"
              aria-label={describeChart(chart, metricLabel)}
              style={{ display: "block", height: "auto", overflow: "visible" }}
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

              {chart.points.map((p, index) => {
                const lines = tooltipLines(p, metricLabel);
                const isActive = index === active;
                return (
                  <g
                    key={p.sessionId}
                    data-progress-point=""
                    tabIndex={0}
                    role="img"
                    aria-label={lines.join(", ")}
                    style={{ cursor: "pointer", outline: "none" }}
                    onMouseEnter={() => setActive(index)}
                    onMouseLeave={() => setActive((current) => (current === index ? null : current))}
                    onFocus={() => setActive(index)}
                    onBlur={() => setActive((current) => (current === index ? null : current))}
                    onClick={() => setActive(index)}
                  >
                    <circle cx={p.x} cy={p.y} r={HIT_RADIUS} fill="transparent" />
                    <circle
                      cx={p.x}
                      cy={p.y}
                      r={isActive ? ACTIVE_DOT_RADIUS : DOT_RADIUS}
                      fill="var(--pine)"
                      stroke={isActive ? "var(--paper-raised)" : "none"}
                      strokeWidth={isActive ? 2 : 0}
                    />
                  </g>
                );
              })}

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

            {activePoint && (
              <PointTooltip
                key={activePoint.sessionId}
                point={activePoint}
                lines={tooltipLines(activePoint, metricLabel)}
                chartWidth={chart.box.width}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Positioned over the chart, next to its dot. Measured after it
 * renders so placeTooltip can keep it inside the chart: it opens to
 * the left near the right edge and below near the top.
 */
function PointTooltip({
  point,
  lines,
  chartWidth,
}: {
  point: PlottedPoint;
  lines: [string, string, string];
  chartWidth: number;
}): ReactElement {
  const ref = useRef<HTMLDivElement | null>(null);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);

  useLayoutEffect(() => {
    const tooltip = ref.current;
    const container = tooltip?.parentElement;
    if (!tooltip || !container) return;
    // The SVG scales with the container: chart units to pixels.
    const scale = container.clientWidth / chartWidth;
    const placed = placeTooltip(
      point.x * scale,
      point.y * scale,
      tooltip.offsetWidth,
      tooltip.offsetHeight,
      container.clientWidth,
    );
    setPosition({ left: placed.left, top: placed.top });
  }, [point, chartWidth]);

  return (
    <div
      ref={ref}
      role="tooltip"
      style={{
        position: "absolute",
        left: position?.left ?? 0,
        top: position?.top ?? 0,
        opacity: position ? 1 : 0,
        transition: "opacity 120ms ease-out",
        pointerEvents: "none",
        maxWidth: "16rem",
        padding: "0.375rem 0.625rem",
        background: "var(--paper-raised)",
        border: "1px solid var(--rule-strong)",
        borderRadius: "var(--radius)",
        fontSize: "0.8125rem",
        lineHeight: 1.45,
        color: "var(--ink)",
        zIndex: 1,
      }}
    >
      <div style={{ fontWeight: 500 }}>{lines[0]}</div>
      <div style={{ color: "var(--ink-soft)" }}>{lines[1]}</div>
      <div>{lines[2]}</div>
    </div>
  );
}
