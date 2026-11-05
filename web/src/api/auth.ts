/**
 * The desktop shell injects a per-process API token before the interface runs.
 *
 * The token is not stored in the URL, local storage or a cookie: a script in
 * `desktop/main_window.py` assigns it to this window property on every page
 * load. A plain browser has no token, which is why the supported development
 * entry point is `scripts/dev.py` (it launches the Qt shell).
 */

declare global {
  interface Window {
    __VINASTUDIO_TOKEN__?: string
  }
}

export const TOKEN_HEADER = 'X-VinaStudio-Token'
export const WS_PROTOCOL_PREFIX = 'vinastudio.'

export function apiToken(): string {
  if (typeof window === 'undefined') return ''
  const value = window.__VINASTUDIO_TOKEN__
  return typeof value === 'string' ? value : ''
}

export function authHeaders(): Record<string, string> {
  const token = apiToken()
  return token ? { [TOKEN_HEADER]: token } : {}
}

export function wsProtocols(): string[] {
  const token = apiToken()
  return token ? [`${WS_PROTOCOL_PREFIX}${token}`] : []
}
