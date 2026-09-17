import { describe, expect, it } from "vitest";

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
} from "../math";

// ---------------------------------------------------------------
// Head pose
// ---------------------------------------------------------------

/**
 * Builds the same flattened 4x4 matrix headPoseFromMatrix expects
 * (column-major), for R = Ry(yaw) * Rx(pitch) * Rz(roll), verified
 * numerically to be the correct forward composition that the
 * production decomposition formula inverts (see PHASE0 notes).
 * This proves the math is internally consistent; it cannot prove
 * it matches MediaPipe's actual matrix — that needs the debug
 * page and a real camera (file header of math.ts).
 */
function buildMatrixData(yawDeg: number, pitchDeg: number, rollDeg: number): number[] {
  const d2r = Math.PI / 180;
  const yaw = yawDeg * d2r;
  const pitch = pitchDeg * d2r;
  const roll = rollDeg * d2r;

  const mul3 = (a: number[][], b: number[][]): number[][] =>
    a.map((row, i) => row.map((_, j) => row.reduce((sum, _v, k) => sum + a[i][k] * b[k][j], 0)));

  const rx = [
    [1, 0, 0],
    [0, Math.cos(pitch), -Math.sin(pitch)],
    [0, Math.sin(pitch), Math.cos(pitch)],
  ];
  const ry = [
    [Math.cos(yaw), 0, Math.sin(yaw)],
    [0, 1, 0],
    [-Math.sin(yaw), 0, Math.cos(yaw)],
  ];
  const rz = [
    [Math.cos(roll), -Math.sin(roll), 0],
    [Math.sin(roll), Math.cos(roll), 0],
    [0, 0, 1],
  ];

  const r = mul3(mul3(ry, rx), rz);

  // Column-major 4x4 flatten (translation column/row are identity;
  // rotation extraction ignores them).
  const m = [
    [r[0][0], r[0][1], r[0][2], 0],
    [r[1][0], r[1][1], r[1][2], 0],
    [r[2][0], r[2][1], r[2][2], 0],
    [0, 0, 0, 1],
  ];
  const flat: number[] = [];
  for (let col = 0; col < 4; col++) {
    for (let row = 0; row < 4; row++) {
      flat.push(m[row][col]);
    }
  }
  return flat;
}

describe("headPoseFromMatrix", () => {
  it("identity matrix yields zero yaw/pitch/roll", () => {
    const pose = headPoseFromMatrix(buildMatrixData(0, 0, 0));
    expect(pose.yaw).toBeCloseTo(0, 6);
    expect(pose.pitch).toBeCloseTo(0, 6);
    expect(pose.roll).toBeCloseTo(0, 6);
  });

  it("recovers a single-axis yaw rotation with the documented sign", () => {
    const pose = headPoseFromMatrix(buildMatrixData(30, 0, 0));
    expect(pose.yaw).toBeCloseTo(30, 4);
    expect(pose.pitch).toBeCloseTo(0, 4);
    expect(pose.roll).toBeCloseTo(0, 4);
  });

  it("recovers a single-axis pitch rotation with the documented sign", () => {
    const pose = headPoseFromMatrix(buildMatrixData(0, 20, 0));
    expect(pose.pitch).toBeCloseTo(20, 4);
    expect(pose.yaw).toBeCloseTo(0, 4);
    expect(pose.roll).toBeCloseTo(0, 4);
  });

  it("recovers a single-axis roll rotation with the documented sign", () => {
    const pose = headPoseFromMatrix(buildMatrixData(0, 0, 15));
    expect(pose.roll).toBeCloseTo(15, 4);
    expect(pose.yaw).toBeCloseTo(0, 4);
    expect(pose.pitch).toBeCloseTo(0, 4);
  });

  it("recovers combined rotations", () => {
    const pose = headPoseFromMatrix(buildMatrixData(-40, 30, -20));
    expect(pose.yaw).toBeCloseTo(-40, 3);
    expect(pose.pitch).toBeCloseTo(30, 3);
    expect(pose.roll).toBeCloseTo(-20, 3);
  });

  it("negative yaw stays negative (sign is preserved, not just magnitude)", () => {
    const positive = headPoseFromMatrix(buildMatrixData(25, 0, 0));
    const negative = headPoseFromMatrix(buildMatrixData(-25, 0, 0));
    expect(positive.yaw).toBeGreaterThan(0);
    expect(negative.yaw).toBeLessThan(0);
    expect(negative.yaw).toBeCloseTo(-positive.yaw, 4);
  });
});

