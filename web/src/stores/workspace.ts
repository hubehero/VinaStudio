import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/api/http'
import type { WorkspaceInfo } from '@/types/api'

export const useWorkspaceStore = defineStore('workspace', () => {
  const workspace = ref<WorkspaceInfo | null>(null)
  const loading = ref(true)  // Start true to prevent wizard flash before API responds
  const error = ref<string | null>(null)

  const isConfigured = computed(() => workspace.value?.isValid ?? false)
  const workspacePath = computed(() => workspace.value?.path ?? '')
  const workspaceName = computed(() => workspace.value?.name ?? '')
  const subdirectories = computed(() => workspace.value?.subdirectories ?? {})

  async function fetchWorkspace() {
    loading.value = true
    error.value = null
    try {
      workspace.value = await api.getWorkspace()
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  async function initWorkspace(path: string, name?: string) {
    loading.value = true
    error.value = null
    try {
      workspace.value = await api.initWorkspace(path, name)
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function setWorkspace(path: string) {
    loading.value = true
    error.value = null
    try {
      workspace.value = await api.setWorkspace(path)
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function migrateWorkspace(targetPath: string) {
    loading.value = true
    error.value = null
    try {
      workspace.value = await api.migrateWorkspace(targetPath)
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function renameWorkspace(name: string) {
    loading.value = true
    error.value = null
    try {
      workspace.value = await api.renameWorkspace(name)
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  return {
    workspace,
    loading,
    error,
    isConfigured,
    workspacePath,
    workspaceName,
    subdirectories,
    fetchWorkspace,
    initWorkspace,
    setWorkspace,
    migrateWorkspace,
    renameWorkspace,
  }
})
