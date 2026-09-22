import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api } from '@/api/http'
import type {
  BatchDockingRequest,
  BatchJobCreated,
  BatchJobResult,
  BatchJobStatus,
  BatchLigandProgress,
  DockingDefaults,
  DockingJobResult,
  DockingJobStatus,
  DockingRequest,
  DockingStatus,
  PoseInfo,
} from '@/types/api'

/** Extended status that includes 'idle' for when no job is active. */
type ExtendedDockingStatus = DockingStatus | 'idle'

export const useDockingStore = defineStore('docking', () => {
  // -- form defaults --------------------------------------------------------
  const defaults = ref<DockingDefaults | null>(null)

  // -- active job -----------------------------------------------------------
  const activeJobId = ref<string | null>(null)
  const jobStatus = ref<DockingJobStatus | null>(null)
  const jobResult = ref<DockingJobResult | null>(null)

  // -- pose navigation -----------------------------------------------------
  const currentPoseIndex = ref<number>(0)

  // -- batch job ------------------------------------------------------------
  const activeBatchId = ref<string | null>(null)
  const batchStatus = ref<BatchJobStatus | null>(null)
  const batchResult = ref<BatchJobResult | null>(null)

  // -- computed -------------------------------------------------------------
  const status = computed<ExtendedDockingStatus>(() => jobStatus.value?.status ?? 'idle')
  const progress = computed(() => jobStatus.value?.progress ?? 0)
  const stage = computed(() => jobStatus.value?.stage ?? null)
  const logLines = computed(() => {
    const base = jobStatus.value?.log ?? []
    const result = jobResult.value
    if (!result || result.status !== 'completed') return base
    // Append the energy table Vina's Python API omits; the log is text-only
    // so a plain table is both parseable and human-friendly.
    const rows = result.poses.map(
      (p) => `  ${String(p.index).padStart(2)} | ${p.affinity.toFixed(3).padStart(8)} | ${p.rmsdLower.toFixed(3).padStart(6)} | ${p.rmsdUpper.toFixed(3).padStart(6)}`,
    )
    return [
      ...base,
      '--- results ---',
      ` pose | affinity  | rmsd_lb  | rmsd_ub`,
      ...rows,
    ]
  })
  const error = computed(() => jobStatus.value?.error ?? null)
  const poses = computed<PoseInfo[]>(() => jobResult.value?.poses ?? [])
  const bestAffinity = computed(() => jobResult.value?.bestAffinity ?? null)
  const elapsedMs = computed(() => jobStatus.value?.elapsedMs ?? jobResult.value?.elapsedMs ?? null)
  const isRunning = computed(() => status.value === 'running' || status.value === 'queued')
  const isCompleted = computed(() => status.value === 'completed')
  const hasResult = computed(() => jobResult.value !== null)

  // -- pose navigation -----------------------------------------------------
  const currentPose = computed<PoseInfo | null>(() => {
    const all = poses.value
    if (all.length === 0) return null
    const idx = Math.max(0, Math.min(currentPoseIndex.value, all.length - 1))
    return all[idx] ?? null
  })

  /** Individual pose SDF strings extracted from the multi-molecule posesSdf. */
  const poseSdfStrings = computed<string[]>(() => {
    const sdf = jobResult.value?.posesSdf
    if (!sdf) return []
    // SDF molecules are separated by $$$$ line
    const molecules = sdf.split(/\$\$\$\$\n?/)
      .map(s => s.trim())
      .filter(s => s.length > 0)
    return molecules
  })

  /** SDF string for the currently selected pose. */
  const currentPoseSdf = computed<string | null>(() => {
    const strings = poseSdfStrings.value
    if (strings.length === 0) return null
    const idx = Math.max(0, Math.min(currentPoseIndex.value, strings.length - 1))
    return strings[idx] ?? null
  })

  // -- batch computed -------------------------------------------------------
  const batchStatusStr = computed(() => (batchStatus.value?.status ?? 'idle') as ExtendedDockingStatus)
  const batchProgress = computed(() => batchStatus.value?.progress ?? 0)
  const batchCompleted = computed(() => batchStatus.value?.completedLigands ?? 0)
  const batchFailed = computed(() => batchStatus.value?.failedLigands ?? 0)
  const batchTotal = computed(() => batchStatus.value?.totalLigands ?? 0)
  const batchCurrentLigand = computed(() => batchStatus.value?.currentLigand ?? '')
  const batchLigands = computed<BatchLigandProgress[]>(() => batchStatus.value?.ligands ?? [])
  const batchIsRunning = computed(() => batchStatusStr.value === 'running' || batchStatusStr.value === 'queued')
  const batchIsCompleted = computed(() => batchStatusStr.value === 'completed')
  const batchHasResult = computed(() => batchResult.value !== null)
  const batchError = computed(() => batchStatus.value?.error ?? null)
  const batchElapsedMs = computed(() => batchStatus.value?.elapsedMs ?? batchResult.value?.elapsedMs ?? null)

  // -- actions --------------------------------------------------------------

  async function loadDefaults(): Promise<void> {
    defaults.value = await api.dockingDefaults()
  }

  async function startDocking(params: DockingRequest): Promise<string | null> {
    try {
      const result = await api.startDocking(params)
      activeJobId.value = result.jobId
      jobStatus.value = {
        jobId: result.jobId,
        status: 'queued',
        progress: 0,
        stage: null,
        log: [],
        error: null,
        elapsedMs: null,
      }
      jobResult.value = null
      return result.jobId
    } catch {
      return null
    }
  }

  async function refreshStatus(): Promise<void> {
    if (!activeJobId.value) return
    try {
      jobStatus.value = await api.dockingJobStatus(activeJobId.value)
      if (jobStatus.value.status === 'completed') {
        jobResult.value = await api.dockingJobResult(activeJobId.value)
      }
    } catch {
      // Job may have been cleaned up
    }
  }

  async function cancel(): Promise<void> {
    if (!activeJobId.value) return
    try {
      await api.cancelDocking(activeJobId.value)
      await refreshStatus()
    } catch {
      // ignore
    }
  }

  function reset(): void {
    activeJobId.value = null
    jobStatus.value = null
    jobResult.value = null
    currentPoseIndex.value = 0
  }

  function selectPose(index: number): void {
    const all = poses.value
    if (all.length === 0) return
    currentPoseIndex.value = Math.max(0, Math.min(index, all.length - 1))
  }

  function nextPose(): void {
    const all = poses.value
    if (all.length === 0) return
    if (currentPoseIndex.value < all.length - 1) {
      currentPoseIndex.value += 1
    }
  }

  function prevPose(): void {
    if (currentPoseIndex.value > 0) {
      currentPoseIndex.value -= 1
    }
  }

  async function startBatch(params: BatchDockingRequest): Promise<BatchJobCreated | null> {
    try {
      const result = await api.batchDocking(params)
      activeBatchId.value = result.jobId
      batchStatus.value = {
        jobId: result.jobId,
        status: 'queued',
        progress: 0,
        totalLigands: result.total,
        completedLigands: 0,
        failedLigands: 0,
        currentLigand: '',
        ligands: [],
        error: null,
        elapsedMs: null,
      }
      batchResult.value = null
      return result
    } catch {
      return null
    }
  }

  async function refreshBatchStatus(): Promise<void> {
    if (!activeBatchId.value) return
    try {
      batchStatus.value = await api.batchStatus(activeBatchId.value)
      if (batchStatus.value?.status === 'completed') {
        batchResult.value = await api.batchResult(activeBatchId.value)
      }
    } catch {
      // Job may have been cleaned up
    }
  }

  async function cancelBatch(): Promise<void> {
    if (!activeBatchId.value) return
    try {
      await api.cancelDocking(activeBatchId.value)
      await refreshBatchStatus()
    } catch {
      // ignore
    }
  }

  function resetBatch(): void {
    activeBatchId.value = null
    batchStatus.value = null
    batchResult.value = null
  }

  function handleWsEvent(event: Record<string, unknown>): void {
    const jobId = event.jobId as string | undefined
    if (!jobId) return

    // Handle single job events. The worker's own `type` is the event kind
    // (stage/progress/log/completed/failed).
    if (jobId === activeJobId.value) {
      const kind = event.type as string
      if (kind === 'stage' && event.stage && jobStatus.value) {
        jobStatus.value.stage = event.stage as string
      }
      if (kind === 'progress' && typeof event.percent === 'number' && jobStatus.value) {
        jobStatus.value.progress = event.percent
      }
      if (kind === 'log' && typeof event.line === 'string' && jobStatus.value) {
        jobStatus.value.log.push(event.line)
        if (jobStatus.value.log.length > 500) {
          jobStatus.value.log = jobStatus.value.log.slice(-500)
        }
      }
      if (kind === 'completed' || kind === 'failed') {
        refreshStatus()
      }
    }

    // Handle batch job events
    if (jobId === activeBatchId.value) {
      const kind = event.type as string
      if (kind === 'batch_progress' || kind === 'ligand_completed'
        || kind === 'completed' || kind === 'failed') {
        refreshBatchStatus()
      }
    }
  }

  return {
    defaults,
    activeJobId,
    jobStatus,
    jobResult,
    status,
    progress,
    stage,
    logLines,
    error,
    poses,
    bestAffinity,
    elapsedMs,
    isRunning,
    isCompleted,
    hasResult,
    // pose navigation
    currentPoseIndex,
    currentPose,
    poseSdfStrings,
    currentPoseSdf,
    selectPose,
    nextPose,
    prevPose,
    loadDefaults,
    startDocking,
    refreshStatus,
    cancel,
    reset,
    // batch
    activeBatchId,
    batchStatus,
    batchResult,
    batchStatusStr,
    batchProgress,
    batchCompleted,
    batchFailed,
    batchTotal,
    batchCurrentLigand,
    batchLigands,
    batchIsRunning,
    batchIsCompleted,
    batchHasResult,
    batchError,
    batchElapsedMs,
    startBatch,
    refreshBatchStatus,
    cancelBatch,
    resetBatch,
    handleWsEvent,
  }
})
