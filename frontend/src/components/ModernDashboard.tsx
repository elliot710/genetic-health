'use client'

import { useState, useEffect, useCallback } from 'react'
import { 
  Apple, Brain, Dumbbell, Heart, Zap, Palette, 
  ChevronDown, ChevronRight, TrendingUp, AlertTriangle, CheckCircle, 
  Settings, Trash2, Info, Shield, Search,
  Upload, Dna, Activity, BarChart3, Sparkles, Target,
  Sun, Moon, Users, X, LogOut, Home,
  Square, Play, Pause, Pill, FlaskConical, FileText
} from 'lucide-react'
import { getTheme } from '../utils/theme'
import type { LucideIcon } from 'lucide-react'
import type { DashboardData, HealthRisk, DrugResponse, NutritionTrait, SportsPerformance, AncestryResult, CarrierCondition, MethylationProfile, DetoxProfile, IntelligenceTrait, PersonalityTraitData, PhysicalTrait, WellnessTrait, RareMutation, UncommonMutation } from './categories/types'

// Import category components
import FoodNutritionPanel from './categories/FoodNutritionPanel'
import IntelligencePanel from './categories/IntelligencePanel'
import PhysicalTraitsPanel from './categories/PhysicalTraitsPanel'
import PersonalityPanel from './categories/PersonalityPanel'
import SportsPanel from './categories/SportsPanel'
import HealthPanel from './categories/HealthPanel'
import DrugResponsesPanel from './categories/DrugResponsesPanel'
import AncestryPanel from './categories/AncestryPanel'
import CarrierStatusPanel from './categories/CarrierStatusPanel'
import WellnessPanel from './categories/WellnessPanel'
import MethylationPanel from './categories/MethylationPanel'
import DetoxPanel from './categories/DetoxPanel'
import RareMutationsPanel from './categories/RareMutationsPanel'
import UncommonMutationsPanel from './categories/UncommonMutationsPanel'
import { RiskDistributionChart, FunctionalCategoriesChart, OverviewSummaryPie } from './categories/GenomicCharts'
import SmartInsights from './SmartInsights'
import KnowledgeGraph from './KnowledgeGraph'
import AdminPanel from './admin/AdminPanel'
import SettingsPanel from './SettingsPanel'
import VariantSearch from './VariantSearch'
import AnalysisProgressLoader from './AnalysisProgressLoader'
import { getThemeClass } from '../utils/theme'

interface ModernDashboardProps {
  token?: string
  analysisData?: DashboardData | null
  analysisId?: number | null
  onRefresh?: (token: string) => Promise<void>
  isAdmin?: boolean
  userName?: string
  userAvatarUrl?: string | null
}

