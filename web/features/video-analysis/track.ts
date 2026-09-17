/**
 * Accumulates samples into a VisualSignalTrack (task doc §4.11).
 * Pure: no DOM, no MediaPipe, no timers. The recording loop
 * calls appendSample() once per tick; build() produces the final
 * object the upload module serializes.
 *
 * Rounding follows §3.2 exactly (angles 0.1, iris 0.01, scale/
 * coords 0.001). t and infer_ms have no rounding rule in the
 * spec; t is kept to millisecond precision (3 decimals) to bound
 * payload size without losing meaningful resolution, and infer_ms
 * to the nearest whole millisecond, since sub-ms timer resolution
 * isn't meaningful in a browser.
 */

import {
  EMPTY_SAMPLE,
  FRAME_COLUMNS,
  type Calibration,
  type Capture,
  type Context,
  type Degradation,
  type Frames,
  type FrameSample,
  type Gap,
  type GapReason,
  type SetupCheck,
  type Source,
  type VisualSignalTrack,
} from "./types";

function round(value: number | null, decimals: number): number | null {
  if (value === null || Number.isNaN(value)) return null;
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

const ROUNDING: Record<keyof Omit<Frames, "t">, number | null> = {
  face_count: null,
  head_yaw: 1,
  head_pitch: 1,
  head_roll: 1,
  iris_x: 2,
  iris_y: 2,
  face_scale: 3,
  face_cx: 3,
  face_cy: 3,
  lh_present: null,
  lh_score: 2,
  lh_cx: 3,
  lh_cy: 3,
  rh_present: null,
  rh_score: 2,
  rh_cx: 3,
  rh_cy: 3,
  infer_ms: 0,
};

function roundSample(sample: FrameSample): FrameSample {
  const out = { ...sample };
  for (const key of FRAME_COLUMNS) {
    const decimals = ROUNDING[key];
    out[key] = decimals === null ? out[key] : round(out[key], decimals);
  }
  return out;
}

export class TrackBuilder {
  private readonly t: number[] = [];
  private readonly columns: { [K in keyof Omit<Frames, "t">]: Array<number | null> } = {
    face_count: [], head_yaw: [], head_pitch: [], head_roll: [], iris_x: [], iris_y: [],
    face_scale: [], face_cx: [], face_cy: [],
    lh_present: [], lh_score: [], lh_cx: [], lh_cy: [],
    rh_present: [], rh_score: [], rh_cx: [], rh_cy: [],
    infer_ms: [],
  };

  private readonly gapsList: Gap[] = [];
  private readonly degradationsList: Degradation[] = [];
  private openGap: { start: number; reason: GapReason } | null = null;

  private lastT: number | null = null;

  get frameCount(): number {
    return this.t.length;
  }

  get lastAppendedT(): number | null {
    return this.lastT;
  }

  /**
   * Append one tick. Dropped (returns false) if t < 0 or t is
   * not strictly greater than the previous appended t — the
   * schema requires strictly increasing time, so the builder
   * enforces it at the source rather than trusting every caller.
   */
  appendSample(t: number, sample: FrameSample): boolean {
    if (t < 0) return false;
    if (this.lastT !== null && t <= this.lastT) return false;

    const rounded = roundSample(sample);
    this.t.push(round(t, 3) as number);
    for (const key of FRAME_COLUMNS) {
      this.columns[key].push(rounded[key]);
    }
    this.lastT = t;
    return true;
  }

  /** Convenience for a tick where nothing was measured (e.g. face lost). */
  appendEmpty(t: number): boolean {
    return this.appendSample(t, EMPTY_SAMPLE);
  }

  openGapAt(start: number, reason: GapReason): void {
    if (this.openGap) return; // already inside a gap; ignore a duplicate open
    this.openGap = { start, reason };
  }

  closeGapAt(end: number): void {
    if (!this.openGap) return;
    this.gapsList.push({ start: this.openGap.start, end, reason: this.openGap.reason });
    this.openGap = null;
  }

  get hasOpenGap(): boolean {
    return this.openGap !== null;
  }

  pushDegradation(degradation: Degradation): void {
    this.degradationsList.push(degradation);
  }

  /**
   * session_id, source, capture, clock (minus duration_s, filled
   * in here), calibration, context and setup_check come from the
   * caller, since they are decided by the setup screen and the
   * benchmark, not by the frame loop. durationS is measured by
   * the caller (existing recorder stop time minus t0). If a gap
   * is still open when the recording stops, it is closed at
   * durationS so it is never silently dropped.
   */
  build(params: {
    sessionId: string;
    source: Source;
    capture: Capture;
    clockUncertaintyMs: number;
    durationS: number;
    calibration: Calibration;
    context: Context;
    setupCheck: SetupCheck;
  }): VisualSignalTrack {
    if (this.openGap) {
      this.closeGapAt(params.durationS);
    }

    const frames: Frames = { t: [...this.t] } as Frames;
    for (const key of FRAME_COLUMNS) {
      frames[key] = [...this.columns[key]];
    }

    return {
      schema: "debatecoach.visual_signals",
      schema_version: "1.0",
      session_id: params.sessionId,
      source: params.source,
      capture: params.capture,
      clock: {
        t0_reference: "audio_recording_start",
        sync_method: "mediarecorder_start_event",
        uncertainty_ms: params.clockUncertaintyMs,
        duration_s: params.durationS,
      },
      calibration: params.calibration,
      context: params.context,
      setup_check: params.setupCheck,
      frames,
      gaps: [...this.gapsList],
      degradations: [...this.degradationsList],
    };
  }
}
