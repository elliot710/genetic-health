import { Duration, Effect } from 'effect'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { UNAUTHORIZED_EVENT } from '../api'
import { HttpError, ParseError, TransportError, json, request } from './ApiClient'

const runFailure = <A, E>(effect: Effect.Effect<A, E>): Promise<E> =>
  Effect.runPromise(Effect.flip(effect))

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

let dispatched: string[]

beforeEach(() => {
  dispatched = []
  vi.stubGlobal('window', {
    dispatchEvent: (event: Event) => {
      dispatched.push(event.type)
      return true
    },
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('request', () => {
  it('resolves a 200 with the response body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, { ok: true })))
    const response = await Effect.runPromise(request('/api/thing'))
    await expect(response.json()).resolves.toEqual({ ok: true })
  })

  it('retries a 500 on GET and fails with the status after exhausting attempts', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(500, { detail: 'boom' }))
    vi.stubGlobal('fetch', fetchMock)

    const error = await runFailure(request('/api/thing', { timeout: Duration.millis(50) }))

    expect(error).toBeInstanceOf(HttpError)
    expect((error as HttpError).status).toBe(500)
    expect(fetchMock).toHaveBeenCalledTimes(4) // 1 initial + 3 retries
  })

  it('does not retry a 4xx', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(404, { detail: 'nope' }))
    vi.stubGlobal('fetch', fetchMock)

    const error = await runFailure(request('/api/thing'))

    expect((error as HttpError).status).toBe(404)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('dispatches the unauthorized event once on a 401', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(401, { detail: 'nope' })))
    await runFailure(request('/api/thing'))
    expect(dispatched).toEqual([UNAUTHORIZED_EVENT])
  })

  it('does not dispatch the unauthorized event for an auth endpoint', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(401, { detail: 'bad password' })))
    await runFailure(request('/auth/login', { method: 'POST' }))
    expect(dispatched).toEqual([])
  })

  it('surfaces a network rejection as a distinguishable TransportError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network down')))
    const error = await runFailure(request('/api/thing', { timeout: Duration.millis(50) }))
    expect(error).toBeInstanceOf(TransportError)
    expect(error).not.toBeInstanceOf(HttpError)
  })

  it('does not retry a non-idempotent method on a 500', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(500, { detail: 'boom' }))
    vi.stubGlobal('fetch', fetchMock)

    await runFailure(request('/api/analysis/start/1', { method: 'POST' }))

    // Retrying a POST would start a second analysis.
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('retries a non-idempotent method when explicitly opted in', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(500, { detail: 'boom' }))
    vi.stubGlobal('fetch', fetchMock)

    await runFailure(
      request('/api/thing', { method: 'POST', retryable: true, timeout: Duration.millis(50) })
    )

    expect(fetchMock).toHaveBeenCalledTimes(4)
  })

  it('aborts the underlying request when the timeout fires', async () => {
    let observed: AbortSignal | undefined
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init: RequestInit) => {
        observed = init.signal ?? undefined
        return new Promise<Response>(() => {})
      })
    )

    await runFailure(request('/api/thing', { timeout: Duration.millis(20), retryable: false }))

    expect(observed?.aborted).toBe(true)
  })
})

describe('json', () => {
  it('decodes a successful body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, { value: 7 })))
    await expect(Effect.runPromise(json<{ value: number }>('/api/thing'))).resolves.toEqual({ value: 7 })
  })

  it('fails with ParseError when the body is not valid JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('not json', { status: 200, headers: { 'content-type': 'application/json' } }))
    )
    const error = await runFailure(json('/api/thing'))
    expect(error).toBeInstanceOf(ParseError)
  })
})
