const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

// Auth endpoints handle their own error UI (e.g. "wrong password" inline).
// A 401 from these must never trigger the global unauthorized flow, or a
// bad login/register attempt would fire a logout redirect instead of
// showing an inline error — and reset-password would loop back to login.
const AUTH_ENDPOINT_PREFIXES = [
  '/auth/login',
  '/auth/register',
  '/auth/forgot-password',
  '/auth/reset-password',
];

function isAuthEndpoint(path: string): boolean {
  return AUTH_ENDPOINT_PREFIXES.some((prefix) => path.startsWith(prefix));
}

/** Dispatched on any non-auth-endpoint 401 so a single top-level listener can clear the session. */
export const UNAUTHORIZED_EVENT = 'api:unauthorized';

function notifyUnauthorized(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
}

export class ApiError extends Error {
  readonly status: number;
  readonly data: unknown;

  constructor(status: number, message: string, data?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function parseErrorBody(response: Response): Promise<{ message: string; data: unknown }> {
  const contentType = response.headers.get('content-type') || '';
  try {
    if (contentType.includes('application/json')) {
      const data = await response.json();
      const detail = data && typeof data === 'object' ? (data as Record<string, unknown>).detail : undefined;
      const message = typeof detail === 'string' ? detail : response.statusText || `Request failed with status ${response.status}`;
      return { message, data };
    }
    const text = await response.text();
    return { message: text || response.statusText || `Request failed with status ${response.status}`, data: text };
  } catch {
    return { message: response.statusText || `Request failed with status ${response.status}`, data: undefined };
  }
}

export interface ApiFetchOptions extends RequestInit {
  /**
   * Suppress the global 401 handler for this call. Auth endpoints are
   * excluded automatically — this is only for other rare edge cases.
   */
  redirectOn401?: boolean;
}

/**
 * Fetch wrapper that sends HttpOnly auth cookies automatically, throws a
 * typed `ApiError` on any non-2xx response, and centralizes 401 handling.
 *
 * On a 401 (except for auth endpoints, or when `redirectOn401: false` is
 * passed), dispatches `UNAUTHORIZED_EVENT` on `window` so a single
 * top-level listener can clear the session and show the login screen.
 * The call also still throws `ApiError`, so callers that need to react
 * locally (e.g. a login form showing "invalid credentials") can catch it.
 */
export async function apiFetch(path: string, options: ApiFetchOptions = {}): Promise<Response> {
  const { redirectOn401, ...init } = options;
  const response = await fetch(apiUrl(path), {
    ...init,
    credentials: 'include',
  });

  if (response.status === 401 && (redirectOn401 ?? !isAuthEndpoint(path))) {
    notifyUnauthorized();
  }

  if (!response.ok) {
    const { message, data } = await parseErrorBody(response);
    throw new ApiError(response.status, message, data);
  }

  return response;
}
