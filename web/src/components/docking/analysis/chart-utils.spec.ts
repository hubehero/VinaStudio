import { describe, expect, it } from 'vitest'

import { histogram, meanSd, sturgesBinCount } from './chart-utils'

describe('affinity summary statistics', () => {
  // The five values from the screenshot's 1iep job. The screenshot's SD label
  // cannot be 11.95: the whole range is only 2.616 kcal/mol.
  const values = [-13.221, -11.324, -10.878, -10.734, -10.605]

  it('computes the population mean and SD from the actual pose values', () => {
    const { mean, sd } = meanSd(values)

    expect(mean).toBeCloseTo(-11.3524, 4)
    expect(sd).toBeCloseTo(0.96525, 5)
    expect(sd).toBeLessThanOrEqual((Math.max(...values) - Math.min(...values)) / 2 + 1e-12)
  })

  it('keeps the histogram bin count and all five poses', () => {
    const bins = histogram(values, sturgesBinCount(values.length))

    expect(bins).toHaveLength(4)
    expect(bins.reduce((sum, bin) => sum + bin.count, 0)).toBe(values.length)
  })
})
