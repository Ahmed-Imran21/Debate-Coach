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
  placeTooltip,
  scoredPoints,
  tooltipLines,
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

describe("tooltip", () => {
  const point = { title: "Second constructive, nuclear energy", createdAt: "2026-09-26T12:00:00Z", score: 57.6 };

  it("shows the title, the date and the score being charted", () => {
    expect(tooltipLines(point, "Logic", "en-GB", "UTC")).toEqual([
      "Second constructive, nuclear energy",
      expect.stringMatching(/^26 Sep/),
      "Logic: 58",
    ]);
  });

  it("labels the All view as Overall", () => {
    expect(tooltipLines(point, "All", "en-GB", "UTC")[2]).toBe("Overall: 58");
  });

  it("falls back to 'Session of <date>' like the session list", () => {
    const [name, date] = tooltipLines({ ...point, title: null }, "All", "en-GB", "UTC");
    expect(name).toBe(`Session of ${date}`);
    expect(tooltipLines({ ...point, title: "" }, "All", "en-GB", "UTC")[0]).toBe(`Session of ${date}`);
  });

  it("carries each session's title through the chart, null when there is none", () => {
    const chart = buildChart([{ ...pt(1, 40), title: "Named" }, pt(2, 60)]);
    expect(chart.points.map((p) => p.title)).toEqual(["Named", null]);
  });
});

describe("placeTooltip", () => {
  const W = 600;

  it("opens up and to the right by default", () => {
    expect(placeTooltip(200, 150, 120, 60, W)).toEqual({ left: 210, top: 80, openLeft: false, openBelow: false });
  });

  it("opens to the left near the right edge", () => {
    const placed = placeTooltip(560, 150, 120, 60, W);
    expect(placed.openLeft).toBe(true);
    expect(placed.left).toBe(560 - 10 - 120);
    expect(placed.left + 120).toBeLessThanOrEqual(W);
  });

  it("opens below the dot near the top", () => {
    const placed = placeTooltip(200, 20, 120, 60, W);
    expect(placed.openBelow).toBe(true);
    expect(placed.top).toBe(30);
  });

  it("never leaves the container, even when it barely fits", () => {
    for (const x of [0, 5, 60, 300, 590, 600]) {
      for (const y of [0, 10, 200]) {
        const { left, top } = placeTooltip(x, y, 150, 60, 320);
        expect(left).toBeGreaterThanOrEqual(0);
        expect(left + 150).toBeLessThanOrEqual(320);
        expect(top).toBeGreaterThanOrEqual(0);
      }
    }
  });
});
