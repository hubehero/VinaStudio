/**
 * Pure geometry/statistics helpers for the hand-rolled result charts.
 *
 * No dependencies and no DOM: the same functions are used by every figure in
 * `DockingCharts.vue`, so the axis and binning conventions stay identical
 * across charts (academic consistency — a reader must not have to work out
 * whether two figures binned or padded differently).
 */

/** Value domain with a guard so a zero-span series still produces a finite axis. */
export function padDomain([min, max]: [number, number], pad = 0.5): [number, number] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [-pad, pad]
  if (min === max) return [min - pad, max + pad]
  return [min, max]
}

export interface LinearScale {
  domain: [number, number]
  map: (value: number) => number
}

/** Linear map from a value domain onto a pixel range (range may be inverted). */
export function linearScale(domain: [number, number], range: [number, number]): LinearScale {
  const [d0, d1] = padDomain(domain)
  const [r0, r1] = range
  return {
    domain: [d0, d1],
    map: (value: number) => r0 + ((value - d0) / (d1 - d0)) * (r1 - r0),
  }
}

/**
 * "Nice" axis ticks at 1/2/5×10ⁿ steps, inside [min, max].
 *
 * `count` is a target, not a promise — the returned step is always a readable
 * decimal so labels never read like 0.30000000000000004.
 */
export function niceTicks(min: number, max: number, count = 4): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || count < 1) return []
  if (min === max) return [min]
  const [lo, hi] = min < max ? [min, max] : [max, min]
  const rawStep = (hi - lo) / count
  const magnitude = 10 ** Math.floor(Math.log10(rawStep))
  const normalized = rawStep / magnitude
  const step = (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude
  const ticks: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) {
    ticks.push(Number(v.toPrecision(12)))
  }
  return ticks
}

/** Sturges' rule — the conventional bin count for a small pose sample. */
export function sturgesBinCount(n: number): number {
  return Math.max(1, Math.ceil(Math.log2(Math.max(1, n)) + 1))
}

export interface HistogramBin {
  x0: number
  x1: number
  count: number
}

/**
 * Bin an ascending-independent series over [min, max]. The last bin is
 * closed on the right so the maximum value is counted, not dropped.
 */
export function histogram(values: number[], binCount: number): HistogramBin[] {
  if (values.length === 0 || binCount < 1) return []
  const min = Math.min(...values)
  const max = Math.max(...values)
  const lo = min
  const hi = max === min ? min + 1 : max
  const width = (hi - lo) / binCount
  const bins: HistogramBin[] = Array.from({ length: binCount }, (_, i) => ({
    x0: lo + i * width,
    x1: lo + (i + 1) * width,
    count: 0,
  }))
  for (const value of values) {
    let index = Math.floor((value - lo) / width)
    if (index < 0) index = 0
    if (index >= binCount) index = binCount - 1
    const bin = bins[index]
    if (bin) bin.count += 1
  }
  return bins
}

/** Mean and population standard deviation of a series (empty → zeros). */
export function meanSd(values: number[]): { mean: number; sd: number } {
  if (values.length === 0) return { mean: 0, sd: 0 }
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length
  return { mean, sd: Math.sqrt(variance) }
}

/** Fixed-decimal formatting used by every axis label and annotation. */
export function formatValue(value: number, digits = 2): string {
  if (!Number.isFinite(value)) return '—'
  return value.toFixed(digits)
}
