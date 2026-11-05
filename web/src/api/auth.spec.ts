import { afterEach, describe, expect, it, vi } from 'vitest'

import { apiToken, authHeaders, wsProtocols } from './auth'
import { api } from './http'

afterEach(() => {
  delete window.__VINASTUDIO_TOKEN__
  vi.unstubAllGlobals()
})

describe('api token', () => {
  it('is empty when the desktop shell did not inject one', () => {
    expect(apiToken()).toBe('')
    expect(authHeaders()).toEqual({})
    expect(wsProtocols()).toEqual([])
  })

  it('becomes a request header and a WS subprotocol when injected', () => {
    window.__VINASTUDIO_TOKEN__ = 'test-token'

    expect(apiToken()).toBe('test-token')
    expect(authHeaders()).toEqual({ 'X-VinaStudio-Token': 'test-token' })
    expect(wsProtocols()).toEqual(['vinastudio.test-token'])
  })
})

describe('requests', () => {
  it('sends the token on the shared JSON request path', async () => {
    window.__VINASTUDIO_TOKEN__ = 'test-token'
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await api.health()

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(new Headers(init.headers).get('X-VinaStudio-Token')).toBe('test-token')
  })

  it('sends no token header when none was injected', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await api.health()

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(new Headers(init.headers).has('X-VinaStudio-Token')).toBe(false)
  })
})
