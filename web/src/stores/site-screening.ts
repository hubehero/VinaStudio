import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { ApiError, api } from '@/api/http'
import type { SiteRow, SiteScreeningRequest, SiteScreeningStatus } from '@/types/api'

/** One box per second: each candidate is a real docking run, so it takes seconds. */
const POLL_MS = 1000

/**
 * The site screen: one ligand docked into every candidate box, ranked (S2).
 *
 * The screen is a *job* on the backend, so this store only mirrors one run —
 * start it, follow it, read the ranking. Leaving the page does not cancel it:
 * the poll continues until the job settles, and the ranking is still there when
 * the user comes back.
 */
export const useSiteScreeningStore = defineStore('site-screening', () => {
  const jobId = ref<string | null>(null)
  const status = ref<SiteScreeningStatus | null>(null)
  const running = ref(false)
  const error = ref<string | null>(null)
  let timer: ReturnType<typeof setTimeout> | null = null

  const rows = computed<SiteRow[]>(() => status.value?.rows ?? [])
  const total = computed(() => status.value?.totalCandidates ?? 0)
  const done = computed(
    () =>
      (status.value?.completedCandidates ?? 0) + (status.value?.failedCandidates ?? 0),
  )
  /** The box that won *so far* — the table moves as rows land. */
  const best = computed<SiteRow | null>(() => rows.value.find((row) => row.rank === 1) ?? null)

  function stopTimer(): void {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  function describe(cause: unknown): string {
    return cause instanceof ApiError ? cause.message : String(cause)
  }

  async function poll(): Promise<void> {
    const id = jobId.value
    if (id === null) {
      return
    }
    try {
      const next = await api.siteScreenStatus(id)
      status.value = next
      if (next.status === 'running') {
        timer = setTimeout(() => void poll(), POLL_MS)
        return
      }
      running.value = false
    } catch (cause) {
      running.value = false
      error.value = describe(cause)
    }
  }

  /** Start a screen; returns false when the request itself was rejected. */
  async function start(request: SiteScreeningRequest): Promise<boolean> {
    stopTimer()
    error.value = null
    status.value = null
    running.value = true
    try {
      const created = await api.startSiteScreen(request)
      jobId.value = created.jobId
    } catch (cause) {
      running.value = false
      error.value = describe(cause)
      return false
    }
    await poll()
    return true
  }

  async function cancel(): Promise<void> {
    if (jobId.value === null) {
      return
    }
    try {
      await api.cancelSiteScreen(jobId.value)
    } catch (cause) {
      error.value = describe(cause)
    }
    stopTimer()
    running.value = false
    await poll()
  }

  /** Forget the run (the job itself stays in history). */
  function reset(): void {
    stopTimer()
    jobId.value = null
    status.value = null
    running.value = false
    error.value = null
  }

  return { jobId, status, running, error, rows, total, done, best, start, cancel, reset }
})
