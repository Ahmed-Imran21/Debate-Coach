import { describe, expect, it } from "vitest";

import { clamp, meanAbsoluteDeviation, median, percentile90 } from "../stats";

describe("percentile90", () => {
  it("returns the 90th percentile by nearest rank", () => {
    // 10 values 1..10: ceil(0.9*10)-1 = 8 -> index 8 -> value 9
    expect(percentile90([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])).toBe(9);
  });

  it("does not mutate the input", () => {
    const input = [5, 1, 3];
    percentile90(input);
    expect(input).toEqual([5, 1, 3]);
  });

  it("handles an unsorted single-value list", () => {
    expect(percentile90([42])).toBe(42);
  });

  it("returns NaN for an empty list", () => {
    expect(percentile90([])).toBeNaN();
  });
});

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
