'use client'

import React, { useEffect, useRef, useState } from 'react'
import { Bell, BellRing, Check, CheckCheck, Trash2, X } from 'lucide-react'
import { getTheme } from '@/utils/theme'
import type { AppNotification } from '@/hooks/useNotifications'

// ────────────────────────────────── types ────────────────────────────────────

type Theme = ReturnType<typeof getTheme>

interface NotificationBellProps {
  theme: Theme
  isDarkMode: boolean
  notifications: AppNotification[]
  unreadCount: number
  isConnected: boolean
  onMarkRead: (id: number) => Promise<void>
  onMarkAllRead: () => Promise<void>
  onDelete: (id: number) => Promise<void>
}

// ────────────────────────────────── icon map ─────────────────────────────────

type NotifIcon = { emoji: string; color: string }

const ICON_MAP: Record<string, NotifIcon> = {
  analysis_queued:    { emoji: '⏳', color: 'text-blue-500' },
  analysis_completed: { emoji: '✅', color: 'text-green-500' },
  analysis_failed:    { emoji: '❌', color: 'text-red-500' },
  upload_complete:    { emoji: '📂', color: 'text-teal-500' },
  upload_failed:      { emoji: '⚠️',  color: 'text-orange-500' },
  variant_saved:      { emoji: '🔖', color: 'text-purple-500' },
  discovery_approved: { emoji: '🎉', color: 'text-green-500' },
  discovery_rejected: { emoji: '🚫', color: 'text-red-500' },
  data_deleted:       { emoji: '🗑️',  color: 'text-gray-500' },
}

function iconFor(type: string): NotifIcon {
  return ICON_MAP[type] ?? { emoji: '🔔', color: 'text-teal-500' }
}

// ────────────────────────────────── relative time ────────────────────────────

