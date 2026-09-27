/**
 * Golden vectors for the Android port of web/features/video-analysis.
 *
 * Runs the WEBSITE'S OWN modules (imported from ../../web, unchanged)
 * on every input the web's own tests use (web/features/video-analysis/
 * __tests__), plus thousands of seeded random and boundary inputs, and
 * writes the exact outputs to android/app/src/test/resources/parity/.
 * The Kotlin tests (VisualParityGoldenTest and friends) replay the
 * same inputs through the Kotlin port and require identical outputs:
 * bit-identical doubles, and byte-identical JSON.stringify() output for
 * built tracks.
 *
 * Regenerate after any change to the web module:
 *   web/node_modules/.bin/vitest run --config android/parity/vitest.config.mts
 * then run the Android unit tests. check-goldens.sh does both and fails
 * if the committed goldens are stale.
 */

import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, it } from "vitest";

import * as config from "../../web/features/video-analysis/config";
import { toModelProvenance, type RawManifestModel } from "../../web/features/video-analysis/extractor";
import {
  classifyDistance,
  classifyLighting,
  faceVisiblePasses,
  handsRaisedPasses,
  ratioTrue,
} from "../../web/features/video-analysis/framing";
import {
  assignTwoHandSides,
  computeFaceCenter,
  computeFaceScale,
  computeIrisOffset,
  computePalmCentroid,
  headPoseFromMatrix,
  resolveHandSideFromLabel,
  selectPrimaryFace,
  type Landmark,
} from "../../web/features/video-analysis/math";
import { AdaptiveScheduler } from "../../web/features/video-analysis/scheduler";
import { clamp, meanAbsoluteDeviation, median, percentile90 } from "../../web/features/video-analysis/stats";
import { TrackBuilder } from "../../web/features/video-analysis/track";
import { EMPTY_SAMPLE, FRAME_COLUMNS, type FrameSample } from "../../web/features/video-analysis/types";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "..", "app", "src", "test", "resources", "parity");
const WEB = join(HERE, "..", "..", "web");

// ---------------------------------------------------------------
// Deterministic randomness and number encoding
// ---------------------------------------------------------------

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const rand = mulberry32(20260927);
const between = (lo: number, hi: number) => lo + (hi - lo) * rand();
const int = (lo: number, hi: number) => Math.floor(between(lo, hi + 1));
const pick = <T,>(items: readonly T[]): T => items[Math.floor(rand() * items.length)];

/** JSON can't hold NaN/Infinity/-0; encode them so Kotlin can compare exactly. */
function enc(value: unknown): unknown {
  if (typeof value === "number") {
    if (Number.isNaN(value)) return "NaN";
    if (value === Infinity) return "Infinity";
    if (value === -Infinity) return "-Infinity";
    if (Object.is(value, -0)) return "-0";
    return value;
  }
  if (Array.isArray(value)) return value.map(enc);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, enc(v)]));
  }
  return value;
}

function write(name: string, data: unknown): void {
  mkdirSync(OUT, { recursive: true });
  writeFileSync(join(OUT, name), JSON.stringify(enc(data)) + "\n", "utf-8");
}

// Values that stress rounding: exact ties, float-representation traps,
// signs, tiny and large magnitudes.
const EDGE_NUMBERS = [
  0, -0, 0.5, -0.5, 1.5, -1.5, 2.5, -2.5, 0.049, 0.05, -0.05, 0.15, 0.25, 0.35, 1.005, 2.675, 1.45, -1.45,
  0.0005, -0.0005, 0.0015, 0.1234999, 12.3456, -7.891, 12.35, -12.35, 0.999, 0.9995, 1e-7, -1e-7, 123456.789,
  0.1 + 0.2, 1 / 3, -1 / 3, 38.7, 39.5, 40.5, 179.95, -179.95, 89.999, 1.4999999999999998, 0.49999999999999994,
];

// ---------------------------------------------------------------
// Landmark helpers
// ---------------------------------------------------------------

interface SparseLandmarks {
  length: number;
  fill: [number, number, number] | null;
  set: Record<string, [number, number, number]>;
}

function toLandmarks(s: SparseLandmarks): Landmark[] {
  const out: Landmark[] = new Array(s.length);
  for (let i = 0; i < s.length; i++) {
    out[i] = s.fill ? { x: s.fill[0], y: s.fill[1], z: s.fill[2] } : (undefined as unknown as Landmark);
  }
  for (const [k, [x, y, z]] of Object.entries(s.set)) out[Number(k)] = { x, y, z };
  return out;
}

function denseLandmarks(count: number): SparseLandmarks {
  const set: SparseLandmarks["set"] = {};
  for (let i = 0; i < count; i++) set[i] = [rand(), rand(), between(-0.1, 0.1)];
  return { length: count, fill: null, set };
}

/** The web test's eyeLandmarks(), as data. */
function eyeCase(opts: { leftIrisDx?: number; rightIrisDx?: number; irisDy?: number; closed?: boolean }, W = 640, H = 360): SparseLandmarks {
  const set: SparseLandmarks["set"] = {};
  const put = (i: number, x: number, y: number) => {
    set[i] = [x / W, y / H, 0];
  };
  const lCx = 100, lCy = 100, lHalfW = 15, lHalfH = opts.closed ? 0.2 : 8;
  put(33, lCx - lHalfW, lCy);
  put(133, lCx + lHalfW, lCy);
  put(159, lCx, lCy - lHalfH);
  put(145, lCx, lCy + lHalfH);
  put(468, lCx + (opts.leftIrisDx ?? 0) * lHalfW, lCy + (opts.irisDy ?? 0) * lHalfH);
  const rCx = 300, rCy = 100, rHalfW = 15, rHalfH = opts.closed ? 0.2 : 8;
  put(263, rCx - rHalfW, rCy);
  put(362, rCx + rHalfW, rCy);
  put(386, rCx, rCy - rHalfH);
  put(374, rCx, rCy + rHalfH);
  put(473, rCx + (opts.rightIrisDx ?? 0) * rHalfW, rCy + (opts.irisDy ?? 0) * rHalfH);
  return { length: 479, fill: [0, 0, 0], set };
}

