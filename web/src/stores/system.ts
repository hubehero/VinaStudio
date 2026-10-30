import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { ApiError, api } from '@/api/http'
import type {
  Capabilities,
  CitationEntry,
  DiagnosticReport,
  Health,
  SelfCheck,
  SystemInfo,
} from '@/types/api'

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  return error instanceof Error ? error.message : String(error)
}

export const useSystemStore = defineStore('system', () => {
  const health = ref<Health | null>(null)
  const info = ref<SystemInfo | null>(null)
  const selfCheck = ref<SelfCheck | null>(null)
  const diagnostics = ref<DiagnosticReport | null>(null)
  const diagnosing = ref(false)
  const repairing = ref(false)
  const diagnosticError = ref<string | null>(null)
  const capabilities = ref<Capabilities | null>(null)
  const citations = ref<CitationEntry[]>([])

  const loading = ref(false)
  const checking = ref(false)
  const error = ref<string | null>(null)
  const lastCheckedAt = ref<number | null>(null)

  const reachable = computed(() => health.value?.status === 'ok')
  const dockingAvailable = computed(() => selfCheck.value?.dockingAvailable ?? null)
  const missingPackages = computed(() => selfCheck.value?.failed ?? [])

  async function refreshHealth(): Promise<void> {
    try {
      health.value = await api.health()
      if (!reachable.value) {
        error.value = null
      }
    } catch (cause) {
      health.value = null
      error.value = describeError(cause)
    }
  }

  async function refresh(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const [healthResult, infoResult, capabilitiesResult, citationResult] =
        await Promise.all([
          api.health(),
          api.systemInfo(),
          api.capabilities(),
          api.citations(),
        ])
      health.value = healthResult
      info.value = infoResult
      capabilities.value = capabilitiesResult
      citations.value = citationResult.entries
    } catch (cause) {
      error.value = describeError(cause)
    } finally {
      loading.value = false
      lastCheckedAt.value = Date.now()
    }
  }

  async function runDiagnostics(): Promise<void> {
    diagnosing.value = true
    diagnosticError.value = null
    try {
      diagnostics.value = await api.diagnostics()
    } catch (cause) {
      diagnostics.value = null
      diagnosticError.value = describeError(cause)
    } finally {
      diagnosing.value = false
    }
  }

  async function repairDiagnostics(): Promise<number> {
    repairing.value = true
    diagnosticError.value = null
    try {
      const report = await api.repairDiagnostics()
      diagnostics.value = report
      return report.repaired.length
    } catch (cause) {
      diagnosticError.value = describeError(cause)
      return 0
    } finally {
      repairing.value = false
    }
  }

  async function runSelfCheck(): Promise<void> {
    checking.value = true
    error.value = null
    try {
      selfCheck.value = await api.selfCheck()
    } catch (cause) {
      selfCheck.value = null
      error.value = describeError(cause)
    } finally {
      checking.value = false
      lastCheckedAt.value = Date.now()
    }
  }

  return {
    health,
    info,
    selfCheck,
    diagnostics,
    diagnosing,
    repairing,
    diagnosticError,
    capabilities,
    citations,
    loading,
    checking,
    error,
    lastCheckedAt,
    reachable,
    dockingAvailable,
    missingPackages,
    refreshHealth,
    refresh,
    runSelfCheck,
    runDiagnostics,
    repairDiagnostics,
  }
})
