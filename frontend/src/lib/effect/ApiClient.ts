import { Cause, Data, Duration, Effect, Schedule } from 'effect'

import { ApiError, apiFetch, type ApiFetchOptions } from '../api'

/** Network-level failure: the request never produced an HTTP response. */
export class TransportError extends Data.TaggedError('TransportError')<{
  readonly path: string
  readonly cause: unknown
}> {}

/** The server responded, but with a non-2xx status. */
export class HttpError extends Data.TaggedError('HttpError')<{
  readonly path: string
  readonly status: number
  readonly message: string
  readonly data: unknown
}> {}

/** A 2xx response whose body could not be decoded as the expected shape. */
export class ParseError extends Data.TaggedError('ParseError')<{
  readonly path: string
  readonly cause: unknown
}> {}

export type RequestError = TransportError | HttpError | Cause.TimeoutError
export type JsonError = RequestError | ParseError

const DEFAULT_TIMEOUT = Duration.seconds(30)
const RETRY_BASE_DELAY = Duration.millis(250)
const MAX_RETRIES = 3

const IDEMPOTENT_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])

// Retrying a POST/PUT/DELETE can duplicate the side effect -- a second analysis
// start, a second upload, a second admin mutation. Retries are therefore opt-in
// for anything that is not idempotent by method.
function isIdempotent(method: string | undefined): boolean {
  return IDEMPOTENT_METHODS.has((method ?? 'GET').toUpperCase())
}

// 4xx is never retried: the request will fail identically, and repeating a 401
// would fire the global unauthorized flow once per attempt.
function isTransient(error: RequestError): boolean {
  if (error._tag === 'HttpError') return error.status >= 500
  if (error._tag === 'TransportError') return true
  return Cause.isTimeoutError(error)
}

export interface RequestOptions extends ApiFetchOptions {
  /** Opt a non-idempotent request into retries when the endpoint is known safe. */
  readonly retryable?: boolean
  readonly timeout?: Duration.Duration
}

/**
 * Wraps `apiFetch` so failures arrive as tagged errors and transient ones are
 * retried. `apiFetch` keeps ownership of cookie credentials, the auth-endpoint
 * exemption, and the 401 `UNAUTHORIZED_EVENT` dispatch.
 */
export function request(
  path: string,
  options: RequestOptions = {}
): Effect.Effect<Response, RequestError> {
  const { retryable, timeout, ...init } = options

  const attempt = Effect.tryPromise({
    try: (signal: AbortSignal) => apiFetch(path, { ...init, signal }),
    catch: (cause: unknown) =>
      cause instanceof ApiError
        ? new HttpError({ path, status: cause.status, message: cause.message, data: cause.data })
        : new TransportError({ path, cause }),
  })

  const bounded = Effect.timeout(attempt, timeout ?? DEFAULT_TIMEOUT)

  if (!(retryable ?? isIdempotent(init.method))) return bounded

  return Effect.retry(bounded, {
    schedule: Schedule.exponential(RETRY_BASE_DELAY),
    times: MAX_RETRIES,
    while: isTransient,
  })
}

export function json<A>(
  path: string,
  options: RequestOptions = {}
): Effect.Effect<A, JsonError> {
  return Effect.flatMap(request(path, options), (response) =>
    Effect.tryPromise({
      try: () => response.json() as Promise<A>,
      catch: (cause: unknown) => new ParseError({ path, cause }),
    })
  )
}
