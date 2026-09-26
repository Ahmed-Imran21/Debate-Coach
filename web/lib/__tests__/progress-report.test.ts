/**
 * The progress report section (lib/progress-report.ts) and its API
 * calls: the POST body the backend validates, the long timeout, and
 * the local-time "next available" note.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, PROGRESS_REPORT_TIMEOUT_MS, createProgressReport, getLatestProgressReport } from "../api";
import {
  SESSION_COUNT_OPTIONS,
  formatNextAvailable,
  formatReportDate,
  isFromToday,
  reportCaption,
} from "../progress-report";

afterEach(() => {
  vi.unstubAllGlobals();
});

function captureFetch(respond: () => Response) {
  const calls: { url: string; method: string; body?: BodyInit | null }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      calls.push({ url: url.replace(/^https?:\/\/[^/]+/, ""), method: init.method ?? "GET", body: init.body });
      return respond();
    }),
  );
  return calls;
}

describe("progress report API", () => {
  it("posts the chosen session count", async () => {
    const report = { id: "r1", report_date: "2026-09-26", created_at: "", session_count_requested: 5, session_count_used: 3, bullets: ["One."] };
    const calls = captureFetch(() => new Response(JSON.stringify(report), { status: 201 }));

    await expect(createProgressReport(5)).resolves.toEqual(report);
    expect(calls).toEqual([{ url: "/v1/progress-reports", method: "POST", body: JSON.stringify({ session_count: 5 }) }]);
  });

  it("surfaces the backend's refusal text", async () => {
    captureFetch(
      () => new Response(JSON.stringify({ detail: "You've already generated today's progress report." }), { status: 429 }),
    );
    await expect(createProgressReport(3)).rejects.toEqual(new ApiError(429, "You've already generated today's progress report."));
  });

  it("reads the latest report", async () => {
    const latest = { report: null, can_generate: true, next_available_at: null };
    const calls = captureFetch(() => new Response(JSON.stringify(latest), { status: 200 }));

    await expect(getLatestProgressReport()).resolves.toEqual(latest);
    expect(calls[0]).toMatchObject({ url: "/v1/progress-reports/latest", method: "GET" });
  });

  it("allows far longer than the default timeout for the LLM call", () => {
    expect(PROGRESS_REPORT_TIMEOUT_MS).toBeGreaterThanOrEqual(90_000);
  });
});

describe("progress report helpers", () => {
  it("offers exactly the counts the backend accepts", () => {
    expect(SESSION_COUNT_OPTIONS).toEqual([3, 5, 7]);
  });

  it("shows the UTC-midnight reset in the viewer's own time zone", () => {
    // Midnight UTC is 05:00 the same morning in Pakistan.
    expect(formatNextAvailable("2026-09-27T00:00:00Z", "Asia/Karachi")).toMatch(/27 Sep.*05:00/);
    expect(formatNextAvailable("2026-09-27T00:00:00Z", "UTC")).toMatch(/27 Sep.*00:00/);
  });

  it("labels a report as today's only on the same UTC day", () => {
    const now = new Date("2026-09-26T23:30:00Z");
    expect(isFromToday("2026-09-26", now)).toBe(true);
    expect(isFromToday("2026-09-25", now)).toBe(false);
    expect(reportCaption(3, "2026-09-26", now)).toBe("Compares your last 3 sessions. Generated today.");
    expect(reportCaption(5, "2026-09-20", now)).toBe(`Compares your last 5 sessions. Generated on ${formatReportDate("2026-09-20")}.`);
    expect(formatReportDate("2026-09-20")).toMatch(/^20 Sep/);
  });
});