/** A random but face-like set of the landmarks the math reads. */
function randomFace(): SparseLandmarks {
  // Sparse: a fill point plus ~30 scattered ones, and every landmark
  // the math reads. The face center is still the mean of all 478.
  const s: SparseLandmarks = { length: 478, fill: [rand(), rand(), 0], set: {} };
  for (let i = 0; i < 30; i++) s.set[int(0, 477)] = [rand(), rand(), between(-0.1, 0.1)];
  const cx = between(0.2, 0.8), cy = between(0.2, 0.8), eyeW = between(0.01, 0.06), eyeH = pick([0.0005, 0.002, between(0.002, 0.03)]);
  const eye = (outer: number, inner: number, upper: number, lower: number, iris: number, ox: number) => {
    s.set[outer] = [cx + ox - eyeW, cy + between(-0.005, 0.005), 0];
    s.set[inner] = [cx + ox + eyeW, cy + between(-0.005, 0.005), 0];
    s.set[upper] = [cx + ox, cy - eyeH, 0];
    s.set[lower] = [cx + ox, cy + eyeH, 0];
    s.set[iris] = [cx + ox + between(-2, 2) * eyeW, cy + between(-2, 2) * eyeH, 0];
  };
  const sep = between(0.03, 0.12);
  eye(33, 133, 159, 145, 468, -sep);
  eye(263, 362, 386, 374, 473, sep);
  return s;
}

// ---------------------------------------------------------------
// Rotation matrices (the web test's buildMatrixData, as data)
// ---------------------------------------------------------------

function buildMatrixData(yawDeg: number, pitchDeg: number, rollDeg: number): number[] {
  const d2r = Math.PI / 180;
  const [yaw, pitch, roll] = [yawDeg * d2r, pitchDeg * d2r, rollDeg * d2r];
  const mul3 = (a: number[][], b: number[][]): number[][] =>
    a.map((row, i) => row.map((_, j) => row.reduce((sum, _v, k) => sum + a[i][k] * b[k][j], 0)));
  const rx = [[1, 0, 0], [0, Math.cos(pitch), -Math.sin(pitch)], [0, Math.sin(pitch), Math.cos(pitch)]];
  const ry = [[Math.cos(yaw), 0, Math.sin(yaw)], [0, 1, 0], [-Math.sin(yaw), 0, Math.cos(yaw)]];
  const rz = [[Math.cos(roll), -Math.sin(roll), 0], [Math.sin(roll), Math.cos(roll), 0], [0, 0, 1]];
  const r = mul3(mul3(ry, rx), rz);
  const m = [[r[0][0], r[0][1], r[0][2], 0], [r[1][0], r[1][1], r[1][2], 0], [r[2][0], r[2][1], r[2][2], 0], [0, 0, 0, 1]];
  const flat: number[] = [];
  for (let col = 0; col < 4; col++) for (let row = 0; row < 4; row++) flat.push(m[row][col]);
  return flat;
}

// ===============================================================
// math.ts
// ===============================================================

