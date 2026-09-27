import type { DesktopBridge } from '@/types/api'
import { downloadTextFile } from '@/utils/download'

/**
 * Access to the QWebChannel object published by the PySide6 host.
 *
 * `qwebchannel.js` is injected at document creation, but the constructor can
 * still land a tick later, so resolution is retried with a deadline. The same
 * deadline covers a channel that never calls back — otherwise every file-picker
 * call would wait on it forever with no way to fall back. When the interface
 * runs in a plain browser the promise resolves to `null` and the UI keeps
 * working with the browser-only feature set.
 */

const HANDSHAKE_TIMEOUT_MS = 5_000

let cached: DesktopBridge | null = null
let pending: Promise<DesktopBridge | null> | null = null

export function isDesktopHost(): boolean {
  return typeof window !== 'undefined' && Boolean(window.qt?.webChannelTransport)
}

export function desktopBridge(): Promise<DesktopBridge | null> {
  if (cached) {
    return Promise.resolve(cached)
  }
  if (pending) {
    return pending
  }
  if (!isDesktopHost()) {
    return Promise.resolve(null)
  }

  pending = new Promise<DesktopBridge | null>((resolve) => {
    const deadline = Date.now() + HANDSHAKE_TIMEOUT_MS

    const giveUp = (): void => {
      // Left un-cached so a later call can try again.
      pending = null
      resolve(null)
    }

    const attempt = (): void => {
      if (Date.now() > deadline) {
        giveUp()
        return
      }
      if (typeof window.QWebChannel !== 'function') {
        setTimeout(attempt, 50)
        return
      }
      const timer = setTimeout(giveUp, Math.max(0, deadline - Date.now()))
      new window.QWebChannel(window.qt!.webChannelTransport, (channel) => {
        clearTimeout(timer)
        cached = (channel.objects.bridge as DesktopBridge | undefined) ?? null
        resolve(cached)
      })
    }

    attempt()
  })
  return pending
}

export async function nativeAppInfo(): Promise<Record<string, unknown> | null> {
  const bridge = await desktopBridge()
  if (!bridge) {
    return null
  }
  try {
    return JSON.parse(await bridge.appInfo()) as Record<string, unknown>
  } catch {
    return null
  }
}

/**
 * Ask for file paths.
 *
 * In the desktop host the native dialog returns real filesystem paths, which
 * the backend reads in place. A plain browser cannot produce a path from an
 * `<input type="file">`, so callers get an empty list and should use
 * {@link pickFileForUpload} instead.
 */
export async function pickFiles(options: {
  title: string
  filters: string
  multiple?: boolean
}): Promise<string[]> {
  const bridge = await desktopBridge()
  if (!bridge) {
    return []
  }
  try {
    const raw = await bridge.openFiles(options.title, options.filters, options.multiple ?? false)
    return JSON.parse(raw) as string[]
  } catch {
    return []
  }
}

/** Ask for a directory; only meaningful in the desktop host. */
export async function pickDirectory(title: string): Promise<string | null> {
  const bridge = await desktopBridge()
  if (!bridge) {
    return null
  }
  return (await bridge.openDirectory(title)) || null
}

/**
 * Open a URL in the system default browser.
 *
 * In the desktop host this uses QDesktopServices.openUrl() via the bridge,
 * which reliably opens the system browser even when QWebEngine blocks popups.
 * In a plain browser, falls back to window.open().
 */
export async function openInBrowser(url: string): Promise<void> {
  const bridge = await desktopBridge()
  if (bridge) {
    await bridge.openUrl(url)
  } else {
    window.open(url, '_blank')
  }
}

/**
 * Ask the user for a save path; only meaningful in the desktop host.
 *
 * Returns the chosen path or ``null`` when the user cancels.
 */
export async function pickSaveFile(
  title: string,
  suggestedName: string,
  filters: string,
): Promise<string | null> {
  const bridge = await desktopBridge()
  if (!bridge) {
    return null
  }
  return (await bridge.saveFile(title, suggestedName, filters)) || null
}

/**
 * Save base64 image data to a user-chosen path, or download it in a browser.
 *
 * Returns whether the image went anywhere: the host returns an empty string when
 * the user cancels, and the browser fallback has no way to report anything. A
 * `null` here used to mean both "cancelled" and "downloaded", which made the
 * caller's success message unconditional.
 */
export async function saveImage(dataUrl: string, suggestedName: string): Promise<boolean> {
  const bridge = await desktopBridge()
  if (bridge) {
    return Boolean(await bridge.saveImage(dataUrl, suggestedName))
  }
  const link = document.createElement('a')
  link.href = dataUrl
  link.download = suggestedName
  document.body.appendChild(link)
  link.click()
  link.remove()
  return true
}

/**
 * Write UTF-8 text to `path` through the desktop host (TASK-24).
 *
 * The path-selection dialog is the caller's concern — this shell only writes
 * and reports whether it worked. Returns `false` without a host (plain
 * browser) so callers fall back through {@link saveTextFile} instead of
 * assuming success.
 */
export async function writeTextFile(path: string, content: string): Promise<boolean> {
  const bridge = await desktopBridge()
  if (!bridge) {
    return false
  }
  try {
    return await bridge.writeTextFile(path, content)
  } catch {
    return false
  }
}

/**
 * The one place that chooses between desktop write and browser download.
 *
 * Desktop host: native save dialog, then {@link writeTextFile}; a cancelled
 * dialog or a failed write both yield `false`. Plain browser: the historical
 * `<a download>` blob and `true` (there is nothing to report back).
 */
export async function saveTextFile(
  content: string,
  options: { filename: string; mime: string; saveTitle: string; filters?: string },
): Promise<boolean> {
  const bridge = await desktopBridge()
  if (bridge) {
    const path = await pickSaveFile(options.saveTitle, options.filename, options.filters ?? '')
    if (!path) {
      return false
    }
    return writeTextFile(path, content)
  }
  downloadTextFile(content, options.filename, options.mime)
  return true
}

/**
 * Browser fallback for {@link pickFiles}: opens a file input and resolves with
 * the chosen `File` objects so the caller can POST them to `/api/files/upload`.
 */
export function pickFileForUpload(
  accept: string[],
  multiple = false,
): Promise<File[]> {
  return new Promise((resolve) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = accept.join(',')
    input.multiple = multiple
    input.style.display = 'none'
    let settled = false
    let cancelTimer: number | null = null
    let onWindowFocus: () => void = () => {}

    const finish = (files: File[]): void => {
      if (settled) {
        return
      }
      settled = true
      // Both of these outlive the picker otherwise; a later focus would call
      // finish() again on an already-settled promise.
      if (cancelTimer !== null) {
        clearTimeout(cancelTimer)
      }
      window.removeEventListener('focus', onWindowFocus)
      input.remove()
      resolve(files)
    }

    onWindowFocus = () => {
      // A cancelled picker fires no event in some engines; window focus
      // returning without a change is the only signal, so settle empty on it.
      cancelTimer = window.setTimeout(() => finish(Array.from(input.files ?? [])), 400)
    }

    input.addEventListener('change', () => finish(Array.from(input.files ?? [])))
    window.addEventListener('focus', onWindowFocus)
    document.body.append(input)
    input.click()
  })
}
