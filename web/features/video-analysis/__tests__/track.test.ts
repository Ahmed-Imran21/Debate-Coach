import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { type RawManifestModel, toModelProvenance } from "../extractor";
import { TrackBuilder } from "../track";
import { EMPTY_SAMPLE, FRAME_COLUMNS, type FrameSample } from "../types";

// The real file the browser fetches, not a hand-typed stand-in —
// see the "cross-language fixture" describe block below.
import manifest from "../../../public/mediapipe/manifest.json";

const __dirname = dirname(fileURLToPath(import.meta.url));

function sample(overrides: Partial<FrameSample>): FrameSample {
  return { ...EMPTY_SAMPLE, ...overrides };
}

describe("TrackBuilder — sample acceptance", () => {
  it("drops samples with t < 0", () => {
    const b = new TrackBuilder();
    expect(b.appendSample(-0.01, sample({}))).toBe(false);
    expect(b.frameCount).toBe(0);
  });

  it("accepts t === 0", () => {
    const b = new TrackBuilder();
    expect(b.appendSample(0, sample({}))).toBe(true);
    expect(b.frameCount).toBe(1);
  });

  it("enforces strictly increasing t, dropping equal or earlier samples", () => {
    const b = new TrackBuilder();
    expect(b.appendSample(1.0, sample({}))).toBe(true);
    expect(b.appendSample(1.0, sample({}))).toBe(false); // equal
    expect(b.appendSample(0.5, sample({}))).toBe(false); // earlier
    expect(b.appendSample(1.1, sample({}))).toBe(true);
    expect(b.frameCount).toBe(2);
  });
});

describe("TrackBuilder — column integrity", () => {
  it("every column has the same length as t after mixed appends", () => {
    const b = new TrackBuilder();
    b.appendSample(0.1, sample({ face_count: 1, head_yaw: 3.456, lh_present: 1, lh_cx: 0.31 }));
    b.appendEmpty(0.2);
    b.appendSample(0.3, sample({ face_count: 0 }));

    const built = b.build(minimalBuildParams());

    expect(built.frames.t).toHaveLength(3);
    for (const key of FRAME_COLUMNS) {
      expect(built.frames[key]).toHaveLength(3);
    }
  });

  it("nulls are preserved, never coerced to 0", () => {
    const b = new TrackBuilder();
    b.appendEmpty(0.1);
    const built = b.build(minimalBuildParams());

    expect(built.frames.head_yaw[0]).toBeNull();
    expect(built.frames.face_count[0]).toBeNull();
    expect(built.frames.lh_cx[0]).toBeNull();
  });

  it("rounds each column to its documented precision", () => {
    const b = new TrackBuilder();
    b.appendSample(0.123456, sample({
      head_yaw: 12.3456,
      head_pitch: -7.891,
      head_roll: 0.049, // rounds to 0.0
      iris_x: 0.12345,
      iris_y: -0.5,
      face_scale: 0.081234,
      face_cx: 0.512345,
      face_cy: 0.399999,
      lh_present: 1,
      lh_score: 0.94321,
      lh_cx: 0.31049,
      lh_cy: 0.72001,
      infer_ms: 38.7,
    }));
    const built = b.build(minimalBuildParams());
    const f = built.frames;

    expect(f.t[0]).toBeCloseTo(0.123, 3);
    expect(f.head_yaw[0]).toBe(12.3);
    expect(f.head_pitch[0]).toBe(-7.9);
    expect(f.head_roll[0]).toBe(0.0);
    expect(f.iris_x[0]).toBe(0.12);
    expect(f.iris_y[0]).toBe(-0.5);
    expect(f.face_scale[0]).toBe(0.081);
    expect(f.face_cx[0]).toBe(0.512);
    expect(f.face_cy[0]).toBe(0.4);
    expect(f.lh_score[0]).toBe(0.94);
    expect(f.lh_cx[0]).toBe(0.31);
    expect(f.lh_cy[0]).toBe(0.72);
    expect(f.infer_ms[0]).toBe(39);
  });

  it("integer columns (presence, face_count) are not rounded/altered", () => {
    const b = new TrackBuilder();
    b.appendSample(0.1, sample({ face_count: 2, lh_present: 0, rh_present: 1 }));
    const built = b.build(minimalBuildParams());
    expect(built.frames.face_count[0]).toBe(2);
    expect(built.frames.lh_present[0]).toBe(0);
    expect(built.frames.rh_present[0]).toBe(1);
  });
});

