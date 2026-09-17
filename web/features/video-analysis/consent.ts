/**
 * Remembers whether the user opted in to visual analysis
 * (task doc §4.3). localStorage, matching the existing token
 * storage pattern in lib/api.ts — same known trade-off (readable
 * by any script on this origin), same reason to accept it (no
 * sensitive data, just a preference).
 */

const OPT_IN_KEY = "dc.videoAnalysisOptIn";

export type ConsentChoice = "in" | "out";

export function getVideoAnalysisConsent(): ConsentChoice | null {
  if (typeof window === "undefined") return null;
  try {
    const value = window.localStorage.getItem(OPT_IN_KEY);
    return value === "in" || value === "out" ? value : null;
  } catch {
    return null;
  }
}

export function setVideoAnalysisConsent(choice: ConsentChoice): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(OPT_IN_KEY, choice);
  } catch {
    // Private browsing / storage blocked: the panel will just
    // ask again next time, which is an acceptable degradation.
  }
}