// ---------------------------------------------------------------
// Iris offset
// ---------------------------------------------------------------

const W = 640;
const H = 360;

/** A minimal landmark set with just the 6 indices computeIrisOffset reads, both eyes symmetric. */
function eyeLandmarks(opts: {
  leftIrisDx?: number; // fraction of half-width, + = toward image-right
  rightIrisDx?: number;
  irisDy?: number; // fraction of half-height, + = toward image-bottom
  closed?: boolean;
}): Landmark[] {
  const lm: Landmark[] = new Array(479).fill(null).map(() => ({ x: 0, y: 0, z: 0 }));

  const set = (i: number, x: number, y: number) => {
    lm[i] = { x: x / W, y: y / H, z: 0 };
  };

  // Left eye (LEFT_EYE: outer=33, inner=133, upper=159, lower=145, iris=468)
  const lCx = 100, lCy = 100, lHalfW = 15, lHalfH = opts.closed ? 0.2 : 8;
  set(33, lCx - lHalfW, lCy);
  set(133, lCx + lHalfW, lCy);
  set(159, lCx, lCy - lHalfH);
  set(145, lCx, lCy + lHalfH);
  set(468, lCx + (opts.leftIrisDx ?? 0) * lHalfW, lCy + (opts.irisDy ?? 0) * lHalfH);

  // Right eye (RIGHT_EYE: outer=263, inner=362, upper=386, lower=374, iris=473)
  const rCx = 300, rCy = 100, rHalfW = 15, rHalfH = opts.closed ? 0.2 : 8;
  set(263, rCx - rHalfW, rCy);
  set(362, rCx + rHalfW, rCy);
  set(386, rCx, rCy - rHalfH);
  set(374, rCx, rCy + rHalfH);
  set(473, rCx + (opts.rightIrisDx ?? 0) * rHalfW, rCy + (opts.irisDy ?? 0) * rHalfH);

  return lm;
}

describe("computeIrisOffset", () => {
  it("centered iris in both eyes is (0, 0)", () => {
    const offset = computeIrisOffset(eyeLandmarks({}), W, H);
    expect(offset).not.toBeNull();
    expect(offset!.x).toBeCloseTo(0, 6);
    expect(offset!.y).toBeCloseTo(0, 6);
  });

  it("iris toward speaker's own right is positive x", () => {
    // In an unmirrored frame the speaker's right is image-left,
    // so the iris moves toward negative image-x (toward the
    // outer corner in our layout) to look to their own right.
    const offset = computeIrisOffset(
      eyeLandmarks({ leftIrisDx: -0.5, rightIrisDx: -0.5 }),
      W,
      H,
    );
    expect(offset!.x).toBeGreaterThan(0);
  });

  it("iris toward speaker's own left is negative x", () => {
    const offset = computeIrisOffset(
      eyeLandmarks({ leftIrisDx: 0.5, rightIrisDx: 0.5 }),
      W,
      H,
    );
    expect(offset!.x).toBeLessThan(0);
  });

  it("iris looking up is positive y", () => {
    const offset = computeIrisOffset(eyeLandmarks({ irisDy: -0.5 }), W, H);
    expect(offset!.y).toBeGreaterThan(0);
  });

  it("iris looking down is negative y", () => {
    const offset = computeIrisOffset(eyeLandmarks({ irisDy: 0.5 }), W, H);
    expect(offset!.y).toBeLessThan(0);
  });

  it("clamps extreme offsets to +/-1.5", () => {
    const offset = computeIrisOffset(eyeLandmarks({ leftIrisDx: -10, rightIrisDx: -10 }), W, H);
    expect(offset!.x).toBe(1.5);
  });

  it("closed eyes (height < 2px) yield null", () => {
    const offset = computeIrisOffset(eyeLandmarks({ closed: true }), W, H);
    expect(offset).toBeNull();
  });

  it("missing landmarks yield null rather than throwing", () => {
    expect(computeIrisOffset([], W, H)).toBeNull();
  });
});

