/**
 * The profile page's rules and wording, kept out of the component so
 * they can be tested. The username and bio checks mirror
 * app/services/profile.py exactly (same rules, same messages), so a
 * mistake is shown under its field before anything is sent; the
 * backend still checks everything.
 */

import { CATEGORY_LABEL, type BestCategory, type Profile } from "./types";

export const USERNAME_LENGTH_MESSAGE = "A username must be 3 to 20 characters.";
export const USERNAME_CHARS_MESSAGE =
  "A username can only use lowercase letters, numbers and underscores.";
export const USERNAME_TAKEN_MESSAGE = "That username is taken.";
export const BIO_LENGTH_MESSAGE = "A bio can be at most 160 characters.";
export const BIO_PLAIN_MESSAGE = "A bio can only contain plain text.";

export const BIO_MAX = 160;
export const GOAL_OPTIONS = [1, 2, 3, 4, 5, 6, 7] as const;

/** Trimmed and lowercased, as the backend stores it; null when blank. */
export function normalizeUsername(raw: string): string | null {
  const value = raw.trim().toLowerCase();
  return value === "" ? null : value;
}

export function validateUsername(raw: string): string | null {
  const value = normalizeUsername(raw);
  if (value === null) return null; // blank clears it
  // Characters, not UTF-16 units, as Python counts them.
  const length = [...value].length;
  if (length < 3 || length > 20) return USERNAME_LENGTH_MESSAGE;
  if (!/^[a-z0-9_]+$/.test(value)) return USERNAME_CHARS_MESSAGE;
  return null;
}

function unifyLineBreaks(raw: string): string {
  return raw.replace(/\r\n?/g, "\n");
}

/** Line breaks kept, tabs as spaces, outer whitespace trimmed; null when blank. */
export function normalizeBio(raw: string): string | null {
  const value = unifyLineBreaks(raw).replace(/\t/g, " ").trim();
  return value === "" ? null : value;
}

/** The live counter: characters typed (an emoji is one), line breaks as one. */
export function bioLength(raw: string): number {
  return [...unifyLineBreaks(raw)].length;
}

export function validateBio(raw: string): string | null {
  const value = normalizeBio(raw);
  if (value === null) return null;
  // Control characters other than a line break.
  if (/[\u0000-\u0009\u000b-\u001f\u007f-\u009f]/.test(value)) return BIO_PLAIN_MESSAGE;
  if ([...value].length > BIO_MAX) return BIO_LENGTH_MESSAGE;
  return null;
}

/** Which field a backend message belongs under, so it's shown in the same place. */
export function fieldForMessage(message: string): "username" | "bio" | null {
  if ([USERNAME_LENGTH_MESSAGE, USERNAME_CHARS_MESSAGE, USERNAME_TAKEN_MESSAGE].includes(message)) {
    return "username";
  }
  if ([BIO_LENGTH_MESSAGE, BIO_PLAIN_MESSAGE].includes(message)) return "bio";
  return null;
}

/** The browser's IANA time zone (e.g. "Asia/Karachi"), or null if it can't say. */
export function browserTimeZone(): string | null {
  try {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return typeof zone === "string" && zone !== "" ? zone : null;
  } catch {
    return null;
  }
}

/* ---------------------------------------------------------- */
/* Streak and week                                             */
/* ---------------------------------------------------------- */

export function longestText(longest: number): string {
  return `Longest: ${longest} ${longest === 1 ? "day" : "days"}`;
}

/** Shown while the streak is alive only because of yesterday. */
export function streakNote(streak: Profile["streak"]): string | null {
  return streak.current > 0 && !streak.practised_today ? "Practise today to keep your streak." : null;
}

export function weekText(week: Profile["week"]): string {
  return `${week.completed} of ${week.goal} this week`;
}

export function weekCaption(week: Profile["week"]): string | null {
  return week.goal_met ? "Goal met this week" : null;
}

/** Bar width in percent, full once the goal is met. */
export function weekFill(week: Profile["week"]): number {
  return Math.min(100, Math.round((week.completed / week.goal) * 100));
}

/* ---------------------------------------------------------- */
/* Personal bests                                              */
/* ---------------------------------------------------------- */

export const BEST_LABEL: Record<BestCategory, string> = {
  overall: "Overall",
  ...CATEGORY_LABEL,
};

export function formatRecorded(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** The session list's name: its title, or "Session of <date>". */
export function sessionName(title: string | null, createdAt: string): string {
  return title || `Session of ${formatRecorded(createdAt)}`;
}
