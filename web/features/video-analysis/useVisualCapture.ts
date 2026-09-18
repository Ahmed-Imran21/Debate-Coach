"use client";

/**
 * Orchestrates camera acquisition, MediaPipe extraction, the
 * setup screen's live checks/benchmark/calibration, and the
 * during-recording track build (task doc §4.3-§4.11). Every
 * derived number comes from math.ts/framing.ts (already unit
 * tested); this file is the stateful glue around them and is
 * exercised by the debug page and manual testing instead, since
 * it needs a real camera and can't run under Vitest.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  BENCHMARK_DURATION_S,
  CALIBRATION_DURATION_S,
  CALIBRATION_MIN_SAMPLES,
  CALIBRATION_STABILITY_YAW_NORM_DEG,
  CAPTURE_FRAME_RATE_IDEAL,
  CAPTURE_HEIGHT_IDEAL,
  CAPTURE_WIDTH_IDEAL,
  CLOCK_OFFSET_S,
  CLOCK_UNCERTAINTY_MS,
  FACE_MISSING_HINT_AFTER_S,
  FACE_VISIBLE_WINDOW,
  HANDEDNESS_LABEL_INVERTED_DEFAULT,
  HANDS_RAISED_WINDOW_S,
  LIGHTING_SAMPLE_MS,
  RIGHT_HAND_CHECK_MIN_RATIO,
  RIGHT_HAND_CHECK_WINDOW_S,
  SIGNAL_FRAME_HEIGHT,
  SIGNAL_FRAME_WIDTH,
  TIER_FACE_ONLY_MIN_FPS,
  TIER_FULL_MAX_P90_MS,
  TIER_FULL_MIN_FPS,
  TIER_REDUCED_MIN_FPS,
} from "./config";
import { MediaPipeExtractor, type FrameResult, type VisionExtractor } from "./extractor";
import { classifyDistance, classifyLighting, faceVisiblePasses, handsRaisedPasses, ratioTrue } from "./framing";
import {
  computeFaceCenter,
  computeFaceScale,
  computeIrisOffset,
  computePalmCentroid,
  headPoseFromMatrix,
  resolveHandSideFromLabel,
  selectPrimaryFace,
  type HeadPose,
  type IrisOffset,
} from "./math";
import { AdaptiveScheduler, type HandsMode } from "./scheduler";
import { clamp, meanAbsoluteDeviation, median, percentile90 } from "./stats";
import { TrackBuilder } from "./track";
import type {
  Calibration,
  CalibrationBaseline,
  Capture,
  Context,
  DeviceTier,
  Gap,
  GapReason,
  RightHandCheck,
  Setting,
  Source,
  VisualSignalTrack,
} from "./types";

// ---------------------------------------------------------------
// Public types
// ---------------------------------------------------------------

export type UnavailableReason =
  | "camera_denied"
  | "unsupported"
  | "model_load_failed"
  | "device_too_slow"
  | "user_opted_out"
  | "upload_failed"
  | "face_not_found";

export type CaptureStage = "idle" | "requesting" | "setup" | "recording" | "stopped" | "unavailable";

export interface LiveReading {
  faceCount: number;
  headPose: HeadPose | null;
  iris: IrisOffset | null;
  faceScale: number | null;
  handsPresent: { lh: boolean; rh: boolean };
  effectiveFps: number;
  handsMode: HandsMode;
  inferMs: number;
}

export interface FramingChecksState {
  faceVisible: boolean;
  distance: "ok" | "too_close" | "too_far";
  lighting: "ok" | "dim" | "backlit";
  handsRaised: boolean;
}

export interface CalibrationState {
  performed: boolean;
  baseline: CalibrationBaseline | null;
  samples: number;
  stability: number;
  rightHandCheck: RightHandCheck;
}

export interface AcquireResult {
  ok: boolean;
  audioStream: MediaStream | null;
  reason?: UnavailableReason;
}

interface UseVisualCaptureOptions {
  /** Video-analysis feature flag; when false this hook is inert. */
  enabled: boolean;
  requestAudio?: boolean; // default true; the debug page passes false
}

// ---------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------

function now(): number {
  return performance.now();
}

