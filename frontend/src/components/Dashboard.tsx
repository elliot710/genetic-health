'use client'

import React, { useState, useEffect, useCallback, Suspense } from 'react'
import {
  Apple, Brain, Dumbbell, Heart, Zap, Palette,
  AlertTriangle, Shield, Search, Pill, Ruler, Globe, ShieldCheck,
  Dna, Activity, Users, Home,
  Loader2,
} from 'lucide-react'
import { getTheme } from '../utils/theme'
import { apiUrl } from '@/lib/api'
import type { DashboardData } from './categories/types'

// Hooks
import { useDashboardData } from '@/hooks/useDashboardData'
import { useAnalysisControls } from '@/hooks/useAnalysisControls'

// Dashboard sub-components
import DashboardHeader from './dashboard/DashboardHeader'
import DashboardSidebar from './dashboard/DashboardSidebar'
import type { SidebarCategory } from './dashboard/DashboardSidebar'
import DashboardOverview from './dashboard/DashboardOverview'
import DeleteDataDialog from './dashboard/DeleteDataDialog'
import NotificationToast from './dashboard/NotificationToast'

// Category panels — lazy-loaded (only one visible at a time)
const FoodNutritionPanel = React.lazy(() => import('./categories/FoodNutritionPanel'))
const IntelligencePanel = React.lazy(() => import('./categories/IntelligencePanel'))
const PhysicalTraitsPanel = React.lazy(() => import('./categories/PhysicalTraitsPanel'))
const PersonalityPanel = React.lazy(() => import('./categories/PersonalityPanel'))
const SportsPanel = React.lazy(() => import('./categories/SportsPanel'))
const HealthPanel = React.lazy(() => import('./categories/HealthPanel'))
const DrugResponsesPanel = React.lazy(() => import('./categories/DrugResponsesPanel'))
const AncestryPanel = React.lazy(() => import('./categories/AncestryPanel'))
const CarrierStatusPanel = React.lazy(() => import('./categories/CarrierStatusPanel'))
const WellnessPanel = React.lazy(() => import('./categories/WellnessPanel'))
const MethylationPanel = React.lazy(() => import('./categories/MethylationPanel'))
const DetoxPanel = React.lazy(() => import('./categories/DetoxPanel'))
const RareMutationsPanel = React.lazy(() => import('./categories/RareMutationsPanel'))
const UncommonMutationsPanel = React.lazy(() => import('./categories/UncommonMutationsPanel'))
const SmartInsights = React.lazy(() => import('./SmartInsights'))
const KnowledgeGraph = React.lazy(() => import('./KnowledgeGraph'))
const AdminPanel = React.lazy(() => import('./admin/AdminPanel'))
const SettingsPanel = React.lazy(() => import('./SettingsPanel'))
const VariantSearch = React.lazy(() => import('./VariantSearch'))

import { ErrorState, useThemeClasses } from './categories/shared'
import { RiskDistributionChart, FunctionalCategoriesChart, OverviewSummaryPie } from './categories/GenomicCharts'
import AnalysisProgressLoader from './AnalysisProgressLoader'

interface DashboardProps {
  token?: string
  analysisData?: DashboardData | null
  analysisId?: number | null
  onRefresh?: (token: string) => Promise<void>
  onNavigateToUpload?: () => void
  isAdmin?: boolean
  userName?: string
  userAvatarUrl?: string | null
}

const CATEGORIES: SidebarCategory[] = [
  { id: 'overview', title: 'Overview', icon: Home },
  { id: 'health', title: 'Health & Wellness', icon: Heart },
  { id: 'food-nutrition', title: 'Food & Nutrition', icon: Apple },
  { id: 'drug-responses', title: 'Drug Responses', icon: Pill },
  { id: 'physical-traits', title: 'Physical Traits', icon: Ruler },
  { id: 'sports', title: 'Sports & Fitness', icon: Dumbbell },
  { id: 'intelligence', title: 'Intelligence', icon: Brain },
  { id: 'personality', title: 'Personality', icon: Palette },
  { id: 'ancestry', title: 'Ancestry & Origins', icon: Globe },
  { id: 'carrier-status', title: 'Carrier Status', icon: ShieldCheck },
  { id: 'wellness', title: 'Wellness Reports', icon: Activity },
  { id: 'separator-1', title: '', icon: null, isSeparator: true },
  { id: 'methylation', title: 'Methylation', icon: Dna },
  { id: 'detox', title: 'Detoxification', icon: Shield },
  { id: 'rare-mutations', title: 'Rare Mutations', icon: AlertTriangle },
  { id: 'uncommon-mutations', title: 'Uncommon Mutations', icon: Dna },
  { id: 'separator-2', title: '', icon: null, isSeparator: true },
  { id: 'variant-search', title: 'Variant Search', icon: Search },
  { id: 'knowledge-graph', title: 'Knowledge Graph', icon: Activity },
]

