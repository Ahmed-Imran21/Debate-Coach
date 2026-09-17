/**
 * Pure classification logic for the setup screen's framing
 * checks (task doc §4.9.1). Kept separate from math.ts (which is
 * per-frame landmark derivation) since this operates on rolling
 * windows / aggregates instead.
 */

import {
  DISTANCE_SCALE_MAX,
  DISTANCE_SCALE_MIN,
  FACE_VISIBLE_MIN_RATIO,
  HANDS_RAISED_MIN_RATIO,
  LIGHTING_BACKLIT_RATIO,
  LIGHTING_DIM_LUMA,
} from "./config";
import { median } from "./stats";

export type DistanceCheck = "ok" | "too_close" | "too_far";
export type LightingCheck = "ok" | "dim" | "backlit";

export function ratioTrue(flags: readonly boolean[]): number {
  if (flags.length === 0) return 0;
  return flags.filter(Boolean).length / flags.length;
}

export function faceVisiblePasses(recentFacePresent: readonly boolean[]): boolean {
  return ratioTrue(recentFacePresent) >= FACE_VISIBLE_MIN_RATIO;
}

export function classifyDistance(recentFaceScales: readonly number[]): DistanceCheck {
  if (recentFaceScales.length === 0) return "too_far";
  const value = median(recentFaceScales);
  if (value > DISTANCE_SCALE_MAX) return "too_close";
  if (value < DISTANCE_SCALE_MIN) return "too_far";
  return "ok";
}

/**
 * meanLuma: average brightness (0-255) of the whole sampled
 * frame. faceLuma: average brightness of just the face region.
 * null faceLuma (no face yet) can't detect backlighting, so it
 * only checks overall dimness.
 */
export function classifyLighting(meanLuma: number, faceLuma: number | null): LightingCheck {
  if (meanLuma < LIGHTING_DIM_LUMA) return "dim";
  if (faceLuma !== null && faceLuma < meanLuma * LIGHTING_BACKLIT_RATIO) return "backlit";
  return "ok";
}

export function handsRaisedPasses(recentBothHandsPresent: readonly boolean[]): boolean {
  return ratioTrue(recentBothHandsPresent) >= HANDS_RAISED_MIN_RATIO;
}
