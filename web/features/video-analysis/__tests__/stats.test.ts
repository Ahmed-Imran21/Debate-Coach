import { describe, expect, it } from "vitest";

import { clamp, meanAbsoluteDeviation, median } from "../stats";

describe("median", () => {
  it("returns the middle value for an odd-length list", () => {
    expect(median([3, 1, 2])).toBe(2);
  });

  it("averages the two middle values for an even-length list", () => {
    expect(median([1, 2, 3, 4])).toBe(2.5);
  });

  it("does not mutate the input", () => {
    const input = [3, 1, 2];
    median(input);
    expect(input).toEqual([3, 1, 2]);
  });

  it("returns NaN for an empty list", () => {
    expect(median([])).toBeNaN();
  });
});

describe("meanAbsoluteDeviation", () => {
  it("is zero when every value equals the center", () => {
    expect(meanAbsoluteDeviation([5, 5, 5], 5)).toBe(0);
  });

  it("averages absolute distances from the center", () => {
    expect(meanAbsoluteDeviation([0, 10], 5)).toBe(5);
    expect(meanAbsoluteDeviation([1, 2, 3], 2)).toBeCloseTo(0.667, 3);
  });
});

describe("clamp", () => {
  it("passes values through unchanged when inside range", () => {
    expect(clamp(5, 0, 10)).toBe(5);
  });

  it("clamps to the bounds", () => {
    expect(clamp(-1, 0, 10)).toBe(0);
    expect(clamp(11, 0, 10)).toBe(10);
  });
});
