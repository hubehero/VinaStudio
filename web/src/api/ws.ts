/** Reconnecting WebSocket client for job progress and log streaming. */

export type SocketStatus = 'idle' | 'connecting' | 'open' | 'closed'

export interface ServerEvent {
  type: string
  [key: string]: unknown
}

type EventListener = (event: ServerEvent) => void
type StatusListener = (status: SocketStatus) => void

const MAX_BACKOFF_MS = 10_000

function socketUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws`
}

export class EventSocket {
  private socket: WebSocket | null = null
  private eventListeners = new Set<EventListener>()
  private statusListeners = new Set<StatusListener>()
  private retries = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private closedByUser = false
  private readonly keepAliveMs: number

  constructor(keepAliveMs = 25_000) {
    this.keepAliveMs = keepAliveMs
  }

  connect(): void {
    if (this.socket && this.socket.readyState <= WebSocket.OPEN) {
      return
    }
    this.closedByUser = false
    this.emitStatus('connecting')

    const socket = new WebSocket(socketUrl())
    this.socket = socket

    socket.onopen = () => {
      this.retries = 0
      this.emitStatus('open')
      this.startKeepAlive()
    }
    socket.onmessage = (message) => {
      try {
        const parsed = JSON.parse(message.data as string) as ServerEvent
        this.emitEvent(parsed)
      } catch {
        // Ignore malformed frames rather than tearing the channel down.
      }
    }
    socket.onerror = () => {
      // `onclose` always follows, which is where reconnection is handled.
    }
    socket.onclose = () => {
      this.stopKeepAlive()
      this.socket = null
      // close() already reported the deliberate shutdown; a late browser
      // onclose must neither contradict it nor trigger a reconnect.
      if (this.closedByUser) {
        return
      }
      this.emitStatus('closed')
      this.scheduleReconnect()
    }
  }

  close(): void {
    this.closedByUser = true
    this.stopKeepAlive()
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.socket?.close()
    this.socket = null
    this.emitStatus('idle')
  }

  onEvent(listener: EventListener): () => void {
    this.eventListeners.add(listener)
    return () => this.eventListeners.delete(listener)
  }

  onStatus(listener: StatusListener): () => void {
    this.statusListeners.add(listener)
    listener(this.currentStatus())
    return () => this.statusListeners.delete(listener)
  }

  send(payload: Record<string, unknown>): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) {
      return false
    }
    this.socket.send(JSON.stringify(payload))
    return true
  }

  get status(): SocketStatus {
    return this.currentStatus()
  }

  /** Single source of truth for the reported state, so listeners agree. */
  private currentStatus(): SocketStatus {
    const socket = this.socket
    if (!socket) {
      return 'idle'
    }
    if (socket.readyState === WebSocket.OPEN) {
      return 'open'
    }
    if (socket.readyState === WebSocket.CONNECTING) {
      return 'connecting'
    }
    return 'closed'
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer !== null) {
      return
    }
    const delay = Math.min(MAX_BACKOFF_MS, 500 * 2 ** this.retries)
    this.retries += 1
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, delay)
  }

  private keepAliveTimer: ReturnType<typeof setInterval> | null = null

  private startKeepAlive(): void {
    this.stopKeepAlive()
    this.keepAliveTimer = setInterval(() => this.send({ type: 'ping' }), this.keepAliveMs)
  }

  private stopKeepAlive(): void {
    if (this.keepAliveTimer !== null) {
      clearInterval(this.keepAliveTimer)
      this.keepAliveTimer = null
    }
  }

  private emitEvent(event: ServerEvent): void {
    for (const listener of this.eventListeners) {
      listener(event)
    }
  }

  private emitStatus(status: SocketStatus): void {
    for (const listener of this.statusListeners) {
      listener(status)
    }
  }
}

export const eventSocket = new EventSocket()
