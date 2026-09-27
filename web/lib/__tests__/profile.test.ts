/**
 * The profile page's rules and wording (lib/profile.ts), and its two
 * API calls. The username and bio checks must match
 * app/services/profile.py: same rules, same messages.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  BEST_LABEL,
  BIO_LENGTH_MESSAGE,
  BIO_PLAIN_MESSAGE,
  USERNAME_CHARS_MESSAGE,
  USERNAME_LENGTH_MESSAGE,
  USERNAME_TAKEN_MESSAGE,
  bioLength,
  browserTimeZone,
  fieldForMessage,
  longestText,
  normalizeBio,
  normalizeUsername,
  sessionName,
  streakNote,
  validateBio,
  validateUsername,
  weekCaption,
  weekFill,
  weekText,
} from "../profile";
import type { Profile } from "../types";

describe("username", () => {
  it.each(["abc", "a_1", "x".repeat(20), "debater_2026", "___", "  Ahmed_K  "])("accepts %j", (raw) => {
    expect(validateUsername(raw)).toBeNull();
  });

  it("is trimmed and lowercased, and blank clears it", () => {
    expect(normalizeUsername("  Ahmed_K ")).toBe("ahmed_k");
    expect(normalizeUsername("")).toBeNull();
    expect(normalizeUsername("   ")).toBeNull();
    expect(validateUsername("")).toBeNull();
  });

  it.each(["ab", "a", "x".repeat(21), "  ab  ", "🎤🎤"])("refuses the length of %j", (raw) => {
    expect(validateUsername(raw)).toBe(USERNAME_LENGTH_MESSAGE);
  });

  it.each(["ab-c", "ab c", "abc!", "@abc", "abc.def", "émile", "ab٣c", "abс", "ab\nc"])(
    "refuses the characters in %j",
    (raw) => {
      expect(validateUsername(raw)).toBe(USERNAME_CHARS_MESSAGE);
    },
  );
});

describe("bio", () => {
  it("keeps line breaks, turns tabs into spaces and trims", () => {
    expect(normalizeBio("  Line one\r\nLine two\rLine three\n  ")).toBe("Line one\nLine two\nLine three");
    expect(normalizeBio("a\tb")).toBe("a b");
    expect(normalizeBio(" \n\t ")).toBeNull();
  });

  it("counts characters, not UTF-16 units, with a line break as one", () => {
    expect(bioLength("🎤🎤")).toBe(2);
    expect(bioLength("a\r\nb")).toBe(3);
    expect(bioLength("ü".repeat(10))).toBe(10);
  });

  it("allows exactly 160 characters, emoji included", () => {
    expect(validateBio("x".repeat(160))).toBeNull();
    expect(validateBio("🎤".repeat(160))).toBeNull();
    expect(validateBio("x".repeat(160) + "   \n")).toBeNull(); // trailing whitespace is trimmed
    expect(validateBio("x".repeat(161))).toBe(BIO_LENGTH_MESSAGE);
    expect(validateBio("🎤".repeat(161))).toBe(BIO_LENGTH_MESSAGE);
  });

  it.each(["a\u0000b", "a\u0007b", "a\u001bb", "a\u007fb"])("refuses control characters (%#)", (raw) => {
    expect(validateBio(raw)).toBe(BIO_PLAIN_MESSAGE);
  });

  it("allows line breaks and ordinary text that looks like formatting", () => {
    expect(validateBio("one\ntwo\n\nthree")).toBeNull();
    expect(validateBio("**bold** <b>x</b> https://example.com")).toBeNull();
  });
});

describe("backend messages go under their field", () => {
  it.each([
    [USERNAME_TAKEN_MESSAGE, "username"],
    [USERNAME_LENGTH_MESSAGE, "username"],
    [USERNAME_CHARS_MESSAGE, "username"],
    [BIO_LENGTH_MESSAGE, "bio"],
    [BIO_PLAIN_MESSAGE, "bio"],
    ["The server could not complete that request. Try again shortly.", null],
  ])("%j -> %s", (message, field) => {
    expect(fieldForMessage(message)).toBe(field);
  });

  it("uses exactly the backend's wording for a taken username", () => {
    expect(USERNAME_TAKEN_MESSAGE).toBe("That username is taken.");
  });
});

const week = (completed: number, goal: number): Profile["week"] => ({
  completed,
  goal,
  goal_met: completed >= goal,
  starts_on: "2026-09-21",
  ends_on: "2026-09-27",
});

describe("streak wording", () => {
  it("asks for practice today only while yesterday is keeping the streak alive", () => {
    expect(streakNote({ current: 3, longest: 5, practised_today: false })).toBe("Practise today to keep your streak.");
    expect(streakNote({ current: 3, longest: 5, practised_today: true })).toBeNull();
    expect(streakNote({ current: 0, longest: 5, practised_today: false })).toBeNull();
  });

  it("says day or days", () => {
    expect(longestText(1)).toBe("Longest: 1 day");
    expect(longestText(0)).toBe("Longest: 0 days");
    expect(longestText(12)).toBe("Longest: 12 days");
  });
});

describe("weekly goal wording", () => {
  it("counts sessions against the goal, beyond it too", () => {
    expect(weekText(week(2, 3))).toBe("2 of 3 this week");
    expect(weekText(week(4, 3))).toBe("4 of 3 this week");
  });

  it("says the goal is met only once it is", () => {
    expect(weekCaption(week(2, 3))).toBeNull();
    expect(weekCaption(week(3, 3))).toBe("Goal met this week");
    expect(weekCaption(week(4, 3))).toBe("Goal met this week");
  });

  it("fills the bar in proportion, never past full", () => {
    expect(weekFill(week(0, 3))).toBe(0);
    expect(weekFill(week(1, 3))).toBe(33);
    expect(weekFill(week(3, 3))).toBe(100);
    expect(weekFill(week(9, 3))).toBe(100);
  });
});

describe("personal bests wording", () => {
  it("labels every category, Delivery for the engine's quantitative", () => {
    expect(BEST_LABEL).toEqual({
      overall: "Overall",
      quantitative: "Delivery",
      argumentation: "Argumentation",
      rebuttal: "Rebuttal",
      structure: "Structure",
      persuasion: "Persuasion",
      logic: "Logic",
    });
  });

  it("names a session by its title, or 'Session of <date>' as the session list does", () => {
    expect(sessionName("Carbon tax", "2026-09-12T10:00:00Z")).toBe("Carbon tax");
    const recorded = new Date("2026-09-12T10:00:00Z").toLocaleDateString(undefined, {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
    expect(sessionName(null, "2026-09-12T10:00:00Z")).toBe(`Session of ${recorded}`);
    expect(sessionName("", "2026-09-12T10:00:00Z")).toBe(`Session of ${recorded}`);
  });
});

describe("browserTimeZone", () => {
  afterEach(() => vi.restoreAllMocks());

  it("reads the IANA zone from the browser", () => {
    vi.spyOn(Intl, "DateTimeFormat").mockReturnValue({
      resolvedOptions: () => ({ timeZone: "Asia/Karachi" }),
    } as unknown as Intl.DateTimeFormat);
    expect(browserTimeZone()).toBe("Asia/Karachi");
  });

  it("gives null instead of throwing when the browser can't say", () => {
    vi.spyOn(Intl, "DateTimeFormat").mockImplementation(() => {
      throw new Error("no Intl");
    });
    expect(browserTimeZone()).toBeNull();
    vi.spyOn(Intl, "DateTimeFormat").mockReturnValue({
      resolvedOptions: () => ({ timeZone: "" }),
    } as unknown as Intl.DateTimeFormat);
    expect(browserTimeZone()).toBeNull();
  });
});

describe("profile API calls", () => {
  let calls: { url: string; method: string; body: unknown; auth?: string }[] = [];

  beforeEach(() => {
    vi.resetModules();
    const memory = new Map<string, string>();
    const storage = {
      getItem: (k: string) => memory.get(k) ?? null,
      setItem: (k: string, v: string) => void memory.set(k, v),
      removeItem: (k: string) => void memory.delete(k),
      clear: () => memory.clear(),
      key: () => null,
      length: 0,
    };
    vi.stubGlobal("window", { localStorage: storage, sessionStorage: storage });
    calls = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init: RequestInit = {}) => {
        const headers = (init.headers ?? {}) as Record<string, string>;
        calls.push({
          url: url.replace(/^https?:\/\/[^/]+/, ""),
          method: init.method ?? "GET",
          body: init.body ? JSON.parse(String(init.body)) : undefined,
          auth: headers.Authorization,
        });
        return new Response(JSON.stringify({ username: "x" }), { status: 200 });
      }),
    );
  });

  afterEach(() => vi.unstubAllGlobals());

  it("reads the signed-in user's own profile, with no id in the URL", async () => {
    const { getProfile } = await import("../api");
    await getProfile();
    expect(calls).toEqual([{ url: "/v1/profile", method: "GET", body: undefined, auth: undefined }]);
  });

  it("sends only the fields being changed, with PUT", async () => {
    const { updateProfile } = await import("../api");
    await updateProfile({ weekly_goal: 5 });
    await updateProfile({ username: null, bio: "Hi" });
    expect(calls.map(({ url, method, body }) => ({ url, method, body }))).toEqual([
      { url: "/v1/profile", method: "PUT", body: { weekly_goal: 5 } },
      { url: "/v1/profile", method: "PUT", body: { username: null, bio: "Hi" } },
    ]);
  });
});
