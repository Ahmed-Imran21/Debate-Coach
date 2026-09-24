import { describe, expect, it } from "vitest";

import { DISTANCE_SCALE_MAX, DISTANCE_SCALE_MIN, LIGHTING_DIM_LUMA } from "../config";
import {
  classifyDistance,
  classifyLighting,
  faceVisiblePasses,
  handsRaisedPasses,
  ratioTrue,
} from "../framing";

describe("ratioTrue", () => {
  it("computes the fraction of true values", () => {
    expect(ratioTrue([true, true, false, false])).toBe(0.5);
  });
  it("is 0 for an empty window", () => {
    expect(ratioTrue([])).toBe(0);
  });
});

describe("faceVisiblePasses", () => {
  it("passes at exactly the 80% threshold", () => {
    const flags = [...Array(16).fill(true), ...Array(4).fill(false)]; // 80%
    expect(faceVisiblePasses(flags)).toBe(true);
  });
  it("fails just under the threshold", () => {
    const flags = [...Array(15).fill(true), ...Array(5).fill(false)]; // 75%
    expect(faceVisiblePasses(flags)).toBe(false);
  });
});

describe("classifyDistance", () => {
  it("is ok within [min, max]", () => {
    expect(classifyDistance([DISTANCE_SCALE_MIN])).toBe("ok");
    expect(classifyDistance([DISTANCE_SCALE_MAX])).toBe("ok");
    expect(classifyDistance([(DISTANCE_SCALE_MIN + DISTANCE_SCALE_MAX) / 2])).toBe("ok");
  });
  it("is too_close above the max", () => {
    expect(classifyDistance([DISTANCE_SCALE_MAX + 0.01])).toBe("too_close");
  });
  it("is too_far below the min", () => {
    expect(classifyDistance([DISTANCE_SCALE_MIN - 0.01])).toBe("too_far");
  });
  it("is too_far with no samples", () => {
    expect(classifyDistance([])).toBe("too_far");
  });
  it("uses the median, so one outlier tick doesn't flip the result", () => {
    const scales = [0.09, 0.09, 0.09, 0.09, 0.3]; // one spurious close reading
    expect(classifyDistance(scales)).toBe("ok");
  });
});

describe("classifyLighting", () => {
  it("is ok in good light with no backlighting", () => {
    expect(classifyLighting(150, 140)).toBe("ok");
  });
  it("is dim when overall brightness is too low, even if faceLuma is unknown", () => {
    expect(classifyLighting(LIGHTING_DIM_LUMA - 1, null)).toBe("dim");
  });
  it("is backlit when the face is much darker than the background", () => {
    expect(classifyLighting(200, 100)).toBe("backlit"); // 100 < 200*0.6
  });
  it("dim takes precedence over backlit when both would apply", () => {
    expect(classifyLighting(LIGHTING_DIM_LUMA - 1, 1)).toBe("dim");
  });
  it("cannot assess backlighting without a face region reading", () => {
    expect(classifyLighting(150, null)).toBe("ok");
  });
});

describe("handsRaisedPasses", () => {
  it("passes at the 60% threshold", () => {
    const flags = [true, true, true, false, false]; // 60%
    expect(handsRaisedPasses(flags)).toBe(true);
  });
  it("fails below it", () => {
    const flags = [true, true, false, false, false]; // 40%
    expect(handsRaisedPasses(flags)).toBe(false);
  });
});