function mathGoldens() {
  const headPose: unknown[] = [];
  const angles: [number, number, number][] = [
    [0, 0, 0], [30, 0, 0], [0, 20, 0], [0, 0, 15], [-40, 30, -20], [25, 0, 0], [-25, 0, 0],
    [90, 0, 0], [0, 90, 0], [0, -90, 0], [180, 0, 0], [-180, 45, 170],
  ];
  for (let i = 0; i < 300; i++) angles.push([between(-180, 180), between(-89, 89), between(-180, 180)]);
  for (const [y, p, r] of angles) {
    const matrix = buildMatrixData(y, p, r);
    headPose.push({ matrix, columns: 4, out: headPoseFromMatrix(matrix) });
  }
  // Arbitrary (non-rotation) matrices, including |r12| > 1 (asin clamp).
  for (let i = 0; i < 100; i++) {
    const matrix = Array.from({ length: 16 }, () => between(-2, 2));
    headPose.push({ matrix, columns: 4, out: headPoseFromMatrix(matrix) });
  }
  // A 3-column layout.
  for (let i = 0; i < 20; i++) {
    const matrix = Array.from({ length: 9 }, () => between(-1, 1));
    headPose.push({ matrix, columns: 3, out: headPoseFromMatrix(matrix, 3) });
  }

  const iris: unknown[] = [];
  const irisInputs: [SparseLandmarks, number, number][] = [
    [eyeCase({}), 640, 360],
    [eyeCase({ leftIrisDx: -0.5, rightIrisDx: -0.5 }), 640, 360],
    [eyeCase({ leftIrisDx: 0.5, rightIrisDx: 0.5 }), 640, 360],
    [eyeCase({ irisDy: -0.5 }), 640, 360],
    [eyeCase({ irisDy: 0.5 }), 640, 360],
    [eyeCase({ leftIrisDx: -10, rightIrisDx: -10 }), 640, 360],
    [eyeCase({ closed: true }), 640, 360],
    [{ length: 0, fill: null, set: {} }, 640, 360],
    [{ length: 400, fill: [0.5, 0.5, 0], set: {} }, 640, 360],
  ];
  for (let i = 0; i < 400; i++) irisInputs.push([randomFace(), pick([640, 360, 1280]), pick([360, 640, 720])]);
  for (const [landmarks, w, h] of irisInputs) {
    iris.push({ landmarks, width: w, height: h, out: computeIrisOffset(toLandmarks(landmarks), w, h) });
  }

  const faceScale: unknown[] = [];
  const scaleInputs: [SparseLandmarks, number][] = [
    [{ length: 264, fill: [0, 0, 0], set: { 33: [0.4, 0.5, 0], 263: [0.6, 0.5, 0] } }, 640],
    [{ length: 0, fill: null, set: {} }, 640],
    [{ length: 100, fill: [0, 0, 0], set: {} }, 640],
  ];
  for (let i = 0; i < 300; i++) scaleInputs.push([randomFace(), pick([640, 360, 1280, 1])]);
  for (const [landmarks, w] of scaleInputs) {
    faceScale.push({ landmarks, width: w, out: computeFaceScale(toLandmarks(landmarks), w) });
  }

  const faceCenter: unknown[] = [];
  const centerInputs: SparseLandmarks[] = [
    { length: 2, fill: null, set: { 0: [0, 0, 0], 1: [1, 1, 0] } },
    { length: 0, fill: null, set: {} },
  ];
  for (let i = 0; i < 60; i++) centerInputs.push(denseLandmarks(pick([1, 5, 478])));
  for (const landmarks of centerInputs) faceCenter.push({ landmarks, out: computeFaceCenter(toLandmarks(landmarks)) });

  const primary: unknown[] = [];
  const faceA = { center: { cx: 0.2, cy: 0.5 }, scale: 0.05 };
  const faceB = { center: { cx: 0.7, cy: 0.5 }, scale: 0.09 };
  const primaryInputs: [typeof faceA[], { cx: number; cy: number } | null][] = [
    [[faceA, faceB], { cx: 0.75, cy: 0.5 }],
    [[faceA, faceB], { cx: 0.15, cy: 0.5 }],
    [[faceA, faceB], null],
    [[], null],
    [[faceA], null],
    [[faceA, { ...faceA }], null], // equal scale: first wins
    [[faceA, { ...faceA }], { cx: 0.2, cy: 0.5 }], // equal distance: first wins
  ];
  for (let i = 0; i < 200; i++) {
    const n = int(0, 4);
    const faces = Array.from({ length: n }, () => ({ center: { cx: rand(), cy: rand() }, scale: pick([rand() * 0.2, 0.05]) }));
    primaryInputs.push([faces, rand() < 0.5 ? null : { cx: rand(), cy: rand() }]);
  }
  for (const [faces, baseline] of primaryInputs) primary.push({ faces, baseline, out: selectPrimaryFace(faces, baseline) });

  const palm: unknown[] = [];
  const palmInputs: SparseLandmarks[] = [
    { length: 21, fill: [0, 0, 0], set: { 0: [0.5, 0.5, 0], 5: [0.5, 0.5, 0], 9: [0.5, 0.5, 0], 13: [0.5, 0.5, 0], 17: [0.5, 0.5, 0] } },
    { length: 10, fill: [0, 0, 0], set: {} },
  ];
  for (let i = 0; i < 200; i++) palmInputs.push(denseLandmarks(21));
  for (const landmarks of palmInputs) palm.push({ landmarks, out: computePalmCentroid(toLandmarks(landmarks)) });

  const twoHands: unknown[] = [];
  const pairs: [number, number][] = [[0.2, 0.7], [0.7, 0.2], [0.5, 0.5]];
  for (let i = 0; i < 100; i++) pairs.push([rand(), rand()]);
  for (const [a, b] of pairs) {
    const ha = { cx: a, id: 0 };
    const hb = { cx: b, id: 1 };
    const out = assignTwoHandSides([ha, hb]);
    twoHands.push({ cx: [a, b], rh: out.rh.id, lh: out.lh.id });
  }

  const handLabel: unknown[] = [];
  for (const label of ["Left", "Right"] as const) {
    for (const inverted of [true, false]) {
      handLabel.push({ label, inverted, out: resolveHandSideFromLabel(label, inverted) });
    }
  }

  write("math.json", { headPose, iris, faceScale, faceCenter, primary, palm, twoHands, handLabel });
}

// ===============================================================
// stats.ts and framing.ts
// ===============================================================

function randomList(maxLen: number, lo: number, hi: number): number[] {
  return Array.from({ length: int(0, maxLen) }, () => (rand() < 0.1 ? pick(EDGE_NUMBERS) : between(lo, hi)));
}

function statsGoldens() {
  const lists: number[][] = [
    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], [5, 1, 3], [42], [], [3, 1, 2], [1, 2, 3, 4], [5, 5, 5], [0, 10], [1, 2, 3],
    [-0, 0], [0, -0], [2, 2, 1, 1],
  ];
  for (let i = 0; i < 400; i++) lists.push(randomList(40, -200, 200));
  const percentile = lists.map((values) => ({ values, out: percentile90(values) }));
  const med = lists.map((values) => ({ values, out: median(values) }));
  const mad = lists.map((values) => {
    const center = rand() < 0.3 ? 5 : between(-50, 50);
    return { values, center, out: meanAbsoluteDeviation(values, center) };
  });
  const clampCases: unknown[] = [[5, 0, 10], [-1, 0, 10], [11, 0, 10], [-0, 0, 1], [0, -0, 1]].map(([v, lo, hi]) => ({
    v, lo, hi, out: clamp(v as number, lo as number, hi as number),
  }));
  for (let i = 0; i < 200; i++) {
    const [v, lo, hi] = [between(-5, 5), between(-3, 0), between(0, 3)];
    clampCases.push({ v, lo, hi, out: clamp(v, lo, hi) });
  }
  write("stats.json", { percentile90: percentile, median: med, meanAbsoluteDeviation: mad, clamp: clampCases });
}

