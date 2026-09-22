import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { desktopBridge, isDesktopHost } from '@/api/bridge'
import type { SocketStatus } from '@/api/ws'
import {
  DEFAULT_LOCALE,
  currentLocale,
  resolveInitialLocale,
  setLocale,
  type AppLocale,
} from '@/i18n'

export type ThemeMode = 'dark' | 'light' | 'system'

const THEME_KEY = 'vinastudio.theme'
const SIDEBAR_KEY = 'vinastudio.sidebar'

/** Theme the interface starts from, and returns to on a reset. */
export const DEFAULT_THEME: ThemeMode = 'dark'

function readStored<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const stored = window.localStorage.getItem(key)
    if (stored && (allowed as readonly string[]).includes(stored)) {
      return stored as T
    }
  } catch {
    // Ignore storage failures; fall back to the default.
  }
  return fallback
}

export const useUiStore = defineStore('ui', () => {
  const locale = ref<AppLocale>(resolveInitialLocale())
  const theme = ref<ThemeMode>(
    readStored<ThemeMode>(THEME_KEY, ['dark', 'light', 'system'], DEFAULT_THEME),
  )
  const sidebarCollapsed = ref(readStored(SIDEBAR_KEY, ['0', '1'], '0') === '1')
  const socketStatus = ref<SocketStatus>('idle')
  const desktop = ref(isDesktopHost())
  const systemPrefersDark = ref(
    window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? true,
  )

  const resolvedTheme = computed<'dark' | 'light'>(() => {
    if (theme.value === 'system') {
      return systemPrefersDark.value ? 'dark' : 'light'
    }
    return theme.value
  })

  function applyTheme(): void {
    const dark = resolvedTheme.value === 'dark'
    document.documentElement.classList.toggle('dark', dark)
    document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
  }

  function persist(key: string, value: string): void {
    try {
      window.localStorage.setItem(key, value)
    } catch {
      // Best-effort only.
    }
  }

  async function setLocalePreference(next: string): Promise<void> {
    locale.value = setLocale(next)
    // Keep the native menu bar and window title in step with the interface.
    const bridge = await desktopBridge()
    bridge?.setLanguage(locale.value)
  }

  function setTheme(next: ThemeMode): void {
    theme.value = next
    persist(THEME_KEY, next)
    applyTheme()
  }

  function toggleSidebar(): void {
    sidebarCollapsed.value = !sidebarCollapsed.value
    persist(SIDEBAR_KEY, sidebarCollapsed.value ? '1' : '0')
  }

  /** Return theme and language to their defaults. */
  async function resetPreferences(): Promise<void> {
    setTheme(DEFAULT_THEME)
    await setLocalePreference(DEFAULT_LOCALE)
  }

  function setSocketStatus(status: SocketStatus): void {
    socketStatus.value = status
  }

  function watchSystemTheme(): void {
    const query = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!query) {
      return
    }
    query.addEventListener('change', (event) => {
      systemPrefersDark.value = event.matches
    })
  }

  async function init(): Promise<void> {
    applyTheme()
    watchSystemTheme()
    const bridge = await desktopBridge()
    if (bridge) {
      desktop.value = true
      // The host may have started in a different language than the stored
      // preference; the interface is the source of truth.
      bridge.setLanguage(currentLocale())
    }
  }

  return {
    locale,
    theme,
    resolvedTheme,
    sidebarCollapsed,
    socketStatus,
    desktop,
    init,
    setLocalePreference,
    setTheme,
    toggleSidebar,
    setSocketStatus,
    resetPreferences,
  }
})
