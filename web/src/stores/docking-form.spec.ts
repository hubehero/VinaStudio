import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useDockingFormStore } from './docking-form'

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('docking form persistence', () => {
  it('retains the live protocol across a route component remount', () => {
    const form = useDockingFormStore()
    form.exhaustiveness = 32
    form.seed = 42
    form.mapPathsRaw = '/maps/receptor'
    form.weightsRaw = '1, 2, 3'

    const snapshot = form.snapshot()

    expect(snapshot.exhaustiveness).toBe(32)
    expect(snapshot.seed).toBe(42)
    expect(snapshot.mapPaths).toEqual(['/maps/receptor'])
    expect(snapshot.weights).toEqual([1, 2, 3])
  })

  it('restores a saved project protocol without leaking ensemble ids', () => {
    const form = useDockingFormStore()
    form.ensembleMode = true
    form.ensembleReceptorIds = ['one', 'two']

    form.applyProject({
      scoring: 'vinardo',
      exhaustiveness: 16,
      nPoses: 12,
      energyRange: 2.5,
      minRmsd: 1.2,
      cpu: 2,
      seed: 7,
      noRefine: true,
      maxEvals: 1000,
      verbosity: 0,
      mapPaths: null,
      weights: [1, 2],
    })

    expect(form.scoring).toBe('vinardo')
    expect(form.exhaustiveness).toBe(16)
    expect(form.seed).toBe(7)
    expect(form.weightsRaw).toBe('1,2')
    expect(form.ensembleMode).toBe(false)
    expect(form.ensembleReceptorIds).toEqual([])
  })
})