function framingGoldens() {
  const flags: boolean[][] = [
    [true, true, false, false], [],
    [...Array(16).fill(true), ...Array(4).fill(false)],
    [...Array(15).fill(true), ...Array(5).fill(false)],
    [true, true, true, false, false], [true, true, false, false, false],
  ];
  for (let i = 0; i < 300; i++) flags.push(Array.from({ length: int(0, 25) }, () => rand() < 0.7));
  const ratio = flags.map((f) => ({ flags: f, out: ratioTrue(f) }));
  const faceVisible = flags.map((f) => ({ flags: f, out: faceVisiblePasses(f) }));
  const handsRaised = flags.map((f) => ({ flags: f, out: handsRaisedPasses(f) }));

  const scales: number[][] = [
    [config.DISTANCE_SCALE_MIN], [config.DISTANCE_SCALE_MAX], [(config.DISTANCE_SCALE_MIN + config.DISTANCE_SCALE_MAX) / 2],
    [config.DISTANCE_SCALE_MAX + 0.01], [config.DISTANCE_SCALE_MIN - 0.01], [], [0.09, 0.09, 0.09, 0.09, 0.3],
  ];
  for (let i = 0; i < 300; i++) scales.push(Array.from({ length: int(0, 20) }, () => between(0, 0.25)));
  const distance = scales.map((s) => ({ scales: s, out: classifyDistance(s) }));

  const lightingInputs: [number, number | null][] = [
    [150, 140], [config.LIGHTING_DIM_LUMA - 1, null], [200, 100], [config.LIGHTING_DIM_LUMA - 1, 1], [150, null],
    [config.LIGHTING_DIM_LUMA, null], [100, 60], [100, 59.999],
  ];
  for (let i = 0; i < 300; i++) lightingInputs.push([between(0, 255), rand() < 0.2 ? null : between(0, 255)]);
  const lighting = lightingInputs.map(([mean, face]) => ({ mean, face, out: classifyLighting(mean, face) }));

  write("framing.json", { ratioTrue: ratio, faceVisible, handsRaised, distance, lighting });
}

// ===============================================================
// scheduler.ts: replayable operation logs
// ===============================================================

type Op =
  | { op: "shouldTick"; now: number; out: boolean }
  | { op: "planHands"; out: boolean }
  | { op: "recordTick"; now: number; inferMs: number; handsRan: boolean; out: unknown }
  | { op: "state"; out: { mode: string; disabled: boolean; fps: number } };

class Recorder {
  readonly ops: Op[] = [];
  constructor(readonly s = new AdaptiveScheduler()) {}
  shouldTick(now: number): boolean {
    const out = this.s.shouldTick(now);
    this.ops.push({ op: "shouldTick", now, out });
    return out;
  }
  planHands(): boolean {
    const out = this.s.planHands();
    this.ops.push({ op: "planHands", out });
    return out;
  }
  recordTick(now: number, inferMs: number, handsRan: boolean) {
    const out = this.s.recordTick(now, inferMs, handsRan);
    this.ops.push({ op: "recordTick", now, inferMs, handsRan, out });
    return out;
  }
  state(): void {
    this.ops.push({ op: "state", out: { mode: this.s.currentHandsMode, disabled: this.s.isDisabled, fps: this.s.currentEffectiveFps } });
  }
}

/** The web test's run(): fixed interval and latency. */
function runFixed(r: Recorder, count: number, intervalMs: number, inferMsFor: (i: number) => number, startMs = 0): number {
  let now = startMs;
  for (let i = 0; i < count; i++) {
    const handsRan = r.planHands();
    r.recordTick(now, inferMsFor(i), handsRan);
    r.state();
    now += intervalMs;
  }
  return now;
}

function schedulerGoldens() {
  const scenarios: { name: string; ops: Op[] }[] = [];
  const add = (name: string, build: (r: Recorder) => void) => {
    const r = new Recorder();
    build(r);
    r.state();
    scenarios.push({ name, ops: r.ops });
  };
  const { MIN_INTERVAL_MS, P90_WINDOW, REDUCE_HANDS_P90_MS, DISABLE_HANDS_P90_MS, DISABLE_ALL_SUSTAINED_S } = config;

  // Every scenario from web/features/video-analysis/__tests__/scheduler.test.ts.
  add("rate limiting", (r) => {
    r.shouldTick(0);
    r.recordTick(0, 20, true);
    r.shouldTick(MIN_INTERVAL_MS - 1);
    r.shouldTick(MIN_INTERVAL_MS);
  });
  add("fast device stays full", (r) => void runFixed(r, P90_WINDOW * 3, MIN_INTERVAL_MS, () => 30));
  add("hands every tick in full", (r) => {
    for (let i = 0; i < 5; i++) {
      const h = r.planHands();
      r.recordTick(i * MIN_INTERVAL_MS, 20, h);
    }
  });
  add("downgrade to reduced", (r) => void runFixed(r, P90_WINDOW, MIN_INTERVAL_MS, () => REDUCE_HANDS_P90_MS + 10));
  add("downgrade to off", (r) => void runFixed(r, P90_WINDOW, MIN_INTERVAL_MS, () => DISABLE_HANDS_P90_MS + 10));
  add("reduced alternates", (r) => {
    runFixed(r, P90_WINDOW, MIN_INTERVAL_MS, () => REDUCE_HANDS_P90_MS + 10);
    let now = P90_WINDOW * MIN_INTERVAL_MS;
    for (let i = 0; i < 6; i++) {
      const h = r.planHands();
      r.recordTick(now, 20, h);
      now += MIN_INTERVAL_MS;
    }
  });
  add("never upgrades", (r) => {
    const end = runFixed(r, P90_WINDOW, MIN_INTERVAL_MS, () => REDUCE_HANDS_P90_MS + 10);
    runFixed(r, P90_WINDOW * 2, MIN_INTERVAL_MS, () => 5, end);
  });
  add("window not yet full", (r) => void runFixed(r, P90_WINDOW - 1, MIN_INTERVAL_MS, () => DISABLE_HANDS_P90_MS + 100));
  add("brief dip", (r) => {
    r.recordTick(0, 20, true);
    runFixed(r, 20, MIN_INTERVAL_MS, () => 20, 2000);
  });
  add("sustained low fps disables", (r) => {
    let now = 0;
    for (let i = 0; i < DISABLE_ALL_SUSTAINED_S + 2; i++) {
      r.recordTick(now, 20, false);
      r.state();
      now += 1000;
    }
    r.shouldTick(now);
  });

  // Random ticking loops like the real one: shouldTick() gates each
  // candidate frame, latency drifts through regimes.
  for (let n = 0; n < 60; n++) {
    add(`random ${n}`, (r) => {
      let now = between(0, 5000);
      let base = pick([20, 50, 70, 90, 120, 170, 250]);
      for (let i = 0; i < int(50, 400); i++) {
        now += pick([16.667, 33.333, 50, 100, 250, 400, 1000, between(1, 1500)]);
        if (rand() < 0.02) base = pick([20, 50, 90, 170, 250]);
        if (!r.shouldTick(now)) continue;
        const h = r.planHands();
        r.recordTick(now, Math.max(0, base + between(-30, 30)), h);
        if (rand() < 0.2) r.state();
      }
    });
  }

  write("scheduler.json", { scenarios });
}

