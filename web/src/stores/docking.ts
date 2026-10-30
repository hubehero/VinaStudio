import { defineStore } from 'pinia'
import { computed, onBeforeUnmount, ref } from 'vue'

import { api } from '@/api/http'
import { useProjectStore } from '@/stores/project'
import type {
  BatchDockingRequest,
  BatchJobCreated,
  BatchJobResult,
  BatchJobStatus,
  BatchLigandProgress,
  ClusterResponse,
  DockingDefaults,
  DockingJobResult,
  DockingJobStatus,
  DockingJobSummary,
  DockingRequest,
  DockingStatus,
  EnsembleDockingRequest,
  InteractionData,
  PoseInfo,
  PoseValidationItem,
  RmsdResponse,
  ValidatePosesResponse,
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
  /** True when jobResult came from Report/History rather than this run. */
  const isHistoryView = ref(false)
  /** Ligand filename for the result reference recorded on completion. */
  const activeJobLabel = ref('')

  // -- history (TASK-07) ----------------------------------------------------
  const jobSummaries = ref<DockingJobSummary[]>([])

  // -- pose navigation -----------------------------------------------------
  const currentPoseIndex = ref<number>(0)
  /** Overlay every pose (capped) instead of showing only the selected one. */
  const overlayPoses = ref(false)

  // -- geometric pose validation (TASK-02) ---------------------------------
  // Report-only health check: never re-docks or edits coordinates.
  const validation = ref<ValidatePosesResponse | null>(null)
  const validating = ref(false)
  const validationError = ref<string | null>(null)

  // -- redocking RMSD vs reference (TASK-03) -------------------------------
  // Report-only symmetry-corrected RMSD; kept alongside validation so the
  // CSV export can re-use the reference the user picked.
  const rmsd = ref<RmsdResponse | null>(null)
  const rmsding = ref(false)
  const rmsdError = ref<string | null>(null)
  const rmsdReferencePath = ref<string | null>(null)

  // -- pose clustering (TASK-04) --------------------------------------------
  // On-demand and cached in the front end — never written into the job
  // result (persistence is TASK-07's decision).
  const clusters = ref<ClusterResponse | null>(null)
  const clustering = ref(false)
  const clusterError = ref<string | null>(null)
  const clusterCutoff = ref<number>(2.0)
  const representativesOnly = ref(false)
  let clusterCacheKey: string | null = null

  // -- batch job ------------------------------------------------------------
  const activeBatchId = ref<string | null>(null)
  const batchStatus = ref<BatchJobStatus | null>(null)
  const batchResult = ref<BatchJobResult | null>(null)

  // -- interaction analysis snapshot (TASK-12) ------------------------------
  // DockView keeps the live analysis rows in a local ref (viewport draws
  // them). The snapshot copies each beat of that ref so the sequence view in
  // Molecules can still highlight contact residues after this route
  // unmounts; `sourcePath` is the pipeline receptor's source file at the
  // time of the write, gating consumers to the molecule the rows describe.
  const interactionRows = ref<InteractionData[]>([])
  const interactionSourcePath = ref<string | null>(null)

  /** Unique ``CHAIN:SEQ`` contact keys of the last analysis beat. */
  const contactResidueKeys = computed<string[]>(() => {
    const keys = new Set<string>()
    for (const row of interactionRows.value) {
      // Rows without chain or sequence number cannot name a sequence cell.
      if (row.receptorChain && row.receptorResSeq) {
        keys.add(`${row.receptorChain}:${row.receptorResSeq}`)
      }
    }
    return [...keys]
  })

  /** Single writer; DockView's watcher calls it with every local-ref beat. */
  function setInteractionSnapshot(rows: InteractionData[], sourcePath: string | null): void {
    interactionRows.value = [...rows]
    interactionSourcePath.value = sourcePath
  }

  // -- HTTP polling fallback ------------------------------------------------
  // WebSocket events are the primary channel, but if an event is missed
  // (connection hiccup, worker crash before pipe closes) the UI would freeze.
  // HTTP polling is the safety net: it runs at a low cadence and stops once
  // the job reaches a terminal state.
  let pollTimer: ReturnType<typeof setInterval> | null = null
  const POLL_INTERVAL_MS = 3_000

  function startPolling(jobId: string, kind: 'job' | 'batch'): void {
    stopPolling()
    pollTimer = setInterval(() => {
      if (kind === 'job' && jobId === activeJobId.value) {
        void refreshStatus()
      } else if (kind === 'batch' && jobId === activeBatchId.value) {
        void refreshBatchStatus()
      } else {
        stopPolling()
      }
    }, POLL_INTERVAL_MS)
  }

  function stopPolling(): void {
    if (pollTimer !== null) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  onBeforeUnmount(stopPolling)

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

  /** Hard cap keeps a 100-pose result from creating 100 WebGL models. */
  const OVERLAY_POSE_LIMIT = 20
  const overlayPoseSdfs = computed<string[]>(() =>
    overlayPoses.value ? poseSdfStrings.value.slice(0, OVERLAY_POSE_LIMIT) : [],
  )

  /** Validation item for the selected pose (1-based poseIndex on the wire). */
  const currentPoseValidation = computed<PoseValidationItem | null>(() => {
    const result = validation.value
    if (!result) return null
    const index = currentPoseIndex.value + 1
    return result.poses.find((p) => p.poseIndex === index) ?? null
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
      activeJobLabel.value = params.ligandPath ? basename(params.ligandPath) : ''
      jobStatus.value = {
        jobId: result.jobId,
        status: 'running',
        progress: 0,
        stage: null,
        log: [],
        error: null,
        elapsedMs: null,
      }
      jobResult.value = null
      isHistoryView.value = false
      startPolling(result.jobId, 'job')
      return result.jobId
    } catch {
      return null
    }
  }

  async function startEnsemble(params: EnsembleDockingRequest): Promise<string | null> {
    try {
      const result = await api.startEnsembleDocking(params)
      activeJobId.value = result.jobId
      activeJobLabel.value = params.ligandPath ? basename(params.ligandPath) : 'ensemble'
      jobStatus.value = {
        jobId: result.jobId,
        status: 'running',
        progress: 0,
        stage: null,
        log: [],
        error: null,
        elapsedMs: null,
      }
      jobResult.value = null
      isHistoryView.value = false
      startPolling(result.jobId, 'job')
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
        stopPolling()
        // Persist the reference into the open project (idempotent — polling
        // and the WebSocket path both land here).
        useProjectStore().recordResult(activeJobId.value, activeJobLabel.value)
      } else if (jobStatus.value.status === 'failed' || jobStatus.value.status === 'cancelled') {
        stopPolling()
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
    stopPolling()
    activeJobId.value = null
    activeJobLabel.value = ''
    jobStatus.value = null
    jobResult.value = null
    isHistoryView.value = false
    currentPoseIndex.value = 0
    overlayPoses.value = false
    validation.value = null
    validating.value = false
    validationError.value = null
    clearRmsd()
    clearClusters()
  }

  /**
   * Run the geometric health-check on this job's poses.
   *
   * Box and reference are optional: omitting them skips the corresponding
   * checks rather than failing. Callers pass what the UI currently has.
   */
  async function runValidation(options: {
    center?: [number, number, number] | null
    size?: [number, number, number] | null
    referenceSdfPath?: string | null
  } = {}): Promise<void> {
    if (!activeJobId.value) return
    validating.value = true
    validationError.value = null
    try {
      validation.value = await api.validatePoses(activeJobId.value, {
        center: options.center ?? null,
        size: options.size ?? null,
        referenceSdfPath: options.referenceSdfPath ?? null,
      })
    } catch (err) {
      validation.value = null
      validationError.value = err instanceof Error ? err.message : String(err)
    } finally {
      validating.value = false
    }
  }

  function clearValidation(): void {
    validation.value = null
    validationError.value = null
  }

  /**
   * Compute the symmetry-corrected RMSD of every pose against a reference
   * ligand. A structure mismatch comes back as ``structureMatch: false`` with
   * empty values — the caller surfaces it as a warning, not an error.
   */
  async function runRmsd(referencePath: string): Promise<void> {
    if (!activeJobId.value || !referencePath) return
    rmsding.value = true
    rmsdError.value = null
    rmsdReferencePath.value = referencePath
    try {
      rmsd.value = await api.jobRmsd(activeJobId.value, { referencePath })
    } catch (err) {
      rmsd.value = null
      rmsdError.value = err instanceof Error ? err.message : String(err)
    } finally {
      rmsding.value = false
    }
  }

  function clearRmsd(): void {
    rmsd.value = null
    rmsdError.value = null
    rmsdReferencePath.value = null
  }

  /**
   * Cluster this job's poses at *cutoff* (default: the slider's value).
   * Results are cached per `jobId:cutoff` so re-clicking with an unchanged
   * slider does not re-hit the API; changing the cutoff recomputes.
   */
  async function runCluster(cutoff: number = clusterCutoff.value): Promise<void> {
    if (!activeJobId.value) return
    clusterCutoff.value = cutoff
    const cacheKey = `${activeJobId.value}:${cutoff}`
    if (clusters.value && clusterCacheKey === cacheKey) return
    clustering.value = true
    clusterError.value = null
    try {
      clusters.value = await api.clusterPoses(activeJobId.value, { cutoff })
      clusterCacheKey = cacheKey
    } catch (err) {
      clusters.value = null
      clusterCacheKey = null
      clusterError.value = err instanceof Error ? err.message : String(err)
    } finally {
      clustering.value = false
    }
  }

  function clearClusters(): void {
    clusters.value = null
    clusterError.value = null
    clusterCacheKey = null
    representativesOnly.value = false
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

  /**
   * Advance from the current pose to the next cluster representative.
   *
   * Centroids are 0-based pose indices just like `currentPoseIndex`. The walk
   * goes forward and wraps to the first cluster so repeated clicks cycle
   * through representatives; with no clusters it does nothing and the toolbar
   * button stays disabled. Reuses the ordinary pose switch — no separate
   * rendering path.
   */
  function jumpToNextRepresentative(): void {
    const result = clusters.value
    if (!result || result.clusters.length === 0) return
    const centroids = [...new Set(result.clusters.map((c) => c.centroid))].sort(
      (a, b) => a - b,
    )
    const next = centroids.find((index) => index > currentPoseIndex.value)
    currentPoseIndex.value = next ?? centroids[0] ?? currentPoseIndex.value
  }

  async function startBatch(params: BatchDockingRequest): Promise<BatchJobCreated | null> {
    try {
      const result = await api.batchDocking(params)
      activeBatchId.value = result.jobId
      batchStatus.value = {
        jobId: result.jobId,
        status: 'running',
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
      startPolling(result.jobId, 'batch')
      return result
    } catch {
      return null
    }
  }

  async function refreshBatchStatus(): Promise<void> {
    if (!activeBatchId.value) return
    try {
      // Polling carries counters only; the full row array is fetched once on
      // completion for the results table, not every three seconds.
      const progress = await api.batchProgress(activeBatchId.value)
      batchStatus.value = {
        ...progress,
        ligands: batchStatus.value?.ligands ?? [],
      }
      if (progress.status === 'completed') {
        batchStatus.value = await api.batchStatus(activeBatchId.value)
        batchResult.value = await api.batchResult(activeBatchId.value)
        stopPolling()
        useProjectStore().recordResult(activeBatchId.value, '')
      } else if (progress.status === 'failed' || progress.status === 'cancelled') {
        batchStatus.value = await api.batchStatus(activeBatchId.value)
        stopPolling()
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
    stopPolling()
    activeBatchId.value = null
    batchStatus.value = null
    batchResult.value = null
  }

  function basename(path: string): string {
    const parts = path.split(/[\\/]/)
    return parts[parts.length - 1] || path
  }

  /** Refresh the history list (live + restored jobs share this endpoint). */
  async function fetchJobs(): Promise<void> {
    try {
      jobSummaries.value = await api.dockingJobs()
    } catch {
      jobSummaries.value = []
    }
  }

  /**
   * Open a finished (or still live) job from the history list as the active
   * view. Restored jobs replay from workspace artifacts, so their poses and
   * log are read exactly like a fresh completion; a live row keeps polling.
   */
  async function openHistoryJob(job: DockingJobSummary): Promise<void> {
    reset()
    activeJobId.value = job.jobId
    isHistoryView.value = true
    activeJobLabel.value = job.label
    try {
      jobStatus.value = await api.dockingJobStatus(job.jobId)
      const current = jobStatus.value.status
      if (current === 'completed') {
        jobResult.value = await api.dockingJobResult(job.jobId)
      } else if (current === 'running' || current === 'queued') {
        startPolling(job.jobId, 'job')
      }
    } catch {
      reset()
    }
  }

  /**
   * Rehydrate a batch job into the store so BatchDockingView (which reads
   * only store state) renders it; the caller navigates to /batch.
   */
  async function openHistoryBatch(job: DockingJobSummary): Promise<void> {
    resetBatch()
    activeBatchId.value = job.jobId
    try {
      batchStatus.value = await api.batchStatus(job.jobId)
      const current = batchStatus.value?.status
      if (current === 'completed') {
        batchResult.value = await api.batchResult(job.jobId)
      } else if (current === 'running' || current === 'queued') {
        startPolling(job.jobId, 'batch')
      }
    } catch {
      resetBatch()
    }
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
    // The active job's ligand label — the report card titles itself with it.
    activeJobLabel,
    jobStatus,
    jobResult,
    isHistoryView,
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
    overlayPoses,
    overlayPoseSdfs,
    overlayPoseLimit: OVERLAY_POSE_LIMIT,
    selectPose,
    nextPose,
    prevPose,
    jumpToNextRepresentative,
    // geometric validation
    validation,
    validating,
    validationError,
    currentPoseValidation,
    runValidation,
    clearValidation,
    // redocking RMSD
    rmsd,
    rmsding,
    rmsdError,
    rmsdReferencePath,
    runRmsd,
    clearRmsd,
    // pose clustering
    clusters,
    clustering,
    clusterError,
    clusterCutoff,
    representativesOnly,
    runCluster,
    clearClusters,
    loadDefaults,
    startDocking,
    startEnsemble,
    refreshStatus,
    cancel,
    reset,
    // history (TASK-07)
    jobSummaries,
    fetchJobs,
    openHistoryJob,
    openHistoryBatch,
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
    // interaction analysis snapshot (TASK-12)
    interactionRows,
    interactionSourcePath,
    contactResidueKeys,
    setInteractionSnapshot,
  }
})
