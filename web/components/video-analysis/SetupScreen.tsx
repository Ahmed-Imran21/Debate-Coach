"use client";

import { useState } from "react";
import type { ReactElement } from "react";

import type { useVisualCapture } from "@/features/video-analysis/useVisualCapture";
import type { Context, Setting } from "@/features/video-analysis/types";

type Capture = ReturnType<typeof useVisualCapture>;

type Step = "framing" | "benchmark" | "calibrate-gaze" | "calibrate-hand" | "context" | "ready";

interface Props {
  capture: Capture;
  onReady: (context: Context) => void;
  onSkip: () => void;
}

const LIGHTING_HINT: Record<string, string> = {
  dim: "The room looks dim. More light on your face will help.",
  backlit: "There's a lot of light behind you. Try facing a window or lamp instead.",
  ok: "",
};

const DISTANCE_HINT: Record<string, string> = {
  too_close: "Move back a little so your hands fit in the frame.",
  too_far: "Move a bit closer so your face is easy to track.",
  ok: "",
};

/**
 * Framing checks -> benchmark -> calibration (gaze, then right
 * hand) -> context questions -> ready (task doc §4.9). Every
 * number shown here comes from the useVisualCapture hook, which
 * in turn comes from the already-tested pure modules; this
 * component is just sequencing and copy.
 */