// ===============================================================
// track.ts: op logs -> JSON.stringify(build(...)), byte for byte
// ===============================================================

const manifest = JSON.parse(readFileSync(join(WEB, "public", "mediapipe", "manifest.json"), "utf-8")) as {
  runtime_version: string;
  models: RawManifestModel[];
};

function sample(overrides: Partial<FrameSample>): FrameSample {
  return { ...EMPTY_SAMPLE, ...overrides };
}

type TrackOp =
  | { op: "append"; t: number; sample: FrameSample; out: boolean }
  | { op: "appendEmpty"; t: number; out: boolean }
  | { op: "openGap"; t: number; reason: string }
  | { op: "closeGap"; t: number }
  | { op: "degradation"; value: { t: number; face_fps: number; hands_fps: number; reason: string } }
  | { op: "state"; out: { frameCount: number; hasOpenGap: boolean; lastT: number | null } };

function buildParams(overrides: { durationS?: number; platform?: string } = {}) {
  return {
    sessionId: "s-test",
    source: {
      platform: (overrides.platform ?? "web") as "web",
      client_version: "test",
      user_agent_family: "chrome" as const,
      runtime: { name: "mediapipe-tasks-vision", version: "1.0.1", delegate: "GPU" as const },
      models: [],
      device_tier: "full" as const,
      benchmark_fps: 10,
    },
    capture: { frame_width: 640, frame_height: 360, input_mirrored: false, handedness_convention: "anatomical" as const, target_fps: 10 },
    clockUncertaintyMs: 150,
    durationS: overrides.durationS ?? 10,
    calibration: { performed: false, baseline: null, samples: 0, stability: 0, right_hand_check: "skipped" as const },
    context: { setting: "camera_audience" as const, uses_notes: false },
    setupCheck: { face_visible: true, hands_visible_when_raised: true, lighting: "ok" as const, distance: "ok" as const },
  };
}

