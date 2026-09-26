/**
 * The progress report section's logic, free of React so vitest can
 * test it. app/practice/ProgressReportPanel.tsx renders it.
 */

import type { ReportSessionCount } from "./types";

export const SESSION_COUNT_OPTIONS: ReportSessionCount[] = [3, 5, 7];

/** "Sun 27 Sept, 05:00": the day resets at midnight UTC, shown in local time. */
export function formatNextAvailable(iso: string, timeZone?: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone,
  });
}

/** A report's UTC day, "26 Sept 2026". */
export function formatReportDate(reportDate: string): string {
  return new Date(`${reportDate}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

export function isFromToday(reportDate: string, now: Date = new Date()): boolean {
  return reportDate === now.toISOString().slice(0, 10);
}

/** The note under a report: which sessions it compared, and when. */
export function reportCaption(used: number, reportDate: string, now: Date = new Date()): string {
  const when = isFromToday(reportDate, now) ? "today" : `on ${formatReportDate(reportDate)}`;
  return `Compares your last ${used} sessions. Generated ${when}.`;
}
