'use client'

import { CheckCircle, X, Info } from 'lucide-react'
import { getTheme } from '@/utils/theme'

type Theme = ReturnType<typeof getTheme>

interface NotificationToastProps {
  theme: Theme
  show: boolean
  message: string
  type: 'success' | 'error' | 'info'
  onDismiss: () => void
}

export default function NotificationToast({ theme, show, message, type, onDismiss }: NotificationToastProps) {
  if (!show) return null

  return (
    <div
      className={`fixed top-4 right-4 z-50 max-w-sm w-full ${theme.glass} border ${theme.glassBorder} rounded-lg p-4 shadow-xl backdrop-blur-xl transition-all duration-300 ${
        type === 'success'
          ? 'border-green-500/50 bg-green-50/90 dark:bg-green-900/30'
          : type === 'error'
            ? 'border-red-500/50 bg-red-50/90 dark:bg-red-900/30'
            : 'border-blue-500/50 bg-blue-50/90 dark:bg-blue-900/30'
      }`}
    >
      <div className="flex items-start space-x-3">
        <div
          className={`flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center ${
            type === 'success' ? 'bg-green-500' : type === 'error' ? 'bg-red-500' : 'bg-blue-500'
          }`}
        >
          {type === 'success' ? (
            <CheckCircle className="w-3 h-3 text-white" />
          ) : type === 'error' ? (
            <X className="w-3 h-3 text-white" />
          ) : (
            <Info className="w-3 h-3 text-white" />
          )}
        </div>
        <div className="flex-1">
          <p
            className={`text-sm font-medium ${
              type === 'success'
                ? 'text-green-800 dark:text-green-200'
                : type === 'error'
                  ? 'text-red-800 dark:text-red-200'
                  : 'text-blue-800 dark:text-blue-200'
            }`}
          >
            {message}
          </p>
        </div>
        <button
          onClick={onDismiss}
          className={`flex-shrink-0 w-4 h-4 rounded-full flex items-center justify-center hover:bg-white/20 transition-colors ${
            type === 'success'
              ? 'text-green-600 dark:text-green-400'
              : type === 'error'
                ? 'text-red-600 dark:text-red-400'
                : 'text-blue-600 dark:text-blue-400'
          }`}
        >
          <X className="w-3 h-3" />
        </button>
      </div>
    </div>
  )
}