function trackGoldens() {
  const scenarios: { name: string; ops: TrackOp[]; params: unknown; json: string }[] = [];

  function scenario(name: string, params: ReturnType<typeof buildParams> | Record<string, unknown>, run: (b: TrackBuilder, ops: TrackOp[]) => void) {
    const b = new TrackBuilder();
    const ops: TrackOp[] = [];
    run(b, ops);
    ops.push({ op: "state", out: { frameCount: b.frameCount, hasOpenGap: b.hasOpenGap, lastT: b.lastAppendedT } });
    const json = JSON.stringify(b.build(params as Parameters<TrackBuilder["build"]>[0]));
    scenarios.push({ name, ops, params, json });
  }

  const append = (b: TrackBuilder, ops: TrackOp[], t: number, s: FrameSample) => ops.push({ op: "append", t, sample: s, out: b.appendSample(t, s) });
  const empty = (b: TrackBuilder, ops: TrackOp[], t: number) => ops.push({ op: "appendEmpty", t, out: b.appendEmpty(t) });
  const open = (b: TrackBuilder, ops: TrackOp[], t: number, reason: string) => {
    b.openGapAt(t, reason as never);
    ops.push({ op: "openGap", t, reason });
  };
  const close = (b: TrackBuilder, ops: TrackOp[], t: number) => {
    b.closeGapAt(t);
    ops.push({ op: "closeGap", t });
  };
  const degrade = (b: TrackBuilder, ops: TrackOp[], value: { t: number; face_fps: number; hands_fps: number; reason: string }) => {
    b.pushDegradation(value as never);
    ops.push({ op: "degradation", value });
  };

  // Every scenario from track.test.ts.
  scenario("drops t < 0", buildParams(), (b, o) => append(b, o, -0.01, sample({})));
  scenario("accepts t === 0", buildParams(), (b, o) => append(b, o, 0, sample({})));
  scenario("strictly increasing", buildParams(), (b, o) => {
    append(b, o, 1.0, sample({}));
    append(b, o, 1.0, sample({}));
    append(b, o, 0.5, sample({}));
    append(b, o, 1.1, sample({}));
  });
  scenario("mixed appends", buildParams(), (b, o) => {
    append(b, o, 0.1, sample({ face_count: 1, head_yaw: 3.456, lh_present: 1, lh_cx: 0.31 }));
    empty(b, o, 0.2);
    append(b, o, 0.3, sample({ face_count: 0 }));
  });
  scenario("nulls preserved", buildParams(), (b, o) => empty(b, o, 0.1));
  scenario("rounding", buildParams(), (b, o) =>
    append(b, o, 0.123456, sample({
      head_yaw: 12.3456, head_pitch: -7.891, head_roll: 0.049, iris_x: 0.12345, iris_y: -0.5, face_scale: 0.081234,
      face_cx: 0.512345, face_cy: 0.399999, lh_present: 1, lh_score: 0.94321, lh_cx: 0.31049, lh_cy: 0.72001, infer_ms: 38.7,
    })));
  scenario("integer columns", buildParams(), (b, o) => append(b, o, 0.1, sample({ face_count: 2, lh_present: 0, rh_present: 1 })));
  scenario("gap closed", buildParams(), (b, o) => {
    open(b, o, 5.0, "tab_hidden");
    close(b, o, 8.5);
  });
  scenario("gap auto-closed", buildParams({ durationS: 12.0 }), (b, o) => open(b, o, 2.0, "camera_interrupted"));
  scenario("second open ignored", buildParams(), (b, o) => {
    open(b, o, 1.0, "tab_hidden");
    open(b, o, 1.5, "model_error");
    close(b, o, 2.0);
  });
  scenario("degradations", buildParams(), (b, o) => {
    degrade(b, o, { t: 4.0, face_fps: 5, hands_fps: 2, reason: "p90_latency" });
    degrade(b, o, { t: 9.0, face_fps: 2, hands_fps: 0, reason: "thermal_suspected" });
  });

  // The cross-language fixture scenario, with the real manifest.
  const fixtureParams = {
    sessionId: "11111111-1111-4111-8111-111111111111",
    source: {
      platform: "web",
      client_version: "test-fixture",
      user_agent_family: "chrome",
      runtime: { name: "mediapipe-tasks-vision", version: manifest.runtime_version, delegate: "GPU" },
      models: toModelProvenance(manifest.models),
      device_tier: "full",
      benchmark_fps: 11.5,
    },
    capture: { frame_width: 640, frame_height: 360, input_mirrored: false, handedness_convention: "anatomical", target_fps: 10 },
    clockUncertaintyMs: 150,
    durationS: 2.2,
    calibration: { performed: true, baseline: { head_yaw: 1.8, head_pitch: -2.5, iris_x: 0.02, iris_y: -0.01 }, samples: 28, stability: 0.91, right_hand_check: "passed" },
    context: { setting: "camera_audience", uses_notes: false },
    setupCheck: { face_visible: true, hands_visible_when_raised: true, lighting: "ok", distance: "ok" },
  };
  scenario("cross-language fixture", fixtureParams, (b, o) => {
    for (let i = 0; i < 10; i++) {
      append(b, o, 0.1 + i * 0.1, sample({
        face_count: 1, head_yaw: 2.0 + i * 0.1, head_pitch: -3.0, head_roll: 0.5, iris_x: 0.05, iris_y: -0.02, face_scale: 0.09,
        face_cx: 0.5, face_cy: 0.4, lh_present: 1, lh_score: 0.9, lh_cx: 0.32, lh_cy: 0.7, rh_present: 1, rh_score: 0.88,
        rh_cx: 0.68, rh_cy: 0.71, infer_ms: 35 + i,
      }));
    }
    empty(b, o, 1.2);
    empty(b, o, 1.3);
    open(b, o, 1.4, "tab_hidden");
    close(b, o, 2.0);
    append(b, o, 2.1, sample({ face_count: 1, head_yaw: -1.0, head_pitch: 4.0, head_roll: -0.2, face_scale: 0.085, face_cx: 0.48, face_cy: 0.41, infer_ms: 42 }));
    degrade(b, o, { t: 2.1, face_fps: 7, hands_fps: 3, reason: "p90_latency" });
  });

  // Random recordings: realistic value ranges, edge numbers mixed in,
  // gaps and degradations, both platforms.
  const gapReasons = ["tab_hidden", "perf_disabled", "model_error", "camera_interrupted"];
  const degradeReasons = ["p90_latency", "thermal_suspected", "manual"];
  const value = (lo: number, hi: number) => (rand() < 0.15 ? pick(EDGE_NUMBERS) : rand() < 0.1 ? null : between(lo, hi));
  for (let n = 0; n < 40; n++) {
    const duration = between(1, 120);
    const params = {
      ...buildParams({ durationS: duration, platform: n % 2 ? "android" : "web" }),
      calibration: rand() < 0.5
        ? { performed: true, baseline: { head_yaw: between(-10, 10), head_pitch: between(-10, 10), iris_x: between(-1, 1), iris_y: between(-1, 1) }, samples: int(15, 30), stability: rand(), right_hand_check: pick(["passed", "failed", "skipped"]) }
        : { performed: false, baseline: null, samples: int(0, 14), stability: 0, right_hand_check: "skipped" },
    };
    scenario(`random ${n}`, params, (b, o) => {
      let t = between(-0.3, 0.2);
      for (let i = 0; i < int(0, 300); i++) {
        t += pick([0.1, 0.1, 0.1, 0.2, 0.0, -0.05, between(0.09, 0.35)]);
        const r = rand();
        if (r < 0.1) empty(b, o, t);
        else if (r < 0.13) open(b, o, t, pick(gapReasons));
        else if (r < 0.16) close(b, o, t);
        else if (r < 0.18) degrade(b, o, { t, face_fps: int(0, 12), hands_fps: int(0, 12), reason: pick(degradeReasons) });
        else {
          const handsRan = rand() < 0.7;
          const lhOn = handsRan && rand() < 0.6;
          const rhOn = handsRan && rand() < 0.6;
          append(b, o, t, sample({
            face_count: pick([0, 1, 1, 1, 2]),
            head_yaw: value(-60, 60), head_pitch: value(-40, 40), head_roll: value(-30, 30),
            iris_x: value(-1.5, 1.5), iris_y: value(-1.5, 1.5),
            face_scale: value(0, 0.3), face_cx: value(0, 1), face_cy: value(0, 1),
            lh_present: handsRan ? (lhOn ? 1 : 0) : null, lh_score: lhOn ? value(0, 1) : null, lh_cx: lhOn ? value(0, 1) : null, lh_cy: lhOn ? value(0, 1) : null,
            rh_present: handsRan ? (rhOn ? 1 : 0) : null, rh_score: rhOn ? value(0, 1) : null, rh_cx: rhOn ? value(0, 1) : null, rh_cy: rhOn ? value(0, 1) : null,
            infer_ms: value(0, 300),
          }));
        }
      }
    });
  }

  write("track.json", { scenarios });
}

