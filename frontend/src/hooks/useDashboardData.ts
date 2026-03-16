'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { apiUrl } from '@/lib/api'
import type { DashboardData } from '@/components/categories/types'

interface UseDashboardDataOptions {
  /** Pre-loaded data from parent (page.tsx) */
  initialData?: DashboardData | null
  /** Analysis ID for progress tracking */
  analysisId?: number | null
  /** Parent refresh callback */
  onRefresh?: (token: string) => Promise<void>
  /** Token/auth indicator */
  token?: string
}

interface UseDashboardDataReturn {
  data: DashboardData | undefined
  loading: boolean
  error: string | null
  /** Timestamp of last successful fetch */
  lastFetchedAt: number | null
  /** Whether data is from cache (not a fresh fetch) */
  isCached: boolean
  /** Refresh data — pass `true` to force re-fetch from server */
  refreshData: (force?: boolean) => Promise<void>
  /** Set data directly (e.g. from AnalysisProgressLoader) */
  setData: (data: DashboardData | undefined) => void
  /** Clear all data (e.g. on delete) */
  clearData: () => void
  /** Variant categories for overview */
  variantCategories: { name: string; count: number }[]
  variantCategoryStats: { total: number; annotated: number }
}

export function useDashboardData({
  initialData,
  analysisId,
  onRefresh,
  token,
}: UseDashboardDataOptions): UseDashboardDataReturn {
  const [data, setData] = useState<DashboardData | undefined>(initialData || undefined)
  const [loading, setLoading] = useState(!initialData)
  const [error, setError] = useState<string | null>(null)
  const [lastFetchedAt, setLastFetchedAt] = useState<number | null>(
    initialData ? Date.now() : null
  )
  const [isCached, setIsCached] = useState(false)
  const [variantCategories, setVariantCategories] = useState<{ name: string; count: number }[]>([])
  const [variantCategoryStats, setVariantCategoryStats] = useState<{ total: number; annotated: number }>({ total: 0, annotated: 0 })

  // Track whether we've done the initial fetch
  const hasFetchedRef = useRef(!!initialData)

  // Fetch dashboard data from server
  const fetchDashboardData = useCallback(async () => {
    try {
      const response = await fetch(apiUrl('/api/analysis/dashboard-data'), {
        credentials: 'include',
      })

      if (response.ok) {
        const result = await response.json()
        setData(result)
        setError(null)
        setLastFetchedAt(Date.now())
        setIsCached(false)
        return result
      } else {
        const msg = `Failed to load dashboard data (HTTP ${response.status}). Please try again.`
        console.error('Failed to load dashboard data:', response.status)
        setError(msg)
        return null
      }
    } catch (err) {
      const msg = 'Could not reach the server. Check your connection and try again.'
      console.error('Error loading dashboard data:', err)
      setError(msg)
      return null
    }
  }, [])

  // Fetch variant categories
  const fetchVariantCategories = useCallback(async () => {
    try {
      const response = await fetch(apiUrl('/api/variants/categories'), {
        credentials: 'include',
      })
      if (response.ok) {
        const d = await response.json()
        if (d?.categories) {
          setVariantCategories(d.categories)
          setVariantCategoryStats({
            total: d.total_variants || 0,
            annotated: d.annotated_variants || 0,
          })
        }
      }
    } catch {
      // silently handle
    }
  }, [])

  // Public refresh function — used by "Refresh Data" button
  const refreshData = useCallback(
    async (force = false) => {
      // If we have cached data and not forcing, return cached
      if (!force && data && lastFetchedAt) {
        setIsCached(true)
        return
      }

      setLoading(true)
      try {
        // If parent provides onRefresh, use it (syncs parent state too)
        if (onRefresh && token) {
          await onRefresh(token)
        } else {
          await fetchDashboardData()
        }
        // Also refresh variant categories
        await fetchVariantCategories()
      } finally {
        setLoading(false)
      }
    },
    [data, lastFetchedAt, onRefresh, token, fetchDashboardData, fetchVariantCategories]
  )

  // Clear all data (used on delete)
  const clearData = useCallback(() => {
    setData(undefined)
    setError(null)
    setLastFetchedAt(null)
    setIsCached(false)
    setVariantCategories([])
    setVariantCategoryStats({ total: 0, annotated: 0 })
  }, [])

  // Initial fetch if no data provided
  useEffect(() => {
    if (!hasFetchedRef.current && token && !initialData) {
      hasFetchedRef.current = true
      setLoading(true)
      fetchDashboardData()
        .then((result) => {
          if (!result && analysisId) {
            // No data but we have an analysis ID — analysis may be in progress
          }
        })
        .finally(() => setLoading(false))
    }
  }, [token, initialData, analysisId, fetchDashboardData])

  // Fetch variant categories on mount
  useEffect(() => {
    if (token) {
      fetchVariantCategories()
    }
  }, [token, fetchVariantCategories])

  // Sync with analysisData prop changes (e.g. parent re-fetched)
  useEffect(() => {
    if (initialData) {
      setData(initialData)
      setLastFetchedAt(Date.now())
      setLoading(false)
      hasFetchedRef.current = true
    }
  }, [initialData])

  return {
    data,
    loading,
    error,
    lastFetchedAt,
    isCached,
    refreshData,
    setData,
    clearData,
    variantCategories,
    variantCategoryStats,
  }
}
