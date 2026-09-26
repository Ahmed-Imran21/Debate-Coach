/**
 * Practice-motion picker logic, free of React so vitest can test it.
 * The list itself comes from GET /v1/motions (app/motions.py on the
 * backend is the single source of truth); nothing here hard-codes it.
 */

import type { Motion } from "./types";

/** The dropdown value meaning "No prompt". */
export const NO_PROMPT = "";

/** The dropdown's value as a motion_id: null for "No prompt". */
export function toMotionId(value: string): string | null {
  return value === NO_PROMPT ? null : value;
}

export function findMotion(motions: Motion[], id: string | null): Motion | null {
  if (id === null) return null;
  return motions.find((m) => m.id === id) ?? null;
}