// ===============================================================
// The per-frame glue in useVisualCapture.ts (processTick, the
// benchmark tier, calibration, lighting), composed from the real
// exported functions exactly as the hook composes them. The hook
// itself can't be imported (React, DOM, MediaPipe), so these few
// lines are transcribed verbatim; every number still comes from the
// web module's own functions.
// ===============================================================

interface DetectedFace { landmarks: SparseLandmarks; transformMatrix: number[] | null }
interface DetectedHand { landmarks: SparseLandmarks; handednessLabel: "Left" | "Right"; handednessScore: number }

function processFrame(faces: DetectedFace[], hands: DetectedHand[], baseline: { cx: number; cy: number } | null, inverted: boolean, runHands: boolean, inferMs: number) {
  const W = config.SIGNAL_FRAME_WIDTH;
  const H = config.SIGNAL_FRAME_HEIGHT;
  const lm = faces.map((f) => toLandmarks(f.landmarks));

  // --- processTick(): Face ---
  const faceCandidates = lm.map((l) => ({
    center: computeFaceCenter(l) ?? { cx: 0.5, cy: 0.5 },
    scale: computeFaceScale(l, W) ?? 0,
  }));
  const primaryIndex = faces.length > 0 ? selectPrimaryFace(faceCandidates, baseline) : -1;
  const primaryFace = primaryIndex >= 0 ? faces[primaryIndex] : null;
  const primaryLm = primaryIndex >= 0 ? lm[primaryIndex] : null;
  const headPose = primaryFace?.transformMatrix != null ? headPoseFromMatrix(primaryFace.transformMatrix) : null;
  const iris = primaryLm ? computeIrisOffset(primaryLm, W, H) : null;
  const faceScale = primaryLm ? computeFaceScale(primaryLm, W) : null;
  const faceCenter = primaryLm ? computeFaceCenter(primaryLm) : null;

  // --- processTick(): Hands ---
  let lh: { cx: number; cy: number; score: number } | null = null;
  let rh: { cx: number; cy: number; score: number } | null = null;
  if (hands.length === 2) {
    const centroids = hands.map((h) => ({ ...(computePalmCentroid(toLandmarks(h.landmarks)) ?? { cx: 0.5, cy: 0.5 }), score: h.handednessScore }));
    const assigned = centroids[0].cx <= centroids[1].cx ? { rh: centroids[0], lh: centroids[1] } : { rh: centroids[1], lh: centroids[0] };
    lh = assigned.lh;
    rh = assigned.rh;
  } else if (hands.length === 1) {
    const hand = hands[0];
    const centroid = computePalmCentroid(toLandmarks(hand.landmarks));
    if (centroid) {
      const side = resolveHandSideFromLabel(hand.handednessLabel, inverted);
      const v = { ...centroid, score: hand.handednessScore };
      if (side === "rh") rh = v;
      else lh = v;
    }
  }

  // --- processTick(): the sample appended while recording ---
  const out: FrameSample = {
    face_count: faces.length,
    head_yaw: headPose?.yaw ?? null,
    head_pitch: headPose?.pitch ?? null,
    head_roll: headPose?.roll ?? null,
    iris_x: iris?.x ?? null,
    iris_y: iris?.y ?? null,
    face_scale: faceScale,
    face_cx: faceCenter?.cx ?? null,
    face_cy: faceCenter?.cy ?? null,
    lh_present: runHands ? (lh ? 1 : 0) : null,
    lh_score: lh?.score ?? null,
    lh_cx: lh?.cx ?? null,
    lh_cy: lh?.cy ?? null,
    rh_present: runHands ? (rh ? 1 : 0) : null,
    rh_score: rh?.score ?? null,
    rh_cx: rh?.cx ?? null,
    rh_cy: rh?.cy ?? null,
    infer_ms: inferMs,
  };
  expect(Object.keys(out)).toEqual([...FRAME_COLUMNS]);
  return { sample: out, bothHands: lh !== null && rh !== null, rightHand: rh !== null, faceVisible: faces.length > 0 };
}

function randomHand(): DetectedHand {
  return { landmarks: denseLandmarks(21), handednessLabel: pick(["Left", "Right"] as const), handednessScore: rand() };
}

