/**
 * Pure derivation math: head pose, iris offset, face scale,
 * hand centroid and side assignment. No DOM, no MediaPipe
 * import — everything here takes plain numbers/arrays so it can
 * be unit tested with constructed data (see __tests__/math.test.ts)
 * and so a worker-based implementation could reuse it unchanged.
 *
 * IMPORTANT — head pose sign verification required:
 * rotationFromMatrix()'s layout assumption (column-major) and
 * the three *_SIGN constants below are a best-effort mapping to
 * MediaPipe's actual facial transformation matrix, which is not
 * documented precisely enough to be certain of from the SDK's
 * TypeScript types alone. They MUST be checked against a real
 * camera on the debug page (/dev/vision-debug, see
 * docs/video-analysis/MANUAL_TEST_PLAN.md) by turning your head
 * and confirming the sign of each reading, before this feature
 * is trusted. If a sign is backwards, flip only the matching
 * constant below — nothing else needs to change.
 */

export interface Point3 {
  x: number;
  y: number;
  z: number;
}

export type Landmark = Point3;

// ---------------------------------------------------------------
// Head pose
// ---------------------------------------------------------------

/**
 * MediaPipe's Matrix.data is documented only as "the values as a
 * flattened one-dimensional array" (no stated row/column-major
 * order). Assumed column-major here, matching the Eigen
 * convention MediaPipe's C++ core uses internally. If the debug
 * page shows axes that don't round-trip sensibly, this is the
 * other thing to flip (see file header).
 */
const MATRIX_IS_COLUMN_MAJOR = true;

export type Mat3 = readonly [
  readonly [number, number, number],
  readonly [number, number, number],
  readonly [number, number, number],
];

/** Top-left 3x3 rotation block of a flattened 4x4 (or larger) matrix. */
export function rotationFromMatrix(data: readonly number[], columns = 4): Mat3 {
  const at = (row: number, col: number): number =>
    MATRIX_IS_COLUMN_MAJOR ? data[col * columns + row] : data[row * columns + col];

  return [
    [at(0, 0), at(0, 1), at(0, 2)],
    [at(1, 0), at(1, 1), at(1, 2)],
    [at(2, 0), at(2, 1), at(2, 2)],
  ];
}

// Flip exactly one of these (+1 <-> -1) if the corresponding
// reading on the debug page runs backwards. See file header.
export const YAW_SIGN = 1;
export const PITCH_SIGN = 1;
export const ROLL_SIGN = 1;

const RAD_TO_DEG = 180 / Math.PI;

export interface HeadPose {
  yaw: number;
  pitch: number;
  roll: number;
}

/**
 * Euler angles from a rotation matrix, decomposed as
 * R = Ry(yaw) * Rx(pitch) * Rz(roll) (intrinsic yaw-pitch-roll,
 * the standard "head looking at camera" decomposition). Degrees,
 * unrounded; the track builder rounds to the schema's precision.
 *
 * Gimbal lock (pitch at +/-90 deg) is not specially handled:
 * a face pose that extreme means the face is barely visible
 * anyway, and the caller nulls out the frame when face_ok is
 * false rather than trusting the angle.
 */
export function headPoseFromRotation(rotation: Mat3): HeadPose {
  const pitchRad = Math.asin(clamp(-rotation[1][2], -1, 1));
  const yawRad = Math.atan2(rotation[0][2], rotation[2][2]);
  const rollRad = Math.atan2(rotation[1][0], rotation[1][1]);

  return {
    yaw: YAW_SIGN * yawRad * RAD_TO_DEG,
    pitch: PITCH_SIGN * pitchRad * RAD_TO_DEG,
    roll: ROLL_SIGN * rollRad * RAD_TO_DEG,
  };
}

export function headPoseFromMatrix(data: readonly number[], columns = 4): HeadPose {
  return headPoseFromRotation(rotationFromMatrix(data, columns));
}

function clamp(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, value));
}

// ---------------------------------------------------------------
// Iris offset
// ---------------------------------------------------------------

// 478-point Face Landmarker indices (task doc §4.8). Verified
// against the canonical MediaPipe face mesh iris topology.
export const LEFT_EYE = { outer: 33, inner: 133, upper: 159, lower: 145, iris: 468 };
export const RIGHT_EYE = { outer: 263, inner: 362, upper: 386, lower: 374, iris: 473 };

const MIN_EYE_HEIGHT_PX = 2;
const IRIS_CLAMP = 1.5;

export interface IrisOffset {
  x: number;
  y: number;
}

function eyeOffset(
  landmarks: readonly Landmark[],
  eye: typeof LEFT_EYE,
  frameWidth: number,
  frameHeight: number,
): { rawX: number; rawY: number; heightPx: number } | null {
  const outer = landmarks[eye.outer];
  const inner = landmarks[eye.inner];
  const upper = landmarks[eye.upper];
  const lower = landmarks[eye.lower];
  const iris = landmarks[eye.iris];
  if (!outer || !inner || !upper || !lower || !iris) return null;

  const outerX = outer.x * frameWidth;
  const innerX = inner.x * frameWidth;
  const upperY = upper.y * frameHeight;
  const lowerY = lower.y * frameHeight;
  const irisX = iris.x * frameWidth;
  const irisY = iris.y * frameHeight;

  const cx = (outerX + innerX) / 2;
  const halfW = Math.abs(outerX - innerX) / 2;
  const cy = (upperY + lowerY) / 2;
  const heightPx = Math.abs(upperY - lowerY);
  const halfH = Math.max(heightPx / 2, 1e-6);

  return {
    rawX: (irisX - cx) / Math.max(halfW, 1e-6),
    rawY: (irisY - cy) / halfH,
    heightPx,
  };
}

