'use client'

import { useState, useEffect } from 'react'
import { 
  Apple, Brain, Dumbbell, Heart, Zap, Palette, 
  ChevronDown, TrendingUp, AlertTriangle, CheckCircle, 
  Settings, Trash2, Info, Shield, Search,
  Upload, Dna, Activity, BarChart3, Sparkles, Target,
  Sun, Moon, Users, X, LogOut, Home,
  Square, Play, Pause
} from 'lucide-react'
import { getTheme } from '../utils/theme'

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
import VariantSearch from './VariantSearch'
import AnalysisProgressLoader from './AnalysisProgressLoader'
import { getThemeClass } from '../utils/theme'

interface ModernDashboardProps {
  token?: string
  analysisData?: any
  analysisId?: number | null
  onRefresh?: (token: string) => Promise<void>
}

export default function ModernDashboard({ token, analysisData, analysisId, onRefresh }: ModernDashboardProps) {
  console.log('Dashboard component props:', { token: !!token, analysisData, analysisId })
  console.log('Analysis ID in dashboard:', analysisId)
  
  // ALL STATE HOOKS MUST BE AT THE TOP
  const [data, setData] = useState<any>(analysisData || null)
  const [loading, setLoading] = useState(!analysisData)
  const [showProgress, setShowProgress] = useState(false)
  const [progressInterval, setProgressInterval] = useState<NodeJS.Timeout | null>(null)
  const [activeCategory, setActiveCategory] = useState('overview')
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [currentPage, setCurrentPage] = useState(1)
  const [variantsPerPage] = useState(25)
  const [searchRsid, setSearchRsid] = useState('')
  const [goToPage, setGoToPage] = useState('')
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  
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
    }
  }, [isDarkMode])

  // Reset pagination when changing categories
  useEffect(() => {
    setCurrentPage(1)
  }, [activeCategory])

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (progressInterval) {
        clearInterval(progressInterval)
        setProgressInterval(null)
      }
    }
  }, [progressInterval])

  // Check initial status and start polling if needed
  useEffect(() => {
    const checkStatus = async () => {
      if (!token || !analysisId) return

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
          setIsAnalysisRunning(['processing', 'running'].includes(progress.status))
        }
      } catch (error) {
        console.error('Error checking analysis status:', error)
      }
    }

    checkStatus()
    
    // Start polling if analysis is running
    if (analysisId && token && isAnalysisRunning && !progressInterval) {
      const interval = setInterval(checkStatus, 2000)
      setProgressInterval(interval)
    }
  }, [analysisId, token, isAnalysisRunning, progressInterval])

  // Load real data from backend on component mount only if no analysisData provided
  useEffect(() => {
    if (!analysisData && token) {
      const loadRealData = async () => {
        setLoading(true)
        
        try {
          const response = await fetch('/api/upload/dashboard-data', {
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
              setData(null)
            }
          }
        } catch (error) {
          console.error('Error loading dashboard data:', error)
          // Check if there's an analysis in progress
          if (analysisId) {
            setShowProgress(true)
          } else {
            setData(null)
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
    setData(null)
    setActiveCategory('overview')
    setCurrentPage(1)
    setSearchRsid('')
    setGoToPage('')
  }

  // Progress handlers
  const handleAnalysisComplete = (results: any) => {
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
    }
  ]

  const handleDeleteData = async () => {
    try {
      const response = await fetch('http://localhost:8000/upload/data', {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })

      if (response.ok) {
        setData(null)
        setActiveCategory('overview')
        setShowDeleteDialog(false)
        showNotification('All data deleted successfully', 'success')
      } else {
        showNotification('Failed to delete data', 'error')
      }
    } catch (error) {
      console.error('Error deleting data:', error)
      showNotification('Error deleting data', 'error')
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
          // Auto-fix status mismatch
          console.log('Status mismatch detected, auto-correcting...')
          const resetResponse = await fetch(`http://localhost:8000/api/analysis/cancel/${analysisId}`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` }
          })
          if (resetResponse.ok) {
            const resetResult = await resetResponse.json()
            setAnalysisStatus(resetResult.status)
            setAnalysisProgress(resetResult.progress_percentage || 0)
            setTotalVariants(resetResult.total_variants || 0)
            setProcessedVariants(resetResult.processed_variants || 0)
            setIsAnalysisRunning(false)
          }
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

  const stats = [
    {
      title: 'Variants Uploaded',
      value: data?.real_data?.variants?.length || data?.summary?.total_variants || 0,
      icon: Upload,
      color: getThemeClass('text-gray-600', isDarkMode),
      bgColor: getThemeClass('bg-gray-50', isDarkMode)
    },
    {
      title: 'Variants Analyzed',
      value: data?.summary?.analyzed_variants || data?.analysis_results?.variants_actually_processed || data?.processed_variants || 0,
      icon: BarChart3,
      color: getThemeClass('text-blue-600', isDarkMode),
      bgColor: getThemeClass('bg-blue-50', isDarkMode)
    },
    {
      title: 'Health Score',
      value: `${Math.round(data?.health_risks?.overall_score || 85)}%`,
      icon: Activity,
      color: getThemeClass('text-green-600', isDarkMode),
      bgColor: getThemeClass('bg-green-50', isDarkMode)
    },
    {
      title: 'Insights Found',
      value: data?.summary?.insights_found || (data?.analysis_results?.insights_generated || 0) + (data?.analysis_results?.drug_responses_generated || 0),
      icon: TrendingUp,
      color: getThemeClass('text-purple-600', isDarkMode),
      bgColor: getThemeClass('bg-purple-50', isDarkMode)
    }
  ]

  const generateHealthInsights = (): any[] => {
    const insights: any[] = []
    
    // Return empty array if data is not loaded yet
    if (!data) return insights
    
    if (data?.health_risks?.risk_categories && Object.keys(data.health_risks.risk_categories).length > 0) {
      const highRisk = Object.values(data.health_risks.risk_categories).filter((risk: any) => risk.score > 80).length
      const moderateRisk = Object.values(data.health_risks.risk_categories).filter((risk: any) => risk.score > 60 && risk.score <= 80).length
      
      if (highRisk > 0) {
        insights.push({
          category: 'High Risk Variants',
          insight: `${highRisk} high-risk genetic variants identified requiring attention`,
          icon: AlertTriangle,
          color: getThemeClass('text-red-600', isDarkMode),
          bgColor: getThemeClass('bg-red-50', isDarkMode)
        })
      }
      
      if (moderateRisk > 0) {
        insights.push({
          category: 'Moderate Risk',
          insight: `${moderateRisk} variants show moderate risk associations`,
          icon: Info,
          color: getThemeClass('text-amber-600', isDarkMode),
          bgColor: getThemeClass('bg-amber-50', isDarkMode)
        })
      }
    }
    
    if (data?.drug_interactions?.high_risk_genes?.length > 0) {
      insights.push({
        category: 'Drug Metabolism',
        insight: `${data.drug_interactions.high_risk_genes.length} genes may affect drug responses`,
        icon: Shield,
        color: getThemeClass('text-purple-600', isDarkMode),
        bgColor: getThemeClass('bg-purple-50', isDarkMode)
      })
    }
    
    if (data?.real_data?.variants?.length > 0) {
      const withRsId = data.real_data.variants.filter((v: any) => v.rsid && v.rsid !== '-' && v.rsid !== 'nan').length
      const coverage = Math.round((withRsId / data.real_data.variants.length) * 100)
      
      insights.push({
        category: 'Analysis Coverage',
        insight: `${coverage}% of variants have reference IDs for clinical analysis`,
        icon: Target,
        color: getThemeClass('text-green-600', isDarkMode),
        bgColor: getThemeClass('bg-green-50', isDarkMode)
      })
    }
    
    return insights
  }

  const healthInsights = generateHealthInsights()

  const quickInsights = healthInsights.length > 0 ? healthInsights : [
    {
      category: 'Genetic Analysis',
      insight: data?.real_data?.variants?.length > 0 
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
        return <FoodNutritionPanel data={data} isDarkMode={isDarkMode} theme={theme} />
      case 'intelligence':
        return <IntelligencePanel data={data} isDarkMode={isDarkMode} theme={theme} />
      case 'physical-traits':
        return <PhysicalTraitsPanel data={data} isDarkMode={isDarkMode} theme={theme} />
      case 'personality':
        return <PersonalityPanel data={data} isDarkMode={isDarkMode} theme={theme} token={token} />
      case 'sports':
        return <SportsPanel data={data} isDarkMode={isDarkMode} theme={theme} />
      case 'health':
        return <HealthPanel data={data} isDarkMode={isDarkMode} theme={theme} token={token} />
      case 'drug-responses':
        return <DrugResponsesPanel data={data} isDarkMode={isDarkMode} token={token} />
      case 'ancestry':
        return <AncestryPanel data={data} isDarkMode={isDarkMode} />
      case 'carrier-status':
        return <CarrierStatusPanel data={data} isDarkMode={isDarkMode} />
      case 'wellness':
        return <WellnessPanel data={data} isDarkMode={isDarkMode} token={token} />
      case 'methylation':
        return <MethylationPanel data={data} isDarkMode={isDarkMode} theme={theme} />
      case 'detox':
        return <DetoxPanel data={data} isDarkMode={isDarkMode} theme={theme} />
      case 'rare-mutations':
        return <RareMutationsPanel data={data} isDarkMode={isDarkMode} theme={theme} />
      case 'uncommon-mutations':
        return <UncommonMutationsPanel data={data} isDarkMode={isDarkMode} theme={theme} />
      case 'variant-search':
        return <VariantSearch token={token} isDarkMode={isDarkMode} theme={theme} />
      default:
        return (
          <div className="space-y-8">
            {/* Hero Stats Row - Redesigned Compact */}
            <div className="grid grid-cols-4 gap-4">
              {stats.map((stat, index) => {
                const Icon = stat.icon
                return (
                  <div key={index} className={`${theme.glass} border ${theme.glassBorder} rounded-lg p-4 ${theme.glassHover} transition-all duration-300 group cursor-pointer`}>
                    <div className="flex items-center space-x-3">
                      <div className={`p-2.5 ${stat.bgColor} rounded-lg flex-shrink-0 group-hover:scale-110 transition-transform duration-300`}>
                        <Icon className={`h-5 w-5 ${stat.color}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className={`text-xs ${theme.text.muted} font-medium uppercase tracking-wide mb-1`}>
                          {stat.title}
                        </div>
                        <div className={`text-2xl font-bold ${theme.text.primary} leading-none`}>
                          {stat.value}
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Main Content - Two Column Layout */}
            <div className="grid grid-cols-1 xl:grid-cols-4 gap-8">
              {/* Left Column - Insights and Analysis (3 columns) */}
              <div className="xl:col-span-3 space-y-8">
                {/* Quick Insights */}
                <div className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-8`}>
                  <div className="flex items-center justify-between mb-8">
                    <div className="flex items-center space-x-4">
                      <div className="p-3 bg-gradient-to-br from-blue-500/20 to-purple-500/20 backdrop-blur-xl rounded-xl border border-blue-500/30">
                        <Sparkles className={`h-7 w-7 ${getThemeClass('text-blue-500', isDarkMode)}`} />
                      </div>
                      <div>
                        <h3 className={`text-2xl font-bold ${theme.text.primary}`}>
                          Quick Insights
                        </h3>
                        <p className={`text-sm ${theme.text.secondary}`}>
                          Key findings from your genetic analysis
                        </p>
                      </div>
                    </div>
                    <div className={`px-3 py-1.5 ${theme.glass} border ${theme.glassBorder} rounded-full text-xs font-medium ${theme.text.secondary}`}>
                      {quickInsights.length} insights
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {quickInsights.map((insight, index) => {
                      const Icon = insight.icon
                      return (
                        <div key={index} className={`${theme.glass} border ${theme.glassBorder} rounded-xl p-6 ${theme.glassHover} transition-all duration-300 group relative overflow-hidden`}>
                          {/* Subtle background accent */}
                          <div className={`absolute top-0 right-0 w-24 h-24 ${insight.bgColor} opacity-10 rounded-full blur-2xl`}></div>
                          
                          <div className="relative z-10">
                            <div className="flex items-start justify-between mb-4">
                              <div className={`p-3 ${insight.bgColor} rounded-xl group-hover:scale-110 transition-transform duration-300 shadow-lg`}>
                                <Icon className={`h-6 w-6 ${insight.color}`} />
                              </div>
                              <div className={`px-2 py-1 ${theme.glass} border ${theme.glassBorder} rounded-md text-xs font-medium ${theme.text.muted}`}>
                                {index === 0 ? 'Critical' : index === 1 ? 'Moderate' : 'Info'}
                              </div>
                            </div>
                            <h4 className={`font-bold ${theme.text.primary} mb-3 text-lg`}>
                              {insight.category}
                            </h4>
                            <p className={`${theme.text.secondary} text-sm leading-relaxed`}>
                              {insight.insight}
                            </p>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>

                {/* Analysis Summary */}
                <div className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-8`}>
                  <div className="flex items-center space-x-4 mb-8">
                    <div className="p-3 bg-gradient-to-br from-green-500/20 to-teal-500/20 backdrop-blur-xl rounded-xl border border-green-500/30">
                      <BarChart3 className={`h-7 w-7 ${getThemeClass('text-green-600', isDarkMode)}`} />
                    </div>
                    <div>
                      <h3 className={`text-2xl font-bold ${theme.text.primary}`}>
                        Analysis Summary
                      </h3>
                      <p className={`text-sm ${theme.text.secondary}`}>
                        Detailed breakdown of your genetic data
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                    {[
                      { 
                        label: 'Total Variants', 
                        value: data?.summary?.total_variants || data?.real_data?.variants?.length || 0,
                        icon: Dna,
                        color: getThemeClass('text-blue-600', isDarkMode),
                        bgColor: getThemeClass('bg-blue-50', isDarkMode)
                      },
                      { 
                        label: 'Chromosomes', 
                        value: data?.real_data?.variants ? [...new Set(data.real_data.variants.map((v: any) => v.chromosome))].length : 0,
                        icon: Target,
                        color: getThemeClass('text-purple-600', isDarkMode),
                        bgColor: getThemeClass('bg-purple-50', isDarkMode)
                      },
                      { 
                        label: 'With RS IDs', 
                        value: data?.real_data?.variants ? data.real_data.variants.filter((v: any) => v.rsid && v.rsid !== '-' && v.rsid !== 'nan').length : 0,
                        icon: CheckCircle,
                        color: getThemeClass('text-green-600', isDarkMode),
                        bgColor: getThemeClass('bg-green-50', isDarkMode)
                      },
                      { 
                        label: 'Coverage', 
                        value: data?.real_data?.variants ? 
                          `${Math.round((data.real_data.variants.filter((v: any) => v.rsid && v.rsid !== '-' && v.rsid !== 'nan').length / data.real_data.variants.length) * 100)}%` : 
                          '0%',
                        icon: Activity,
                        color: getThemeClass('text-orange-600', isDarkMode),
                        bgColor: getThemeClass('bg-orange-50', isDarkMode)
                      }
                    ].map((metric, index) => {
                      const Icon = metric.icon
                      return (
                        <div key={index} className={`${theme.glass} border ${theme.glassBorder} rounded-xl p-4 text-center group ${theme.glassHover} transition-all duration-300`}>
                          <div className={`p-3 ${metric.bgColor} rounded-lg mx-auto mb-3 w-fit group-hover:scale-110 transition-transform duration-300`}>
                            <Icon className={`h-5 w-5 ${metric.color}`} />
                          </div>
                          <div className={`text-2xl font-bold ${theme.text.primary} mb-1`}>
                            {metric.value}
                          </div>
                          <div className={`text-xs ${theme.text.muted} font-medium uppercase tracking-wider`}>
                            {metric.label}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>

              {/* Right Column - Data Overview and Quick Actions (1 column) */}
              <div className="xl:col-span-1 space-y-6">
                {/* Analysis Progress (if running) */}
                {(analysisStatus === 'processing' || isAnalysisRunning) && (
                  <div 
                    className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-6 cursor-pointer hover:shadow-lg transition-all duration-300 hover:scale-[1.02]`}
                    onClick={() => setShowProgress(true)}
                    title="Click to view detailed analysis progress"
                  >
                    <div className="flex items-center space-x-3 mb-6">
                      <div className="p-3 bg-gradient-to-br from-blue-500/20 to-cyan-500/20 backdrop-blur-xl rounded-xl border border-blue-500/30">
                        <Activity className={`h-6 w-6 ${getThemeClass('text-blue-600', isDarkMode)} animate-pulse`} />
                      </div>
                      <h3 className={`text-lg font-bold ${theme.text.primary}`}>
                        Analysis in Progress
                      </h3>
                      <div className="ml-auto">
                        <svg className={`w-5 h-5 ${theme.text.secondary}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                      </div>
                    </div>
                    
                    <div className="space-y-4">
                      {/* Progress Bar */}
                      <div>
                        <div className="flex justify-between items-center mb-2">
                          <span className={`text-sm font-medium ${theme.text.secondary}`}>
                            {totalVariants > 0 ? `Processing ${processedVariants.toLocaleString()}/${totalVariants.toLocaleString()} variants` : 'Processing variants...'}
                          </span>
                          <span className={`text-sm font-bold ${theme.text.primary}`}>
                            {analysisProgress}%
                          </span>
                        </div>
                        <div className={`w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3`}>
                          <div
                            className="bg-gradient-to-r from-blue-500 to-cyan-500 h-3 rounded-full transition-all duration-500"
                            style={{ width: `${Math.max(0, Math.min(100, analysisProgress))}%` }}
                          />
                        </div>
                      </div>
                      
                      {/* Progress Stats */}
                      <div className="grid grid-cols-2 gap-3">
                        <div className={`${theme.glass} border ${theme.glassBorder} rounded-lg p-3 text-center`}>
                          <div className={`text-lg font-bold ${theme.text.primary}`}>
                            {totalVariants > 0 ? processedVariants.toLocaleString() : '0'}
                          </div>
                          <div className={`text-xs ${theme.text.secondary}`}>Processed</div>
                        </div>
                        <div className={`${theme.glass} border ${theme.glassBorder} rounded-lg p-3 text-center`}>
                          <div className={`text-lg font-bold ${theme.text.primary}`}>
                            {totalVariants > 0 ? totalVariants.toLocaleString() : '0'}
                          </div>
                          <div className={`text-xs ${theme.text.secondary}`}>Total</div>
                        </div>
                      </div>
                      
                      {/* Status Message */}
                      <div className={`p-3 rounded-lg ${getThemeClass('bg-blue-50', isDarkMode)} border ${getThemeClass('border-blue-200', isDarkMode)}`}>
                        <div className={`text-sm ${getThemeClass('text-blue-800', isDarkMode)}`}>
                          <div className="flex items-center space-x-2">
                            <div className={`w-2 h-2 rounded-full ${getThemeClass('bg-blue-500', isDarkMode)} animate-pulse`}></div>
                            <span>
                              {totalVariants > 0 
                                ? `Analyzing ${processedVariants.toLocaleString()} of ${totalVariants.toLocaleString()} variants for health insights...`
                                : 'Analyzing your genetic variants for health insights...'
                              }
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Data Overview */}
                <div className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-6`}>
                  <div className="flex items-center space-x-3 mb-6">
                    <div className="p-3 bg-gradient-to-br from-green-500/20 to-emerald-500/20 backdrop-blur-xl rounded-xl border border-green-500/30">
                      <Dna className={`h-6 w-6 ${getThemeClass('text-green-600', isDarkMode)}`} />
                    </div>
                    <h3 className={`text-lg font-bold ${theme.text.primary}`}>
                      Your Data
                    </h3>
                  </div>
                  
                  <div className="space-y-4">
                    {data && data.summary && data.summary.total_variants > 0 ? (
                      <>
                        <div className={`${theme.glass} border ${theme.glassBorder} rounded-xl p-4 text-center`}>
                          <div className="text-3xl font-bold text-green-600 mb-1">
                            {data?.summary?.total_variants || 0}
                          </div>
                          <div className={`text-sm ${theme.text.secondary}`}>DNA Variants</div>
                        </div>
                        
                        <div className="space-y-3">
                          {[
                            { 
                              label: 'File', 
                              value: data.summary?.upload_info?.filename || 
                                     data.summary?.data_sources?.[0] || 
                                     data.real_data?.upload_result?.filename ||
                                     data.summary?.upload_info?.file_name ||
                                     'Unknown', 
                              icon: Upload 
                            },
                            { label: 'Analysis ID', value: data.summary?.analysis_id || 'N/A', icon: Shield }
                          ].map((item, index) => (
                            <div key={index} className={`flex items-center justify-between p-3 ${theme.glass} border ${theme.glassBorder} rounded-lg`}>
                              <div className="flex items-center space-x-2">
                                <item.icon className={`h-4 w-4 ${theme.text.muted}`} />
                                <span className={`text-sm ${theme.text.secondary}`}>{item.label}</span>
                              </div>
                              <span className={`text-sm font-medium ${theme.text.primary} truncate max-w-24`} title={item.value}>
                                {item.value}
                              </span>
                            </div>
                          ))}
                        </div>
                      </>
                    ) : (
                      <div className={`${theme.glass} border ${theme.glassBorder} rounded-xl p-6 text-center`}>
                        <Upload className={`h-12 w-12 ${theme.text.muted} mx-auto mb-4`} />
                        <h4 className={`font-medium ${theme.text.primary} mb-2`}>No Data Uploaded</h4>
                        <p className={`text-sm ${theme.text.secondary} mb-4`}>Upload your genetic data to get started</p>
                        <button
                          onClick={onReset}
                          className="bg-gradient-to-r from-blue-500/80 to-purple-500/80 hover:from-blue-600/80 hover:to-purple-600/80 backdrop-blur-xl text-white px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 border border-white/20 shadow-lg w-full"
                        >
                          Upload Data
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Sample Variants Table - Glassmorphism with Pagination */}
            {data.real_data?.variants && data.real_data.variants.length > 0 && (() => {
              // Filter variants by search term
              const filteredVariants = searchRsid 
                ? data.real_data.variants.filter((variant: { rsid?: string }) => 
                    variant.rsid && variant.rsid.toLowerCase().includes(searchRsid.toLowerCase())
                  )
                : data.real_data.variants

              const totalVariants = filteredVariants.length
              const totalPages = Math.ceil(totalVariants / variantsPerPage)
              const startIndex = (currentPage - 1) * variantsPerPage
              const endIndex = startIndex + variantsPerPage
              const currentVariants = filteredVariants.slice(startIndex, endIndex)

              // Handler for search
              const handleSearch = (value: string) => {
                setSearchRsid(value)
                setCurrentPage(1) // Reset to first page when searching
              }

              // Handler for go to page
              const handleGoToPage = (pageStr: string) => {
                const pageNum = parseInt(pageStr)
                if (pageNum >= 1 && pageNum <= totalPages) {
                  setCurrentPage(pageNum)
                  setGoToPage('')
                }
              }

              return (
                <div className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-8`}>
                  <div className="flex items-center justify-between mb-6">
                    <h4 className={`font-bold ${theme.text.primary} text-xl`}>Sample Genetic Variants</h4>
                    <div className={`text-sm ${theme.text.muted}`}>
                      {searchRsid && (
                        <span className="mr-4">
                          Filtered: {totalVariants} of {data.real_data.variants.length} variants
                        </span>
                      )}
                      Showing {startIndex + 1}-{Math.min(endIndex, totalVariants)} of {totalVariants} variants
                    </div>
                  </div>

                  {/* Search and Navigation Controls */}
                  <div className="flex flex-col sm:flex-row gap-4 mb-6">
                    {/* Search by RS ID */}
                    <div className="flex-1 relative">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <Search className={`h-4 w-4 ${theme.text.muted}`} />
                      </div>
                      <input
                        type="text"
                        placeholder="Search by RS ID (e.g., rs1234567)"
                        value={searchRsid}
                        onChange={(e) => handleSearch(e.target.value)}
                        className={`
                          w-full pl-10 pr-4 py-2 text-sm
                          ${theme.glass} border ${theme.glassBorder} 
                          rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50
                          ${theme.text.primary} placeholder:${theme.text.muted}
                          ${isDarkMode ? 'focus:bg-white/10' : 'focus:bg-white/80'}
                        `}
                      />
                      {searchRsid && (
                        <button
                          onClick={() => handleSearch('')}
                          className={`absolute inset-y-0 right-0 pr-3 flex items-center ${theme.text.muted} hover:${theme.text.primary}`}
                        >
                          <X className="h-4 w-4" />
                        </button>
                      )}
                    </div>

                    {/* Go to Page */}
                    <div className="flex items-center space-x-2">
                      <span className={`text-sm ${theme.text.secondary} whitespace-nowrap`}>Go to page:</span>
                      <input
                        type="number"
                        min="1"
                        max={totalPages}
                        placeholder="Page"
                        value={goToPage}
                        onChange={(e) => setGoToPage(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            handleGoToPage(goToPage)
                          }
                        }}
                        className={`
                          w-20 px-3 py-2 text-sm text-center
                          ${theme.glass} border ${theme.glassBorder} 
                          rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/50
                          ${theme.text.primary}
                          ${isDarkMode ? 'focus:bg-white/10' : 'focus:bg-white/80'}
                        `}
                      />
                      <button
                        onClick={() => handleGoToPage(goToPage)}
                        disabled={!goToPage || parseInt(goToPage) < 1 || parseInt(goToPage) > totalPages}
                        className={`
                          px-3 py-2 text-sm font-medium rounded-lg transition-all duration-200
                          ${theme.glass} border ${theme.glassBorder}
                          ${!goToPage || parseInt(goToPage) < 1 || parseInt(goToPage) > totalPages
                            ? `${theme.text.muted} cursor-not-allowed opacity-50`
                            : `${theme.text.primary} ${isDarkMode ? 'hover:bg-slate-700/40' : 'hover:bg-gray-200/40'}`
                          }
                        `}
                      >
                        Go
                      </button>
                      <span className={`text-sm ${theme.text.muted}`}>of {totalPages}</span>
                    </div>
                  </div>
                  
                  <div className="overflow-x-auto">
                    {totalVariants === 0 && searchRsid ? (
                      <div className="text-center py-12">
                        <Search className={`h-12 w-12 ${theme.text.muted} mx-auto mb-4`} />
                        <h3 className={`text-lg font-medium ${theme.text.primary} mb-2`}>No variants found</h3>
                        <p className={`${theme.text.secondary} mb-4`}>
                          No variants match the search term &quot;{searchRsid}&quot;
                        </p>
                        <button
                          onClick={() => handleSearch('')}
                          className={`
                            px-4 py-2 text-sm font-medium rounded-lg transition-all duration-200
                            ${theme.glass} border ${theme.glassBorder}
                            ${theme.text.primary} ${isDarkMode ? 'hover:bg-slate-700/40' : 'hover:bg-gray-200/40'}
                          `}
                        >
                          Clear search
                        </button>
                      </div>
                    ) : (
                      <table className="w-full text-sm">
                        <thead>
                          <tr className={`${theme.glassBorder} border-b`}>
                            <th className={`text-left py-4 px-4 ${theme.text.secondary} font-semibold`}>Chromosome</th>
                            <th className={`text-left py-4 px-4 ${theme.text.secondary} font-semibold`}>Position</th>
                            <th className={`text-left py-4 px-4 ${theme.text.secondary} font-semibold`}>RS ID</th>
                            <th className={`text-left py-4 px-4 ${theme.text.secondary} font-semibold`}>Ref</th>
                            <th className={`text-left py-4 px-4 ${theme.text.secondary} font-semibold`}>Alt</th>
                            <th className={`text-left py-4 px-4 ${theme.text.secondary} font-semibold`}>Genotype</th>
                          </tr>
                        </thead>
                        <tbody>
                          {currentVariants.map((variant: { 
                            chromosome: string | number;
                            position?: number;
                            rsid?: string;
                            ref_allele: string;
                            alt_allele: string;
                            genotype?: string;
                          }, index: number) => (
                            <tr key={index} className={`${theme.glassBorder} border-b transition-all duration-200 ${isDarkMode ? 'hover:bg-slate-700/30' : 'hover:bg-gray-200/30'}`}>
                              <td className={`py-4 px-4 font-semibold font-mono ${theme.text.primary}`}>{variant.chromosome}</td>
                              <td className={`py-4 px-4 font-mono ${theme.text.secondary}`}>{variant.position?.toLocaleString()}</td>
                              <td className={`py-4 px-4 font-mono ${theme.text.secondary}`}>
                                {variant.rsid ? (
                                  <span className={`${searchRsid && variant.rsid.toLowerCase().includes(searchRsid.toLowerCase()) ? 'bg-yellow-200 dark:bg-yellow-800 px-1 rounded' : ''}`}>
                                    {variant.rsid}
                                  </span>
                                ) : '-'}
                              </td>
                              <td className={`py-4 px-4 font-mono ${theme.text.secondary}`}>{variant.ref_allele}</td>
                              <td className={`py-4 px-4 font-mono ${theme.text.secondary}`}>{variant.alt_allele}</td>
                              <td className={`py-4 px-4 font-mono ${theme.text.secondary}`}>{variant.genotype || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>

                  {/* Pagination Controls */}
                  {totalPages > 1 && totalVariants > 0 && (
                    <div className="flex items-center justify-between mt-6">
                      <button
                        onClick={() => setCurrentPage(Math.max(currentPage - 1, 1))}
                        disabled={currentPage === 1}
                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                          currentPage === 1
                            ? `${theme.text.muted} cursor-not-allowed opacity-50`
                            : `${theme.text.primary} ${isDarkMode ? 'hover:bg-slate-700/40' : 'hover:bg-gray-200/40'} ${theme.glass} border ${theme.glassBorder}`
                        }`}
                      >
                        Previous
                      </button>

                      <div className="flex items-center space-x-2">
                        {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                          let pageNum
                          if (totalPages <= 5) {
                            pageNum = i + 1
                          } else if (currentPage <= 3) {
                            pageNum = i + 1
                          } else if (currentPage >= totalPages - 2) {
                            pageNum = totalPages - 4 + i
                          } else {
                            pageNum = currentPage - 2 + i
                          }

                          return (
                            <button
                              key={pageNum}
                              onClick={() => setCurrentPage(pageNum)}
                              className={`w-10 h-10 rounded-lg text-sm font-medium transition-all duration-200 ${
                                currentPage === pageNum
                                  ? 'bg-blue-500 text-white shadow-lg'
                                  : `${theme.text.secondary} ${isDarkMode ? 'hover:bg-slate-700/40' : 'hover:bg-gray-200/40'} ${theme.glass} border ${theme.glassBorder}`
                              }`}
                            >
                              {pageNum}
                            </button>
                          )
                        })}
                      </div>

                      <button
                        onClick={() => setCurrentPage(Math.min(currentPage + 1, totalPages))}
                        disabled={currentPage === totalPages}
                        className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                          currentPage === totalPages
                            ? `${theme.text.muted} cursor-not-allowed opacity-50`
                            : `${theme.text.primary} ${isDarkMode ? 'hover:bg-slate-700/40' : 'hover:bg-gray-200/40'} ${theme.glass} border ${theme.glassBorder}`
                        }`}
                      >
                        Next
                      </button>
                    </div>
                  )}
                </div>
              )
            })()}
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
      <header className={`${theme.glass} border-b ${theme.glassBorder} relative z-20`}>
        <div className="flex items-center justify-between px-6 py-4">
          {/* Logo and Title */}
          <div className="flex items-center space-x-4">
            <div className="p-3 bg-gradient-to-br from-purple-500/80 to-pink-500/80 backdrop-blur-xl rounded-xl border border-white/20 shadow-xl">
              <Dna className="h-7 w-7 text-white" />
            </div>
            <div>
              <h1 className={`text-xl font-bold ${theme.text.primary}`}>
                Genetic Health Analysis Toolkit
              </h1>
              <p className={`text-sm ${theme.text.muted}`}>
                {data?.summary?.total_variants || 0} DNA variants
              </p>
            </div>
          </div>

          {/* Spacer for better layout */}
          <div className="flex-1"></div>

          {/* Right side actions */}
          <div className="flex items-center space-x-4">
            {/* Theme Toggle */}
            <button
              onClick={() => setIsDarkMode(!isDarkMode)}
              className={`p-2.5 ${theme.glass} border ${theme.glassBorder} rounded-xl ${theme.glassHover} transition-all duration-300`}
            >
              {isDarkMode ? (
                <Sun className={`h-5 w-5 ${theme.text.secondary}`} />
              ) : (
                <Moon className={`h-5 w-5 ${theme.text.secondary}`} />
              )}
            </button>

            {/* Analysis Controls */}
            <div className="flex items-center space-x-2">
              {/* Analysis Status Indicator */}
              {analysisId && (
                <div className={`px-3 py-1.5 rounded-lg text-xs font-medium border ${
                  analysisStatus === 'completed' 
                    ? 'bg-green-50 text-green-700 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-green-800'
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
                    <span>Completed</span>
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

            {/* User Menu - Glassmorphism style */}
            <div className="relative">
              <button
                onClick={() => setShowUserMenu(!showUserMenu)}
                className={`flex items-center space-x-3 ${theme.glass} border ${theme.glassBorder} px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-300 ${theme.glassHover}`}
              >
                <div className="w-7 h-7 bg-gradient-to-br from-purple-500 to-pink-500 rounded-full flex items-center justify-center shadow-lg">
                  <span className="text-white text-sm font-bold">V</span>
                </div>
                <span className={theme.text.primary}>Victor</span>
                <ChevronDown className={`h-4 w-4 ${theme.text.secondary}`} />
              </button>

              {showUserMenu && (
                <div className={`absolute right-0 mt-3 w-52 ${theme.glass} border ${theme.glassBorder} rounded-xl shadow-2xl py-2 z-50`}>
                  <button
                    onClick={() => setShowUserMenu(false)}
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
      <div className="flex h-screen">
        {/* Sidebar - Glassmorphism style */}
        <aside className={`w-72 ${theme.glass} border-r ${theme.glassBorder} relative z-10`}>
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
                        ? 'bg-gradient-to-r from-blue-500/80 to-purple-500/80 text-white shadow-lg border border-white/20 backdrop-blur-xl' 
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
                  className={`px-4 py-2 rounded-lg ${theme.glass} border ${theme.glassBorder} ${theme.text.primary} hover:bg-white/10 transition-colors`}
                >
                  Cancel
                </button>
                <button
                  onClick={() => {
                    setShowDeleteDialog(false);
                    handleDeleteData();
                  }}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-colors"
                >
                  Delete
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