export default function Dashboard({
  token,
  analysisData,
  analysisId,
  onRefresh,
  onNavigateToUpload,
  isAdmin,
  userName,
  userAvatarUrl,
}: DashboardProps) {
  // ── UI state ──────────────────────────────────────────────
  const [activeCategory, setActiveCategory] = useState(() => {
    if (typeof window !== 'undefined') {
      const hash = window.location.hash.slice(1)
      // admin/tab → admin (sub-tab handled by AdminPanel)
      return (hash.startsWith('admin/') ? 'admin' : hash) || 'overview'
    }
    return 'overview'
  })
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [currentUserName, setCurrentUserName] = useState(userName || 'User')
  const [currentAvatarUrl, setCurrentAvatarUrl] = useState<string | null | undefined>(userAvatarUrl)
  const [notification, setNotification] = useState<{
    show: boolean
    message: string
    type: 'success' | 'error' | 'info'
  }>({ show: false, message: '', type: 'info' })
  const [isDarkMode, setIsDarkMode] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('darkMode')
      return saved ? JSON.parse(saved) : false
    }
    return false
  })

  const theme = getTheme(isDarkMode)
  const panelTheme = useThemeClasses(isDarkMode)

  // ── Notification helper ───────────────────────────────────
  const showNotification = useCallback(
    (message: string, type: 'success' | 'error' | 'info' = 'info') => {
      setNotification({ show: true, message, type })
      setTimeout(() => setNotification((prev) => ({ ...prev, show: false })), 3000)
    },
    [],
  )

  // ── Data hook ─────────────────────────────────────────────
  const {
    data,
    loading,
    error: dataError,
    lastFetchedAt,
    isCached,
    refreshData,
    setData,
    clearData,
    variantCategories,
    variantCategoryStats,
  } = useDashboardData({
    initialData: analysisData,
    analysisId,
    onRefresh,
    token,
  })

  // ── Analysis controls hook ────────────────────────────────
  const analysis = useAnalysisControls({
    analysisId,
    token,
    onRefresh,
    onDataRefresh: () => refreshData(true),
    showNotification,
  })

  // ── Theme persistence ─────────────────────────────────────
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('darkMode', JSON.stringify(isDarkMode))
      document.documentElement.classList.toggle('dark', isDarkMode)
    }
  }, [isDarkMode])

  // ── URL hash sync ─────────────────────────────────────────
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const currentHash = window.location.hash.slice(1)
      // Don't overwrite admin sub-tab hashes (admin/data, admin/rules etc.)
      if (activeCategory === 'admin' && currentHash.startsWith('admin')) return
      const newHash = activeCategory === 'overview' ? '' : activeCategory
      if (currentHash !== newHash) {
        window.history.replaceState(null, '', newHash ? `#${newHash}` : window.location.pathname)
      }
    }
  }, [activeCategory])

  useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash.slice(1)
      setActiveCategory((hash.startsWith('admin/') ? 'admin' : hash) || 'overview')
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  // ── Re-fetch user info (e.g. after avatar update) ─────────
  const refreshUserInfo = useCallback(async () => {
    if (!token) return
    try {
      const res = await fetch(apiUrl('/auth/me'), { credentials: 'include' })
      if (res.ok) {
        const u = await res.json()
        setCurrentUserName(u.full_name || u.username || 'User')
        setCurrentAvatarUrl(u.avatar_url)
      }
    } catch {
      /* ignore */
    }
  }, [token])

  // ── Show progress if analysis ID present but no data ──────
  useEffect(() => {
    if (analysisId && !data) {
      analysis.setShowProgress(true)
    }
  }, [analysisId, data, analysis])

  // ── Handlers ──────────────────────────────────────────────
  const onReset = () => {
    clearData()
    if (onNavigateToUpload) {
      onNavigateToUpload()
    } else {
      setActiveCategory('overview')
    }
  }

  const handleAnalysisComplete = (results: DashboardData) => {
    setData(results)
    analysis.setShowProgress(false)
  }

  const handleAnalysisError = (error: string) => {
    analysis.setShowProgress(false)
    // "Analysis not found" means the analysis was deleted — not a real error, ignore silently
    if (error.toLowerCase().includes('not found')) return
    showNotification(error || 'Analysis error occurred', 'error')
  }

  const handleRefreshData = async () => {
    try {
      await refreshData(true)
      showNotification('Data refreshed successfully', 'success')
    } catch {
      showNotification('Error refreshing data', 'error')
    }
  }

  const handleDeleteData = async () => {
    setIsDeleting(true)
    try {
      const response = await fetch(apiUrl('/upload/data'), {
        method: 'DELETE',
        credentials: 'include',
      })
      if (response.ok) {
        clearData()
        analysis.resetAnalysisState()
        setActiveCategory('overview')
        setShowDeleteDialog(false)
        showNotification('All data deleted successfully', 'success')
        if (onRefresh && token) {
          await onRefresh(token)
        }
      } else {
        showNotification('Failed to delete data', 'error')
      }
    } catch {
      showNotification('Error deleting data', 'error')
    } finally {
      setIsDeleting(false)
    }
  }

  // ── Panel content switcher ────────────────────────────────
  const renderCategoryContent = () => {
    if (dataError) {
      return (
        <ErrorState
          message={dataError}
          onRetry={() => refreshData(true)}
          theme={panelTheme}
        />
      )
    }
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
          <DashboardOverview
            theme={theme}
            isDarkMode={isDarkMode}
            data={data}
            token={token}
            analysisStatus={analysis.analysisStatus}
            analysisProgress={analysis.analysisProgress}
            isAnalysisRunning={analysis.isAnalysisRunning}
            variantCategories={variantCategories}
            variantCategoryStats={variantCategoryStats}
            lastFetchedAt={lastFetchedAt}
            isCached={isCached}
            setActiveCategory={setActiveCategory}
            setShowProgress={analysis.setShowProgress}
            onRefreshData={refreshData}
          />
        )
    }
  }

  // ── Loading state ─────────────────────────────────────────
  if (loading) {
    return (
      <div className={`min-h-screen ${theme.background} relative overflow-hidden flex items-center justify-center`}>
        <div className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-8 text-center`}>
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
          <h2 className={`text-xl font-semibold ${theme.text.primary} mb-2`}>Loading Genetic Analysis</h2>
          <p className={theme.text.secondary}>Preparing your personalized health insights...</p>
        </div>
      </div>
    )
  }

  // ── Empty state ───────────────────────────────────────────
  if (!data && !loading && !isAdmin) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-xl font-semibold mb-2">No Data Available</h2>
          <p className="text-gray-600">Please upload your genetic data to get started.</p>
        </div>
      </div>
    )
  }

  // ── Main render ───────────────────────────────────────────
  return (
    <div className={`min-h-screen ${theme.background} relative overflow-hidden`}>
      {/* Background blobs */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className={`absolute -top-40 -right-40 w-96 h-96 ${theme.blobs.primary} rounded-full filter blur-3xl animate-float`}></div>
        <div className={`absolute top-1/3 -left-40 w-80 h-80 ${theme.blobs.secondary} rounded-full filter blur-3xl animate-float-delayed`}></div>
        <div className={`absolute bottom-0 right-1/3 w-72 h-72 ${theme.blobs.tertiary} rounded-full filter blur-3xl animate-float-slow`}></div>
        <div className={`absolute top-1/2 left-1/2 w-64 h-64 ${theme.blobs.primary} rounded-full filter blur-3xl animate-float-reverse`}></div>
      </div>

      <DashboardHeader
        theme={theme}
        isDarkMode={isDarkMode}
        setIsDarkMode={setIsDarkMode}
        data={data}
        analysisId={analysisId}
        analysisStatus={analysis.analysisStatus}
        analysisProgress={analysis.analysisProgress}
        isAnalysisRunning={analysis.isAnalysisRunning}
        isAdmin={isAdmin}
        currentUserName={currentUserName}
        currentAvatarUrl={currentAvatarUrl}
        showUserMenu={showUserMenu}
        setShowUserMenu={setShowUserMenu}
        setActiveCategory={setActiveCategory}
        onStartAnalysis={analysis.handleStartAnalysis}
        onStopAnalysis={analysis.handleStopAnalysis}
        onPauseAnalysis={analysis.handlePauseAnalysis}
        onResumeAnalysis={analysis.handleResumeAnalysis}
        onRefreshData={handleRefreshData}
        onReset={onReset}
        onDeleteClick={() => setShowDeleteDialog(true)}
      />

      <div className="flex" style={{ height: 'calc(100vh - 73px)' }}>
        <DashboardSidebar
          theme={theme}
          isDarkMode={isDarkMode}
          categories={CATEGORIES}
          activeCategory={activeCategory}
          setActiveCategory={setActiveCategory}
        />

        <main className={`flex-1 overflow-auto ${theme.background}`}>
          <div className="p-8 max-w-none">
            {analysis.showProgress && analysisId ? (
              <AnalysisProgressLoader
                analysisId={analysisId}
                isDarkMode={isDarkMode}
                onComplete={handleAnalysisComplete}
                onError={handleAnalysisError}
                onBack={() => analysis.setShowProgress(false)}
              />
            ) : (
              <Suspense fallback={
                <div className="flex items-center justify-center py-24">
                  <Loader2 className="h-8 w-8 animate-spin opacity-40" />
                </div>
              }>
                {renderCategoryContent()}
              </Suspense>
            )}
          </div>
        </main>
      </div>

      {/* CSS Animations */}
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
        .animate-float { animation: float 15s ease-in-out infinite; }
        .animate-float-delayed { animation: float-delayed 18s ease-in-out infinite; animation-delay: 2s; }
        .animate-float-slow { animation: float-slow 20s ease-in-out infinite; animation-delay: 4s; }
        .animate-float-reverse { animation: float-reverse 22s ease-in-out infinite; animation-delay: 6s; }
      `}</style>

      {showDeleteDialog && (
        <DeleteDataDialog
          theme={theme}
          isDeleting={isDeleting}
          onConfirm={handleDeleteData}
          onCancel={() => setShowDeleteDialog(false)}
        />
      )}

      <NotificationToast
        theme={theme}
        show={notification.show}
        message={notification.message}
        type={notification.type}
        onDismiss={() => setNotification((prev) => ({ ...prev, show: false }))}
      />
    </div>
  )
}
