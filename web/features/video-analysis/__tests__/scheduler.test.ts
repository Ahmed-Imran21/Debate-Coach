import { describe, expect, it } from "vitest";

import {
  DISABLE_ALL_SUSTAINED_S,
  DISABLE_HANDS_P90_MS,
  MIN_INTERVAL_MS,
  P90_WINDOW,
  REDUCE_HANDS_P90_MS,
} from "../config";
import { AdaptiveScheduler } from "../scheduler";

/** Feeds a scheduler ticks at a fixed interval with a fixed latency. */
function run(
  scheduler: AdaptiveScheduler,
  count: number,
  intervalMs: number,
  inferMsFor: (index: number) => number,
  startMs = 0,
): { events: ReturnType<AdaptiveScheduler["recordTick"]>[]; endMs: number } {
  const events: ReturnType<AdaptiveScheduler["recordTick"]>[] = [];
  let now = startMs;
  for (let i = 0; i < count; i++) {
    const handsRan = scheduler.planHands();
    const event = scheduler.recordTick(now, inferMsFor(i), handsRan);
    events.push(event);
    now += intervalMs;
  }
  return { events, endMs: now };
}

describe("AdaptiveScheduler — shouldTick rate limiting", () => {
  it("allows the first tick, then enforces MIN_INTERVAL_MS", () => {
    const s = new AdaptiveScheduler();
    expect(s.shouldTick(0)).toBe(true);
    s.recordTick(0, 20, true);
    expect(s.shouldTick(MIN_INTERVAL_MS - 1)).toBe(false);
    expect(s.shouldTick(MIN_INTERVAL_MS)).toBe(true);
  });
});

describe("AdaptiveScheduler — hands throttling on fast devices", () => {
  it("stays in full mode with no degradations when latency is always low", () => {
    const s = new AdaptiveScheduler();
    const { events } = run(s, P90_WINDOW * 3, MIN_INTERVAL_MS, () => 30);
    expect(s.currentHandsMode).toBe("full");
    expect(s.isDisabled).toBe(false);
    expect(events.every((e) => e === null)).toBe(true);
  });

  it("hands run on every tick in full mode", () => {
    const s = new AdaptiveScheduler();
    const ran: boolean[] = [];
    for (let i = 0; i < 5; i++) {
      const handsRan = s.planHands();
      ran.push(handsRan);
      s.recordTick(i * MIN_INTERVAL_MS, 20, handsRan);
    }
    expect(ran).toEqual([true, true, true, true, true]);
  });
});

describe("AdaptiveScheduler — latency-driven downgrades", () => {
  it("downgrades to reduced once p90 exceeds REDUCE_HANDS_P90_MS, with one event", () => {
    const s = new AdaptiveScheduler();
    const { events } = run(s, P90_WINDOW, MIN_INTERVAL_MS, () => REDUCE_HANDS_P90_MS + 10);

    expect(s.currentHandsMode).toBe("reduced");
    const fired = events.filter((e) => e !== null);
    expect(fired).toHaveLength(1);
    expect(fired[0]!.reason).toBe("p90_latency");
    // Hands ran on every tick right up to this one (mode was
    // still "full" when planHands() was called for it).
    expect(fired[0]!.hands_fps).toBe(fired[0]!.face_fps);
  });

  it("downgrades straight to off once p90 exceeds DISABLE_HANDS_P90_MS", () => {
    const s = new AdaptiveScheduler();
    const { events } = run(s, P90_WINDOW, MIN_INTERVAL_MS, () => DISABLE_HANDS_P90_MS + 10);

    expect(s.currentHandsMode).toBe("off");
    const fired = events.filter((e) => e !== null);
    expect(fired).toHaveLength(1);
    expect(fired[0]!.reason).toBe("p90_latency");
    expect(fired[0]!.hands_fps).toBe(0);
  });

  it("reduced tier runs hands on every other tick", () => {
    const s = new AdaptiveScheduler();
    run(s, P90_WINDOW, MIN_INTERVAL_MS, () => REDUCE_HANDS_P90_MS + 10);
    expect(s.currentHandsMode).toBe("reduced");

    const ran: boolean[] = [];
    let now = P90_WINDOW * MIN_INTERVAL_MS;
    for (let i = 0; i < 6; i++) {
      const handsRan = s.planHands();
      ran.push(handsRan);
      s.recordTick(now, 20, handsRan);
      now += MIN_INTERVAL_MS;
    }
    expect(ran).toEqual([true, false, true, false, true, false]);
  });

  it("never upgrades back to full even after latency recovers", () => {
    const s = new AdaptiveScheduler();
    const first = run(s, P90_WINDOW, MIN_INTERVAL_MS, () => REDUCE_HANDS_P90_MS + 10);
    expect(s.currentHandsMode).toBe("reduced");

    run(s, P90_WINDOW * 2, MIN_INTERVAL_MS, () => 5, first.endMs);
    expect(s.currentHandsMode).toBe("reduced");
  });

  it("does not evaluate p90 before the window has filled", () => {
    const s = new AdaptiveScheduler();
    const { events } = run(s, P90_WINDOW - 1, MIN_INTERVAL_MS, () => DISABLE_HANDS_P90_MS + 100);
    expect(s.currentHandsMode).toBe("full");
    expect(events.every((e) => e === null)).toBe(true);
  });
});

describe("AdaptiveScheduler — sustained low fps disables everything", () => {
  it("does not disable on a brief dip under DISABLE_ALL_EFFECTIVE_FPS", () => {
    const s = new AdaptiveScheduler();
    // One slow tick (simulates a stall), then fast ticks resume
    // well before the 10s sustained threshold.
    s.recordTick(0, 20, true);
    run(s, 20, MIN_INTERVAL_MS, () => 20, 2000);
    expect(s.isDisabled).toBe(false);
  });

  it("disables after effective fps stays below threshold for DISABLE_ALL_SUSTAINED_S", () => {
    const s = new AdaptiveScheduler();
    // One tick per second (effective fps ~1, well under the
    // threshold of 3) for just over the sustained window.
    const events: ReturnType<AdaptiveScheduler["recordTick"]>[] = [];
    let now = 0;
    const stepMs = 1000;
    const steps = DISABLE_ALL_SUSTAINED_S + 2;
    for (let i = 0; i < steps; i++) {
      events.push(s.recordTick(now, 20, false));
      now += stepMs;
    }
    expect(s.isDisabled).toBe(true);
    const fired = events.filter((e) => e !== null);
    expect(fired).toHaveLength(1);
    expect(fired[0]!.reason).toBe("thermal_suspected");
  });

  it("stops ticking once disabled", () => {
    const s = new AdaptiveScheduler();
    let now = 0;
    for (let i = 0; i < DISABLE_ALL_SUSTAINED_S + 2; i++) {
      s.recordTick(now, 20, false);
      now += 1000;
    }
    expect(s.isDisabled).toBe(true);
    expect(s.shouldTick(now)).toBe(false);
  });
});
