'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { apiUrl } from '@/lib/api'

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
  const progressIntervalRef = useRef<NodeJS.Timeout | null>(null)

  // Check analysis status
  const checkAnalysisStatus = useCallback(async () => {
    if (!token || !analysisId) return

    try {
      const response = await fetch(apiUrl(`/api/analysis/status/${analysisId}`), {
        credentials: 'include',
      })
      if (response.ok) {
        const progress = await response.json()

        const hasCompletedResults =
          progress.analysis_results &&
          progress.analysis_results.status === 'completed' &&
          progress.status === 'processing'

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
          stopProgressPolling()
          if (onRefresh && token) {
            await onRefresh(token)
          }
        }
      }
    } catch (error) {
      console.error('Error checking analysis status:', error)
    }
  }, [token, analysisId, onRefresh])

  const startProgressPolling = useCallback(() => {
    if (progressIntervalRef.current) return
    const interval = setInterval(checkAnalysisStatus, 2000)
    progressIntervalRef.current = interval
  }, [checkAnalysisStatus])

  const stopProgressPolling = useCallback(() => {
    if (progressIntervalRef.current) {
      clearInterval(progressIntervalRef.current)
      progressIntervalRef.current = null
    }
  }, [])

  // Clean up on unmount
  useEffect(() => {
    return () => stopProgressPolling()
  }, [stopProgressPolling])

  // Initial status check + polling
  useEffect(() => {
    if (!token || !analysisId) return

    const checkStatus = async () => {
      try {
        const response = await fetch(apiUrl(`/api/analysis/status/${analysisId}`), {
          credentials: 'include',
        })
        if (response.ok) {
          const progress = await response.json()
          setAnalysisStatus(progress.status)
          setAnalysisProgress(progress.progress_percentage || 0)
          setTotalVariants(progress.total_variants || 0)
          setProcessedVariants(progress.processed_variants || 0)
          const stillRunning = ['processing', 'running'].includes(progress.status)
          setIsAnalysisRunning(stillRunning)
          return stillRunning
        }
      } catch (error) {
        console.error('Error checking analysis status:', error)
      }
      return false
    }

    checkStatus()

    if (!isAnalysisRunning) return

    const interval = setInterval(async () => {
      const stillRunning = await checkStatus()
      if (!stillRunning) {
        clearInterval(interval)
      }
    }, 2000)

    return () => clearInterval(interval)
  }, [analysisId, token, isAnalysisRunning])

  const handleStartAnalysis = useCallback(async () => {
    if (!token || !analysisId) {
      showNotification('Missing authentication or analysis ID. Please refresh the page.', 'error')
      return
    }

    try {
      setIsAnalysisRunning(true)
      const response = await fetch(apiUrl(`/api/analysis/start/${analysisId}`), {
        method: 'POST',
        credentials: 'include',
      })

      if (response.ok) {
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
      } else {
        const errorText = await response.text()
        showNotification(`Failed to start analysis: ${response.status} - ${errorText}`, 'error')
        setIsAnalysisRunning(false)
      }
    } catch (error) {
      showNotification(`Error starting analysis: ${error}`, 'error')
      setIsAnalysisRunning(false)
    }
  }, [token, analysisId, showNotification, startProgressPolling])

  const handleStopAnalysis = useCallback(async () => {
    if (!token || !analysisId) {
      showNotification('Missing authentication or analysis ID. Please refresh the page.', 'error')
      return
    }

    try {
      const response = await fetch(apiUrl(`/api/analysis/cancel/${analysisId}`), {
        method: 'POST',
        credentials: 'include',
      })

      if (response.ok) {
        setAnalysisStatus('stopped')
        setIsAnalysisRunning(false)
        stopProgressPolling()
        await checkAnalysisStatus()
        showNotification('Analysis stopped successfully', 'success')
      } else {
        const errorText = await response.text()
        showNotification(`Failed to stop analysis: ${response.status} - ${errorText}`, 'error')
      }
    } catch (error) {
      showNotification(`Error stopping analysis: ${error}`, 'error')
    }
  }, [token, analysisId, showNotification, stopProgressPolling, checkAnalysisStatus])

  const handlePauseAnalysis = useCallback(async () => {
    if (!token || !analysisId) {
      showNotification('Missing authentication or analysis ID. Please refresh the page.', 'error')
      return
    }

    try {
      const response = await fetch(apiUrl(`/api/analysis/pause/${analysisId}`), {
        method: 'POST',
        credentials: 'include',
      })

      if (response.ok) {
        setAnalysisStatus('paused')
        setIsAnalysisRunning(false)
        stopProgressPolling()
        await checkAnalysisStatus()
        showNotification('Analysis paused successfully', 'success')
      } else {
        const errorText = await response.text()
        showNotification(`Failed to pause analysis: ${response.status} - ${errorText}`, 'error')
      }
    } catch (error) {
      showNotification(`Error pausing analysis: ${error}`, 'error')
    }
  }, [token, analysisId, showNotification, stopProgressPolling, checkAnalysisStatus])

  const handleResumeAnalysis = useCallback(async () => {
    if (!token || !analysisId) {
      showNotification('Missing authentication or analysis ID. Please refresh the page.', 'error')
      return
    }

    try {
      setIsAnalysisRunning(true)
      const response = await fetch(apiUrl(`/api/analysis/resume/${analysisId}`), {
        method: 'POST',
        credentials: 'include',
      })

      if (response.ok) {
        setAnalysisStatus('processing')
        setShowProgress(true)
        startProgressPolling()
        showNotification('Analysis resumed successfully', 'success')
      } else {
        const errorText = await response.text()
        showNotification(`Failed to resume analysis: ${response.status} - ${errorText}`, 'error')
        setIsAnalysisRunning(false)
      }
    } catch (error) {
      showNotification(`Error resuming analysis: ${error}`, 'error')
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
