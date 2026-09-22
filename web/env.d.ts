/// <reference types="vite/client" />

/**
 * Globals provided by the PySide6 host.
 *
 * `qwebchannel.js` is injected by the desktop shell at document creation, so
 * these are absent (and the UI degrades gracefully) when the interface is
 * opened in a plain browser.
 */
declare global {
  interface QWebChannelInit {
    objects: Record<string, unknown>
  }

  interface Window {
    qt?: { webChannelTransport: unknown }
    QWebChannel?: new (
      transport: unknown,
      init: (channel: QWebChannelInit) => void,
    ) => unknown
    /** JavaScript bridge the native menus call into. */
    vinastudio?: Record<string, (...args: unknown[]) => void>
  }
}

export {}