describe("TrackBuilder — gaps and degradations", () => {
  it("closes a gap when told to, recording start/end/reason", () => {
    const b = new TrackBuilder();
    b.openGapAt(5.0, "tab_hidden");
    expect(b.hasOpenGap).toBe(true);
    b.closeGapAt(8.5);
    expect(b.hasOpenGap).toBe(false);

    const built = b.build(minimalBuildParams());
    expect(built.gaps).toEqual([{ start: 5.0, end: 8.5, reason: "tab_hidden" }]);
  });

  it("auto-closes a still-open gap at build() using durationS", () => {
    const b = new TrackBuilder();
    b.openGapAt(2.0, "camera_interrupted");
    const built = b.build(minimalBuildParams({ durationS: 12.0 }));
    expect(built.gaps).toEqual([{ start: 2.0, end: 12.0, reason: "camera_interrupted" }]);
  });

  it("ignores a second openGapAt while one is already open", () => {
    const b = new TrackBuilder();
    b.openGapAt(1.0, "tab_hidden");
    b.openGapAt(1.5, "model_error");
    b.closeGapAt(2.0);
    const built = b.build(minimalBuildParams());
    expect(built.gaps).toEqual([{ start: 1.0, end: 2.0, reason: "tab_hidden" }]);
  });

  it("records degradations verbatim, in push order", () => {
    const b = new TrackBuilder();
    b.pushDegradation({ t: 4.0, face_fps: 5, hands_fps: 2, reason: "p90_latency" });
    b.pushDegradation({ t: 9.0, face_fps: 2, hands_fps: 0, reason: "thermal_suspected" });
    const built = b.build(minimalBuildParams());
    expect(built.degradations).toHaveLength(2);
    expect(built.degradations[1].reason).toBe("thermal_suspected");
  });
});

// ---------------------------------------------------------------
// Cross-language contract fixture
// ---------------------------------------------------------------
//
// This test's real assertion is in Python: tests/visual_analysis/
// test_frontend_fixture.py loads the exact file written here and
// validates it against visual_analysis.schema.VisualSignalTrack +
// visual_analysis.signals.validate_track. Run the frontend suite
// before the backend suite (or just accept the fixture is a day
// stale) when regenerating.

