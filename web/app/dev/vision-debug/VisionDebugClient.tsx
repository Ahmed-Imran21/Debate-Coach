"use client";

import { useState } from "react";
import type { ReactElement } from "react";

import { useVisualCapture } from "@/features/video-analysis/useVisualCapture";
import type { LiveReading } from "@/features/video-analysis/useVisualCapture";

function fmt(value: number | null | undefined, digits = 2): string {
  return value === null || value === undefined ? "-" : value.toFixed(digits);
}

interface ChecklistItem {
  field: string;
  instruction: string;
  expect: string;
  read: (live: LiveReading | null) => string;
}

// Explicit per-item readers rather than a dynamic key lookup: the
// schema column names (head_yaw, iris_x) don't match HeadPose's own
// property names (yaw) or IrisOffset's (x), so a generic
// live?.[field] indexer would silently read the wrong property.
const CHECKLIST: ChecklistItem[] = [
  {
    field: "head_yaw",
    instruction: "Turn your head to your right",
    expect: "increases",
    read: (live) => fmt(live?.headPose?.yaw),
  },
  {
    field: "head_pitch",
    instruction: "Look up",
    expect: "increases",
    read: (live) => fmt(live?.headPose?.pitch),
  },
  {
    field: "head_roll",
    instruction: "Tilt your head toward your right shoulder",
    expect: "increases",
    read: (live) => fmt(live?.headPose?.roll),
  },
  {
    field: "iris_x",
    instruction: "Keep your head still, look right with your eyes only",
    expect: "increases",
    read: (live) => fmt(live?.iris?.x),
  },
  {
    field: "rh_present",
    instruction: "Raise your right hand",
    expect: "becomes 1",
    read: (live) => String(live?.handsPresent.rh ?? false),
  },
];

export default function VisionDebugClient(): ReactElement {
  const capture = useVisualCapture({ enabled: true, requestAudio: false });
  const [log, setLog] = useState<string[]>([]);

  function note(message: string): void {
    setLog((prev) => [`${new Date().toLocaleTimeString()}  ${message}`, ...prev].slice(0, 20));
  }

  async function start(): Promise<void> {
    const result = await capture.acquireAndStartSetup();
    note(result.ok ? "camera + models ready" : `failed: ${result.reason}`);
  }

  async function benchmark(): Promise<void> {
    const tier = await capture.runBenchmark();
    note(`benchmark tier: ${tier}`);
  }

  async function calibrateGaze(): Promise<void> {
    await capture.runGazeCalibration();
    note(`gaze calibration: performed=${capture.calibration.performed} stability=${fmt(capture.calibration.stability)}`);
  }

  async function calibrateHand(): Promise<void> {
    const result = await capture.runRightHandCheck();
    note(`right-hand check: ${result}`);
  }

  const l = capture.live;

  return (
    <div className="shell">
      <main>
        <section className="block-tight" style={{ paddingTop: "2.5rem" }}>
          <div className="wrap">
            <h1 style={{ fontSize: "var(--step-3)", marginBottom: "0.5rem" }}>Vision debug</h1>
            <p className="note" style={{ marginBottom: "1.5rem" }}>
              Dev-only. Verifies head-pose signs, iris direction and handedness against a
              real camera — see docs/video-analysis/MANUAL_TEST_PLAN.md.
            </p>

            <div className="split">
              <div>
                <video
                  ref={capture.videoRef}
                  muted
                  playsInline
                  autoPlay
                  style={{
                    width: "100%",
                    aspectRatio: "16 / 9",
                    background: "var(--well)",
                    borderRadius: "var(--radius)",
                    transform: "scaleX(-1)",
                    objectFit: "cover",
                    marginBottom: "1rem",
                  }}
                />

                <div className="btn-row" style={{ marginBottom: "1.5rem" }}>
                  <button className="btn" type="button" onClick={start}>
                    Start camera
                  </button>
                  <button className="btn btn-quiet" type="button" onClick={benchmark}>
                    Benchmark
                  </button>
                  <button className="btn btn-quiet" type="button" onClick={calibrateGaze}>
                    Calibrate gaze
                  </button>
                  <button className="btn btn-quiet" type="button" onClick={calibrateHand}>
                    Calibrate hand
                  </button>
                </div>

                <h2 style={{ fontSize: "var(--step-1)", marginBottom: "0.5rem" }}>
                  Sign checklist
                </h2>
                <ol className="steps">
                  {CHECKLIST.map((item) => (
                    <li key={item.field}>
                      <div>
                        <h3>{item.instruction}</h3>
                        <p>
                          {item.field} should {item.expect}. Currently:{" "}
                          <strong>{item.read(l)}</strong>
                        </p>
                      </div>
                    </li>
                  ))}
                </ol>
              </div>

              <div>
                <h2 style={{ fontSize: "var(--step-1)", marginBottom: "0.5rem" }}>Live readout</h2>
                <dl className="defs" style={{ marginBottom: "1.5rem" }}>
                  <dt>stage / tier</dt>
                  <dd>
                    {capture.stage} / {capture.deviceTier ?? "-"} (benchmark {fmt(capture.benchmarkFps, 1)} fps)
                  </dd>

                  <dt>face_count / effective fps / hands mode</dt>
                  <dd>
                    {l?.faceCount ?? "-"} / {l?.effectiveFps ?? "-"} / {l?.handsMode ?? "-"}
                  </dd>

                  <dt>head_yaw / head_pitch / head_roll</dt>
                  <dd>
                    {fmt(l?.headPose?.yaw)} / {fmt(l?.headPose?.pitch)} / {fmt(l?.headPose?.roll)}
                  </dd>

                  <dt>iris_x / iris_y</dt>
                  <dd>
                    {fmt(l?.iris?.x)} / {fmt(l?.iris?.y)}
                  </dd>

                  <dt>face_scale</dt>
                  <dd>{fmt(l?.faceScale, 3)}</dd>

                  <dt>lh_present / rh_present</dt>
                  <dd>
                    {String(l?.handsPresent.lh ?? false)} / {String(l?.handsPresent.rh ?? false)}
                  </dd>

                  <dt>infer_ms</dt>
                  <dd>{fmt(l?.inferMs, 1)}</dd>

                  <dt>calibration</dt>
                  <dd>
                    performed={String(capture.calibration.performed)}, samples=
                    {capture.calibration.samples}, stability={fmt(capture.calibration.stability)},
                    right_hand_check={capture.calibration.rightHandCheck}
                  </dd>

                  <dt>framing</dt>
                  <dd>
                    face_visible={String(capture.framing.faceVisible)}, distance=
                    {capture.framing.distance}, lighting={capture.framing.lighting}
                  </dd>
                </dl>

                <h2 style={{ fontSize: "var(--step-1)", marginBottom: "0.5rem" }}>Log</h2>
                <ul style={{ fontSize: "0.8125rem", color: "var(--ink-soft)", listStyle: "none", padding: 0 }}>
                  {log.map((line, i) => (
                    <li key={i}>{line}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
