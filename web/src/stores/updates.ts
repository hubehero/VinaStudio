import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { installUpdate, isDesktopHost, openInBrowser } from '@/api/bridge'
import { api } from '@/api/http'
import type { UpdateCheck, UpdateDownload } from '@/types/api'

const POLL_INTERVAL_MS = 600

/**
 * Update state is shared by Settings and the app header so a background
 * download stays visible after Settings is closed. The server owns the
 * transfer; this store only polls its state and hands the verified path to the
 * native installer.
 */
export const useUpdateStore = defineStore('updates', () => {
  const checking = ref(false)
  const result = ref<UpdateCheck | null>(null)
  const download = ref<UpdateDownload | null>(null)
  let timer: ReturnType<typeof setInterval> | null = null
  let autoInstall = false
  let installing = false

  const downloadActive = computed(() =>
    download.value !== null &&
    ['starting', 'downloading', 'verifying'].includes(download.value.state),
  )
  const downloaded = computed(() => download.value?.state === 'ready')
  const updateAttention = computed(() => downloadActive.value || downloaded.value)

  function stopPolling(): void {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  function ensurePolling(): void {
    if (timer !== null) return
    timer = setInterval(() => void refreshDownload(), POLL_INTERVAL_MS)
  }

  async function check(): Promise<UpdateCheck | null> {
    checking.value = true
    try {
      result.value = await api.updateCheck()
      return result.value
    } catch {
      result.value = {
        current: '',
        latest: null,
        updateAvailable: false,
        url: '',
        publishedAt: null,
        error: 'unavailable',
      }
      return result.value
    } finally {
      checking.value = false
    }
  }

  async function refreshDownload(): Promise<void> {
    try {
      const state = await api.updateDownloadStatus()
      download.value = state
      if (state.state === 'ready') {
        stopPolling()
        if (autoInstall) {
          autoInstall = false
          await installDownloaded()
        }
      } else if (!['starting', 'downloading', 'verifying'].includes(state.state)) {
        stopPolling()
      }
    } catch {
      stopPolling()
    }
  }

  async function restoreDownload(): Promise<void> {
    try {
      const state = await api.updateDownloadStatus()
      if (state.state === 'idle') return
      download.value = state
      if (['starting', 'downloading', 'verifying'].includes(state.state)) {
        ensurePolling()
      }
    } catch {
      // The service may be starting or the host may be offline.
    }
  }

  function failedDownload(error: string): void {
    download.value = {
      state: 'error',
      version: result.value?.latest ?? null,
      assetName: null,
      installKind: null,
      bytes: 0,
      totalBytes: 0,
      percent: 0,
      path: null,
      sha256: null,
      error,
    }
  }

  async function startDownload(): Promise<void> {
    if (!result.value?.updateAvailable) return
    if (!isDesktopHost()) {
      await openInBrowser(result.value.url)
      return
    }
    if (download.value?.state === 'ready') {
      await installDownloaded()
      return
    }
    if (downloadActive.value) {
      ensurePolling()
      return
    }
    autoInstall = true
    try {
      download.value = await api.startUpdateDownload()
    } catch {
      autoInstall = false
      failedDownload('download_failed')
      return
    }
    ensurePolling()
    await refreshDownload()
  }

  async function installDownloaded(): Promise<boolean> {
    if (installing) return false
    const path = download.value?.path
    if (!path) return false
    installing = true
    try {
      const started = await installUpdate(path)
      if (!started) {
        await openInBrowser(result.value?.url ?? '')
      }
      return started
    } finally {
      installing = false
    }
  }

  function reset(): void {
    stopPolling()
    autoInstall = false
    download.value = null
  }

  return {
    checking,
    result,
    download,
    downloadActive,
    downloaded,
    updateAttention,
    check,
    startDownload,
    refreshDownload,
    restoreDownload,
    installDownloaded,
    reset,
  }
})