export default function ModernDashboard({ token, analysisData, analysisId, onRefresh, isAdmin, userName, userAvatarUrl }: ModernDashboardProps) {
  console.log('Dashboard component props:', { token: !!token, analysisData, analysisId })
  console.log('Analysis ID in dashboard:', analysisId)
  
  // ALL STATE HOOKS MUST BE AT THE TOP
  const [data, setData] = useState<DashboardData | undefined>(analysisData || undefined)
  const [loading, setLoading] = useState(!analysisData)
  const [showProgress, setShowProgress] = useState(false)
  const [progressInterval, setProgressInterval] = useState<NodeJS.Timeout | null>(null)
  const [activeCategory, setActiveCategory] = useState(() => {
    if (typeof window !== 'undefined') {
      const hash = window.location.hash.slice(1)
      return hash || 'overview'
    }
    return 'overview'
  })
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [variantCategories, setVariantCategories] = useState<{name: string, count: number}[]>([])
  const [variantCategoryStats, setVariantCategoryStats] = useState<{total: number, annotated: number}>({total: 0, annotated: 0})
  const [currentUserName, setCurrentUserName] = useState(userName || 'User')
  const [currentAvatarUrl, setCurrentAvatarUrl] = useState<string | null | undefined>(userAvatarUrl)
  
  // Notification system
  const [notification, setNotification] = useState<{
    show: boolean
    message: string
    type: 'success' | 'error' | 'info'
  }>({ show: false, message: '', type: 'info' })
  
  // Initialize theme from localStorage or default to false
  const [isDarkMode, setIsDarkMode] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('darkMode')
      return saved ? JSON.parse(saved) : false
    }
    return false
  })

  // Analysis control state - MOVED TO TOP
  const [analysisStatus, setAnalysisStatus] = useState<string>('pending')
  const [analysisProgress, setAnalysisProgress] = useState<number>(0)
  const [totalVariants, setTotalVariants] = useState<number>(0)
  const [processedVariants, setProcessedVariants] = useState<number>(0)
  const [isAnalysisRunning, setIsAnalysisRunning] = useState(false)

  // Show notification helper
  const showNotification = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    setNotification({ show: true, message, type })
    setTimeout(() => {
      setNotification(prev => ({ ...prev, show: false }))
    }, 3000) // Hide after 3 seconds
  }

  // Save theme preference to localStorage whenever it changes
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('darkMode', JSON.stringify(isDarkMode))
      document.documentElement.classList.toggle('dark', isDarkMode)
    }
  }, [isDarkMode])

  // Re-fetch user info (e.g. after avatar update in settings)
  const refreshUserInfo = useCallback(async () => {
    if (!token) return
    try {
      const res = await fetch('http://localhost:8000/auth/me', {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (res.ok) {
        const u = await res.json()
        setCurrentUserName(u.full_name || u.username || 'User')
        setCurrentAvatarUrl(u.avatar_url)
      }
    } catch { /* ignore */ }
  }, [token])

  // Sync URL hash with active category
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const newHash = activeCategory === 'overview' ? '' : activeCategory
      if (window.location.hash.slice(1) !== newHash) {
        window.history.replaceState(null, '', newHash ? `#${newHash}` : window.location.pathname)
      }
    }
  }, [activeCategory])

  useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash.slice(1)
      setActiveCategory(hash || 'overview')
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  // Fetch variant categories for overview
  useEffect(() => {
    if (!token) return
    fetch('http://localhost:8000/api/variants/categories', {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.categories) { setVariantCategories(d.categories); setVariantCategoryStats({total: d.total_variants || 0, annotated: d.annotated_variants || 0}) } })
      .catch(() => {})
  }, [token])

  // Check initial status and start polling if needed
  useEffect(() => {
    if (!token || !analysisId) return

    const checkStatus = async () => {
      try {
        const response = await fetch(`http://localhost:8000/api/analysis/status/${analysisId}`, {
          headers: { 'Authorization': `Bearer ${token}` }
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

    // Initial check
    checkStatus()

    // Only start polling if analysis is running
    if (!isAnalysisRunning) return

    const interval = setInterval(async () => {
      const stillRunning = await checkStatus()
      if (!stillRunning) {
        clearInterval(interval)
      }
    }, 2000)

    return () => clearInterval(interval)
  }, [analysisId, token, isAnalysisRunning])

  // Load real data from backend on component mount only if no analysisData provided
  useEffect(() => {
    if (!analysisData && token) {
      const loadRealData = async () => {
        setLoading(true)
        
        try {
          const response = await fetch('http://localhost:8000/api/analysis/dashboard-data', {
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json',
            },
          })

          if (response.ok) {
            const realData = await response.json()
            console.log('Loaded real dashboard data:', realData)
            setData(realData)
          } else {
            console.error('Failed to load dashboard data:', response.status)
            // Check if there's an analysis in progress
            if (analysisId) {
              setShowProgress(true)
            } else {
              setData(undefined)
            }
          }
        } catch (error) {
          console.error('Error loading dashboard data:', error)
          // Check if there's an analysis in progress
          if (analysisId) {
            setShowProgress(true)
          } else {
            setData(undefined)
          }
        } finally {
          setLoading(false)
        }
      }

      loadRealData()
    }
  }, [analysisData, token, analysisId])

  // Check if analysis ID is provided and show progress
  useEffect(() => {
    if (analysisId && !data) {
      setShowProgress(true)
    }
  }, [analysisId, data])

  // Update data when analysisData prop changes
  useEffect(() => {
    if (analysisData) {
      console.log('Dashboard received analysisData:', {
        summary: analysisData.summary,
        filename_paths: {
          upload_info_filename: analysisData.summary?.upload_info?.filename,
          data_sources: analysisData.summary?.data_sources,
          real_data_filename: analysisData.real_data?.upload_result?.filename
        }
      })
      setData(analysisData)
      setLoading(false)
    }
  }, [analysisData])

  // Safety check - if no data available, show loading or empty state
  if (!data && !loading) {
    console.log('Dashboard: No data and not loading, showing empty state')
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-xl font-semibold mb-2">No Data Available</h2>
          <p className="text-gray-600">Please upload your genetic data to get started.</p>
        </div>
      </div>
    )
  }

  console.log('Dashboard about to render with data:', data)

  // Reset function for clearing data
  const onReset = () => {
    setData(undefined)
    setActiveCategory('overview')
  }

  // Progress handlers
  const handleAnalysisComplete = (results: DashboardData) => {
    console.log('Analysis completed:', results)
    setData(results)
    setShowProgress(false)
  }

  const handleAnalysisError = (error: string) => {
    console.error('Analysis error:', error)
    setShowProgress(false)
    // Could show an error message to the user
  }

  // Use centralized theme system
  const theme = getTheme(isDarkMode)

  const categories = [
    {
      id: 'overview',
      title: 'Overview',
      icon: Home,
    },
    {
      id: 'health',
      title: 'Health & Wellness',
      icon: Heart,
    },
    {
      id: 'food-nutrition',
      title: 'Food & Nutrition',
      icon: Apple,
    },
    {
      id: 'drug-responses',
      title: 'Drug Responses',
      icon: Shield,
    },
    {
      id: 'physical-traits',
      title: 'Physical Traits',
      icon: Target,
    },
    {
      id: 'sports',
      title: 'Sports & Fitness',
      icon: Dumbbell,
    },
    {
      id: 'intelligence',
      title: 'Intelligence',
      icon: Brain,
    },
    {
      id: 'personality',
      title: 'Personality',
      icon: Palette,
    },
    {
      id: 'ancestry',
      title: 'Ancestry & Origins',
      icon: Users,
    },
    {
      id: 'carrier-status',
      title: 'Carrier Status',
      icon: AlertTriangle,
    },
    {
      id: 'wellness',
      title: 'Wellness Reports',
      icon: Activity,
    },
    // Separator
    {
      id: 'separator-1',
      title: '',
      icon: null,
      isSeparator: true
    },
    {
      id: 'methylation',
      title: 'Methylation',
      icon: Dna,
    },
    {
      id: 'detox',
      title: 'Detoxification',
      icon: Zap,
    },
    {
      id: 'rare-mutations',
      title: 'Rare Mutations',
      icon: AlertTriangle,
    },
    {
      id: 'uncommon-mutations',
      title: 'Uncommon Mutations', 
      icon: Dna,
    },
    // Separator
    {
      id: 'separator-2',
      title: '',
      icon: null,
      isSeparator: true
    },
    {
      id: 'variant-search',
      title: 'Variant Search',
      icon: Search,
    },
    {
      id: 'knowledge-graph',
      title: 'Knowledge Graph',
      icon: Activity,
    },
  ]

  const handleDeleteData = async () => {
    setIsDeleting(true)
    try {
      const response = await fetch('http://localhost:8000/upload/data', {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })

      if (response.ok) {
        // Clear all data state immediately
        setData(undefined)
        setAnalysisStatus('pending')
        setAnalysisProgress(0)
        setTotalVariants(0)
        setProcessedVariants(0)
        setIsAnalysisRunning(false)
        if (progressInterval) { clearInterval(progressInterval); setProgressInterval(null) }
        setActiveCategory('overview')
        setShowDeleteDialog(false)
        showNotification('All data deleted successfully', 'success')
        // Re-fetch from server to fully sync parent state
        if (onRefresh && token) {
          await onRefresh(token)
        }
      } else {
        showNotification('Failed to delete data', 'error')
      }
    } catch (error) {
      console.error('Error deleting data:', error)
      showNotification('Error deleting data', 'error')
    } finally {
      setIsDeleting(false)
    }
  }

  // Check analysis status
  const checkAnalysisStatus = async () => {
    if (!token || !analysisId) return

    try {
      const response = await fetch(`http://localhost:8000/api/analysis/status/${analysisId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (response.ok) {
        const progress = await response.json()
        
        // Check for status mismatch (analysis shows processing but has completed results)
        const hasCompletedResults = (
          progress.analysis_results && 
          progress.analysis_results.status === 'completed' &&
          progress.status === 'processing'
        )
        
        // Check for progress mismatch (100% but not marked as completed)
        const shouldBeCompleted = (
          progress.progress_percentage >= 100 && 
          progress.status !== 'completed'
        )
        
        if (hasCompletedResults || shouldBeCompleted) {
          // Auto-fix status mismatch — treat as completed
          console.log('Status mismatch detected, marking as completed...')
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
        
        // If analysis is complete, stop polling and refresh data
        if (progress.status === 'completed' || hasCompletedResults || shouldBeCompleted) {
          stopProgressPolling()
          if (onRefresh) {
            await onRefresh(token)
          }
        }
      }
    } catch (error) {
      console.error('Error checking analysis status:', error)
    }
  }

  // Start automatic progress polling
  const startProgressPolling = () => {
    if (progressInterval) return // Already polling
    
    const interval = setInterval(checkAnalysisStatus, 2000) // Poll every 2 seconds
    setProgressInterval(interval)
  }

  // Stop automatic progress polling
  const stopProgressPolling = () => {
    if (progressInterval) {
      clearInterval(progressInterval)
      setProgressInterval(null)
    }
  }

  // Start analysis
  const handleStartAnalysis = async () => {
    console.log('Start analysis clicked. Token:', !!token, 'Analysis ID:', analysisId)
    if (!token || !analysisId) {
      console.error('Missing token or analysisId:', { token: !!token, analysisId })
      showNotification('Missing authentication or analysis ID. Please refresh the page.', 'error')
      return
    }

    try {
      setIsAnalysisRunning(true)
      console.log(`Starting analysis for ID: ${analysisId}`)
      const response = await fetch(`http://localhost:8000/api/analysis/start/${analysisId}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      })
      
      console.log('Start analysis response status:', response.status)
      
      if (response.ok) {
        const result = await response.json()
        console.log('Start analysis result:', result)
        
        // Check if backend says analysis is already completed/processing
        if (result.message && result.message.includes('already')) {
          // Backend prevented restart - sync with actual status
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
          // Analysis actually started or restarted
          const isRestart = result.status === 'processing' && result.progress_percentage === 0
          
          setAnalysisStatus(result.status)
          setAnalysisProgress(result.progress_percentage || 0)
          setTotalVariants(result.total_variants || 0)
          setProcessedVariants(result.processed_variants || 0)
          setShowProgress(true)
          startProgressPolling()
          
          if (isRestart) {
            showNotification('Analysis restarted successfully', 'success')
          } else {
            showNotification('Analysis started successfully', 'success')
          }
        }
      } else {
        const errorText = await response.text()
        console.error('Start analysis failed:', response.status, errorText)
        showNotification(`Failed to start analysis: ${response.status} - ${errorText}`, 'error')
        setIsAnalysisRunning(false)
      }
    } catch (error) {
      console.error('Error starting analysis:', error)
      showNotification(`Error starting analysis: ${error}`, 'error')
      setIsAnalysisRunning(false)
    }
  }

  const handleStopAnalysis = async () => {
    console.log('Stop analysis clicked. Token:', !!token, 'Analysis ID:', analysisId)
    if (!token || !analysisId) {
      console.error('Missing token or analysisId:', { token: !!token, analysisId })
      showNotification('Missing authentication or analysis ID. Please refresh the page.', 'error')
      return
    }

    try {
      console.log(`Stopping analysis for ID: ${analysisId}`)
      const response = await fetch(`http://localhost:8000/api/analysis/cancel/${analysisId}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      })
      
      console.log('Stop analysis response status:', response.status)
      
      if (response.ok) {
        const result = await response.json()
        console.log('Stop analysis result:', result)
        setAnalysisStatus('stopped')
        setIsAnalysisRunning(false)
        stopProgressPolling()
        await checkAnalysisStatus() // Refresh status
        showNotification('Analysis stopped successfully', 'success')
      } else {
        const errorText = await response.text()
        console.error('Stop analysis failed:', response.status, errorText)
        showNotification(`Failed to stop analysis: ${response.status} - ${errorText}`, 'error')
      }
    } catch (error) {
      console.error('Error stopping analysis:', error)
      showNotification(`Error stopping analysis: ${error}`, 'error')
    }
  }

  const handlePauseAnalysis = async () => {
    console.log('Pause analysis clicked. Token:', !!token, 'Analysis ID:', analysisId)
    if (!token || !analysisId) {
      console.error('Missing token or analysisId:', { token: !!token, analysisId })
      showNotification('Missing authentication or analysis ID. Please refresh the page.', 'error')
      return
    }

    try {
      console.log(`Pausing analysis for ID: ${analysisId}`)
      const response = await fetch(`http://localhost:8000/api/analysis/pause/${analysisId}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      })
      
      console.log('Pause analysis response status:', response.status)
      
      if (response.ok) {
        const result = await response.json()
        console.log('Pause analysis result:', result)
        setAnalysisStatus('paused')
        setIsAnalysisRunning(false)
        stopProgressPolling()
        await checkAnalysisStatus() // Refresh status
        showNotification('Analysis paused successfully', 'success')
      } else {
        const errorText = await response.text()
        console.error('Pause analysis failed:', response.status, errorText)
        showNotification(`Failed to pause analysis: ${response.status} - ${errorText}`, 'error')
      }
    } catch (error) {
      console.error('Error pausing analysis:', error)
      showNotification(`Error pausing analysis: ${error}`, 'error')
    }
  }

  const handleResumeAnalysis = async () => {
    console.log('Resume analysis clicked. Token:', !!token, 'Analysis ID:', analysisId)
    if (!token || !analysisId) {
      console.error('Missing token or analysisId:', { token: !!token, analysisId })
      showNotification('Missing authentication or analysis ID. Please refresh the page.', 'error')
      return
    }

    try {
      setIsAnalysisRunning(true)
      console.log(`Resuming analysis for ID: ${analysisId}`)
      const response = await fetch(`http://localhost:8000/api/analysis/resume/${analysisId}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      })
      
      console.log('Resume analysis response status:', response.status)
      
      if (response.ok) {
        const result = await response.json()
        console.log('Resume analysis result:', result)
        setAnalysisStatus('processing')
        setShowProgress(true)
        startProgressPolling()
        showNotification('Analysis resumed successfully', 'success')
      } else {
        const errorText = await response.text()
        console.error('Resume analysis failed:', response.status, errorText)
        showNotification(`Failed to resume analysis: ${response.status} - ${errorText}`, 'error')
        setIsAnalysisRunning(false)
      }
    } catch (error) {
      console.error('Error resuming analysis:', error)
      showNotification(`Error resuming analysis: ${error}`, 'error')
      setIsAnalysisRunning(false)
    }
  }

  const handleRefreshData = async () => {
    try {
      if (onRefresh && token) {
        await onRefresh(token)
        showNotification('Data refreshed successfully', 'success')
      }
    } catch (error) {
      console.error('Error refreshing data:', error)
      showNotification('Error refreshing data', 'error')
    }
  }

  const generateHealthInsights = (): { category: string; insight: string; icon: LucideIcon; color: string; bgColor: string; navigateTo?: string }[] => {
    const insights: { category: string; insight: string; icon: LucideIcon; color: string; bgColor: string; navigateTo?: string }[] = []
    
    // Return empty array if data is not loaded yet
    if (!data) return insights
    
    if (Array.isArray(data?.health_risks) && data.health_risks.length > 0) {
      const highRisk = data.health_risks.filter((r: { risk_level?: string }) => r.risk_level === 'high' || r.risk_level === 'very_high').length
      const moderateRisk = data.health_risks.filter((r: { risk_level?: string }) => r.risk_level === 'moderate').length
      
      if (highRisk > 0) {
        insights.push({
          category: 'High Risk Variants',
          insight: `${highRisk} high-risk genetic variants identified requiring attention`,
          icon: AlertTriangle,
          color: getThemeClass('text-red-600', isDarkMode),
          bgColor: getThemeClass('bg-red-50', isDarkMode),
          navigateTo: 'health',
        })
      }
      
      if (moderateRisk > 0) {
        insights.push({
          category: 'Moderate Risk',
          insight: `${moderateRisk} variants show moderate risk associations`,
          icon: Info,
          color: getThemeClass('text-amber-600', isDarkMode),
          bgColor: getThemeClass('bg-amber-50', isDarkMode),
          navigateTo: 'health',
        })
      }
    }
    
    if (Array.isArray(data?.drug_responses) && data.drug_responses.length > 0) {
      const poor = data.drug_responses.filter((r: DrugResponse) => r.response_type === 'poor').length
      const rapid = data.drug_responses.filter((r: DrugResponse) => r.response_type === 'rapid').length
      const detail = poor > 0 || rapid > 0
        ? ` — ${poor > 0 ? `${poor} poor metabolizer` : ''}${poor > 0 && rapid > 0 ? ', ' : ''}${rapid > 0 ? `${rapid} rapid metabolizer` : ''}`
        : ''
      insights.push({
        category: 'Drug Metabolism',
        insight: `${data.drug_responses.length} drug-gene interactions identified${detail}`,
        icon: Shield,
        color: getThemeClass('text-purple-600', isDarkMode),
        bgColor: getThemeClass('bg-purple-50', isDarkMode),
        navigateTo: 'drug-responses',
      })
    }

    // Rare mutations
    if (Array.isArray(data?.rare_mutations) && data.rare_mutations.length > 0) {
      const pathogenic = data.rare_mutations.filter((m: RareMutation) => m.mutation_type === 'pathogenic' || m.clinical_significance === 'very_high').length
      insights.push({
        category: 'Rare Mutations',
        insight: `${data.rare_mutations.length} rare mutation${data.rare_mutations.length > 1 ? 's' : ''} detected${pathogenic > 0 ? ` — ${pathogenic} pathogenic` : ''}`,
        icon: AlertTriangle,
        color: getThemeClass('text-red-600', isDarkMode),
        bgColor: getThemeClass('bg-red-50', isDarkMode),
        navigateTo: 'rare-mutations',
      })
    }

    // Carrier status
    if (Array.isArray(data?.carrier_status) && data.carrier_status.length > 0) {
      const carriers = data.carrier_status.filter((c: CarrierCondition) => c.carrier_status === 'carrier').length
      const counseling = data.carrier_status.filter((c: CarrierCondition) => c.genetic_counseling_recommended).length
      if (carriers > 0) {
        insights.push({
          category: 'Carrier Status',
          insight: `Carrier for ${carriers} condition${carriers > 1 ? 's' : ''}${counseling > 0 ? ` — counseling recommended for ${counseling}` : ''}`,
          icon: AlertTriangle,
          color: getThemeClass('text-orange-600', isDarkMode),
          bgColor: getThemeClass('bg-orange-50', isDarkMode),
          navigateTo: 'carrier-status',
        })
      }
    }

    // Nutrition sensitivities
    if (Array.isArray(data?.nutrition_traits) && data.nutrition_traits.length > 0) {
      const sensitivities = data.nutrition_traits.filter((n: NutritionTrait) => n.metabolism_type === 'slow' || n.metabolism_type === 'deficient').length
      if (sensitivities > 0) {
        insights.push({
          category: 'Nutrition',
          insight: `${sensitivities} nutrient metabolism concern${sensitivities > 1 ? 's' : ''} detected`,
          icon: Apple,
          color: getThemeClass('text-orange-600', isDarkMode),
          bgColor: getThemeClass('bg-orange-50', isDarkMode),
          navigateTo: 'food-nutrition',
        })
      }
    }

    // Methylation
    if (Array.isArray(data?.methylation_profiles) && data.methylation_profiles.length > 0) {
      const impaired = data.methylation_profiles.filter((m: MethylationProfile) => m.methylation_capacity === 'impaired' || m.methylation_capacity === 'reduced').length
      if (impaired > 0) {
        insights.push({
          category: 'Methylation',
          insight: `${impaired} gene${impaired > 1 ? 's' : ''} with reduced methylation capacity`,
          icon: Dna,
          color: getThemeClass('text-teal-600', isDarkMode),
          bgColor: getThemeClass('bg-teal-50', isDarkMode),
          navigateTo: 'methylation',
        })
      }
    }

    // Sports performance
    if (Array.isArray(data?.sports_performance) && data.sports_performance.length > 0) {
      const highAdvantage = data.sports_performance.filter((s: SportsPerformance) => s.genetic_advantage === 'high').length
      if (highAdvantage > 0) {
        insights.push({
          category: 'Athletic Potential',
          insight: `High genetic advantage in ${highAdvantage} performance categor${highAdvantage > 1 ? 'ies' : 'y'}`,
          icon: Dumbbell,
          color: getThemeClass('text-green-600', isDarkMode),
          bgColor: getThemeClass('bg-green-50', isDarkMode),
          navigateTo: 'sports',
        })
      }
    }
    
    if (data?.real_data?.variants && data.real_data.variants.length > 0) {
      const variants = data.real_data.variants
      const withRsId = variants.filter((v) => v.rsid && v.rsid !== '-' && v.rsid !== 'nan').length
      const coverage = Math.round((withRsId / variants.length) * 100)
      
      insights.push({
        category: 'Analysis Coverage',
        insight: `${coverage}% of variants have reference IDs for clinical analysis`,
        icon: Target,
        color: getThemeClass('text-green-600', isDarkMode),
        bgColor: getThemeClass('bg-green-50', isDarkMode),
        navigateTo: 'variant-search',
      })
    }
    
    return insights
  }

  const healthInsights = generateHealthInsights()

  const quickInsights = healthInsights.length > 0 ? healthInsights : [
    {
      category: 'Genetic Analysis',
      insight: data?.real_data?.variants && data.real_data.variants.length > 0 
        ? `${data.real_data.variants.length} variants uploaded and ready for analysis`
        : 'Upload genetic data to begin analysis',
      icon: Dna,
      color: getThemeClass('text-blue-600', isDarkMode),
      bgColor: getThemeClass('bg-blue-50', isDarkMode)
    },
    {
      category: 'Processing Status',
      insight: 'Background analysis in progress - check back for updated results',
      icon: Activity,
      color: getThemeClass('text-amber-600', isDarkMode),
      bgColor: getThemeClass('bg-amber-50', isDarkMode)
    },
    {
      category: 'Data Quality',
      insight: data?.summary?.analysis_id 
        ? `Analysis ID: ${data.summary.analysis_id} - Data successfully stored`
        : 'Ready to process your genetic information',
      icon: CheckCircle,
      color: getThemeClass('text-green-600', isDarkMode),
      bgColor: getThemeClass('bg-green-50', isDarkMode)
    }
  ]

  const renderCategoryContent = () => {
    switch (activeCategory) {
      case 'food-nutrition':
        return <FoodNutritionPanel data={data} isDarkMode={isDarkMode} token={token} />
      case 'intelligence':
        return <IntelligencePanel data={data} isDarkMode={isDarkMode} token={token} />
      case 'physical-traits':
        return <PhysicalTraitsPanel data={data} isDarkMode={isDarkMode} token={token} />
      case 'personality':
        return <PersonalityPanel data={data} isDarkMode={isDarkMode} token={token} />
      case 'sports':
        return <SportsPanel data={data} isDarkMode={isDarkMode} token={token} />
      case 'health':
        return <HealthPanel data={data} isDarkMode={isDarkMode} token={token} />
      case 'drug-responses':
        return <DrugResponsesPanel data={data} isDarkMode={isDarkMode} token={token} />
      case 'ancestry':
        return <AncestryPanel data={data} isDarkMode={isDarkMode} />
      case 'carrier-status':
        return <CarrierStatusPanel data={data} isDarkMode={isDarkMode} token={token} />
      case 'wellness':
        return <WellnessPanel data={data} isDarkMode={isDarkMode} token={token} />
      case 'methylation':
        return <MethylationPanel data={data} isDarkMode={isDarkMode} token={token} />
      case 'detox':
        return <DetoxPanel data={data} isDarkMode={isDarkMode} token={token} />
      case 'rare-mutations':
        return <RareMutationsPanel data={data} isDarkMode={isDarkMode} token={token} />
      case 'uncommon-mutations':
        return <UncommonMutationsPanel data={data} isDarkMode={isDarkMode} token={token} />
      case 'variant-search':
        return <VariantSearch token={token} isDarkMode={isDarkMode} theme={theme} />
      case 'knowledge-graph':
        return <KnowledgeGraph isDarkMode={isDarkMode} token={token} />
      case 'admin':
        return <AdminPanel token={token} isDarkMode={isDarkMode} theme={theme} />
      case 'settings':
        return <SettingsPanel token={token} theme={theme} data={data} onProfileUpdate={refreshUserInfo} />
      default:
        return (
          <div className="space-y-6">
            {/* Analysis Progress Banner (if running) */}
            {(analysisStatus === 'processing' || isAnalysisRunning) && (
              <div 
                className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-5 cursor-pointer hover:shadow-lg transition-all duration-300`}
                onClick={() => setShowProgress(true)}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center space-x-3">
                    <div className="p-2 bg-gradient-to-br from-teal-500/20 to-cyan-500/20 rounded-lg border border-teal-500/30">
                      <Activity className={`h-5 w-5 ${getThemeClass('text-teal-600', isDarkMode)} animate-pulse`} />
                    </div>
                    <span className={`font-semibold ${theme.text.primary}`}>Analysis in Progress</span>
                  </div>
                  <span className={`text-sm font-bold ${theme.text.primary}`}>{analysisProgress}%</span>
                </div>
                <div className={`w-full ${isDarkMode ? 'bg-gray-700' : 'bg-gray-200'} rounded-full h-2`}>
                  <div className="bg-gradient-to-r from-teal-500 to-cyan-500 h-2 rounded-full transition-all duration-500" style={{ width: `${Math.max(0, Math.min(100, analysisProgress))}%` }} />
                </div>
              </div>
            )}

            {/* Key Metrics Row - 6 columns, clickable */}
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
              {[
                {
                  label: 'Total Variants',
                  value: (data?.summary?.total_variants || data?.real_data?.variants?.length || 0).toLocaleString(),
                  icon: Dna,
                  gradient: 'from-blue-500 to-indigo-500',
                  navigateTo: 'variant-search',
                },
                {
                  label: 'Analyzed',
                  value: (data?.summary?.analyzed_variants || 0).toLocaleString(),
                  icon: FlaskConical,
                  gradient: 'from-violet-500 to-purple-500',
                  navigateTo: 'variant-search',
                },
                {
                  label: 'Health Risks',
                  value: Array.isArray(data?.health_risks) ? data.health_risks.length : 0,
                  icon: Heart,
                  gradient: 'from-rose-500 to-pink-500',
                  navigateTo: 'health',
                },
                {
                  label: 'Drug Interactions',
                  value: Array.isArray(data?.drug_responses) ? data.drug_responses.length : 0,
                  icon: Pill,
                  gradient: 'from-amber-500 to-orange-500',
                  navigateTo: 'drug-responses',
                },
                {
                  label: 'Carrier Conditions',
                  value: Array.isArray(data?.carrier_status) ? data.carrier_status.filter((c: CarrierCondition) => c.carrier_status === 'carrier').length : 0,
                  icon: AlertTriangle,
                  gradient: 'from-orange-500 to-red-500',
                  navigateTo: 'carrier-status',
                },
                {
                  label: 'Rare Mutations',
                  value: Array.isArray(data?.rare_mutations) ? data.rare_mutations.length : 0,
                  icon: Sparkles,
                  gradient: 'from-red-500 to-rose-600',
                  navigateTo: 'rare-mutations',
                },
              ].map((m, i) => {
                const Icon = m.icon
                return (
                  <div
                    key={i}
                    className={`${theme.glass} border ${theme.glassBorder} rounded-xl p-4 cursor-pointer ${theme.glassHover} transition-all duration-300 group hover:shadow-lg hover:-translate-y-0.5`}
                    onClick={() => setActiveCategory(m.navigateTo)}
                  >
                    <div className="flex items-center gap-3">
                      <div className={`p-2 bg-gradient-to-br ${m.gradient} rounded-lg shadow-lg shadow-black/5 group-hover:scale-110 transition-transform`}>
                        <Icon className="h-4 w-4 text-white" />
                      </div>
                      <div className="min-w-0">
                        <div className={`text-xs ${theme.text.muted} font-medium`}>{m.label}</div>
                        <div className={`text-xl font-bold ${theme.text.primary} leading-tight`}>{m.value}</div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Category Highlights Grid */}
            {(() => {
              const categoryCards: {
                id: string
                title: string
                icon: LucideIcon
                gradient: string
                items: { label: string; value: string | number; color?: string }[]
                summary: string
                hasData: boolean
              }[] = []

              // Health
              if (Array.isArray(data?.health_risks) && data.health_risks.length > 0) {
                const high = data.health_risks.filter((r: HealthRisk) => r.risk_level === 'high').length
                const moderate = data.health_risks.filter((r: HealthRisk) => r.risk_level === 'moderate').length
                const low = data.health_risks.filter((r: HealthRisk) => r.risk_level === 'low').length
                const topCondition = data.health_risks.find((r: HealthRisk) => r.risk_level === 'high')?.condition || data.health_risks[0]?.condition || ''
                categoryCards.push({
                  id: 'health', title: 'Health & Wellness', icon: Heart, gradient: 'from-rose-500 to-pink-500',
                  items: [
                    ...(high > 0 ? [{ label: 'High risk', value: high, color: isDarkMode ? 'text-red-400' : 'text-red-600' }] : []),
                    ...(moderate > 0 ? [{ label: 'Moderate', value: moderate, color: isDarkMode ? 'text-amber-400' : 'text-amber-600' }] : []),
                    ...(low > 0 ? [{ label: 'Low risk', value: low, color: isDarkMode ? 'text-green-400' : 'text-green-600' }] : []),
                  ],
                  summary: topCondition ? `Top: ${topCondition}` : `${data.health_risks.length} conditions analyzed`,
                  hasData: true,
                })
              }

              // Drug Responses
              if (Array.isArray(data?.drug_responses) && data.drug_responses.length > 0) {
                const poor = data.drug_responses.filter((r: DrugResponse) => r.response_type === 'poor').length
                const rapid = data.drug_responses.filter((r: DrugResponse) => r.response_type === 'rapid').length
                const normal = data.drug_responses.filter((r: DrugResponse) => r.response_type === 'normal').length
                const genes = [...new Set(data.drug_responses.map((r: DrugResponse) => r.gene))].slice(0, 3)
                categoryCards.push({
                  id: 'drug-responses', title: 'Drug Responses', icon: Pill, gradient: 'from-amber-500 to-orange-500',
                  items: [
                    ...(poor > 0 ? [{ label: 'Poor metab.', value: poor, color: isDarkMode ? 'text-red-400' : 'text-red-600' }] : []),
                    ...(rapid > 0 ? [{ label: 'Rapid metab.', value: rapid, color: isDarkMode ? 'text-amber-400' : 'text-amber-600' }] : []),
                    ...(normal > 0 ? [{ label: 'Normal', value: normal, color: isDarkMode ? 'text-green-400' : 'text-green-600' }] : []),
                  ],
                  summary: genes.length > 0 ? `Genes: ${genes.join(', ')}` : `${data.drug_responses.length} interactions`,
                  hasData: true,
                })
              }

              // Nutrition
              if (Array.isArray(data?.nutrition_traits) && data.nutrition_traits.length > 0) {
                const slow = data.nutrition_traits.filter((n: NutritionTrait) => n.metabolism_type === 'slow' || n.metabolism_type === 'deficient').length
                const fast = data.nutrition_traits.filter((n: NutritionTrait) => n.metabolism_type === 'fast').length
                const normal = data.nutrition_traits.filter((n: NutritionTrait) => n.metabolism_type === 'normal').length
                const notable = data.nutrition_traits.find((n: NutritionTrait) => n.metabolism_type === 'slow' || n.metabolism_type === 'deficient')
                categoryCards.push({
                  id: 'food-nutrition', title: 'Food & Nutrition', icon: Apple, gradient: 'from-green-500 to-emerald-500',
                  items: [
                    ...(slow > 0 ? [{ label: 'Slow/deficient', value: slow, color: isDarkMode ? 'text-red-400' : 'text-red-600' }] : []),
                    ...(fast > 0 ? [{ label: 'Fast metab.', value: fast, color: isDarkMode ? 'text-amber-400' : 'text-amber-600' }] : []),
                    ...(normal > 0 ? [{ label: 'Normal', value: normal, color: isDarkMode ? 'text-green-400' : 'text-green-600' }] : []),
                  ],
                  summary: notable ? `Watch: ${notable.nutrient}` : `${data.nutrition_traits.length} nutrients analyzed`,
                  hasData: true,
                })
              }

              // Sports Performance
              if (Array.isArray(data?.sports_performance) && data.sports_performance.length > 0) {
                const high = data.sports_performance.filter((s: SportsPerformance) => s.genetic_advantage === 'high').length
                const moderate = data.sports_performance.filter((s: SportsPerformance) => s.genetic_advantage === 'moderate').length
                const topCategory = data.sports_performance.find((s: SportsPerformance) => s.genetic_advantage === 'high')?.category
                categoryCards.push({
                  id: 'sports', title: 'Sports & Fitness', icon: Dumbbell, gradient: 'from-teal-500 to-emerald-500',
                  items: [
                    ...(high > 0 ? [{ label: 'High advantage', value: high, color: isDarkMode ? 'text-green-400' : 'text-green-600' }] : []),
                    ...(moderate > 0 ? [{ label: 'Moderate', value: moderate, color: isDarkMode ? 'text-amber-400' : 'text-amber-600' }] : []),
                  ],
                  summary: topCategory ? `Strength: ${topCategory}` : `${data.sports_performance.length} categories`,
                  hasData: true,
                })
              }

              // Ancestry
              if (Array.isArray(data?.ancestry_results) && data.ancestry_results.length > 0) {
                const sorted = [...data.ancestry_results].sort((a: AncestryResult, b: AncestryResult) => parseFloat(b.percentage) - parseFloat(a.percentage))
                const top = sorted.slice(0, 3)
                categoryCards.push({
                  id: 'ancestry', title: 'Ancestry & Origins', icon: Users, gradient: 'from-indigo-500 to-blue-500',
                  items: top.map((a: AncestryResult) => ({ label: a.population, value: `${parseFloat(a.percentage).toFixed(1)}%` })),
                  summary: top.length > 0 ? `Primary: ${top[0].population}` : 'Ancestry data available',
                  hasData: true,
                })
              }

              // Carrier Status
              if (Array.isArray(data?.carrier_status) && data.carrier_status.length > 0) {
                const carriers = data.carrier_status.filter((c: CarrierCondition) => c.carrier_status === 'carrier').length
                const nonCarrier = data.carrier_status.filter((c: CarrierCondition) => c.carrier_status === 'non-carrier').length
                const counseling = data.carrier_status.filter((c: CarrierCondition) => c.genetic_counseling_recommended).length
                categoryCards.push({
                  id: 'carrier-status', title: 'Carrier Status', icon: AlertTriangle, gradient: 'from-orange-500 to-red-500',
                  items: [
                    ...(carriers > 0 ? [{ label: 'Carrier', value: carriers, color: isDarkMode ? 'text-orange-400' : 'text-orange-600' }] : []),
                    ...(nonCarrier > 0 ? [{ label: 'Non-carrier', value: nonCarrier, color: isDarkMode ? 'text-green-400' : 'text-green-600' }] : []),
                    ...(counseling > 0 ? [{ label: 'Counsel. rec.', value: counseling, color: isDarkMode ? 'text-red-400' : 'text-red-600' }] : []),
                  ],
                  summary: `${data.carrier_status.length} conditions screened`,
                  hasData: true,
                })
              }

              // Methylation
              if (Array.isArray(data?.methylation_profiles) && data.methylation_profiles.length > 0) {
                const impaired = data.methylation_profiles.filter((m: MethylationProfile) => m.methylation_capacity === 'impaired').length
                const reduced = data.methylation_profiles.filter((m: MethylationProfile) => m.methylation_capacity === 'reduced').length
                const normal = data.methylation_profiles.filter((m: MethylationProfile) => m.methylation_capacity === 'normal').length
                categoryCards.push({
                  id: 'methylation', title: 'Methylation', icon: Dna, gradient: 'from-cyan-500 to-teal-500',
                  items: [
                    ...(impaired > 0 ? [{ label: 'Impaired', value: impaired, color: isDarkMode ? 'text-red-400' : 'text-red-600' }] : []),
                    ...(reduced > 0 ? [{ label: 'Reduced', value: reduced, color: isDarkMode ? 'text-amber-400' : 'text-amber-600' }] : []),
                    ...(normal > 0 ? [{ label: 'Normal', value: normal, color: isDarkMode ? 'text-green-400' : 'text-green-600' }] : []),
                  ],
                  summary: `${data.methylation_profiles.length} genes profiled`,
                  hasData: true,
                })
              }

              // Detoxification
              if (Array.isArray(data?.detoxification_profiles) && data.detoxification_profiles.length > 0) {
                const impaired = data.detoxification_profiles.filter((d: DetoxProfile) => d.detox_capacity === 'impaired' || d.detox_capacity === 'slow').length
                const normal = data.detoxification_profiles.filter((d: DetoxProfile) => d.detox_capacity === 'normal').length
                categoryCards.push({
                  id: 'detox', title: 'Detoxification', icon: Zap, gradient: 'from-lime-500 to-green-500',
                  items: [
                    ...(impaired > 0 ? [{ label: 'Impaired/Slow', value: impaired, color: isDarkMode ? 'text-red-400' : 'text-red-600' }] : []),
                    ...(normal > 0 ? [{ label: 'Normal', value: normal, color: isDarkMode ? 'text-green-400' : 'text-green-600' }] : []),
                  ],
                  summary: `${data.detoxification_profiles.length} pathways analyzed`,
                  hasData: true,
                })
              }

              // Intelligence / Cognitive
              if (Array.isArray(data?.intelligence) && data.intelligence.length > 0) {
                const topPercentile = data.intelligence.reduce((max: IntelligenceTrait | null, c: IntelligenceTrait) => c.percentile > (max?.percentile || 0) ? c : max, null)
                categoryCards.push({
                  id: 'intelligence', title: 'Intelligence', icon: Brain, gradient: 'from-purple-500 to-violet-500',
                  items: data.intelligence.slice(0, 3).map((c: IntelligenceTrait) => ({
                    label: c.cognitive_ability || c.trait_name,
                    value: c.percentile ? `${c.percentile}th` : c.genetic_advantage || '—',
                  })),
                  summary: topPercentile ? `Top: ${topPercentile.cognitive_ability || topPercentile.trait_name} (${topPercentile.percentile}th)` : `${data.intelligence.length} domains`,
                  hasData: true,
                })
              }

              // Personality
              if (Array.isArray(data?.personality_traits) && data.personality_traits.length > 0) {
                const sorted = [...data.personality_traits].sort((a: PersonalityTraitData, b: PersonalityTraitData) => (b.score || 0) - (a.score || 0))
                categoryCards.push({
                  id: 'personality', title: 'Personality', icon: Palette, gradient: 'from-pink-500 to-rose-500',
                  items: sorted.slice(0, 3).map((p: PersonalityTraitData) => ({
                    label: p.trait || p.name,
                    value: p.score ? `${p.score}%` : p.confidence || '—',
                  })),
                  summary: sorted[0] ? `Strongest: ${sorted[0].trait || sorted[0].name}` : `${data.personality_traits.length} traits`,
                  hasData: true,
                })
              }

              // Physical Traits
              if (Array.isArray(data?.physical_traits) && data.physical_traits.length > 0) {
                const byCategory: Record<string, number> = {}
                data.physical_traits.forEach((t: PhysicalTrait) => { byCategory[t.trait_category || 'other'] = (byCategory[t.trait_category || 'other'] || 0) + 1 })
                categoryCards.push({
                  id: 'physical-traits', title: 'Physical Traits', icon: Target, gradient: 'from-sky-500 to-blue-500',
                  items: Object.entries(byCategory).slice(0, 3).map(([cat, count]) => ({
                    label: cat.charAt(0).toUpperCase() + cat.slice(1), value: count,
                  })),
                  summary: `${data.physical_traits.length} traits identified`,
                  hasData: true,
                })
              }

              // Wellness
              if (Array.isArray(data?.wellness_traits) && data.wellness_traits.length > 0) {
                const wellnessVariant = data.wellness_traits.filter((w: WellnessTrait) => w.value === 'variant_detected' || w.value === 'reduced').length
                const wellnessImpaired = data.wellness_traits.filter((w: WellnessTrait) => w.value === 'impaired').length
                const wellnessNormal = data.wellness_traits.filter((w: WellnessTrait) => w.value === 'normal').length
                categoryCards.push({
                  id: 'wellness', title: 'Wellness Reports', icon: Activity, gradient: 'from-emerald-500 to-green-500',
                  items: [
                    ...(wellnessImpaired > 0 ? [{ label: 'Impaired', value: wellnessImpaired, color: isDarkMode ? 'text-red-400' : 'text-red-600' }] : []),
                    ...(wellnessVariant > 0 ? [{ label: 'Variant Detected', value: wellnessVariant, color: isDarkMode ? 'text-amber-400' : 'text-amber-600' }] : []),
                    ...(wellnessNormal > 0 ? [{ label: 'Normal', value: wellnessNormal, color: isDarkMode ? 'text-green-400' : 'text-green-600' }] : []),
                  ],
                  summary: `${data.wellness_traits.length} wellness metrics`,
                  hasData: true,
                })
              }

              // Rare Mutations
              if (Array.isArray(data?.rare_mutations) && data.rare_mutations.length > 0) {
                const pathogenic = data.rare_mutations.filter((m: RareMutation) => m.mutation_type === 'pathogenic').length
                const likelyPath = data.rare_mutations.filter((m: RareMutation) => m.mutation_type === 'likely_pathogenic').length
                categoryCards.push({
                  id: 'rare-mutations', title: 'Rare Mutations', icon: AlertTriangle, gradient: 'from-red-500 to-rose-600',
                  items: [
                    ...(pathogenic > 0 ? [{ label: 'Pathogenic', value: pathogenic, color: isDarkMode ? 'text-red-400' : 'text-red-600' }] : []),
                    ...(likelyPath > 0 ? [{ label: 'Likely pathogenic', value: likelyPath, color: isDarkMode ? 'text-orange-400' : 'text-orange-600' }] : []),
                  ],
                  summary: `${data.rare_mutations.length} rare variants found`,
                  hasData: true,
                })
              }

              // Uncommon Mutations
              if (Array.isArray(data?.uncommon_mutations) && data.uncommon_mutations.length > 0) {
                const protective = data.uncommon_mutations.filter((m: UncommonMutation) => m.mutation_type === 'protective_rare').length
                categoryCards.push({
                  id: 'uncommon-mutations', title: 'Uncommon Mutations', icon: Dna, gradient: 'from-violet-500 to-purple-600',
                  items: [
                    { label: 'Total', value: data.uncommon_mutations.length },
                    ...(protective > 0 ? [{ label: 'Protective', value: protective, color: isDarkMode ? 'text-green-400' : 'text-green-600' }] : []),
                  ],
                  summary: protective > 0 ? `${protective} protective variant${protective > 1 ? 's' : ''}` : `${data.uncommon_mutations.length} uncommon variants`,
                  hasData: true,
                })
              }

              return categoryCards.length > 0 ? (
                <div>
                  <div className="flex items-center gap-3 mb-4">
                    <div className="p-2 bg-gradient-to-br from-blue-500/20 to-indigo-500/20 rounded-xl border border-blue-500/30">
                      <BarChart3 className={`h-5 w-5 ${getThemeClass('text-blue-500', isDarkMode)}`} />
                    </div>
                    <div>
                      <h3 className={`text-lg font-bold ${theme.text.primary}`}>Category Highlights</h3>
                      <p className={`text-xs ${theme.text.muted}`}>Click any card to explore in detail</p>
                    </div>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                    {categoryCards.map(card => {
                      const Icon = card.icon
                      return (
                        <div
                          key={card.id}
                          className={`${theme.glass} border ${theme.glassBorder} rounded-xl p-5 cursor-pointer ${theme.glassHover} transition-all duration-300 group hover:shadow-lg hover:-translate-y-0.5`}
                          onClick={() => setActiveCategory(card.id)}
                        >
                          <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-2.5">
                              <div className={`p-2 bg-gradient-to-br ${card.gradient} rounded-lg shadow-lg shadow-black/5 group-hover:scale-110 transition-transform`}>
                                <Icon className="h-4 w-4 text-white" />
                              </div>
                              <h4 className={`font-semibold text-sm ${theme.text.primary}`}>{card.title}</h4>
                            </div>
                            <ChevronRight className={`h-4 w-4 ${theme.text.muted} group-hover:translate-x-0.5 transition-transform`} />
                          </div>
                          {card.items.length > 0 && (
                            <div className="flex flex-wrap gap-x-4 gap-y-1 mb-2">
                              {card.items.map((item, idx) => (
                                <div key={idx} className="flex items-baseline gap-1 max-w-full overflow-hidden">
                                  <span className={`text-base font-bold shrink-0 ${item.color || theme.text.primary}`}>{item.value}</span>
                                  <span className={`text-xs ${theme.text.muted} truncate`}>{item.label}</span>
                                </div>
                              ))}
                            </div>
                          )}
                          <p className={`text-xs ${theme.text.secondary} truncate`}>{card.summary}</p>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ) : null
            })()}

            {/* Two-Column: Insights + Categories */}
            {/* Overview Charts Row */}
            {(() => {
              const pieCounts: { label: string; count: number; color: string }[] = []
              if (Array.isArray(data?.health_risks) && data.health_risks.length > 0) pieCounts.push({ label: 'Health Risks', count: data.health_risks.length, color: '#ef4444' })
              if (Array.isArray(data?.drug_responses) && data.drug_responses.length > 0) pieCounts.push({ label: 'Drug Responses', count: data.drug_responses.length, color: '#f59e0b' })
              if (Array.isArray(data?.carrier_status) && data.carrier_status.length > 0) pieCounts.push({ label: 'Carrier Status', count: data.carrier_status.length, color: '#f97316' })
              if (Array.isArray(data?.nutrition_traits) && data.nutrition_traits.length > 0) pieCounts.push({ label: 'Nutrition', count: data.nutrition_traits.length, color: '#22c55e' })
              if (Array.isArray(data?.sports_performance) && data.sports_performance.length > 0) pieCounts.push({ label: 'Sports', count: data.sports_performance.length, color: '#14b8a6' })
              if (Array.isArray(data?.personality_traits) && data.personality_traits.length > 0) pieCounts.push({ label: 'Personality', count: data.personality_traits.length, color: '#ec4899' })
              if (Array.isArray(data?.intelligence) && data.intelligence.length > 0) pieCounts.push({ label: 'Intelligence', count: data.intelligence.length, color: '#8b5cf6' })
              if (Array.isArray(data?.rare_mutations) && data.rare_mutations.length > 0) pieCounts.push({ label: 'Rare Mutations', count: data.rare_mutations.length, color: '#dc2626' })
              if (Array.isArray(data?.wellness_traits) && data.wellness_traits.length > 0) pieCounts.push({ label: 'Wellness', count: data.wellness_traits.length, color: '#10b981' })
              if (Array.isArray(data?.methylation_profiles) && data.methylation_profiles.length > 0) pieCounts.push({ label: 'Methylation', count: data.methylation_profiles.length, color: '#06b6d4' })
              if (Array.isArray(data?.detoxification_profiles) && data.detoxification_profiles.length > 0) pieCounts.push({ label: 'Detox', count: data.detoxification_profiles.length, color: '#84cc16' })
              if (pieCounts.length < 2) return null
              return (
                <div className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-6`}>
                  <div className="flex items-center gap-3 mb-4">
                    <div className="p-2.5 bg-gradient-to-br from-indigo-500/20 to-purple-500/20 rounded-xl border border-indigo-500/30">
                      <Activity className={`h-5 w-5 ${getThemeClass('text-indigo-500', isDarkMode)}`} />
                    </div>
                    <div>
                      <h3 className={`text-lg font-bold ${theme.text.primary}`}>Analysis Distribution</h3>
                      <p className={`text-xs ${theme.text.muted}`}>Results breakdown across all categories</p>
                    </div>
                  </div>
                  <OverviewSummaryPie counts={pieCounts} isDarkMode={isDarkMode} height={260} />
                </div>
              )
            })()}

            {/* Smart AI Insights */}
            <SmartInsights isDarkMode={isDarkMode} token={token} section="overview" title="AI-Powered Analysis" />

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              {/* Genetic Insights */}
              <div className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-6`}>
                <div className="flex items-center justify-between mb-5">
                  <div className="flex items-center gap-3">
                    <div className="p-2.5 bg-gradient-to-br from-teal-500/20 to-cyan-500/20 rounded-xl border border-teal-500/30">
                      <Sparkles className={`h-5 w-5 ${getThemeClass('text-blue-500', isDarkMode)}`} />
                    </div>
                    <h3 className={`text-lg font-bold ${theme.text.primary}`}>Key Insights</h3>
                  </div>
                  <span className={`px-2.5 py-1 ${theme.glass} border ${theme.glassBorder} rounded-full text-xs font-medium ${theme.text.secondary}`}>
                    {quickInsights.length} findings
                  </span>
                </div>
                <div className="space-y-3">
                  {quickInsights.map((insight, index) => {
                    const Icon = insight.icon
                    const severity = index === 0 && Array.isArray(data?.health_risks) && data.health_risks.some((r: HealthRisk) => r.risk_level === 'high')
                      ? 'High' : index === 0 ? 'Critical' : index === 1 ? 'Moderate' : 'Info'
                    const severityColor = severity === 'High' || severity === 'Critical'
                      ? isDarkMode ? 'bg-red-500/20 text-red-300 border-red-500/30' : 'bg-red-50 text-red-600 border-red-200'
                      : severity === 'Moderate'
                        ? isDarkMode ? 'bg-amber-500/20 text-amber-300 border-amber-500/30' : 'bg-amber-50 text-amber-600 border-amber-200'
                        : isDarkMode ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' : 'bg-emerald-50 text-emerald-600 border-emerald-200'
                    return (
                      <div
                        key={index}
                        className={`flex items-start gap-4 p-4 rounded-xl border ${theme.glassBorder} ${theme.glassHover} transition-all ${insight.navigateTo ? 'cursor-pointer hover:shadow-md' : ''}`}
                        onClick={() => insight.navigateTo && setActiveCategory(insight.navigateTo)}
                      >
                        <div className={`p-2.5 ${insight.bgColor} rounded-lg flex-shrink-0`}>
                          <Icon className={`h-5 w-5 ${insight.color}`} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className={`font-semibold text-sm ${theme.text.primary}`}>{insight.category}</span>
                            <span className={`px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase border ${severityColor}`}>
                              {severity}
                            </span>
                          </div>
                          <p className={`text-sm ${theme.text.secondary} leading-relaxed`}>{insight.insight}</p>
                        </div>
                        {insight.navigateTo && (
                          <ChevronRight className={`h-4 w-4 ${theme.text.muted} flex-shrink-0 mt-1`} />
                        )}
                      </div>
                    )
                  })}

                </div>
              </div>

              {/* Variant Categories Breakdown */}
              <div className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-6`}>
                <div className="flex items-center gap-3 mb-5">
                  <div className="p-2.5 bg-gradient-to-br from-violet-500/20 to-purple-500/20 rounded-xl border border-violet-500/30">
                    <BarChart3 className={`h-5 w-5 ${getThemeClass('text-violet-500', isDarkMode)}`} />
                  </div>
                  <div>
                    <h3 className={`text-lg font-bold ${theme.text.primary}`}>Functional Categories</h3>
                    <p className={`text-xs ${theme.text.muted}`}>Variant distribution by consequence type</p>
                  </div>
                </div>

                {variantCategories.length > 0 ? (
                  <div>
                    <FunctionalCategoriesChart data={variantCategories.filter(c => c.name !== 'Unknown')} isDarkMode={isDarkMode} />
                    <div className={`flex justify-between pt-3 mt-2 border-t ${theme.glassBorder}`}>
                      <span className={`text-xs font-medium ${theme.text.muted}`}>Total variants</span>
                      <span className={`text-xs font-bold ${theme.text.primary}`}>{variantCategoryStats.total.toLocaleString()}</span>
                    </div>
                    <div className={`flex justify-between pt-1`}>
                      <span className={`text-xs font-medium ${theme.text.muted}`}>Annotated</span>
                      <span className={`text-xs font-bold ${theme.text.primary}`}>{variantCategoryStats.annotated.toLocaleString()} ({variantCategoryStats.total > 0 ? ((variantCategoryStats.annotated / variantCategoryStats.total) * 100).toFixed(1) : 0}%)</span>
                    </div>
                  </div>
                ) : (
                  <div className={`text-center py-8 ${theme.text.muted}`}>
                    <BarChart3 className="h-10 w-10 mx-auto mb-3 opacity-30" />
                    <p className="text-sm">Category data loading...</p>
                  </div>
                )}
              </div>
            </div>

            {/* Risk Breakdown & Pharmacogenomic Highlights */}
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              {/* Risk Breakdown - with chart */}
              {Array.isArray(data?.health_risks) && data.health_risks.length > 0 && (() => {
                const risks = data.health_risks as HealthRisk[]
                return (
                <div
                  className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-6 cursor-pointer hover:shadow-md transition-all`}
                  onClick={() => setActiveCategory('health')}
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <FileText className={`h-4 w-4 ${getThemeClass('text-blue-500', isDarkMode)}`} />
                      <span className={`text-xs font-semibold uppercase tracking-wider ${theme.text.muted}`}>Risk Breakdown</span>
                    </div>
                    <ChevronRight className={`h-3.5 w-3.5 ${theme.text.muted}`} />
                  </div>
                  <RiskDistributionChart data={risks} isDarkMode={isDarkMode} height={160} />
                </div>
                )
              })()}

              {/* Drug response detail - clickable */}
              {Array.isArray(data?.drug_responses) && data.drug_responses.length > 0 && (
                <div
                  className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-6 cursor-pointer hover:shadow-md transition-all`}
                  onClick={() => setActiveCategory('drug-responses')}
                >
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <Pill className={`h-4 w-4 ${getThemeClass('text-purple-500', isDarkMode)}`} />
                      <span className={`text-xs font-semibold uppercase tracking-wider ${theme.text.muted}`}>Pharmacogenomic Highlights</span>
                    </div>
                    <ChevronRight className={`h-3.5 w-3.5 ${theme.text.muted}`} />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {data.drug_responses.slice(0, 8).map((dr: DrugResponse, i: number) => (
                      <span key={i} className={`px-2.5 py-1 rounded-lg text-xs font-medium border ${theme.glassBorder} ${isDarkMode ? 'bg-purple-500/10 text-purple-300' : 'bg-purple-50 text-purple-700'}`}>
                        {dr.gene}{dr.drug ? ` → ${dr.drug}` : ''}
                      </span>
                    ))}
                    {data.drug_responses.length > 8 && (
                      <span className={`px-2.5 py-1 rounded-lg text-xs font-medium ${theme.text.muted}`}>
                        +{data.drug_responses.length - 8} more
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )
    }
  }

  // Show loading state while data is being fetched
  if (loading) {
    return (
      <div className={`min-h-screen ${theme.background} relative overflow-hidden flex items-center justify-center`}>
        <div className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-8 text-center`}>
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
          <h2 className={`text-xl font-semibold ${theme.text.primary} mb-2`}>
            Loading Genetic Analysis
          </h2>
          <p className={theme.text.secondary}>
            Preparing your personalized health insights...
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className={`min-h-screen ${theme.background} relative overflow-hidden`}>
      {/* Glassmorphism Background Elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className={`absolute -top-40 -right-40 w-96 h-96 ${theme.blobs.primary} rounded-full filter blur-3xl animate-float`}></div>
        <div className={`absolute top-1/3 -left-40 w-80 h-80 ${theme.blobs.secondary} rounded-full filter blur-3xl animate-float-delayed`}></div>
        <div className={`absolute bottom-0 right-1/3 w-72 h-72 ${theme.blobs.tertiary} rounded-full filter blur-3xl animate-float-slow`}></div>
        <div className={`absolute top-1/2 left-1/2 w-64 h-64 ${theme.blobs.primary} rounded-full filter blur-3xl animate-float-reverse`}></div>
      </div>

      {/* Header - Glassmorphism Effect */}
      <header className={`${theme.glass} border-b ${theme.glassBorder} sticky top-0 z-30`}>
        <div className="flex items-center justify-between px-6 py-4">
          {/* Logo and Title */}
          <button
            onClick={() => { setActiveCategory('overview'); window.scrollTo(0, 0); }}
            className="flex items-center space-x-4 cursor-pointer hover:opacity-80 transition-opacity"
          >
            <div className="p-3 bg-gradient-to-br from-teal-500/80 to-cyan-500/80 backdrop-blur-xl rounded-xl border border-white/20 shadow-xl">
              <Dna className="h-7 w-7 text-white" />
            </div>
            <div className="text-left">
              <h1 className={`text-xl font-bold ${theme.text.primary}`}>
                Genetic Health Analysis Toolkit
              </h1>
              <p className={`text-sm ${theme.text.muted}`}>
                {data?.summary?.total_variants || 0} DNA variants
              </p>
            </div>
          </button>

          {/* Spacer for better layout */}
          <div className="flex-1"></div>

          {/* Right side actions */}
          <div className="flex items-center space-x-4">
            {/* Analysis Controls */}
            <div className="flex items-center space-x-2">
              {/* Analysis Status Indicator */}
              {analysisId && (
                <div className={`px-3 py-1.5 rounded-lg text-xs font-medium border ${
                  analysisStatus === 'completed' 
                    ? 'bg-green-600 text-white border-green-700 dark:bg-green-700 dark:text-white dark:border-green-600'
                    : analysisStatus === 'processing'
                    ? 'bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:border-blue-800'
                    : analysisStatus === 'stopped'
                    ? 'bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-800'
                    : analysisStatus === 'paused'
                    ? 'bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-900/30 dark:text-orange-400 dark:border-orange-800'
                    : analysisStatus === 'failed'
                    ? 'bg-red-50 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800'
                    : 'bg-gray-50 text-gray-700 border-gray-200 dark:bg-gray-900/30 dark:text-gray-400 dark:border-gray-800'
                }`}>
                  {analysisStatus === 'processing' ? (
                    <div className="flex items-center space-x-2">
                      <div className={`w-2 h-2 border rounded-full animate-spin ${
                        isDarkMode ? 'border-blue-400 border-t-transparent' : 'border-blue-600 border-t-transparent'
                      }`}></div>
                      <span>Processing {analysisProgress}%</span>
                    </div>
                  ) : analysisStatus === 'stopped' ? (
                    <div className="flex items-center space-x-2">
                      <Square className="w-2 h-2" />
                      <span>
                        {analysisProgress >= 100 ? 'Completed' : `Stopped at ${analysisProgress}%`}
                      </span>
                    </div>
                  ) : analysisStatus === 'paused' ? (
                    <div className="flex items-center space-x-2">
                      <Pause className="w-2 h-2" />
                      <span>Paused at {analysisProgress}%</span>
                    </div>
                  ) : analysisStatus === 'completed' ? (
                    <span>✓ Completed</span>
                  ) : analysisStatus}
                </div>
              )}

              {/* Compact Analysis Control Buttons */}
              <div className={`flex items-center border rounded-lg backdrop-blur-xl ${
                isDarkMode 
                  ? 'border-white/20 bg-white/10' 
                  : 'border-gray-300 bg-white/90 shadow-sm'
              }`}>
                {/* Start/Resume/Pause/Stop Analysis */}
                {analysisStatus === 'processing' || isAnalysisRunning ? (
                  // Pause and Stop buttons when analysis is running
                  <>
                    <button
                      onClick={handlePauseAnalysis}
                      className={`px-3 py-2 text-xs font-medium transition-all duration-200 flex items-center space-x-1 ${
                        isDarkMode 
                          ? 'text-orange-400 hover:bg-orange-500/10' 
                          : 'text-orange-600 hover:bg-orange-50'
                      }`}
                      title="Pause Analysis"
                    >
                      <Pause className="h-3 w-3" />
                      <span className="hidden sm:inline">Pause</span>
                    </button>
                    <button
                      onClick={handleStopAnalysis}
                      className={`px-3 py-2 text-xs font-medium transition-all duration-200 flex items-center space-x-1 rounded-r-lg border-l ${
                        isDarkMode 
                          ? 'text-red-400 hover:bg-red-500/10 border-white/10' 
                          : 'text-red-600 hover:bg-red-50 border-gray-200'
                      }`}
                      title="Stop Analysis"
                    >
                      <Square className="h-3 w-3" />
                      <span className="hidden sm:inline">Stop</span>
                    </button>
                  </>
                ) : analysisStatus === 'stopped' || analysisStatus === 'paused' ? (
                  // Resume button when analysis is stopped or paused
                  <button
                    onClick={handleResumeAnalysis}
                    disabled={!analysisId}
                    className={`px-3 py-2 text-xs font-medium transition-all duration-200 flex items-center space-x-1 rounded-l-lg disabled:opacity-50 disabled:cursor-not-allowed ${
                      isDarkMode 
                        ? 'text-blue-400 hover:bg-blue-500/10' 
                        : 'text-blue-600 hover:bg-blue-50'
                    }`}
                    title="Resume Analysis"
                  >
                    <Play className="h-3 w-3" />
                    <span className="hidden sm:inline">Resume</span>
                  </button>
                ) : (
                  // Start button for new/completed analysis
                  <button
                    onClick={handleStartAnalysis}
                    disabled={!analysisId}
                    className={`px-3 py-2 text-xs font-medium transition-all duration-200 flex items-center space-x-1 rounded-l-lg disabled:opacity-50 disabled:cursor-not-allowed ${
                      isDarkMode 
                        ? 'text-green-400 hover:bg-green-500/10' 
                        : 'text-green-600 hover:bg-green-50'
                    }`}
                    title={analysisStatus === 'completed' ? 'Restart Analysis' : 'Start Analysis'}
                  >
                    <Activity className="h-3 w-3" />
                    <span className="hidden sm:inline">
                      {analysisStatus === 'completed' ? 'Restart' : 'Start'}
                    </span>
                  </button>
                )}

                {/* Refresh Data */}
                <button
                  onClick={handleRefreshData}
                  className={`px-3 py-2 text-xs font-medium transition-all duration-200 flex items-center space-x-1 border-l ${
                    isDarkMode 
                      ? 'text-white hover:bg-white/10 border-white/20' 
                      : 'text-gray-700 hover:bg-gray-100 border-gray-300'
                  }`}
                  title="Refresh Data"
                >
                  <BarChart3 className="h-3 w-3" />
                  <span className="hidden sm:inline">Refresh</span>
                </button>

                {/* Upload New Data */}
                <button
                  onClick={onReset}
                  className={`px-3 py-2 text-xs font-medium transition-all duration-200 flex items-center space-x-1 border-l rounded-r-lg ${
                    isDarkMode 
                      ? 'text-white hover:bg-white/10 border-white/20' 
                      : 'text-gray-700 hover:bg-gray-100 border-gray-300'
                  }`}
                  title="Upload New File"
                >
                  <Upload className="h-3 w-3" />
                  <span className="hidden sm:inline">Upload</span>
                </button>
              </div>
            </div>

            {/* User Menu */}
            <div className="relative">
              <button
                onClick={() => setShowUserMenu(!showUserMenu)}
                className={`flex items-center space-x-3 ${theme.glass} border ${theme.glassBorder} px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-300 ${theme.glassHover}`}
              >
                {currentAvatarUrl ? (
                  <img src={currentAvatarUrl} alt="" className="w-7 h-7 rounded-full object-cover" />
                ) : (
                  <div className="w-7 h-7 bg-gradient-to-br from-teal-500 to-cyan-500 rounded-full flex items-center justify-center shadow-lg">
                    <span className="text-white text-sm font-bold">{(currentUserName || 'U')[0].toUpperCase()}</span>
                  </div>
                )}
                <span className={theme.text.primary}>{currentUserName}</span>
                <ChevronDown className={`h-4 w-4 ${theme.text.secondary}`} />
              </button>

              {showUserMenu && (
                <div className={`absolute right-0 mt-3 w-52 rounded-xl shadow-2xl py-2 z-50 ${isDarkMode ? 'bg-slate-800 border border-slate-700' : 'bg-white border border-gray-200'}`}>
                  <button
                    onClick={() => { setIsDarkMode(!isDarkMode); setShowUserMenu(false) }}
                    className={`w-full text-left px-4 py-3 text-sm ${theme.text.primary} ${theme.glassHover} flex items-center space-x-3 transition-all duration-200`}
                  >
                    {isDarkMode ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
                    <span>{isDarkMode ? 'Light Mode' : 'Dark Mode'}</span>
                  </button>
                  {isAdmin && (
                    <button
                      onClick={() => { setActiveCategory('admin'); setShowUserMenu(false) }}
                      className={`w-full text-left px-4 py-3 text-sm ${theme.text.primary} ${theme.glassHover} flex items-center space-x-3 transition-all duration-200`}
                    >
                      <Shield className="h-4 w-4" />
                      <span>Admin Panel</span>
                    </button>
                  )}
                  <button
                    onClick={() => { setActiveCategory('settings'); setShowUserMenu(false) }}
                    className={`w-full text-left px-4 py-3 text-sm ${theme.text.primary} ${theme.glassHover} flex items-center space-x-3 transition-all duration-200`}
                  >
                    <Settings className="h-4 w-4" />
                    <span>Settings</span>
                  </button>
                  <button
                    onClick={() => setShowDeleteDialog(true)}
                    className={`w-full text-left px-4 py-3 text-sm text-red-500 hover:bg-red-500/10 flex items-center space-x-3 transition-all duration-200`}
                  >
                    <Trash2 className="h-4 w-4" />
                    <span>Delete Data</span>
                  </button>
                  <hr className={`my-2 ${theme.glassBorder} border-t`} />
                  <button
                    onClick={onReset}
                    className={`w-full text-left px-4 py-3 text-sm ${theme.text.primary} ${theme.glassHover} flex items-center space-x-3 transition-all duration-200`}
                  >
                    <LogOut className="h-4 w-4" />
                    <span>Logout</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex" style={{ height: 'calc(100vh - 73px)' }}>
        {/* Sidebar - Glassmorphism style */}
        <aside className={`w-72 ${theme.glass} border-r ${theme.glassBorder} overflow-y-auto relative z-10`}>
          <div className="p-6">
            <div className="space-y-2">
              {categories.map((category) => {
                // Handle separators
                if (category.isSeparator) {
                  return (
                    <div key={category.id} className={`my-4 border-t ${isDarkMode ? 'border-gray-700/50' : 'border-gray-200/50'}`}></div>
                  )
                }
                
                const Icon = category.icon
                const isActive = activeCategory === category.id
                return (
                  <button
                    key={category.id}
                    onClick={() => setActiveCategory(category.id)}
                    className={`w-full flex items-center space-x-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-300 ${
                      isActive 
                        ? 'bg-gradient-to-r from-teal-500/80 to-cyan-500/80 text-white shadow-lg border border-white/20 backdrop-blur-xl' 
                        : isDarkMode
                          ? 'text-gray-300 hover:bg-slate-700/40 hover:text-white border border-transparent hover:border-slate-600/30 backdrop-blur-sm'
                          : 'text-gray-600 hover:bg-gray-200/30 hover:text-gray-900 border border-transparent hover:border-gray-300/30 backdrop-blur-sm'
                    }`}
                  >
                    {Icon && <Icon className={`h-5 w-5 ${isActive ? 'text-white' : getThemeClass('text-gray-500', isDarkMode)}`} />}
                    <span>{category.title}</span>
                  </button>
                )
              })}
            </div>
          </div>
        </aside>

        {/* Main Content Area */}
        <main className={`flex-1 overflow-auto ${theme.background}`}>
          <div className="p-8 max-w-none">
            {showProgress && analysisId ? (
              <AnalysisProgressLoader
                analysisId={analysisId}
                isDarkMode={isDarkMode}
                onComplete={handleAnalysisComplete}
                onError={handleAnalysisError}
                onBack={() => setShowProgress(false)}
              />
            ) : (
              renderCategoryContent()
            )}
          </div>
        </main>
      </div>
      
      {/* CSS Animations for Glassmorphism */}
      <style jsx>{`
        @keyframes float {
          0%, 100% { transform: translate(0px, 0px) scale(1) rotate(0deg); }
          33% { transform: translate(30px, -30px) scale(1.1) rotate(2deg); }
          66% { transform: translate(-20px, 20px) scale(0.9) rotate(-1deg); }
        }
        @keyframes float-delayed {
          0%, 100% { transform: translate(0px, 0px) scale(1) rotate(0deg); }
          33% { transform: translate(-25px, 25px) scale(1.05) rotate(-2deg); }
          66% { transform: translate(20px, -15px) scale(0.95) rotate(1deg); }
        }
        @keyframes float-slow {
          0%, 100% { transform: translate(0px, 0px) scale(1) rotate(0deg); }
          50% { transform: translate(15px, -15px) scale(1.03) rotate(1deg); }
        }
        @keyframes float-reverse {
          0%, 100% { transform: translate(0px, 0px) scale(1) rotate(0deg); }
          33% { transform: translate(-15px, -20px) scale(0.97) rotate(-1deg); }
          66% { transform: translate(25px, 15px) scale(1.02) rotate(2deg); }
        }
        .animate-float {
          animation: float 15s ease-in-out infinite;
        }
        .animate-float-delayed {
          animation: float-delayed 18s ease-in-out infinite;
          animation-delay: 2s;
        }
        .animate-float-slow {
          animation: float-slow 20s ease-in-out infinite;
          animation-delay: 4s;
        }
        .animate-float-reverse {
          animation: float-reverse 22s ease-in-out infinite;
          animation-delay: 6s;
        }
      `}</style>

      {/* Delete Confirmation Dialog */}
      {showDeleteDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className={`${theme.glass} border ${theme.glassBorder} rounded-xl p-6 m-4 max-w-md w-full`}>
            <div className="text-center">
              <div className="w-12 h-12 mx-auto mb-4 bg-red-100 rounded-full flex items-center justify-center">
                <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                </svg>
              </div>
              <h3 className={`text-lg font-semibold ${theme.text.primary} mb-2`}>
                Delete All Data
              </h3>
              <p className={`${theme.text.secondary} mb-6`}>
                Are you sure you want to delete all your genetic data? This action cannot be undone.
              </p>
              <div className="flex gap-3 justify-center">
                <button
                  onClick={() => setShowDeleteDialog(false)}
                  disabled={isDeleting}
                  className={`px-4 py-2 rounded-lg ${theme.glass} border ${theme.glassBorder} ${theme.text.primary} hover:bg-white/10 transition-colors disabled:opacity-50`}
                >
                  Cancel
                </button>
                <button
                  onClick={handleDeleteData}
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
      )}

      {/* Notification Toast */}
      {notification.show && (
        <div className={`fixed top-4 right-4 z-50 max-w-sm w-full ${theme.glass} border ${theme.glassBorder} rounded-lg p-4 shadow-xl backdrop-blur-xl transition-all duration-300 ${
          notification.type === 'success' 
            ? 'border-green-500/50 bg-green-50/90 dark:bg-green-900/30' 
            : notification.type === 'error'
            ? 'border-red-500/50 bg-red-50/90 dark:bg-red-900/30'
            : 'border-blue-500/50 bg-blue-50/90 dark:bg-blue-900/30'
        }`}>
          <div className="flex items-start space-x-3">
            <div className={`flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center ${
              notification.type === 'success' 
                ? 'bg-green-500' 
                : notification.type === 'error'
                ? 'bg-red-500'
                : 'bg-blue-500'
            }`}>
              {notification.type === 'success' ? (
                <CheckCircle className="w-3 h-3 text-white" />
              ) : notification.type === 'error' ? (
                <X className="w-3 h-3 text-white" />
              ) : (
                <Info className="w-3 h-3 text-white" />
              )}
            </div>
            <div className="flex-1">
              <p className={`text-sm font-medium ${
                notification.type === 'success' 
                  ? 'text-green-800 dark:text-green-200' 
                  : notification.type === 'error'
                  ? 'text-red-800 dark:text-red-200'
                  : 'text-blue-800 dark:text-blue-200'
              }`}>
                {notification.message}
              </p>
            </div>
            <button
              onClick={() => setNotification(prev => ({ ...prev, show: false }))}
              className={`flex-shrink-0 w-4 h-4 rounded-full flex items-center justify-center hover:bg-white/20 transition-colors ${
                notification.type === 'success' 
                  ? 'text-green-600 dark:text-green-400' 
                  : notification.type === 'error'
                  ? 'text-red-600 dark:text-red-400'
                  : 'text-blue-600 dark:text-blue-400'
              }`}
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}