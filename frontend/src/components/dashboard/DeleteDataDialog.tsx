'use client'

import { getTheme } from '@/utils/theme'

type Theme = ReturnType<typeof getTheme>

interface DeleteDataDialogProps {
  theme: Theme
  isDeleting: boolean
  onConfirm: () => void
  onCancel: () => void
}

export default function DeleteDataDialog({ theme, isDeleting, onConfirm, onCancel }: DeleteDataDialogProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className={`${theme.glass} border ${theme.glassBorder} rounded-xl p-6 m-4 max-w-md w-full`}>
        <div className="text-center">
          <div className="w-12 h-12 mx-auto mb-4 bg-red-100 rounded-full flex items-center justify-center">
            <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          </div>
          <h3 className={`text-lg font-semibold ${theme.text.primary} mb-2`}>Delete All Data</h3>
          <p className={`${theme.text.secondary} mb-6`}>
            Are you sure you want to delete all your genetic data? This action cannot be undone.
          </p>
          <div className="flex gap-3 justify-center">
            <button
              onClick={onCancel}
              disabled={isDeleting}
              className={`px-4 py-2 rounded-lg ${theme.glass} border ${theme.glassBorder} ${theme.text.primary} hover:bg-white/10 transition-colors disabled:opacity-50`}
            >
              Cancel
            </button>
            <button
              onClick={onConfirm}
              disabled={isDeleting}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              {isDeleting && (
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              )}
              {isDeleting ? 'Deleting...' : 'Delete'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
