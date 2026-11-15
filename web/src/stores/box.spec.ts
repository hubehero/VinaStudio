import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useBoxStore } from './box'

beforeEach(() => {
  setActivePinia(createPinia())
  // The debounced measurement would call the API; these tests only check the
  // source transition, so keep the timer from firing.
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('box provenance', () => {
  it('starts unknown and becomes manual after an edit', () => {
    const box = useBoxStore()
    expect(box.source).toBe('unknown')

    box.setCenterAxis(0, 10)
    expect(box.source).toBe('manual')

    box.setSizeAxis(1, 25)
    expect(box.source).toBe('manual')
  })

  it('returns to unknown on reset', () => {
    const box = useBoxStore()
    box.setCenterAxis(2, 5)
    box.reset()
    expect(box.source).toBe('unknown')
  })
})
