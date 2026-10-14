import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/api/http'
import type {
  LibraryDetail,
  LibraryImportResult,
  LibrarySummary,
  RankingResponse,
  RankingRow,
  RankingSortBy,
  ScreeningRunStatus,
  ScreeningRunSummary,
  ScreeningStartRequest,
} from '@/types/api'

export const useScreeningStore = defineStore('screening', () => {
  // -- libraries -------------------------------------------------------------
  const libraries = ref<LibrarySummary[]>([])
  const librariesLoading = ref(false)
  const librariesError = ref(false)
  const activeLibraryName = ref<string | null>(null)
  const libraryDetail = ref<LibraryDetail | null>(null)
  const libraryLoading = ref(false)
  const libraryError = ref(false)

  // -- runs ------------------------------------------------------------------
  const runs = ref<ScreeningRunSummary[]>([])
  const activeRunId = ref<string | null>(null)
  /** Polling target; null until the first status fetch lands. */
  const runStatus = ref<ScreeningRunStatus | null>(null)
  const runsLoading = ref(false)
  const runsError = ref(false)

  // -- ranking ---------------------------------------------------------------
  const ranking = ref<RankingRow[]>([])
  const rankingTotal = ref(0)
  const rankingSortBy = ref<RankingSortBy>('affinity')
  const rankingTop = ref(100)
  const rankingLoading = ref(false)
  const rankingError = ref(false)
  /** Dropped responses must not land after the user switched run/sort. */
  let rankingSeq = 0

  // -- actions: libraries ----------------------------------------------------
  async function loadLibraries(): Promise<void> {
    librariesLoading.value = true
    librariesError.value = false
    try {
      libraries.value = await api.screeningLibraries()
    } catch {
      librariesError.value = true
    } finally {
      librariesLoading.value = false
    }
  }

  function importLibrary(payload: FormData): Promise<LibraryImportResult> {
    return api.screeningImport(payload)
  }

  async function selectLibrary(name: string | null): Promise<void> {
    activeLibraryName.value = name
    libraryDetail.value = null
    libraryError.value = false
    if (name === null) {
      return
    }
    libraryLoading.value = true
    try {
      const detail = await api.screeningLibrary(name)
      // A later switch wins; the stale response is dropped, not applied.
      if (activeLibraryName.value === name) {
        libraryDetail.value = detail
      }
    } catch {
      if (activeLibraryName.value === name) {
        libraryError.value = true
      }
    } finally {
      libraryLoading.value = false
    }
  }

  // -- actions: runs ---------------------------------------------------------
  async function loadRuns(): Promise<void> {
    runsLoading.value = true
    runsError.value = false
    try {
      runs.value = await api.screeningRuns()
      // First load (no active run yet) auto-selects the newest row so the
      // status and ranking cards populate without a click (design §3).
      if (activeRunId.value === null) {
        const latest = runs.value[0]?.jobId
        if (latest !== undefined) {
          await selectRun(latest)
        }
      }
    } catch {
      runsError.value = true
    } finally {
      runsLoading.value = false
    }
  }

  /** Select a run: fetch its status + ranking; poll if it is live. */
  async function selectRun(id: string): Promise<void> {
    if (id === activeRunId.value && runStatus.value !== null) {
      return
    }
    stopPolling()
    activeRunId.value = id
    runStatus.value = null
    await Promise.all([refreshRun(id), loadRanking()])
    maybePoll(id)
  }

  /** Read the freshest status outside this frame's null-narrowing. */
  function maybePoll(id: string): void {
    const status = runStatus.value
    if (status !== null && status.status === 'running') {
      startPolling(id)
    }
  }

  /**
   * Single status fetch. Fetch failures are swallowed on purpose: the poll
   * keeps retrying while runStatus is null-or-running, and a vanished job
   * degrades to the empty state instead of an error storm (design §3).
   */
  async function refreshRun(id: string): Promise<void> {
    try {
      const status = await api.screeningRun(id)
      runs.value = runs.value.map((row) => (row.jobId === id ? status : row))
      if (activeRunId.value === id) {
        runStatus.value = status
      }
    } catch {
      // see docstring
    }
  }

  async function startRun(params: ScreeningStartRequest): Promise<{ jobId: string }> {
    const created = await api.screeningStart(params)
    activeRunId.value = created.jobId
    runStatus.value = null
    await Promise.all([loadRuns(), refreshRun(created.jobId), loadRanking()])
    maybePoll(created.jobId)
    return created
  }

  async function resumeRun(id: string): Promise<void> {
    const status = await api.screeningResume(id)
    stopPolling()
    // Resuming switches the watch target: the user resumes to follow progress.
    activeRunId.value = id
    runStatus.value = status
    runs.value = runs.value.map((row) => (row.jobId === id ? status : row))
    await loadRanking()
    if (status.status === 'running') {
      startPolling(id)
    }
  }

  async function cancelRun(id: string): Promise<void> {
    await api.screeningCancel(id)
    if (activeRunId.value === id) {
      stopPolling()
      await refreshRun(id)
      await loadRanking()
    } else {
      await refreshRun(id)
    }
  }

  // -- actions: polling ------------------------------------------------------
  // Polling lives in the store (not the view): cards share one timer and the
  // interval outlives component remounts (design §3, docking-store precedent).
  let pollTimer: ReturnType<typeof setInterval> | null = null
  const POLL_INTERVAL_MS = 1_000

  function startPolling(id: string): void {
    stopPolling()
    pollTimer = setInterval(() => {
      void pollTick(id)
    }, POLL_INTERVAL_MS)
  }

  function stopPolling(): void {
    if (pollTimer !== null) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function pollTick(id: string): Promise<void> {
    if (activeRunId.value !== id) {
      stopPolling()
      return
    }
    await refreshRun(id)
    const status = runStatus.value
    if (status !== null && status.status !== 'running') {
      stopPolling()
      await loadRanking()
    }
  }

  // -- actions: ranking ------------------------------------------------------
  async function loadRanking(): Promise<void> {
    const id = activeRunId.value
    if (id === null) {
      ranking.value = []
      rankingTotal.value = 0
      return
    }
    const seq = ++rankingSeq
    rankingLoading.value = true
    rankingError.value = false
    try {
      const response: RankingResponse = await api.screeningRanking(
        id,
        rankingSortBy.value,
        rankingTop.value,
      )
      if (seq !== rankingSeq) {
        return
      }
      ranking.value = response.rows
      rankingTotal.value = response.total
    } catch {
      if (seq === rankingSeq) {
        rankingError.value = true
      }
    } finally {
      if (seq === rankingSeq) {
        rankingLoading.value = false
      }
    }
  }

  function exportRankingCsv(): Promise<{ csv: string; filename: string }> {
    const id = activeRunId.value
    if (id === null) {
      return Promise.reject(new Error('no active screening run'))
    }
    return api.screeningExportRanking(id, rankingSortBy.value, rankingTop.value)
  }

  return {
    libraries,
    librariesLoading,
    librariesError,
    activeLibraryName,
    libraryDetail,
    libraryLoading,
    libraryError,
    runs,
    activeRunId,
    runStatus,
    runsLoading,
    runsError,
    ranking,
    rankingTotal,
    rankingSortBy,
    rankingTop,
    rankingLoading,
    rankingError,
    loadLibraries,
    importLibrary,
    selectLibrary,
    loadRuns,
    startRun,
    selectRun,
    refreshRun,
    resumeRun,
    cancelRun,
    startPolling,
    stopPolling,
    loadRanking,
    exportRankingCsv,
  }
})