// ---------------------------------------------------------------
// Face scale / center
// ---------------------------------------------------------------

describe("computeFaceScale", () => {
  it("is the outer-eye-corner distance over frame width", () => {
    const lm: Landmark[] = new Array(264).fill({ x: 0, y: 0, z: 0 });
    lm[33] = { x: 0.4, y: 0.5, z: 0 };
    lm[263] = { x: 0.6, y: 0.5, z: 0 };
    expect(computeFaceScale(lm, 640)).toBeCloseTo(0.2, 6);
  });

  it("returns null when a required landmark is missing", () => {
    expect(computeFaceScale([], 640)).toBeNull();
  });
});

describe("computeFaceCenter", () => {
  it("is the mean of all landmark coordinates", () => {
    const lm: Landmark[] = [
      { x: 0, y: 0, z: 0 },
      { x: 1, y: 1, z: 0 },
    ];
    expect(computeFaceCenter(lm)).toEqual({ cx: 0.5, cy: 0.5 });
  });

  it("returns null for an empty landmark list", () => {
    expect(computeFaceCenter([])).toBeNull();
  });
});

describe("selectPrimaryFace", () => {
  const faceA = { center: { cx: 0.2, cy: 0.5 }, scale: 0.05 };
  const faceB = { center: { cx: 0.7, cy: 0.5 }, scale: 0.09 };

  it("picks the face closest to the calibration baseline when one exists", () => {
    expect(selectPrimaryFace([faceA, faceB], { cx: 0.75, cy: 0.5 })).toBe(1);
    expect(selectPrimaryFace([faceA, faceB], { cx: 0.15, cy: 0.5 })).toBe(0);
  });

  it("picks the larger face when there is no baseline yet", () => {
    expect(selectPrimaryFace([faceA, faceB], null)).toBe(1);
  });

  it("returns 0 for zero or one face", () => {
    expect(selectPrimaryFace([], null)).toBe(0);
    expect(selectPrimaryFace([faceA], null)).toBe(0);
  });
});

// ---------------------------------------------------------------
// Hands
// ---------------------------------------------------------------

describe("computePalmCentroid", () => {
  it("is the mean of landmarks 0, 5, 9, 13, 17", () => {
    const lm: Landmark[] = new Array(21).fill({ x: 0, y: 0, z: 0 });
    for (const i of [0, 5, 9, 13, 17]) lm[i] = { x: 0.5, y: 0.5, z: 0 };
    expect(computePalmCentroid(lm)).toEqual({ cx: 0.5, cy: 0.5 });
  });

  it("returns null if any palm landmark is missing", () => {
    expect(computePalmCentroid(new Array(10).fill({ x: 0, y: 0, z: 0 }))).toBeNull();
  });
});

describe("assignTwoHandSides", () => {
  it("the smaller-cx hand (further image-left) is the speaker's right hand", () => {
    const a = { cx: 0.2 };
    const b = { cx: 0.7 };
    expect(assignTwoHandSides([a, b])).toEqual({ rh: a, lh: b });
    expect(assignTwoHandSides([b, a])).toEqual({ rh: a, lh: b });
  });
});

describe("resolveHandSideFromLabel", () => {
  it("with the default inverted mapping, MediaPipe 'Left' means the speaker's right hand", () => {
    expect(resolveHandSideFromLabel("Left", true)).toBe("rh");
    expect(resolveHandSideFromLabel("Right", true)).toBe("lh");
  });

  it("with inversion off, the label is taken at face value", () => {
    expect(resolveHandSideFromLabel("Right", false)).toBe("rh");
    expect(resolveHandSideFromLabel("Left", false)).toBe("lh");
  });
});
