'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { apiUrl } from '@/lib/api'

// ────────────────────────────────── types ────────────────────────────────────

export type NotificationType =
  | 'analysis_queued'
  | 'analysis_completed'
  | 'analysis_failed'
  | 'upload_complete'
  | 'upload_failed'
  | 'variant_saved'
  | 'discovery_approved'
  | 'discovery_rejected'
  | 'data_deleted'
  | 'dashboard_shared'

export interface AppNotification {
  id: number
  type: NotificationType
  title: string
  message: string
  data: Record<string, unknown>
  read: boolean
  created_at: string
}

interface UseNotificationsReturn {
  notifications: AppNotification[]
  unreadCount: number
  isConnected: boolean
  markRead: (id: number) => Promise<void>
  markAllRead: () => Promise<void>
  deleteNotification: (id: number) => Promise<void>
  clearAll: () => void
}

// ────────────────────────────────── hook ─────────────────────────────────────

const RECONNECT_DELAY_MS = 3_000
const MAX_RECONNECT_DELAY_MS = 30_000
const PING_INTERVAL_MS = 25_000

export function useNotifications(token?: string): UseNotificationsReturn {
  const [notifications, setNotifications] = useState<AppNotification[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [wsToken, setWsToken] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectDelayRef = useRef(RECONNECT_DELAY_MS)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const mountedRef = useRef(true)

  const unreadCount = notifications.filter((n) => !n.read).length

  // ── helpers ───────────────────────────────────────────────────

  const upsertNotification = useCallback((notif: AppNotification) => {
    setNotifications((prev) => {
      const idx = prev.findIndex((n) => n.id === notif.id)
      if (idx >= 0) {
        const next = [...prev]
        next[idx] = notif
        return next
      }
      return [notif, ...prev]
    })
  }, [])
  // ── REST fetch (initial load + polling fallback) ──────────

  const fetchFromRest = useCallback(async () => {
    try {
      const res = await fetch(apiUrl('/api/notifications?limit=50'), { credentials: 'include' })
      if (res.ok && mountedRef.current) {
        const data: AppNotification[] = await res.json()
        setNotifications(data)
      }
    } catch { /* ignore */ }
  }, [])
  // ── REST calls ────────────────────────────────────────────────

  const markRead = useCallback(async (id: number) => {
    try {
      await fetch(apiUrl(`/api/notifications/${id}/read`), {
        method: 'POST',
        credentials: 'include',
      })
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, read: true } : n))
      )
    } catch (e) {
      console.error('[notifications] markRead error', e)
    }
  }, [])

  const markAllRead = useCallback(async () => {
    try {
      await fetch(apiUrl('/api/notifications/read-all'), {
        method: 'POST',
        credentials: 'include',
      })
      setNotifications((prev) => prev.map((n) => ({ ...n, read: true })))
    } catch (e) {
      console.error('[notifications] markAllRead error', e)
    }
  }, [])

  const deleteNotification = useCallback(async (id: number) => {
    try {
      await fetch(apiUrl(`/api/notifications/${id}`), {
        method: 'DELETE',
        credentials: 'include',
      })
      setNotifications((prev) => prev.filter((n) => n.id !== id))
    } catch (e) {
      console.error('[notifications] delete error', e)
    }
  }, [])

  const clearAll = useCallback(() => setNotifications([]), [])

  // ── WebSocket connection ──────────────────────────────────────

  const connect = useCallback(() => {
    if (!token) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    // Derive ws:// or wss:// from the API_BASE
    const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const wsBase = apiBase.replace(/^http/, 'ws')
    // Use real JWT from ws-token endpoint; fall back to the app token state
    const wsTokenParam = wsToken || token
    const url = `${wsBase}/ws/notifications?token=${wsTokenParam}`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) return
      setIsConnected(true)
      reconnectDelayRef.current = RECONNECT_DELAY_MS

      // Stop REST polling — WS handles live updates now
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current)
        pollTimerRef.current = null
      }

      // Keepalive ping
      pingTimerRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send('ping')
      }, PING_INTERVAL_MS)
    }

    ws.onmessage = (ev) => {
      if (!mountedRef.current) return
      try {
        const msg = JSON.parse(ev.data)

        if (msg.event === 'connected') {
          // Seed with recent notifications from server
          if (Array.isArray(msg.recent)) {
            setNotifications(msg.recent as AppNotification[])
          }
          return
        }

        if (msg.event === 'notification' && msg.notification) {
          upsertNotification(msg.notification as AppNotification)
          return
        }
      } catch {
        // non-JSON message (e.g. "pong") — ignore
      }
    }

    ws.onerror = () => {
      // Let onclose handle reconnect
    }

    ws.onclose = (ev) => {
      if (!mountedRef.current) return
      setIsConnected(false)

      if (pingTimerRef.current) {
        clearInterval(pingTimerRef.current)
        pingTimerRef.current = null
      }

      // 4001 = unauthorized — don't reconnect via WS, fall back to polling
      if (ev.code === 4001) {
        if (!pollTimerRef.current) {
          pollTimerRef.current = setInterval(fetchFromRest, 30_000)
        }
        return
      }

      // Exponential back-off
      const delay = Math.min(reconnectDelayRef.current, MAX_RECONNECT_DELAY_MS)
      reconnectDelayRef.current = delay * 2
      reconnectTimerRef.current = setTimeout(connect, delay)
    }
  }, [token, wsToken, upsertNotification, fetchFromRest])

  // ── lifecycle ─────────────────────────────────────────────────

  useEffect(() => {
    if (!token) return
    mountedRef.current = true

    // 1. Seed notifications from REST immediately (no wait for WS)
    fetchFromRest()

    // 2. Fetch real JWT for WS auth, then connect
    fetch(apiUrl('/auth/ws-token'), { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.token && mountedRef.current) {
          setWsToken(data.token)
        } else if (mountedRef.current) {
          // No JWT available — use REST polling only
          pollTimerRef.current = setInterval(fetchFromRest, 30_000)
        }
      })
      .catch(() => {
        if (mountedRef.current) {
          pollTimerRef.current = setInterval(fetchFromRest, 30_000)
        }
      })

    return () => {
      mountedRef.current = false
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      if (pingTimerRef.current) clearInterval(pingTimerRef.current)
      if (pollTimerRef.current) clearInterval(pollTimerRef.current)
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [token, fetchFromRest])

  // Connect (or reconnect) when wsToken becomes available
  useEffect(() => {
    if (wsToken && mountedRef.current) {
      connect()
    }
  }, [wsToken, connect])

  return {
    notifications,
    unreadCount,
    isConnected,
    markRead,
    markAllRead,
    deleteNotification,
    clearAll,
  }
}
