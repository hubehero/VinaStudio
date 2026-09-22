import { createI18n } from 'vue-i18n'

import enUS from './locales/en-US'
import zhCN from './locales/zh-CN'

export type AppLocale = 'zh-CN' | 'en-US'

export const SUPPORTED_LOCALES: ReadonlyArray<{ value: AppLocale; label: string }> = [
  { value: 'zh-CN', label: '中文' },
  { value: 'en-US', label: 'English' },
]

/** Chinese is the product default; the desktop shell mirrors this choice. */
export const DEFAULT_LOCALE: AppLocale = 'zh-CN'

const STORAGE_KEY = 'vinastudio.locale'
const HTML_LANG: Record<AppLocale, string> = { 'zh-CN': 'zh-CN', 'en-US': 'en' }

export function normaliseLocale(input: string | null | undefined): AppLocale {
  if (!input) {
    return DEFAULT_LOCALE
  }
  return input.toLowerCase().startsWith('en') ? 'en-US' : 'zh-CN'
}

export function resolveInitialLocale(): AppLocale {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (stored) {
      return normaliseLocale(stored)
    }
  } catch {
    // localStorage can be unavailable; fall through to the default.
  }
  return normaliseLocale(window.navigator.language ?? DEFAULT_LOCALE)
}

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: resolveInitialLocale(),
  fallbackLocale: DEFAULT_LOCALE,
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS,
  },
})

export function currentLocale(): AppLocale {
  return normaliseLocale(i18n.global.locale.value)
}

export function setLocale(locale: string): AppLocale {
  const next = normaliseLocale(locale)
  i18n.global.locale.value = next
  document.documentElement.lang = HTML_LANG[next]
  try {
    window.localStorage.setItem(STORAGE_KEY, next)
  } catch {
    // Persisting is best-effort only.
  }
  return next
}
