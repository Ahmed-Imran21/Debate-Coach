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
  title: string | null;
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
    title: p.title ?? null,
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

/* ---------------------------------------------------------- */
/* Tooltip                                                     */
/* ---------------------------------------------------------- */

/**
 * "26 Sept 2026" in the viewer's locale: the same format the session
 * list uses, so a point's name matches its row there.
 */
export function formatRecordedDate(iso: string, locale?: string, timeZone?: string): string {
  return new Date(iso).toLocaleDateString(locale, { day: "numeric", month: "short", year: "numeric", timeZone });
}

/** The tooltip's three lines: name, date, and the score being shown. */
export function tooltipLines(
  point: Pick<PlottedPoint, "title" | "createdAt" | "score">,
  metricLabel: string,
  locale?: string,
  timeZone?: string,
): [string, string, string] {
  const date = formatRecordedDate(point.createdAt, locale, timeZone);
  const name = point.title || `Session of ${date}`; // the session list's fallback
  const what = metricLabel === "All" ? "Overall" : metricLabel;
  return [name, date, `${what}: ${Math.round(point.score)}`];
}

export interface TooltipPlacement {
  left: number;
  top: number;
  openLeft: boolean;
  openBelow: boolean;
}

/**
 * Where to put a tooltip of the given size next to a point at (x, y),
 * all in pixels within a container `containerWidth` wide. It opens up
 * and to the right by default, to the left near the right edge, below
 * near the top, and is clamped so it never leaves the container.
 */
export function placeTooltip(
  x: number,
  y: number,
  width: number,
  height: number,
  containerWidth: number,
  gap = 10,
): TooltipPlacement {
  const openLeft = x + gap + width > containerWidth;
  const openBelow = y - gap - height < 0;
  const left = openLeft ? x - gap - width : x + gap;
  const top = openBelow ? y + gap : y - gap - height;
  return {
    left: Math.max(0, Math.min(left, containerWidth - width)),
    top: Math.max(0, top),
    openLeft,
    openBelow,
  };
}
