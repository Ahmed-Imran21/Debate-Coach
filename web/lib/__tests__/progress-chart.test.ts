/**
 * The progress graph (lib/progress-chart.ts) and its API call:
 * null scores skipped, fewer than two real points shows a message,
 * a fixed 0-100 axis, and the query the backend validates.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { getProgress } from "../api";
import {
  DEFAULT_BOX as BOX,
  METRIC_OPTIONS,
  RANGE_OPTIONS,
  buildChart,
  describeChart,
  formatDate,
  scoredPoints,
} from "../progress-chart";
import type { ProgressPoint } from "../types";

afterEach(() => {
  vi.unstubAllGlobals();
});

const pt = (n: number, score: number | null): ProgressPoint => ({
  session_id: `s${n}`,
  created_at: `2026-09-${String(n).padStart(2, "0")}T12:00:00Z`,
  score,
});

describe("buildChart", () => {
  it.each([
    ["no sessions", []],
    ["one session", [pt(1, 60)]],
    ["one real point among nulls", [pt(1, null), pt(2, 60), pt(3, null)]],
    ["only nulls", [pt(1, null), pt(2, null)]],
  ])("is not enough to draw with %s", (_, points) => {
    const chart = buildChart(points);
    expect(chart.enough).toBe(false);
    expect(chart.points).toEqual([]);
    expect(chart.path).toBe("");
  });

  it("skips sessions with no score instead of drawing them at 0", () => {
    const chart = buildChart([pt(1, 40), pt(2, null), pt(3, 80)]);

    expect(chart.enough).toBe(true);
    expect(chart.points.map((p) => p.sessionId)).toEqual(["s1", "s3"]);
    expect(Math.max(...chart.points.map((p) => p.y))).toBeLessThan(BOX.height - BOX.bottom);
  });

  it("spaces points evenly, oldest left, across the plot area", () => {
    const chart = buildChart([pt(1, 10), pt(2, 20), pt(3, 30), pt(4, 40), pt(5, 50)]);

    const xs = chart.points.map((p) => p.x);
    expect(xs[0]).toBe(BOX.left);
    expect(xs[4]).toBeCloseTo(BOX.width - BOX.right);
    const gaps = xs.slice(1).map((x, i) => x - xs[i]);
    gaps.forEach((gap) => expect(gap).toBeCloseTo(gaps[0]));
  });

  it("uses a fixed 0-100 axis, clamping anything outside it", () => {
    const chart = buildChart([pt(1, 0), pt(2, 100), pt(3, 50), pt(4, 140), pt(5, -5)]);
    const [zero, hundred, fifty, over, under] = chart.points.map((p) => p.y);

    expect(zero).toBe(BOX.height - BOX.bottom);
    expect(hundred).toBe(BOX.top);
    expect(fifty).toBeCloseTo((zero + hundred) / 2);
    expect(over).toBe(hundred);
    expect(under).toBe(zero);
    expect(chart.ticks.map((t) => t.value)).toEqual([0, 25, 50, 75, 100]);
  });

  it("draws one line through every plotted point", () => {
    const chart = buildChart([pt(1, 10), pt(2, 20), pt(3, 30)]);
    expect(chart.path.startsWith("M")).toBe(true);
    expect(chart.path.match(/L/g)).toHaveLength(2);
  });
});

describe("describeChart", () => {
  it("summarises the trend for screen readers", () => {
    const chart = buildChart([pt(1, 42.4), pt(2, null), pt(9, 71.6)]);
    const day = (iso: string) => formatDate(iso, "UTC"); // month spelling varies by ICU version
    expect(describeChart(chart, "All", "UTC")).toBe(
      `Overall score over 2 sessions, from 42 on ${day(pt(1, 0).created_at)} to 72 on ${day(pt(9, 0).created_at)}.`,
    );
    expect(day(pt(9, 0).created_at)).toMatch(/^9 Sep/);
    expect(describeChart(buildChart([pt(1, 42)]), "Logic", "UTC")).toBe("");
  });
});

describe("options", () => {
  it("offer exactly the values the backend accepts, with All meaning overall", () => {
    expect(METRIC_OPTIONS.map((o) => o.value)).toEqual([
      "overall",
      "argumentation",
      "rebuttal",
      "structure",
      "persuasion",
      "logic",
    ]);
    expect(METRIC_OPTIONS[0].label).toBe("All");
    expect(RANGE_OPTIONS.map((o) => o.value)).toEqual(["1d", "1w", "1m", "5", "10", "15"]);
  });

  it("scoredPoints drops null and non-finite scores", () => {
    expect(scoredPoints([pt(1, 5), pt(2, null), pt(3, Number.NaN)]).map((p) => p.session_id)).toEqual(["s1"]);
  });
});

describe("getProgress", () => {
  it("sends metric and range as query parameters", async () => {
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        urls.push(url);
        return new Response(JSON.stringify([pt(1, 50)]), { status: 200 });
      }),
    );

    await expect(getProgress("rebuttal", "1w")).resolves.toEqual([pt(1, 50)]);
    expect(urls.map((u) => u.replace(/^https?:\/\/[^/]+/, ""))).toEqual([
      "/v1/sessions/progress?metric=rebuttal&range=1w",
    ]);
  });
});
