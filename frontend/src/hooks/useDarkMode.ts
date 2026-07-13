import { useCallback, useEffect, useState } from 'react'

const DARK_MODE_STORAGE_KEY = 'darkMode'

function readStoredDarkMode(useSystemPreference: boolean): boolean | null {
  if (typeof window === 'undefined') return null
  const saved = localStorage.getItem(DARK_MODE_STORAGE_KEY)
  if (saved) return JSON.parse(saved)
  if (useSystemPreference) return window.matchMedia('(prefers-color-scheme: dark)').matches
  return null
}

interface UseDarkModeOptions {
  /** Seed value used before the stored preference is read. Default false. */
  initialValue?: boolean
  /** Gate the stored-preference read (mirrors an external "isHydrated" flag). Default true. */
  enabled?: boolean
  /** Fall back to `prefers-color-scheme` when nothing is stored yet. Default false. */
  useSystemPreference?: boolean
  /** Toggle the `dark` class on `<html>` whenever the value changes. Default true. */
  syncDocumentClass?: boolean
  /** Persist to localStorage whenever the value changes. Default true. */
  persist?: boolean
  /** Read the stored preference synchronously during the initial render instead of after mount. Default false. */
  readSynchronously?: boolean
}

export function useDarkMode(options: UseDarkModeOptions = {}) {
  const {
    initialValue = false,
    enabled = true,
    useSystemPreference = false,
    syncDocumentClass = true,
    persist = true,
    readSynchronously = false,
  } = options

  const [isDarkMode, setIsDarkMode] = useState<boolean>(() =>
    readSynchronously ? readStoredDarkMode(useSystemPreference) ?? initialValue : initialValue,
  )

  useEffect(() => {
    if (readSynchronously || !enabled) return
    const stored = readStoredDarkMode(useSystemPreference)
    if (stored !== null) setIsDarkMode(stored)
  }, [enabled, readSynchronously, useSystemPreference])

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (persist) localStorage.setItem(DARK_MODE_STORAGE_KEY, JSON.stringify(isDarkMode))
    if (syncDocumentClass) document.documentElement.classList.toggle('dark', isDarkMode)
  }, [isDarkMode, persist, syncDocumentClass])

  const toggleDarkMode = useCallback(() => setIsDarkMode((prev) => !prev), [])

  return { isDarkMode, setIsDarkMode, toggleDarkMode }
}