/**
 * Averaged, sign-corrected iris offset in [-1.5, 1.5], or null
 * if either eye is too close to closed to trust (blink).
 * Positive x: speaker looks toward their own right.
 * Positive y: speaker looks up.
 */
export function computeIrisOffset(
  landmarks: readonly Landmark[],
  frameWidth: number,
  frameHeight: number,
): IrisOffset | null {
  const left = eyeOffset(landmarks, LEFT_EYE, frameWidth, frameHeight);
  const right = eyeOffset(landmarks, RIGHT_EYE, frameWidth, frameHeight);
  if (!left || !right) return null;
  if (left.heightPx < MIN_EYE_HEIGHT_PX || right.heightPx < MIN_EYE_HEIGHT_PX) return null;

  const rawX = (left.rawX + right.rawX) / 2;
  const rawY = (left.rawY + right.rawY) / 2;

  return {
    x: clamp(-rawX, -IRIS_CLAMP, IRIS_CLAMP),
    y: clamp(-rawY, -IRIS_CLAMP, IRIS_CLAMP),
  };
}

// ---------------------------------------------------------------
// Face scale and center
// ---------------------------------------------------------------

const FACE_SCALE_LEFT = 33;
const FACE_SCALE_RIGHT = 263;

/** Outer-eye-corner distance in pixels, divided by frame width. */
export function computeFaceScale(landmarks: readonly Landmark[], frameWidth: number): number | null {
  const a = landmarks[FACE_SCALE_LEFT];
  const b = landmarks[FACE_SCALE_RIGHT];
  if (!a || !b) return null;
  const dx = (a.x - b.x) * frameWidth;
  const dy = (a.y - b.y) * frameWidth;
  return Math.hypot(dx, dy) / frameWidth;
}

/** Mean of every landmark's normalized x/y (unmirrored frame). */
export function computeFaceCenter(landmarks: readonly Landmark[]): { cx: number; cy: number } | null {
  if (landmarks.length === 0) return null;
  let sx = 0;
  let sy = 0;
  for (const lm of landmarks) {
    sx += lm.x;
    sy += lm.y;
  }
  return { cx: sx / landmarks.length, cy: sy / landmarks.length };
}

/**
 * Which detected face is "primary" when two are visible: the one
 * closest to the calibration baseline center, or (before
 * calibration) the larger face, by index into `faces`.
 */
export function selectPrimaryFace(
  faces: readonly { center: { cx: number; cy: number }; scale: number }[],
  baseline: { cx: number; cy: number } | null,
): number {
  if (faces.length <= 1) return 0;

  if (baseline) {
    let best = 0;
    let bestDist = Infinity;
    faces.forEach((face, index) => {
      const dist = Math.hypot(face.center.cx - baseline.cx, face.center.cy - baseline.cy);
      if (dist < bestDist) {
        bestDist = dist;
        best = index;
      }
    });
    return best;
  }

  let best = 0;
  faces.forEach((face, index) => {
    if (face.scale > faces[best].scale) best = index;
  });
  return best;
}

// ---------------------------------------------------------------
// Hands
// ---------------------------------------------------------------

const PALM_LANDMARKS = [0, 5, 9, 13, 17];

/** Mean of the palm landmarks, normalized x/y (unmirrored frame). */
export function computePalmCentroid(landmarks: readonly Landmark[]): { cx: number; cy: number } | null {
  let sx = 0;
  let sy = 0;
  let n = 0;
  for (const index of PALM_LANDMARKS) {
    const lm = landmarks[index];
    if (!lm) return null;
    sx += lm.x;
    sy += lm.y;
    n += 1;
  }
  return { cx: sx / n, cy: sy / n };
}

export type HandSide = "lh" | "rh";

/**
 * Two hands detected: the one further to image-left (smaller cx)
 * is the speaker's right hand, in an unmirrored frame (§4.8).
 */
export function assignTwoHandSides<T extends { cx: number }>(
  hands: readonly [T, T],
): { rh: T; lh: T } {
  return hands[0].cx <= hands[1].cx ? { rh: hands[0], lh: hands[1] } : { rh: hands[1], lh: hands[0] };
}

/**
 * One hand detected: fall back to MediaPipe's handedness label.
 * `inverted` accounts for MediaPipe assuming a mirrored selfie
 * image; flip it once if the calibration right-hand check fails
 * (config.HANDEDNESS_LABEL_INVERTED_DEFAULT).
 */
export function resolveHandSideFromLabel(label: "Left" | "Right", inverted: boolean): HandSide {
  const isRight = inverted ? label === "Left" : label === "Right";
  return isRight ? "rh" : "lh";
}
