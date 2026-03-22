const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

/**
 * Fetch wrapper that sends HttpOnly auth cookies automatically.
 * Use instead of raw fetch() for all authenticated API calls.
 */
export function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  return fetch(apiUrl(path), {
    ...options,
    credentials: 'include',
  });
}
