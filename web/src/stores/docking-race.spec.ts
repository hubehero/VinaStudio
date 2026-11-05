import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const mocks = vi.hoisted(() => ({
  dockingJobStatus: vi.fn(),
  dockingJobResult: vi.fn(),
  clusterPoses: vi.fn(),
  batchProgress: vi.fn(),
  batchStatus: vi.fn(),
  batchResult: vi.fn(),
}))

vi.mock('@/api/http', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/http')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      ...mocks,
    },
  }
})

import { useDockingStore } from './docking'
import { useProjectStore } from './project'
import type {
  BatchJobStatus,
  ClusterResponse,
  DockingJobStatus,
} from '@/types/api'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

function status(jobId: string, state: DockingJobStatus['status'] = 'completed'): DockingJobStatus {
  return {
    jobId,
    status: state,
    progress: state === 'completed' ? 100 : 50,
    stage: null,
    log: [],
    error: null,
    elapsedMs: 10,
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('active job request races', () => {
  it('drops a completed response after the user switches jobs', async () => {
    const pending = deferred<DockingJobStatus>()
    mocks.dockingJobStatus.mockReturnValueOnce(pending.promise)
    const docking = useDockingStore()
    const record = vi.spyOn(useProjectStore(), 'recordResult')
    docking.activeJobId = 'A'
    docking.activeJobLabel = 'a'

    const request = docking.refreshStatus()
    docking.activeJobId = 'B'
    docking.activeJobLabel = 'b'
    pending.resolve(status('A'))
    await request

    expect(docking.jobStatus).toBeNull()
    expect(mocks.dockingJobResult).not.toHaveBeenCalled()
    expect(record).not.toHaveBeenCalled()
  })

  it('lets a newer poll win over a slower older poll', async () => {
    const first = deferred<DockingJobStatus>()
    const second = deferred<DockingJobStatus>()
    mocks.dockingJobStatus
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    const docking = useDockingStore()
    docking.activeJobId = 'A'

    const older = docking.refreshStatus()
    const newer = docking.refreshStatus()
    second.resolve(status('A', 'running'))
    await newer
    first.resolve(status('A'))
    await older

    expect(docking.jobStatus?.status).toBe('running')
    expect(mocks.dockingJobResult).not.toHaveBeenCalled()
  })

  it('drops a cluster response for a job the user left', async () => {
    const pending = deferred<ClusterResponse>()
    mocks.clusterPoses.mockReturnValueOnce(pending.promise)
    const docking = useDockingStore()
    docking.activeJobId = 'A'

    const request = docking.runCluster(2)
    docking.reset()
    docking.activeJobId = 'B'
    pending.resolve({ clusters: [], representatives: [] } as unknown as ClusterResponse)
    await request

    expect(docking.clusters).toBeNull()
    expect(docking.clustering).toBe(false)
  })

  it('drops a batch completion for a batch the user left', async () => {
    const progress = deferred<BatchJobStatus>()
    mocks.batchProgress.mockReturnValueOnce(progress.promise)
    const docking = useDockingStore()
    docking.activeBatchId = 'batch-A'

    const request = docking.refreshBatchStatus()
    docking.activeBatchId = 'batch-B'
    progress.resolve({
      jobId: 'batch-A',
      status: 'completed',
      progress: 100,
      totalLigands: 1,
      completedLigands: 1,
      failedLigands: 0,
      currentLigand: '',
      ligands: [],
      error: null,
      elapsedMs: 10,
    } as BatchJobStatus)
    await request

    expect(docking.batchStatus).toBeNull()
    expect(mocks.batchStatus).not.toHaveBeenCalled()
    expect(mocks.batchResult).not.toHaveBeenCalled()
  })
})
