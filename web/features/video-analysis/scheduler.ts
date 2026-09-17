/**
 * Adaptive frame-rate scheduler (task doc §4.7). Pure: every
 * timestamp is passed in by the caller rather than read from
 * performance.now(), so behaviour is fully determined by the
 * sequence of calls and can be replayed exactly in a test.
 *
 * Downgrades only. Once hands throttle down (full -> reduced ->
 * off) or analysis disables entirely, this session never goes
 * back, even if timings improve — matching §4.7's "never upgrade
 * during a recording".
 */

import {
  DISABLE_ALL_EFFECTIVE_FPS,
  DISABLE_ALL_SUSTAINED_S,
  DISABLE_HANDS_P90_MS,
  MIN_INTERVAL_MS,
  P90_WINDOW,
  REDUCE_HANDS_P90_MS,
} from "./config";

export type HandsMode = "full" | "reduced" | "off";

export interface Degradation {
  /** Seconds, same clock as VisualSignalTrack.frames.t. */
  t: number;
  face_fps: number;
  hands_fps: number;
  reason: "p90_latency" | "thermal_suspected" | "manual";
}

function percentile90(sorted_ascending_input: readonly number[]): number {
  const values = [...sorted_ascending_input].sort((a, b) => a - b);
  const index = Math.min(values.length - 1, Math.ceil(0.9 * values.length) - 1);
  return values[Math.max(0, index)];
}

export class AdaptiveScheduler {
  private handsMode: HandsMode = "full";
  // Counts every tick (not just ones hands ran on), so its parity
  // toggles cleanly for the "reduced" alternation below. Gating
  // the increment on handsRan would make it stick on the same
  // parity once a tick is skipped.
  private tickCount = 0;
  private disabled = false;

  private readonly latencyWindow: number[] = [];
  private readonly recentTickMs: number[] = [];
  private readonly recentHandsTickMs: number[] = [];
  private lowFpsSinceMs: number | null = null;
  private lastTickMs: number | null = null;

  /** At most one tick per MIN_INTERVAL_MS. */
  shouldTick(nowMs: number): boolean {
    if (this.disabled) return false;
    if (this.lastTickMs === null) return true;
    return nowMs - this.lastTickMs >= MIN_INTERVAL_MS;
  }

  /** Whether the hand model should run on the tick about to start. */
  planHands(): boolean {
    if (this.handsMode === "off") return false;
    if (this.handsMode === "full") return true;
    return this.tickCount % 2 === 0;
  }

  get currentHandsMode(): HandsMode {
    return this.handsMode;
  }

  get isDisabled(): boolean {
    return this.disabled;
  }

  /**
   * Record a completed tick (face always ran; handsRan reflects
   * what planHands() returned, so the alternation counter and
   * fps estimate stay consistent with what actually happened).
   * Returns a Degradation to append to the track if this tick
   * crossed a threshold, else null.
   */
  recordTick(nowMs: number, inferMs: number, handsRan: boolean): Degradation | null {
    this.lastTickMs = nowMs;
    this.tickCount += 1;

    this.recentTickMs.push(nowMs);
    while (this.recentTickMs.length > 0 && nowMs - this.recentTickMs[0] > 1000) {
      this.recentTickMs.shift();
    }
    const effectiveFps = this.recentTickMs.length;

    if (handsRan) this.recentHandsTickMs.push(nowMs);
    while (this.recentHandsTickMs.length > 0 && nowMs - this.recentHandsTickMs[0] > 1000) {
      this.recentHandsTickMs.shift();
    }
    const handsFps = this.recentHandsTickMs.length;

    this.latencyWindow.push(inferMs);
    if (this.latencyWindow.length > P90_WINDOW) this.latencyWindow.shift();

    const latencyEvent = this.checkLatency(nowMs, effectiveFps, handsFps);
    if (latencyEvent) return latencyEvent;

    return this.checkSustainedLowFps(nowMs, effectiveFps, handsFps);
  }

  private checkLatency(nowMs: number, effectiveFps: number, handsFps: number): Degradation | null {
    if (this.disabled || this.handsMode === "off" || this.latencyWindow.length < P90_WINDOW) {
      return null;
    }

    const p90 = percentile90(this.latencyWindow);

    if (p90 > DISABLE_HANDS_P90_MS) {
      this.handsMode = "off";
      // hands_fps is 0, not the stale rate just before this tick:
      // the event describes the state the transition produces.
      return { t: nowMs / 1000, face_fps: effectiveFps, hands_fps: 0, reason: "p90_latency" };
    }

    if (p90 > REDUCE_HANDS_P90_MS && this.handsMode === "full") {
      this.handsMode = "reduced";
      return {
        t: nowMs / 1000,
        face_fps: effectiveFps,
        hands_fps: handsFps,
        reason: "p90_latency",
      };
    }

    return null;
  }

  private checkSustainedLowFps(nowMs: number, effectiveFps: number, handsFps: number): Degradation | null {
    if (this.disabled) return null;

    if (effectiveFps >= DISABLE_ALL_EFFECTIVE_FPS) {
      this.lowFpsSinceMs = null;
      return null;
    }

    if (this.lowFpsSinceMs === null) {
      this.lowFpsSinceMs = nowMs;
      return null;
    }

    if (nowMs - this.lowFpsSinceMs >= DISABLE_ALL_SUSTAINED_S * 1000) {
      this.disabled = true;
      return {
        t: nowMs / 1000,
        face_fps: effectiveFps,
        hands_fps: handsFps,
        reason: "thermal_suspected",
      };
    }

    return null;
  }
}