export default function SetupScreen({ capture, onReady, onSkip }: Props): ReactElement {
  const [step, setStep] = useState<Step>("framing");
  const [setting, setSetting] = useState<Setting>("camera_audience");
  const [usesNotes, setUsesNotes] = useState(false);
  const [busy, setBusy] = useState(false);

  const { framing, benchmarkFps, deviceTier, calibration, unavailableReason } = capture;

  const framingReady = framing.faceVisible && framing.distance === "ok" && framing.lighting === "ok";

  async function handleBenchmark(): Promise<void> {
    setBusy(true);
    const tier = await capture.runBenchmark();
    setBusy(false);
    if (tier === "too_slow") {
      onSkip();
      return;
    }
    setStep("calibrate-gaze");
  }

  async function handleGazeCalibration(): Promise<void> {
    setBusy(true);
    await capture.runGazeCalibration();
    setBusy(false);
    setStep("calibrate-hand");
  }

  async function handleRightHandCalibration(): Promise<void> {
    setBusy(true);
    await capture.runRightHandCheck();
    setBusy(false);
    setStep("context");
  }

  function skipCalibrationAndContinue(): void {
    capture.skipCalibration();
    setStep("context");
  }

  function finish(): void {
    onReady({ setting, uses_notes: usesNotes });
  }

  if (capture.stage === "unavailable") {
    return (
      <div className="form-panel" style={{ maxWidth: "34rem" }}>
        <p className="note" style={{ margin: 0 }}>
          {unavailableReason === "camera_denied" &&
            "Camera access was blocked. You can still record with audio only."}
          {unavailableReason === "device_too_slow" &&
            "This device can't keep up with visual analysis right now. Continuing with audio only."}
          {unavailableReason === "model_load_failed" &&
            "Visual analysis couldn't start. Continuing with audio only."}
          {(!unavailableReason || unavailableReason === "unsupported") &&
            "Visual analysis isn't available here. Continuing with audio only."}
        </p>
      </div>
    );
  }

  return (
    <div className="form-panel" style={{ maxWidth: "34rem" }}>
      {/*
        Bug fix (2026-09-18): this was the only place in the setup
        flow capture.videoRef could get attached to a real <video>
        element — Recorder.tsx only renders one during phase ===
        "recording". With no element here, videoRef.current stayed
        null for the whole setup screen: acquireAndStartSetup()'s
        `if (videoRef.current) { srcObject = stream; ... }` never
        ran, and loopStep()'s own `if (!video || ...) return;` guard
        fired on every single call, so it never even scheduled a
        rVFC/rAF callback — processTick() was never invoked, not
        once, and framing stayed frozen at its initial defaults.
        Kept mounted (not step-conditional) so the ref stays stable
        across every step, and visible so the framing/calibration
        instructions ("move closer", "look at the camera") have
        something to actually check against.
      */}
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
          marginBottom: "1.25rem",
        }}
      />

      {step === "framing" && (
        <>
          <h2 style={{ fontSize: "var(--step-2)", marginBottom: "0.75rem" }}>Framing</h2>
          <dl className="defs" style={{ marginBottom: "1.25rem" }}>
            <dt>Face</dt>
            <dd>{framing.faceVisible ? "Visible" : "Not clearly visible yet"}</dd>

            <dt>Distance</dt>
            <dd>{framing.distance === "ok" ? "Good" : DISTANCE_HINT[framing.distance]}</dd>

            <dt>Lighting</dt>
            <dd>{framing.lighting === "ok" ? "Good" : LIGHTING_HINT[framing.lighting]}</dd>
          </dl>
          <div className="btn-row">
            <button className="btn" type="button" disabled={!framingReady} onClick={() => setStep("benchmark")}>
              Continue
            </button>
            <button className="btn btn-quiet" type="button" onClick={onSkip}>
              Skip visual feedback
            </button>
          </div>
        </>
      )}

      {step === "benchmark" && (
        <>
          <h2 style={{ fontSize: "var(--step-2)", marginBottom: "0.75rem" }}>Checking this device</h2>
          <p className="note" style={{ marginBottom: "1.25rem" }}>
            A brief check to see how much analysis this device can keep up with.
            {benchmarkFps > 0 && ` Last run: ~${benchmarkFps.toFixed(0)} frames/sec.`}
          </p>
          <div className="btn-row">
            <button className="btn" type="button" disabled={busy} onClick={handleBenchmark}>
              {busy ? "Checking." : "Run check"}
            </button>
            <button className="btn btn-quiet" type="button" onClick={onSkip}>
              Skip visual feedback
            </button>
          </div>
        </>
      )}

      {step === "calibrate-gaze" && (
        <>
          <h2 style={{ fontSize: "var(--step-2)", marginBottom: "0.75rem" }}>
            {deviceTier ? `Device ready (${deviceTier.replace("_", " ")} tracking)` : "Look at the camera"}
          </h2>
          <p className="note" style={{ marginBottom: "1.25rem" }}>
            Look directly at your camera lens, not the screen, for three seconds. This
            sets the baseline for &quot;facing the camera&quot; during your speech.
          </p>
          <div className="btn-row">
            <button className="btn" type="button" disabled={busy} onClick={handleGazeCalibration}>
              {busy ? "Reading." : "Start"}
            </button>
            <button className="btn btn-quiet" type="button" onClick={() => setStep("calibrate-hand")}>
              Skip
            </button>
          </div>
        </>
      )}

      {step === "calibrate-hand" && (
        <>
          <h2 style={{ fontSize: "var(--step-2)", marginBottom: "0.75rem" }}>Raise your right hand</h2>
          <p className="note" style={{ marginBottom: "1.25rem" }}>
            Just for a couple of seconds, so gestures get attributed to the right side.
          </p>
          <div className="btn-row">
            <button className="btn" type="button" disabled={busy} onClick={handleRightHandCalibration}>
              {busy ? "Checking." : "Start"}
            </button>
            <button className="btn btn-quiet" type="button" onClick={skipCalibrationAndContinue}>
              Skip
            </button>
          </div>
        </>
      )}

      {step === "context" && (
        <>
          <h2 style={{ fontSize: "var(--step-2)", marginBottom: "0.75rem" }}>A couple of questions</h2>

          <fieldset style={{ border: 0, padding: 0, margin: "0 0 1.25rem" }}>
            <legend className="note" style={{ marginBottom: "0.5rem" }}>
              Where will your audience be?
            </legend>
            <label style={{ display: "flex", gap: "0.5rem", alignItems: "baseline", marginBottom: "0.5rem" }}>
              <input
                type="radio"
                name="setting"
                checked={setting === "camera_audience"}
                onChange={() => setSetting("camera_audience")}
              />
              <span>Watching this camera (online or recorded)</span>
            </label>
            <label style={{ display: "flex", gap: "0.5rem", alignItems: "baseline" }}>
              <input
                type="radio"
                name="setting"
                checked={setting === "in_room_practice"}
                onChange={() => setSetting("in_room_practice")}
              />
              <span>In the room with me</span>
            </label>
          </fieldset>

          <label style={{ display: "flex", gap: "0.5rem", alignItems: "baseline", marginBottom: "1.25rem" }}>
            <input type="checkbox" checked={usesNotes} onChange={(e) => setUsesNotes(e.target.checked)} />
            <span>I&apos;m using notes</span>
          </label>

          <div className="btn-row" style={{ marginTop: "0.5rem" }}>
            <button className="btn" type="button" onClick={() => setStep("ready")}>
              Continue
            </button>
          </div>
        </>
      )}

      {step === "ready" && (
        <>
          <h2 style={{ fontSize: "var(--step-2)", marginBottom: "0.75rem" }}>Ready</h2>
          <p className="note" style={{ marginBottom: "1.25rem" }}>
            {calibration.performed
              ? "Calibration complete. "
              : "Recording without calibration; gaze tracking will be less precise. "}
            You can start whenever you&apos;re ready.
          </p>
          <div className="btn-row">
            <button className="btn" type="button" onClick={finish}>
              Start recording
            </button>
          </div>
        </>
      )}
    </div>
  );
}