function detectUserAgentFamily(): Source["user_agent_family"] {
  const ua = navigator.userAgent;
  if (/Edg\//.test(ua)) return "edge";
  if (/Chrome\//.test(ua)) return "chrome";
  if (/Firefox\//.test(ua)) return "firefox";
  if (/Safari\//.test(ua) && !/Chrome/.test(ua)) return "safari";
  return "other";
}

function pushWindow<T>(arr: T[], value: T, max: number): void {
  arr.push(value);
  if (arr.length > max) arr.shift();
}

export function useVisualCapture(options: UseVisualCaptureOptions) {
  const { enabled, requestAudio = true } = options;

  const [stage, setStage] = useState<CaptureStage>("idle");
  const [unavailableReason, setUnavailableReason] = useState<UnavailableReason | null>(null);
  const [live, setLive] = useState<LiveReading | null>(null);
  const [framing, setFraming] = useState<FramingChecksState>({
    faceVisible: false,
    distance: "too_far",
    lighting: "ok",
    handsRaised: false,
  });
  const [deviceTier, setDeviceTier] = useState<DeviceTier | null>(null);
  const [benchmarkFps, setBenchmarkFps] = useState(0);
  const [calibration, setCalibration] = useState<CalibrationState>({
    performed: false,
    baseline: null,
    samples: 0,
    stability: 0,
    rightHandCheck: "skipped",
  });
  const [faceMissingSeconds, setFaceMissingSeconds] = useState(0);
  const [showPreview, setShowPreview] = useState(false);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const extractorRef = useRef<VisionExtractor | null>(null);
  const schedulerRef = useRef<AdaptiveScheduler>(new AdaptiveScheduler());
  const trackBuilderRef = useRef<TrackBuilder>(new TrackBuilder());
  const sourceRef = useRef<Source | null>(null);

  // True from the start of acquireAndStartSetup() until a session
  // actually ends (endRecording/abandon/unmount). Guards against a
  // second concurrent acquire — a fast double-click on "Start
  // recording", or an effect re-run (React Strict Mode's mount
  // simulation, or a Next.js Fast Refresh mid-session) — opening a
  // second camera stream + extractor + tick loop that leaks the
  // first set instead of reusing it.
  const sessionActiveRef = useRef(false);

  const loopHandleRef = useRef<number | null>(null);
  const usingRvfcRef = useRef(false);
  const lastMpTimestampRef = useRef<number>(-1);

  const modeRef = useRef<"idle" | "benchmark" | "calibration-gaze" | "calibration-hand" | "armed" | "recording">(
    "idle",
  );
  const t0MsRef = useRef<number | null>(null);
  const handednessInvertedRef = useRef(HANDEDNESS_LABEL_INVERTED_DEFAULT);

  const faceVisibleWindowRef = useRef<boolean[]>([]);
  const faceScaleWindowRef = useRef<number[]>([]);
  const handsRaisedWindowRef = useRef<boolean[]>([]);
  const rightHandWindowRef = useRef<boolean[]>([]);
  const benchmarkTicksRef = useRef<number[]>([]);
  const benchmarkLatenciesRef = useRef<number[]>([]);
  const gazeSamplesRef = useRef<{ yaw: number[]; pitch: number[]; irisX: number[]; irisY: number[] }>({
    yaw: [],
    pitch: [],
    irisX: [],
    irisY: [],
  });

  const faceMissingSinceMsRef = useRef<number | null>(null);
  const lastLightingSampleMsRef = useRef(0);
  const openTabHiddenGapRef = useRef(false);
  const baselineFaceCenterRef = useRef<{ cx: number; cy: number } | null>(null);
  const gazeFaceCenterRef = useRef<{ cx: number[]; cy: number[] }>({ cx: [], cy: [] });

  // ---------------------------------------------------------------
  // Lighting: a small offscreen canvas, sampled and discarded.
  // Never toDataURL/toBlob'd, never persisted (§10 privacy).
  // ---------------------------------------------------------------

  function sampleLighting(video: HTMLVideoElement): { meanLuma: number; faceLuma: number | null } {
    if (!canvasRef.current) {
      canvasRef.current = document.createElement("canvas");
      canvasRef.current.width = 64;
      canvasRef.current.height = 36;
    }
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx || video.videoWidth === 0) return { meanLuma: 128, faceLuma: null };

    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const { data } = ctx.getImageData(0, 0, canvas.width, canvas.height);

    let sum = 0;
    let faceSum = 0;
    let faceN = 0;
    // Centered box, roughly where a face sits when framed decently.
    const fx0 = Math.floor(canvas.width * 0.35);
    const fx1 = Math.ceil(canvas.width * 0.65);
    const fy0 = Math.floor(canvas.height * 0.2);
    const fy1 = Math.ceil(canvas.height * 0.7);

    for (let y = 0; y < canvas.height; y++) {
      for (let x = 0; x < canvas.width; x++) {
        const i = (y * canvas.width + x) * 4;
        const luma = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
        sum += luma;
        if (x >= fx0 && x < fx1 && y >= fy0 && y < fy1) {
          faceSum += luma;
          faceN += 1;
        }
      }
    }

    const meanLuma = sum / (canvas.width * canvas.height);
    const faceLuma = faceN > 0 ? faceSum / faceN : null;
    return { meanLuma, faceLuma };
  }

  // ---------------------------------------------------------------
  // Frame loop
  // ---------------------------------------------------------------

  const processTick = useCallback((frameTimeMs: number) => {
    const video = videoRef.current;
    const extractor = extractorRef.current;
    if (!video || !extractor) return;

    if (frameTimeMs <= lastMpTimestampRef.current) return; // must be strictly increasing
    lastMpTimestampRef.current = frameTimeMs;

    const scheduler = schedulerRef.current;
    // The benchmark measures this device's full-tier cost to pick
    // a tier, so it always runs hands, independent of whatever the
    // scheduler's own (possibly already-throttled) plan would say.
    const runHands = modeRef.current === "benchmark" ? true : scheduler.planHands();

    let result: FrameResult;
    try {
      result = extractor.processFrame(video, frameTimeMs, runHands);
    } catch (err) {
      // TEMP: was silently swallowed. This is exactly what a
      // disposed-but-still-referenced extractor looks like (the
      // "stuck framing" bug): every tick throws here, and framing
      // state below never updates again. Surfacing it so a real
      // recurrence is visible instead of silent.
      console.warn("[vision-debug] processFrame() threw; skipping this tick", err);
      return; // a single bad frame should not kill the loop
    }
    // frameTimeMs is this tick's nominal start (capture/presentation
    // time, or performance.now() at the fallback rAF tick); the gap
    // to now approximates the synchronous detection time just spent.
    const inferMs = Math.max(0, now() - frameTimeMs);

    const degradation = scheduler.recordTick(frameTimeMs, inferMs, runHands);
    if (degradation && modeRef.current === "recording") {
      trackBuilderRef.current.pushDegradation(degradation);
    }

    // --- Face ---
    const faceCandidates = result.faces.map((f) => ({
      center: computeFaceCenter(f.landmarks) ?? { cx: 0.5, cy: 0.5 },
      scale: computeFaceScale(f.landmarks, SIGNAL_FRAME_WIDTH) ?? 0,
    }));
    const primaryIndex =
      result.faces.length > 0 ? selectPrimaryFace(faceCandidates, baselineFaceCenterRef.current) : -1;
    const primaryFace = primaryIndex >= 0 ? result.faces[primaryIndex] : null;

    const headPose =
      primaryFace?.transformMatrix != null ? headPoseFromMatrix(primaryFace.transformMatrix) : null;
    const iris = primaryFace ? computeIrisOffset(primaryFace.landmarks, SIGNAL_FRAME_WIDTH, SIGNAL_FRAME_HEIGHT) : null;
    const faceScale = primaryFace ? computeFaceScale(primaryFace.landmarks, SIGNAL_FRAME_WIDTH) : null;
    const faceCenter = primaryFace ? computeFaceCenter(primaryFace.landmarks) : null;

    // --- Hands ---
    let lh: { cx: number; cy: number; score: number } | null = null;
    let rh: { cx: number; cy: number; score: number } | null = null;

    if (result.hands.length === 2) {
      const centroids = result.hands.map((h) => ({
        ...(computePalmCentroid(h.landmarks) ?? { cx: 0.5, cy: 0.5 }),
        score: h.handednessScore,
      }));
      const assigned = centroids[0].cx <= centroids[1].cx
        ? { rh: centroids[0], lh: centroids[1] }
        : { rh: centroids[1], lh: centroids[0] };
      lh = assigned.lh;
      rh = assigned.rh;
    } else if (result.hands.length === 1) {
      const hand = result.hands[0];
      const centroid = computePalmCentroid(hand.landmarks);
      if (centroid) {
        const side = resolveHandSideFromLabel(hand.handednessLabel, handednessInvertedRef.current);
        const value = { ...centroid, score: hand.handednessScore };
        if (side === "rh") rh = value;
        else lh = value;
      }
    }

    // --- Rolling windows for framing checks (live throughout) ---
    pushWindow(faceVisibleWindowRef.current, result.faces.length > 0, FACE_VISIBLE_WINDOW);
    if (faceScale !== null) pushWindow(faceScaleWindowRef.current, faceScale, FACE_VISIBLE_WINDOW);
    pushWindow(handsRaisedWindowRef.current, lh !== null && rh !== null, Math.round(HANDS_RAISED_WINDOW_S * 10));

    let lightingUpdate: FramingChecksState["lighting"] | null = null;
    if (frameTimeMs - lastLightingSampleMsRef.current >= LIGHTING_SAMPLE_MS) {
      lastLightingSampleMsRef.current = frameTimeMs;
      const { meanLuma, faceLuma } = sampleLighting(video);
      lightingUpdate = classifyLighting(meanLuma, faceLuma);
    }

    const faceVisibleCheck = faceVisiblePasses(faceVisibleWindowRef.current);
    const distanceCheck = classifyDistance(faceScaleWindowRef.current);

    // TEMP diagnostic logging for the "framing permanently stuck"
    // bug. Remove once confirmed fixed (or gate behind a debug flag
    // if it turns out worth keeping longer-term).
    console.info("[vision-debug] tick", {
      facesDetected: result.faces.length,
      faceScale,
      faceVisibleRatio: Number(ratioTrue(faceVisibleWindowRef.current).toFixed(2)),
      windowLen: faceVisibleWindowRef.current.length,
      faceVisibleCheck,
      distanceCheck,
    });

    setFraming((prev) => ({
      faceVisible: faceVisibleCheck,
      distance: distanceCheck,
      handsRaised: handsRaisedPasses(handsRaisedWindowRef.current),
      lighting: lightingUpdate ?? prev.lighting,
    }));

    // --- Face-missing hint timer (during recording) ---
    if (result.faces.length === 0) {
      if (faceMissingSinceMsRef.current === null) faceMissingSinceMsRef.current = frameTimeMs;
      const missingS = (frameTimeMs - faceMissingSinceMsRef.current) / 1000;
      setFaceMissingSeconds(missingS >= FACE_MISSING_HINT_AFTER_S ? missingS : 0);
    } else {
      faceMissingSinceMsRef.current = null;
      setFaceMissingSeconds(0);
    }

    // --- Mode-specific accumulation ---
    const mode = modeRef.current;

    if (mode === "benchmark") {
      pushWindow(benchmarkTicksRef.current, frameTimeMs, 10_000);
      // Runs hands every tick regardless of scheduler.planHands():
      // the benchmark's job is to measure this device's true
      // combined face+hands cost, not the throttled-down cost.
      pushWindow(benchmarkLatenciesRef.current, inferMs, 10_000);
    } else if (mode === "calibration-gaze" && headPose && iris) {
      gazeSamplesRef.current.yaw.push(headPose.yaw);
      gazeSamplesRef.current.pitch.push(headPose.pitch);
      gazeSamplesRef.current.irisX.push(iris.x);
      gazeSamplesRef.current.irisY.push(iris.y);
      if (faceCenter) {
        gazeFaceCenterRef.current.cx.push(faceCenter.cx);
        gazeFaceCenterRef.current.cy.push(faceCenter.cy);
      }
    } else if (mode === "calibration-hand") {
      pushWindow(rightHandWindowRef.current, rh !== null, Math.round(RIGHT_HAND_CHECK_WINDOW_S * 10));
    } else if (mode === "recording" && t0MsRef.current !== null) {
      const tSeconds = (frameTimeMs - t0MsRef.current) / 1000 + CLOCK_OFFSET_S;
      trackBuilderRef.current.appendSample(tSeconds, {
        face_count: result.faces.length,
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
      });

      if (scheduler.isDisabled && !trackBuilderRef.current.hasOpenGap) {
        trackBuilderRef.current.openGapAt(tSeconds, "perf_disabled");
      }
    }

    setLive({
      faceCount: result.faces.length,
      headPose,
      iris,
      faceScale,
      handsPresent: { lh: lh !== null, rh: rh !== null },
      effectiveFps: scheduler.currentEffectiveFps,
      handsMode: scheduler.currentHandsMode,
      inferMs,
    });
  }, []);

  const loopStep = useCallback(() => {
    const video = videoRef.current;
    if (!video || !streamRef.current) return;

    // Once the scheduler disables analysis (sustained low fps),
    // stop scheduling callbacks entirely rather than keep waking
    // up every frame to do nothing on a device that's already
    // struggling. endRecording()/abandon() still call stopLoop()
    // to clear the (by-then-null) handle on their own paths.
    if (schedulerRef.current.isDisabled) return;

    const withRvfc = video as HTMLVideoElement & {
      requestVideoFrameCallback?: (cb: (now: number, metadata: VideoFrameCallbackMetadata) => void) => number;
      cancelVideoFrameCallback?: (handle: number) => void;
    };

    if (typeof withRvfc.requestVideoFrameCallback === "function") {
      usingRvfcRef.current = true;
      loopHandleRef.current = withRvfc.requestVideoFrameCallback((_ts, metadata) => {
        const frameTimeMs = metadata.captureTime ?? metadata.presentationTime ?? now();
        if (schedulerRef.current.shouldTick(frameTimeMs)) processTick(frameTimeMs);
        loopStep();
      });
    } else {
      usingRvfcRef.current = false;
      loopHandleRef.current = requestAnimationFrame(() => {
        const frameTimeMs = now();
        if (schedulerRef.current.shouldTick(frameTimeMs)) processTick(frameTimeMs);
        loopStep();
      });
    }
  }, [processTick]);

  function stopLoop(): void {
    if (loopHandleRef.current === null) return;
    const video = videoRef.current as
      | (HTMLVideoElement & { cancelVideoFrameCallback?: (h: number) => void })
      | null;
    if (usingRvfcRef.current && video?.cancelVideoFrameCallback) {
      video.cancelVideoFrameCallback(loopHandleRef.current);
    } else {
      cancelAnimationFrame(loopHandleRef.current);
    }
    loopHandleRef.current = null;
  }

  // ---------------------------------------------------------------
  // Tab visibility -> gap
  // ---------------------------------------------------------------

  useEffect(() => {
    if (!enabled) return;

    function handleVisibility(): void {
      if (modeRef.current !== "recording") return;
      const t = t0MsRef.current;
      if (t === null) return;
      const nowS = (now() - t) / 1000 + CLOCK_OFFSET_S;

      if (document.hidden) {
        if (!trackBuilderRef.current.hasOpenGap) {
          trackBuilderRef.current.openGapAt(Math.max(0, nowS), "tab_hidden");
          openTabHiddenGapRef.current = true;
        }
      } else if (openTabHiddenGapRef.current) {
        trackBuilderRef.current.closeGapAt(Math.max(0, nowS));
        openTabHiddenGapRef.current = false;
      }
    }

    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, [enabled]);

  // ---------------------------------------------------------------
  // Public: acquire camera + init models, enter "setup"
  // ---------------------------------------------------------------

  const acquireAndStartSetup = useCallback(async (): Promise<AcquireResult> => {
    if (!enabled) return { ok: false, audioStream: null, reason: "user_opted_out" };

    // Reentrancy guard (see sessionActiveRef above): a second call
    // while a session is already being acquired, or is already live
    // on this instance, would otherwise open a second getUserMedia
    // stream and a second MediaPipeExtractor, leak the first pair
    // (never stopped/disposed), and start a second rVFC/rAF tick
    // loop that stopLoop() can no longer fully cancel (loopHandleRef
    // only remembers the most recently scheduled handle).
    if (sessionActiveRef.current) {
      return { ok: false, audioStream: null, reason: "unsupported" };
    }
    sessionActiveRef.current = true;

    setStage("requesting");

    if (
      typeof navigator === "undefined" ||
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined"
    ) {
      sessionActiveRef.current = false;
      setStage("unavailable");
      setUnavailableReason("unsupported");
      return { ok: false, audioStream: null, reason: "unsupported" };
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: requestAudio,
        video: {
          facingMode: "user",
          width: { ideal: CAPTURE_WIDTH_IDEAL },
          height: { ideal: CAPTURE_HEIGHT_IDEAL },
          frameRate: { ideal: CAPTURE_FRAME_RATE_IDEAL },
        },
      });
    } catch {
      sessionActiveRef.current = false;
      setStage("unavailable");
      setUnavailableReason("camera_denied");
      return { ok: false, audioStream: null, reason: "camera_denied" };
    }

    if (!sessionActiveRef.current) {
      // abandon()/unmount ran while getUserMedia() was pending.
      stream.getTracks().forEach((t) => t.stop());
      return { ok: false, audioStream: null, reason: "unsupported" };
    }

    streamRef.current = stream;

    if (videoRef.current) {
      videoRef.current.srcObject = stream;
      await videoRef.current.play().catch(() => {});
    }

    const extractor = new MediaPipeExtractor();
    try {
      const init = await extractor.init();

      if (!sessionActiveRef.current) {
        // abandon()/unmount ran while init() was pending — don't
        // adopt this extractor, just dispose what we just built
        // instead of leaking it (see sessionActiveRef above).
        extractor.dispose();
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        return { ok: false, audioStream: null, reason: "unsupported" };
      }

      extractorRef.current = extractor;
      sourceRef.current = {
        platform: "web",
        client_version: process.env.NEXT_PUBLIC_CLIENT_VERSION ?? "unknown",
        user_agent_family: detectUserAgentFamily(),
        runtime: { name: "mediapipe-tasks-vision", version: init.runtimeVersion, delegate: init.delegate },
        models: init.models,
        device_tier: "full",
        benchmark_fps: 0,
      };
    } catch {
      sessionActiveRef.current = false;
      stream.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      setStage("unavailable");
      setUnavailableReason("model_load_failed");
      return { ok: false, audioStream: null, reason: "model_load_failed" };
    }

    modeRef.current = "idle";
    lastMpTimestampRef.current = -1;
    // Fresh session: clear the rolling framing-check windows too, so
    // a retry after abandon()/camera_denied doesn't start out with
    // stale entries from a prior attempt still sitting in them.
    faceVisibleWindowRef.current = [];
    faceScaleWindowRef.current = [];
    handsRaisedWindowRef.current = [];
    faceMissingSinceMsRef.current = null;
    setFaceMissingSeconds(0);
    setFraming({ faceVisible: false, distance: "too_far", lighting: "ok", handsRaised: false });
    setStage("setup");
    // Guard against starting a second concurrent tick loop (see
    // sessionActiveRef above) — this only matters if the guard
    // above was somehow bypassed, but costs nothing to keep.
    if (loopHandleRef.current === null) loopStep();

    const audioStream = new MediaStream(stream.getAudioTracks());
    return { ok: true, audioStream };
  }, [enabled, requestAudio, loopStep]);

  // ---------------------------------------------------------------
  // Public: benchmark (§4.9.2)
  // ---------------------------------------------------------------

  const runBenchmark = useCallback(async (): Promise<DeviceTier | "too_slow"> => {
    benchmarkTicksRef.current = [];
    benchmarkLatenciesRef.current = [];
    modeRef.current = "benchmark";
    await new Promise((r) => setTimeout(r, BENCHMARK_DURATION_S * 1000));
    modeRef.current = "idle";

    const ticks = benchmarkTicksRef.current;
    const fps = ticks.length / BENCHMARK_DURATION_S;
    setBenchmarkFps(fps);

    const p90 = percentile90(benchmarkLatenciesRef.current);
    const p90Ok = Number.isNaN(p90) || p90 <= TIER_FULL_MAX_P90_MS;

    let tier: DeviceTier | "too_slow";
    if (fps >= TIER_FULL_MIN_FPS && p90Ok) tier = "full";
    else if (fps >= TIER_REDUCED_MIN_FPS) tier = "reduced";
    else if (fps >= TIER_FACE_ONLY_MIN_FPS) tier = "face_only";
    else tier = "too_slow";

    if (tier === "too_slow") {
      setUnavailableReason("device_too_slow");
      return "too_slow";
    }

    setDeviceTier(tier);
    if (sourceRef.current) {
      sourceRef.current = { ...sourceRef.current, device_tier: tier, benchmark_fps: Math.round(fps * 10) / 10 };
    }
    return tier;
  }, []);

  // ---------------------------------------------------------------
  // Public: calibration (§4.9.3)
  // ---------------------------------------------------------------

  const runGazeCalibration = useCallback(async (): Promise<void> => {
    gazeSamplesRef.current = { yaw: [], pitch: [], irisX: [], irisY: [] };
    gazeFaceCenterRef.current = { cx: [], cy: [] };
    modeRef.current = "calibration-gaze";
    await new Promise((r) => setTimeout(r, CALIBRATION_DURATION_S * 1000));
    modeRef.current = "idle";

    const { yaw, pitch, irisX, irisY } = gazeSamplesRef.current;

    if (yaw.length < CALIBRATION_MIN_SAMPLES) {
      setCalibration((prev) => ({ ...prev, performed: false, samples: yaw.length }));
      return;
    }

    const baseline: CalibrationBaseline = {
      head_yaw: median(yaw),
      head_pitch: median(pitch),
      iris_x: median(irisX),
      iris_y: median(irisY),
    };
    const mad = meanAbsoluteDeviation(yaw, baseline.head_yaw);
    const stability = 1 - clamp(mad / CALIBRATION_STABILITY_YAW_NORM_DEG, 0, 1);

    // Position baseline for two-face primary selection (math.ts
    // selectPrimaryFace), distinct from the angle/iris baseline
    // above: while calibrating, the speaker is presumed to be the
    // only (or the centered) face, so this is where they sit.
    const { cx, cy } = gazeFaceCenterRef.current;
    if (cx.length > 0) {
      baselineFaceCenterRef.current = { cx: median(cx), cy: median(cy) };
    }

    setCalibration((prev) => ({ ...prev, performed: true, baseline, samples: yaw.length, stability }));
  }, []);

  const runRightHandCheck = useCallback(async (): Promise<RightHandCheck> => {
    rightHandWindowRef.current = [];
    modeRef.current = "calibration-hand";
    await new Promise((r) => setTimeout(r, RIGHT_HAND_CHECK_WINDOW_S * 1000));
    modeRef.current = "idle";

    let ratio = ratioTrue(rightHandWindowRef.current);
    let result: RightHandCheck = ratio >= RIGHT_HAND_CHECK_MIN_RATIO ? "passed" : "failed";

    if (result === "failed") {
      // Flip the mapping once and retry (§4.8).
      handednessInvertedRef.current = !handednessInvertedRef.current;
      rightHandWindowRef.current = [];
      modeRef.current = "calibration-hand";
      await new Promise((r) => setTimeout(r, RIGHT_HAND_CHECK_WINDOW_S * 1000));
      modeRef.current = "idle";
      ratio = ratioTrue(rightHandWindowRef.current);
      result = ratio >= RIGHT_HAND_CHECK_MIN_RATIO ? "passed" : "failed";
      if (result === "failed") {
        // Neither mapping worked; revert to the default rather
        // than leave it flipped on a guess.
        handednessInvertedRef.current = HANDEDNESS_LABEL_INVERTED_DEFAULT;
      }
    }

    setCalibration((prev) => ({ ...prev, rightHandCheck: result }));
    return result;
  }, []);

  const skipCalibration = useCallback(() => {
    setCalibration({ performed: false, baseline: null, samples: 0, stability: 0, rightHandCheck: "skipped" });
  }, []);

  // ---------------------------------------------------------------
  // Public: recording lifecycle
  // ---------------------------------------------------------------

  /** Called from the audio MediaRecorder's onstart handler. */
  const beginRecording = useCallback((t0Ms: number) => {
    t0MsRef.current = t0Ms;
    modeRef.current = "recording";
    setStage("recording");
  }, []);

  const endRecording = useCallback(
    async (
      durationS: number,
      context: Context,
    ): Promise<{ available: true; track: VisualSignalTrack } | { available: false; reason: UnavailableReason }> => {
      modeRef.current = "idle";
      sessionActiveRef.current = false;
      stopLoop();

      extractorRef.current?.dispose();
      extractorRef.current = null;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;

      setStage("stopped");

      if (!sourceRef.current) {
        return { available: false, reason: "model_load_failed" };
      }

      const capture: Capture = {
        frame_width: SIGNAL_FRAME_WIDTH,
        frame_height: SIGNAL_FRAME_HEIGHT,
        input_mirrored: false,
        handedness_convention: "anatomical",
        target_fps: 10,
      };

      const calibrationOut: Calibration = {
        performed: calibration.performed,
        baseline: calibration.baseline,
        samples: calibration.samples,
        stability: calibration.stability,
        right_hand_check: calibration.rightHandCheck,
      };

      const track = trackBuilderRef.current.build({
        sessionId: "", // filled in by the caller once the session id is known
        source: sourceRef.current,
        capture,
        clockUncertaintyMs: CLOCK_UNCERTAINTY_MS,
        durationS,
        calibration: calibrationOut,
        context,
        setupCheck: {
          face_visible: framing.faceVisible,
          hands_visible_when_raised: framing.handsRaised,
          lighting: framing.lighting,
          distance: framing.distance,
        },
      });

      if (track.frames.t.length === 0) {
        return { available: false, reason: "face_not_found" };
      }

      return { available: true, track };
    },
    [calibration, framing],
  );

  /** Bail out at any point in setup (camera denied handled separately, in acquireAndStartSetup). */
  const abandon = useCallback((reason: UnavailableReason) => {
    sessionActiveRef.current = false;
    stopLoop();
    extractorRef.current?.dispose();
    extractorRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setStage("unavailable");
    setUnavailableReason(reason);
  }, []);

  // Stop tracks on unmount, regardless of what stage we're in.
  //
  // Root cause of the "framing permanently stuck" bug: this cleanup
  // disposed extractorRef.current but never nulled the ref out,
  // unlike endRecording()/abandon() (which both do). Whenever this
  // ran while a session was live — most plausibly a Next.js Fast
  // Refresh re-running this effect mid-session while iterating on
  // this file, though React Strict Mode's one-time mount-simulation
  // dance would hit the same path if it ever coincided with a live
  // session — extractorRef.current was left pointing at a
  // disposed-but-still-truthy extractor. processTick()'s
  // `if (!video || !extractor) return;` guard didn't catch that
  // (the ref was still non-null), so every subsequent tick called
  // processFrame() on it, threw, and was silently swallowed —
  // freezing framing state at its initial defaults ("Not clearly
  // visible yet" / "too_far") forever, even with a face right in
  // frame. sessionActiveRef also gets reset here so a fresh
  // acquireAndStartSetup() (e.g. after a Fast Refresh) isn't
  // permanently blocked by the reentrancy guard above.
  useEffect(
    () => () => {
      sessionActiveRef.current = false;
      stopLoop();
      extractorRef.current?.dispose();
      extractorRef.current = null;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    },
    [],
  );

  return {
    stage,
    unavailableReason,
    live,
    framing,
    deviceTier,
    benchmarkFps,
    calibration,
    faceMissingSeconds,
    showPreview,
    setShowPreview,
    videoRef,
    acquireAndStartSetup,
    runBenchmark,
    runGazeCalibration,
    runRightHandCheck,
    skipCalibration,
    beginRecording,
    endRecording,
    abandon,
  };
}

export type { DeviceTier, GapReason, Gap, RightHandCheck, Setting };
