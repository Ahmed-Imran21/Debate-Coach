/**
 * The progress graph's logic, kept free of React and the DOM so it
 * can be unit-tested (vitest here runs pure TypeScript only). The
 * component in app/practice/ProgressChart.tsx only renders what
 * buildChart returns.
 */

import type { ProgressMetric, ProgressPoint, ProgressRange } from "./types";

export const METRIC_OPTIONS: { value: ProgressMetric; label: string }[] = [
  { value: "overall", label: "All" },
  { value: "argumentation", label: "Argumentation" },
  { value: "rebuttal", label: "Rebuttal" },
  { value: "structure", label: "Structure" },
  { value: "persuasion", label: "Persuasion" },
  { value: "logic", label: "Logic" },
];

/** One selector: a date window or a session count, never both. */
export const RANGE_OPTIONS: { value: ProgressRange; label: string }[] = [
  { value: "1d", label: "Last 1 day" },
  { value: "1w", label: "Last 1 week" },
  { value: "1m", label: "Last 1 month" },
  { value: "5", label: "Last 5 sessions" },
  { value: "10", label: "Last 10 sessions" },
  { value: "15", label: "Last 15 sessions" },
];

export const Y_TICKS = [0, 25, 50, 75, 100];

/** A line needs two real points; fewer shows a message instead. */
export const MIN_POINTS = 2;

export interface ChartBox {
  width: number;
  height: number;
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export const DEFAULT_BOX: ChartBox = {
  width: 640,
  height: 240,
  top: 12,
  right: 12,
  bottom: 28,
  left: 36,
};

export interface PlottedPoint {
  sessionId: string;
  createdAt: string;
  score: number;
  x: number;
  y: number;
}

export interface Chart {
  enough: boolean;
  points: PlottedPoint[];
  path: string;
  ticks: { value: number; y: number }[];
  box: ChartBox;
}

/** Sessions with no score for this metric are skipped, not drawn as 0. */
export function scoredPoints(points: ProgressPoint[]): (ProgressPoint & { score: number })[] {
  return points.filter(
    (p): p is ProgressPoint & { score: number } =>
      typeof p.score === "number" && Number.isFinite(p.score),
  );
}

function clampScore(score: number): number {
  return Math.min(100, Math.max(0, score));
}

/**
 * Points are spaced evenly in session order (oldest left), and the
 * y axis is always 0-100 so a small wobble isn't stretched into a
 * dramatic swing.
 */
export function buildChart(points: ProgressPoint[], box: ChartBox = DEFAULT_BOX): Chart {
  const scored = scoredPoints(points);
  const innerW = box.width - box.left - box.right;
  const innerH = box.height - box.top - box.bottom;
  const yFor = (score: number) => box.top + (1 - clampScore(score) / 100) * innerH;

  const ticks = Y_TICKS.map((value) => ({ value, y: yFor(value) }));

  if (scored.length < MIN_POINTS) {
    return { enough: false, points: [], path: "", ticks, box };
  }

  const step = innerW / (scored.length - 1);
  const plotted = scored.map((p, i) => ({
    sessionId: p.session_id,
    createdAt: p.created_at,
    score: p.score,
    x: box.left + i * step,
    y: yFor(p.score),
  }));

  const path = plotted
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
    .join(" ");

  return { enough: true, points: plotted, path, ticks, box };
}

export function formatDate(iso: string, timeZone?: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone,
  });
}

/** The chart's text alternative, for screen readers. */
export function describeChart(chart: Chart, metricLabel: string, timeZone?: string): string {
  if (!chart.enough) return "";
  const first = chart.points[0];
  const last = chart.points[chart.points.length - 1];
  const what = metricLabel === "All" ? "Overall" : metricLabel;
  return (
    `${what} score over ${chart.points.length} sessions, ` +
    `from ${Math.round(first.score)} on ${formatDate(first.createdAt, timeZone)} ` +
    `to ${Math.round(last.score)} on ${formatDate(last.createdAt, timeZone)}.`
  );
}