function relativeTime(isoDate: string): string {
  const diff = Date.now() - new Date(isoDate).getTime()
  const seconds = Math.floor(diff / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

// ────────────────────────────────── component ────────────────────────────────

export default function NotificationBell({
  theme,
  isDarkMode,
  notifications,
  unreadCount,
  isConnected,
  onMarkRead,
  onMarkAllRead,
  onDelete,
}: NotificationBellProps) {
  const [open, setOpen] = useState(false)
  const [isAnimating, setIsAnimating] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)
  const prevUnreadRef = useRef(unreadCount)

  // Animate bell when new notifications arrive
  useEffect(() => {
    if (unreadCount > prevUnreadRef.current) {
      setIsAnimating(true)
      const t = setTimeout(() => setIsAnimating(false), 600)
      return () => clearTimeout(t)
    }
    prevUnreadRef.current = unreadCount
  }, [unreadCount])

  // Close panel on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const handleBellClick = () => {
    setOpen((v) => !v)
  }

  const handleMarkRead = async (id: number) => {
    await onMarkRead(id)
  }

  return (
    <div className="relative" ref={panelRef}>
      {/* ── Bell button ───────────────────────────────────────── */}
      <button
        onClick={handleBellClick}
        title={isConnected ? 'Notifications' : 'Notifications (offline)'}
        className={`relative flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-200 ${
          theme.glass
        } border ${theme.glassBorder} ${theme.glassHover} ${
          isAnimating ? 'animate-bounce' : ''
        }`}
      >
        {unreadCount > 0 ? (
          <BellRing
            className={`h-5 w-5 ${isDarkMode ? 'text-teal-300' : 'text-teal-600'}`}
          />
        ) : (
          <Bell
            className={`h-5 w-5 ${isDarkMode ? 'text-gray-400' : 'text-gray-500'}`}
          />
        )}

        {/* Unread badge */}
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 min-w-4.5 h-4.5 px-1 bg-red-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center shadow-sm">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}

        {/* Offline indicator */}
        {!isConnected && (
          <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 bg-gray-400 rounded-full border-2 border-white dark:border-slate-800" />
        )}
      </button>

      {/* ── Dropdown panel ────────────────────────────────────── */}
      {open && (
        <div
          className={`absolute right-0 mt-2 w-80 max-h-120 flex flex-col rounded-xl shadow-2xl z-50 overflow-hidden ${
            isDarkMode
              ? 'bg-slate-800 border border-slate-700'
              : 'bg-white border border-gray-200'
          }`}
        >
          {/* Header */}
          <div
            className={`flex items-center justify-between px-4 py-3 border-b ${
              isDarkMode ? 'border-slate-700' : 'border-gray-100'
            }`}
          >
            <div className="flex items-center space-x-2">
              <Bell className={`h-4 w-4 ${isDarkMode ? 'text-teal-300' : 'text-teal-600'}`} />
              <span className={`text-sm font-semibold ${theme.text.primary}`}>
                Notifications
              </span>
              {unreadCount > 0 && (
                <span className="px-1.5 py-0.5 text-[10px] font-bold bg-red-500 text-white rounded-full">
                  {unreadCount}
                </span>
              )}
            </div>
            <div className="flex items-center space-x-1">
              {unreadCount > 0 && (
                <button
                  onClick={onMarkAllRead}
                  title="Mark all as read"
                  className={`p-1.5 rounded-lg transition-colors ${
                    isDarkMode
                      ? 'text-gray-400 hover:text-white hover:bg-slate-700'
                      : 'text-gray-500 hover:text-gray-900 hover:bg-gray-100'
                  }`}
                >
                  <CheckCheck className="h-3.5 w-3.5" />
                </button>
              )}
              <button
                onClick={() => setOpen(false)}
                className={`p-1.5 rounded-lg transition-colors ${
                  isDarkMode
                    ? 'text-gray-400 hover:text-white hover:bg-slate-700'
                    : 'text-gray-500 hover:text-gray-900 hover:bg-gray-100'
                }`}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          {/* Notification list */}
          <div className="flex-1 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 px-4">
                <Bell
                  className={`h-8 w-8 mb-3 ${
                    isDarkMode ? 'text-slate-600' : 'text-gray-300'
                  }`}
                />
                <p className={`text-sm ${theme.text.muted}`}>No notifications yet</p>
                <p className={`text-xs mt-1 ${theme.text.muted}`}>
                  You&apos;ll be notified about analyses and uploads
                </p>
              </div>
            ) : (
              <ul>
                {notifications.map((notif) => {
                  const { emoji, color } = iconFor(notif.type)
                  return (
                    <li
                      key={notif.id}
                      className={`relative group flex items-start gap-3 px-4 py-3 border-b last:border-b-0 transition-colors cursor-default ${
                        isDarkMode
                          ? `border-slate-700/60 ${notif.read ? '' : 'bg-slate-700/40'}`
                          : `border-gray-100 ${notif.read ? '' : 'bg-teal-50/60'}`
                      }`}
                      onClick={() => !notif.read && handleMarkRead(notif.id)}
                    >
                      {/* Unread dot */}
                      {!notif.read && (
                        <span className="absolute left-1.5 top-4 w-1.5 h-1.5 rounded-full bg-teal-500" />
                      )}

                      {/* Icon */}
                      <span className={`text-lg shrink-0 mt-0.5 ${color}`}>
                        {emoji}
                      </span>

                      {/* Body */}
                      <div className="flex-1 min-w-0">
                        <p
                          className={`text-sm font-medium leading-tight ${
                            notif.read ? theme.text.secondary : theme.text.primary
                          }`}
                        >
                          {notif.title}
                        </p>
                        <p className={`text-xs mt-0.5 leading-snug ${theme.text.muted}`}>
                          {notif.message}
                        </p>
                        <p className={`text-[10px] mt-1 ${theme.text.muted}`}>
                          {relativeTime(notif.created_at)}
                        </p>
                      </div>

                      {/* Actions (show on hover) */}
                      <div className="shrink-0 flex flex-col gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        {!notif.read && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              handleMarkRead(notif.id)
                            }}
                            title="Mark as read"
                            className={`p-1 rounded transition-colors ${
                              isDarkMode
                                ? 'text-gray-400 hover:text-white hover:bg-slate-600'
                                : 'text-gray-400 hover:text-gray-700 hover:bg-gray-200'
                            }`}
                          >
                            <Check className="h-3 w-3" />
                          </button>
                        )}
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            onDelete(notif.id)
                          }}
                          title="Delete"
                          className={`p-1 rounded transition-colors ${
                            isDarkMode
                              ? 'text-gray-500 hover:text-red-400 hover:bg-slate-600'
                              : 'text-gray-400 hover:text-red-500 hover:bg-gray-200'
                          }`}
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>

          {/* Footer */}
          {notifications.length > 0 && (
            <div
              className={`px-4 py-2.5 border-t text-center ${
                isDarkMode ? 'border-slate-700' : 'border-gray-100'
              }`}
            >
              <p className={`text-[10px] ${theme.text.muted}`}>
                {isConnected ? (
                  <span className="flex items-center justify-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block" />
                    Live updates active
                  </span>
                ) : (
                  <span className="flex items-center justify-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-gray-400 inline-block" />
                    Reconnecting…
                  </span>
                )}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