describe("TrackBuilder — cross-language fixture", () => {
  it("builds a realistic track and writes it for the backend contract test", () => {
    // Confirmed bug (2026-09-19): source.models used to be built
    // from manifest.json's entries verbatim, `path` field included.
    // The backend's ModelInfo schema forbids unknown fields, so
    // every real upload failed 422 while this exact fixture test —
    // which had always hand-typed a bare {task, model_id, sha256}
    // object instead of using the real manifest — kept passing.
    // Routing through the real manifest.json and the real
    // toModelProvenance() (extractor.ts) closes that gap: this test
    // now fails if either one drifts out of sync with the backend's
    // strict schema again.
    const b = new TrackBuilder();

    // Face present and roughly centered for the first second.
    for (let i = 0; i < 10; i++) {
      const t = 0.1 + i * 0.1;
      b.appendSample(t, sample({
        face_count: 1,
        head_yaw: 2.0 + i * 0.1,
        head_pitch: -3.0,
        head_roll: 0.5,
        iris_x: 0.05,
        iris_y: -0.02,
        face_scale: 0.09,
        face_cx: 0.5,
        face_cy: 0.4,
        lh_present: 1,
        lh_score: 0.9,
        lh_cx: 0.32,
        lh_cy: 0.7,
        rh_present: 1,
        rh_score: 0.88,
        rh_cx: 0.68,
        rh_cy: 0.71,
        infer_ms: 35 + i,
      }));
    }

    // A stretch with no face at all.
    b.appendEmpty(1.2);
    b.appendEmpty(1.3);

    // A tab-hidden gap.
    b.openGapAt(1.4, "tab_hidden");
    b.closeGapAt(2.0);

    // Face back, hands not run this tick (reduced tier).
    b.appendSample(2.1, sample({
      face_count: 1,
      head_yaw: -1.0,
      head_pitch: 4.0,
      head_roll: -0.2,
      face_scale: 0.085,
      face_cx: 0.48,
      face_cy: 0.41,
      infer_ms: 42,
    }));

    b.pushDegradation({ t: 2.1, face_fps: 7, hands_fps: 3, reason: "p90_latency" });

    const track = b.build({
      sessionId: "11111111-1111-4111-8111-111111111111",
      source: {
        platform: "web",
        client_version: "test-fixture",
        user_agent_family: "chrome",
        runtime: { name: "mediapipe-tasks-vision", version: manifest.runtime_version, delegate: "GPU" },
        // JSON imports widen string literals (task: string, not the
        // "face_landmarker" | "hand_landmarker" union) — asserted
        // back, not loosened; the runtime values are the real ones.
        models: toModelProvenance(manifest.models as RawManifestModel[]),
        device_tier: "full",
        benchmark_fps: 11.5,
      },
      capture: {
        frame_width: 640,
        frame_height: 360,
        input_mirrored: false,
        handedness_convention: "anatomical",
        target_fps: 10,
      },
      clockUncertaintyMs: 150,
      durationS: 2.2,
      calibration: {
        performed: true,
        baseline: { head_yaw: 1.8, head_pitch: -2.5, iris_x: 0.02, iris_y: -0.01 },
        samples: 28,
        stability: 0.91,
        right_hand_check: "passed",
      },
      context: { setting: "camera_audience", uses_notes: false },
      setupCheck: {
        face_visible: true,
        hands_visible_when_raised: true,
        lighting: "ok",
        distance: "ok",
      },
    });

    // Sanity checks in JS before handing off to the backend test.
    expect(track.frames.t).toHaveLength(13);
    expect(track.gaps).toHaveLength(1);
    expect(track.degradations).toHaveLength(1);
    // manifest.json's real entries have 4 keys (task, model_id,
    // sha256, path); the backend accepts exactly 3. Fails here,
    // immediately, if toModelProvenance() (or the manifest shape)
    // ever regresses — rather than 422ing on a real upload again.
    for (const model of track.source.models) {
      expect(Object.keys(model).sort()).toEqual(["model_id", "sha256", "task"]);
    }

    const fixtureDir = join(__dirname, "__fixtures__");
    mkdirSync(fixtureDir, { recursive: true });
    writeFileSync(join(fixtureDir, "sample-track.json"), JSON.stringify(track, null, 2) + "\n", "utf-8");
  });
});

function minimalBuildParams(overrides: { durationS?: number } = {}) {
  return {
    sessionId: "s-test",
    source: {
      platform: "web" as const,
      client_version: "test",
      user_agent_family: "chrome" as const,
      runtime: { name: "mediapipe-tasks-vision", version: "1.0.1", delegate: "GPU" as const },
      models: [],
      device_tier: "full" as const,
      benchmark_fps: 10,
    },
    capture: {
      frame_width: 640,
      frame_height: 360,
      input_mirrored: false,
      handedness_convention: "anatomical" as const,
      target_fps: 10,
    },
    clockUncertaintyMs: 150,
    durationS: overrides.durationS ?? 10,
    calibration: {
      performed: false,
      baseline: null,
      samples: 0,
      stability: 0,
      right_hand_check: "skipped" as const,
    },
    context: { setting: "camera_audience" as const, uses_notes: false },
    setupCheck: {
      face_visible: true,
      hands_visible_when_raised: true,
      lighting: "ok" as const,
      distance: "ok" as const,
    },
  };
}
