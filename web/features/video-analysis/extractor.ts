/**
 * Thin MediaPipe wrapper (task doc §4.5). Deliberately dumb: it
 * only calls the SDK and hands back raw landmarks/matrices. Every
 * derived number (head pose, iris offset, scale, centroids, hand
 * side) is computed by the pure, unit-tested functions in
 * math.ts, not here.
 *
 * Client-only. Never imported at module scope by a server
 * component; always behind a dynamic import from an effect or
 * handler (§4.2), which is why the @mediapipe/tasks-vision import
 * below is a dynamic import() inside init(), not a static one.
 *
 * Runs on the main thread (§4.5: "behind a small interface ...
 * so a worker version can replace it later without touching
 * callers"). VisionExtractor is that interface.
 */

import type {
  FaceLandmarker as FaceLandmarkerType,
  HandLandmarker as HandLandmarkerType,
} from "@mediapipe/tasks-vision";

// Not exported as a named type by the package (delegate is an
// inline "CPU" | "GPU" literal on BaseOptions); redeclared here.
type MpDelegate = "GPU" | "CPU";

import type { Landmark } from "./math";

export interface DetectedFace {
  landmarks: Landmark[];
  /** Flattened 4x4 facial transformation matrix, column-major (see math.ts). Null if not available for this face. */
  transformMatrix: number[] | null;
}

export interface DetectedHand {
  landmarks: Landmark[];
  handednessLabel: "Left" | "Right";
  handednessScore: number;
}

export interface FrameResult {
  faces: DetectedFace[];
  hands: DetectedHand[];
}

export interface ModelProvenance {
  task: "face_landmarker" | "hand_landmarker";
  model_id: string;
  sha256: string;
}

export interface InitResult {
  delegate: "GPU" | "CPU";
  runtimeVersion: string;
  models: ModelProvenance[];
}

export interface VisionExtractor {
  init(): Promise<InitResult>;
  processFrame(video: HTMLVideoElement, timestampMs: number, runHands: boolean): FrameResult;
  dispose(): void;
}

interface Manifest {
  runtime_version: string;
  models: ModelProvenance[];
}

async function loadManifest(): Promise<Manifest> {
  const response = await fetch("/mediapipe/manifest.json");
  if (!response.ok) {
    throw new Error(`Could not load /mediapipe/manifest.json (HTTP ${response.status}).`);
  }
  return (await response.json()) as Manifest;
}

function modelPath(manifest: Manifest, task: ModelProvenance["task"]): string {
  const model = manifest.models.find((m) => m.task === task);
  if (!model) throw new Error(`manifest.json has no entry for ${task}.`);
  return `/mediapipe/models/${model.model_id}`;
}

// TEMP: instance counter for the "framing permanently stuck" bug
// investigation (2026-09-18). Distinguishes a legitimate init() (one
// instance, two graphs — face + hand, hence two sets of MediaPipe's
// own startup log lines) from a real double-init (two instances).
// Remove once the fix in useVisualCapture.ts is confirmed.
let debugInstanceCounter = 0;

export class MediaPipeExtractor implements VisionExtractor {
  private faceLandmarker: FaceLandmarkerType | null = null;
  private handLandmarker: HandLandmarkerType | null = null;
  private readonly debugId = ++debugInstanceCounter; // TEMP, see above

  async init(): Promise<InitResult> {
    console.info(`[vision-debug] extractor#${this.debugId}.init() starting`); // TEMP
    const manifest = await loadManifest();

    const vision = await import("@mediapipe/tasks-vision");
    const { FilesetResolver, FaceLandmarker, HandLandmarker } = vision;

    const fileset = await FilesetResolver.forVisionTasks("/mediapipe/wasm");

    const facePath = modelPath(manifest, "face_landmarker");
    const handPath = modelPath(manifest, "hand_landmarker");

    const delegate = await this.createBoth(fileset, FaceLandmarker, HandLandmarker, facePath, handPath);

    console.info(`[vision-debug] extractor#${this.debugId}.init() done, delegate=${delegate}`); // TEMP

    return { delegate, runtimeVersion: manifest.runtime_version, models: manifest.models };
  }

  private async createBoth(
    fileset: Awaited<ReturnType<typeof import("@mediapipe/tasks-vision").FilesetResolver.forVisionTasks>>,
    FaceLandmarker: typeof import("@mediapipe/tasks-vision").FaceLandmarker,
    HandLandmarker: typeof import("@mediapipe/tasks-vision").HandLandmarker,
    facePath: string,
    handPath: string,
  ): Promise<"GPU" | "CPU"> {
    for (const delegate of ["GPU", "CPU"] as MpDelegate[]) {
      try {
        this.faceLandmarker = await FaceLandmarker.createFromOptions(fileset, {
          baseOptions: { modelAssetPath: facePath, delegate },
          runningMode: "VIDEO",
          numFaces: 2,
          outputFaceBlendshapes: false,
          outputFacialTransformationMatrixes: true,
        });
        this.handLandmarker = await HandLandmarker.createFromOptions(fileset, {
          baseOptions: { modelAssetPath: handPath, delegate },
          runningMode: "VIDEO",
          numHands: 2,
        });
        return delegate;
      } catch (error) {
        this.faceLandmarker?.close();
        this.handLandmarker?.close();
        this.faceLandmarker = null;
        this.handLandmarker = null;
        if (delegate === "CPU") {
          throw error instanceof Error ? error : new Error(String(error));
        }
        // else fall through and retry once with CPU
      }
    }
    // Unreachable (the loop either returns or throws), but keeps
    // TypeScript's control-flow analysis happy.
    throw new Error("model_load_failed");
  }

  processFrame(video: HTMLVideoElement, timestampMs: number, runHands: boolean): FrameResult {
    if (!this.faceLandmarker || !this.handLandmarker) {
      throw new Error("MediaPipeExtractor.processFrame() called before init() resolved.");
    }

    const faceResult = this.faceLandmarker.detectForVideo(video, timestampMs);

    const faces: DetectedFace[] = faceResult.faceLandmarks.map((landmarks, index) => ({
      landmarks,
      transformMatrix: faceResult.facialTransformationMatrixes?.[index]?.data ?? null,
    }));

    let hands: DetectedHand[] = [];

    if (runHands) {
      const handResult = this.handLandmarker.detectForVideo(video, timestampMs);
      hands = handResult.landmarks.map((landmarks, index) => {
        const category = handResult.handedness[index]?.[0];
        return {
          landmarks,
          handednessLabel: (category?.categoryName as "Left" | "Right" | undefined) ?? "Right",
          handednessScore: category?.score ?? 0,
        };
      });
    }

    return { faces, hands };
  }

  dispose(): void {
    // TEMP: was silent. Logs which call site disposed this instance
    // (unmount cleanup vs abandon() vs endRecording()) and whether it
    // was still holding live landmarkers when this ran — the "stuck
    // framing" bug's actual disposed-but-still-referenced state.
    console.info(
      `[vision-debug] extractor#${this.debugId}.dispose() called, ` +
        `wasLive=${this.faceLandmarker !== null || this.handLandmarker !== null}`,
      new Error("[vision-debug] dispose() call site").stack,
    );
    this.faceLandmarker?.close();
    this.handLandmarker?.close();
    this.faceLandmarker = null;
    this.handLandmarker = null;
  }
}
