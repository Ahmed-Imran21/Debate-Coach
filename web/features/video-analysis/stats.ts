/** Small pure numeric helpers for calibration (§4.9). */

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