function compositionGoldens() {
  const frames: unknown[] = [];
  for (let i = 0; i < 400; i++) {
    const faces: DetectedFace[] = Array.from({ length: pick([0, 1, 1, 1, 2]) }, () => ({
      landmarks: randomFace(),
      transformMatrix: rand() < 0.9 ? buildMatrixData(between(-60, 60), between(-40, 40), between(-30, 30)) : null,
    }));
    const hands: DetectedHand[] = Array.from({ length: pick([0, 1, 2, 2]) }, randomHand);
    if (hands.length === 1 && rand() < 0.1) hands[0].landmarks = { length: 10, fill: [0, 0, 0], set: {} }; // palm missing
    const baseline = rand() < 0.5 ? null : { cx: rand(), cy: rand() };
    const inverted = rand() < 0.7;
    const runHands = rand() < 0.8;
    const inferMs = between(0, 200);
    frames.push({ faces, hands: runHands ? hands : [], baseline, inverted, runHands, inferMs, out: processFrame(faces, runHands ? hands : [], baseline, inverted, runHands, inferMs) });
  }

  // runBenchmark(): fps and p90 -> tier, benchmark_fps rounding.
  const tiers: unknown[] = [];
  const tierInputs: [number, number[]][] = [
    [27, [30, 40, 50]], [30, [90, 90, 90]], [18, []], [15, [200]], [14, [20]], [0, []], [26, [80]], [27, [80.0001]],
  ];
  for (let i = 0; i < 200; i++) tierInputs.push([int(0, 40), Array.from({ length: int(0, 40) }, () => between(10, 200))]);
  for (const [ticks, latencies] of tierInputs) {
    const fps = ticks / config.BENCHMARK_DURATION_S;
    const p90 = percentile90(latencies);
    const p90Ok = Number.isNaN(p90) || p90 <= config.TIER_FULL_MAX_P90_MS;
    let tier: string;
    if (fps >= config.TIER_FULL_MIN_FPS && p90Ok) tier = "full";
    else if (fps >= config.TIER_REDUCED_MIN_FPS) tier = "reduced";
    else if (fps >= config.TIER_FACE_ONLY_MIN_FPS) tier = "face_only";
    else tier = "too_slow";
    tiers.push({ ticks, latencies, tier, benchmarkFps: Math.round(fps * 10) / 10 });
  }

  // runGazeCalibration(): samples -> baseline, stability.
  const calibrations: unknown[] = [];
  for (let i = 0; i < 150; i++) {
    const n = int(0, 40);
    const yaw = Array.from({ length: n }, () => between(-20, 20));
    const pitch = Array.from({ length: n }, () => between(-20, 20));
    const irisX = Array.from({ length: n }, () => between(-1.5, 1.5));
    const irisY = Array.from({ length: n }, () => between(-1.5, 1.5));
    const cx = Array.from({ length: rand() < 0.1 ? 0 : n }, () => rand());
    const cy = cx.map(() => rand());
    let out: unknown;
    if (yaw.length < config.CALIBRATION_MIN_SAMPLES) {
      out = { performed: false, samples: yaw.length };
    } else {
      const baseline = { head_yaw: median(yaw), head_pitch: median(pitch), iris_x: median(irisX), iris_y: median(irisY) };
      const mad = meanAbsoluteDeviation(yaw, baseline.head_yaw);
      const stability = 1 - clamp(mad / config.CALIBRATION_STABILITY_YAW_NORM_DEG, 0, 1);
      out = { performed: true, baseline, samples: yaw.length, stability, faceCenter: cx.length > 0 ? { cx: median(cx), cy: median(cy) } : null };
    }
    calibrations.push({ yaw, pitch, irisX, irisY, cx, cy, out });
  }

  // runRightHandCheck(): window ratio -> passed/failed.
  const rightHand = Array.from({ length: 100 }, () => {
    const flags = Array.from({ length: int(0, 25) }, () => rand() < 0.6);
    return { flags, out: ratioTrue(flags) >= config.RIGHT_HAND_CHECK_MIN_RATIO ? "passed" : "failed" };
  });

  // sampleLighting(): a 64x36 RGBA frame -> meanLuma, faceLuma.
  const lighting: unknown[] = [];
  for (let n = 0; n < 30; n++) {
    const width = 64, height = 36;
    const bright = between(0, 255), faceBright = between(0, 255);
    const data: number[] = [];
    const fx0 = Math.floor(width * 0.35), fx1 = Math.ceil(width * 0.65), fy0 = Math.floor(height * 0.2), fy1 = Math.ceil(height * 0.7);
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
      const inFace = x >= fx0 && x < fx1 && y >= fy0 && y < fy1;
      const b = inFace ? faceBright : bright;
      data.push(clamp(Math.round(b + between(-40, 40)), 0, 255), clamp(Math.round(b + between(-40, 40)), 0, 255), clamp(Math.round(b + between(-40, 40)), 0, 255), 255);
    }
    let sum = 0, faceSum = 0, faceN = 0;
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;
      const luma = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
      sum += luma;
      if (x >= fx0 && x < fx1 && y >= fy0 && y < fy1) {
        faceSum += luma;
        faceN += 1;
      }
    }
    const meanLuma = sum / (width * height);
    const faceLuma = faceN > 0 ? faceSum / faceN : null;
    lighting.push({ width, height, rgba: data, meanLuma, faceLuma, out: classifyLighting(meanLuma, faceLuma) });
  }

  write("composition.json", { frames, tiers, calibrations, rightHand, lighting });
}

// ===============================================================
// config.ts: every constant, so a drifted Kotlin constant fails.
// ===============================================================

function configGoldens() {
  const values = Object.fromEntries(Object.entries(config).filter(([, v]) => typeof v === "number" || typeof v === "boolean" || Array.isArray(v)));
  write("config.json", { values, manifest: { runtime_version: manifest.runtime_version, models: toModelProvenance(manifest.models) } });
}

it("writes the golden vectors from the website's own modules", () => {
  mathGoldens();
  statsGoldens();
  framingGoldens();
  schedulerGoldens();
  trackGoldens();
  compositionGoldens();
  configGoldens();
});
