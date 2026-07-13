'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { apiFetch, ApiError } from '@/lib/api'

interface UseAnalysisControlsOptions {
  analysisId?: number | null
  token?: string
  onRefresh?: (token: string) => Promise<void>
  onDataRefresh?: () => Promise<void>
  showNotification: (message: string, type: 'success' | 'error' | 'info') => void
}

interface UseAnalysisControlsReturn {
  analysisStatus: string
  analysisProgress: number
  totalVariants: number
  processedVariants: number
  isAnalysisRunning: boolean
  showProgress: boolean
  setShowProgress: (show: boolean) => void
  handleStartAnalysis: () => Promise<void>
  handleStopAnalysis: () => Promise<void>
  handlePauseAnalysis: () => Promise<void>
  handleResumeAnalysis: () => Promise<void>
  resetAnalysisState: () => void
  setAnalysisStatus: (status: string) => void
}

export function useAnalysisControls({
  analysisId,
  token,
  onRefresh,
  onDataRefresh,
  showNotification,
}: UseAnalysisControlsOptions): UseAnalysisControlsReturn {
  const [analysisStatus, setAnalysisStatus] = useState<string>('pending')
  const [analysisProgress, setAnalysisProgress] = useState<number>(0)
  const [totalVariants, setTotalVariants] = useState<number>(0)
  const [processedVariants, setProcessedVariants] = useState<number>(0)
  const [isAnalysisRunning, setIsAnalysisRunning] = useState(false)
  const [showProgress, setShowProgress] = useState(false)
  const eventSourceRef = useRef<EventSource | null>(null)

  const closeSSEStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }, [])

  const openSSEStream = useCallback(() => {
    if (!analysisId || eventSourceRef.current) return

    const es = new EventSource(
      apiUrl(`/api/analysis/stream/${analysisId}`),
      { withCredentials: true }
    )
    eventSourceRef.current = es

    es.onmessage = async (event) => {
      try {
        const progress = JSON.parse(event.data)

        const hasCompletedResults =
          progress.analysis_results?.status === 'completed' && progress.status === 'processing'
        const shouldBeCompleted =
          progress.progress_percentage >= 100 && progress.status !== 'completed'

        if (hasCompletedResults || shouldBeCompleted) {
          setAnalysisStatus('completed')
          setAnalysisProgress(100)
          setTotalVariants(progress.total_variants || 0)
          setProcessedVariants(progress.processed_variants || progress.total_variants || 0)
          setIsAnalysisRunning(false)
        } else {
          setAnalysisStatus(progress.status)
          setAnalysisProgress(progress.progress_percentage || 0)
          setTotalVariants(progress.total_variants || 0)
          setProcessedVariants(progress.processed_variants || 0)
          setIsAnalysisRunning(progress.status === 'processing')
        }

        const isTerminal = ['completed', 'failed', 'stopped', 'cancelled'].includes(progress.status)
        if (isTerminal || hasCompletedResults || shouldBeCompleted) {
          es.close()
          eventSourceRef.current = null
          if (onRefresh && token) {
            await onRefresh(token)
          }
        }
      } catch (err) {
        console.error('SSE message parse error:', err)
      }
    }

    es.onerror = () => {
      console.warn('SSE connection issue for analysis status.')
    }
  }, [analysisId, token, onRefresh])

  // Aliases used by action handlers below
  const startProgressPolling = openSSEStream
  const stopProgressPolling = closeSSEStream

  // One-shot status check used after cancel/pause to sync state
  const checkAnalysisStatus = useCallback(async () => {
    if (!token || !analysisId) return

    try {
      const response = await apiFetch(`/api/analysis/status/${analysisId}`)
      const progress = await response.json()

      const hasCompletedResults =
        progress.analysis_results?.status === 'completed' && progress.status === 'processing'
      const shouldBeCompleted =
        progress.progress_percentage >= 100 && progress.status !== 'completed'

      if (hasCompletedResults || shouldBeCompleted) {
        setAnalysisStatus('completed')
        setAnalysisProgress(100)
        setTotalVariants(progress.total_variants || 0)
        setProcessedVariants(progress.processed_variants || progress.total_variants || 0)
        setIsAnalysisRunning(false)
      } else {
        setAnalysisStatus(progress.status)
        setAnalysisProgress(progress.progress_percentage || 0)
        setTotalVariants(progress.total_variants || 0)
        setProcessedVariants(progress.processed_variants || 0)
        setIsAnalysisRunning(progress.status === 'processing')
      }

      if (progress.status === 'completed' || hasCompletedResults || shouldBeCompleted) {
        closeSSEStream()
        if (onRefresh && token) {
          await onRefresh(token)
        }
      }
    } catch (error) {
      console.error('Error checking analysis status:', error)
    }
  }, [token, analysisId, onRefresh, closeSSEStream])

  // Clean up on unmount
  useEffect(() => {
    return () => closeSSEStream()
  }, [closeSSEStream])

  // Connect to SSE stream on mount / when analysisId changes
  useEffect(() => {
    if (!token || !analysisId) return
    openSSEStream()
  }, [analysisId, token])

  const handleStartAnalysis = useCallback(async () => {
    if (!token || !analysisId) {
      showNotification('Missing authentication or analysis ID. Please refresh the page.', 'error')
      return
    }

    try {
      setIsAnalysisRunning(true)
      const response = await apiFetch(`/api/analysis/start/${analysisId}`, { method: 'POST' })
      const result = await response.json()

      if (result.message && result.message.includes('already')) {
        setAnalysisStatus(result.status)
        setAnalysisProgress(result.progress_percentage || 0)
        setTotalVariants(result.total_variants || 0)
        setProcessedVariants(result.processed_variants || 0)
        setIsAnalysisRunning(result.status === 'processing')

        if (result.status === 'completed') {
          showNotification('Analysis is already completed', 'info')
        } else {
          showNotification(`Analysis is already ${result.status}`, 'info')
        }
      } else {
        const isRestart = result.status === 'processing' && result.progress_percentage === 0
        setAnalysisStatus(result.status)
        setAnalysisProgress(result.progress_percentage || 0)
        setTotalVariants(result.total_variants || 0)
        setProcessedVariants(result.processed_variants || 0)
        setShowProgress(true)
        startProgressPolling()
        showNotification(
          isRestart ? 'Analysis restarted successfully' : 'Analysis started successfully',
          'success'
        )
      }
    } catch (error) {
      if (error instanceof ApiError) {
        showNotification(`Failed to start analysis: ${error.status} - ${error.message}`, 'error')
      } else {
        showNotification(`Error starting analysis: ${error}`, 'error')
      }
      setIsAnalysisRunning(false)
    }
  }, [token, analysisId, showNotification, startProgressPolling])

  const handleStopAnalysis = useCallback(async () => {
    if (!token || !analysisId) {
      showNotification('Missing authentication or analysis ID. Please refresh the page.', 'error')
      return
    }

    try {
      await apiFetch(`/api/analysis/cancel/${analysisId}`, { method: 'POST' })
      setAnalysisStatus('stopped')
      setIsAnalysisRunning(false)
      stopProgressPolling()
      await checkAnalysisStatus()
      showNotification('Analysis stopped successfully', 'success')
    } catch (error) {
      if (error instanceof ApiError) {
        showNotification(`Failed to stop analysis: ${error.status} - ${error.message}`, 'error')
      } else {
        showNotification(`Error stopping analysis: ${error}`, 'error')
      }
    }
  }, [token, analysisId, showNotification, stopProgressPolling, checkAnalysisStatus])

  const handlePauseAnalysis = useCallback(async () => {
    if (!token || !analysisId) {
      showNotification('Missing authentication or analysis ID. Please refresh the page.', 'error')
      return
    }

    try {
      await apiFetch(`/api/analysis/pause/${analysisId}`, { method: 'POST' })
      setAnalysisStatus('paused')
      setIsAnalysisRunning(false)
      stopProgressPolling()
      await checkAnalysisStatus()
      showNotification('Analysis paused successfully', 'success')
    } catch (error) {
      if (error instanceof ApiError) {
        showNotification(`Failed to pause analysis: ${error.status} - ${error.message}`, 'error')
      } else {
        showNotification(`Error pausing analysis: ${error}`, 'error')
      }
    }
  }, [token, analysisId, showNotification, stopProgressPolling, checkAnalysisStatus])

  const handleResumeAnalysis = useCallback(async () => {
    if (!token || !analysisId) {
      showNotification('Missing authentication or analysis ID. Please refresh the page.', 'error')
      return
    }

    try {
      setIsAnalysisRunning(true)
      await apiFetch(`/api/analysis/resume/${analysisId}`, { method: 'POST' })
      setAnalysisStatus('processing')
      setShowProgress(true)
      startProgressPolling()
      showNotification('Analysis resumed successfully', 'success')
    } catch (error) {
      if (error instanceof ApiError) {
        showNotification(`Failed to resume analysis: ${error.status} - ${error.message}`, 'error')
      } else {
        showNotification(`Error resuming analysis: ${error}`, 'error')
      }
      setIsAnalysisRunning(false)
    }
  }, [token, analysisId, showNotification, startProgressPolling])

  const resetAnalysisState = useCallback(() => {
    setAnalysisStatus('pending')
    setAnalysisProgress(0)
    setTotalVariants(0)
    setProcessedVariants(0)
    setIsAnalysisRunning(false)
    stopProgressPolling()
  }, [stopProgressPolling])

  return {
    analysisStatus,
    analysisProgress,
    totalVariants,
    processedVariants,
    isAnalysisRunning,
    showProgress,
    setShowProgress,
    handleStartAnalysis,
    handleStopAnalysis,
    handlePauseAnalysis,
    handleResumeAnalysis,
    resetAnalysisState,
    setAnalysisStatus,
  }
}
