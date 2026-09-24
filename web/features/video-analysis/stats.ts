/** Small pure numeric helpers for calibration (§4.9) and the benchmark/scheduler (§4.7, §4.9.2). */

/** Nearest-rank 90th percentile. Does not mutate the input. */
export function percentile90(values: readonly number[]): number {
  if (values.length === 0) return NaN;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.ceil(0.9 * sorted.length) - 1);
  return sorted[Math.max(0, index)];
}

export function median(values: readonly number[]): number {
  if (values.length === 0) return NaN;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

export function meanAbsoluteDeviation(values: readonly number[], center: number): number {
  if (values.length === 0) return NaN;
  return values.reduce((sum, v) => sum + Math.abs(v - center), 0) / values.length;
}

export function clamp(value: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, value));
}
