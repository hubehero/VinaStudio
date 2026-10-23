import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useDockingStore } from './docking'
import type { DockingJobResult } from '@/types/api'

function resultWithPoses(count: number): DockingJobResult {
  const records = Array.from({ length: count }, (_, index) => `pose ${index + 1}\nM  END`)
  return {
    jobId: 'job',
    status: 'completed',
    poses: [],
    bestAffinity: -10,
    posesPdbqt: '',
    posesSdf: records.join('\n$$$$\n'),
    nPoses: count,
    scoring: 'vina',
    elapsedMs: 1,
    artifacts: [],
    params: {},
  } as DockingJobResult
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('pose overlay', () => {
  it('is empty while the overlay is off', () => {
    const docking = useDockingStore()
    docking.jobResult = resultWithPoses(3)

    expect(docking.overlayPoseSdfs).toEqual([])
  })

  it('caps a large result at the overlay limit', () => {
    const docking = useDockingStore()
    docking.jobResult = resultWithPoses(25)
    docking.overlayPoses = true

    expect(docking.poseSdfStrings).toHaveLength(25)
    expect(docking.overlayPoseSdfs).toHaveLength(docking.overlayPoseLimit)
  })

  it('resets the overlay when the active job is cleared', () => {
    const docking = useDockingStore()
    docking.jobResult = resultWithPoses(3)
    docking.overlayPoses = true

    docking.reset()

    expect(docking.overlayPoses).toBe(false)
    expect(docking.overlayPoseSdfs).toEqual([])
  })
})
