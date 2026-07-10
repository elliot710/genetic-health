'use client'

import {
  Dna, Activity, BarChart3, Upload, Pause, Square, Play,
  ChevronDown, Sun, Moon, Shield, Settings, Trash2, LogOut, Menu,
} from 'lucide-react'
import { getThemeClass, getTheme } from '@/utils/theme'
import NotificationBell from './NotificationBell'
import type { AppNotification } from '@/hooks/useNotifications'

type Theme = ReturnType<typeof getTheme>

interface DashboardHeaderProps {
  theme: Theme
  isDarkMode: boolean
  setIsDarkMode: (v: boolean) => void
  data?: { summary?: { total_variants?: number } }
  analysisId?: number | null
  analysisStatus: string
  analysisProgress: number
  isAnalysisRunning: boolean
  isAdmin?: boolean
  currentUserName: string
  currentAvatarUrl?: string | null
  showUserMenu: boolean
  setShowUserMenu: (v: boolean) => void
  setActiveCategory: (cat: string) => void
  onStartAnalysis: () => void
  onStopAnalysis: () => void
  onPauseAnalysis: () => void
  onResumeAnalysis: () => void
  onRefreshData: () => void
  onReset: () => void
  onDeleteClick: () => void
  // Notification props
  notifications: AppNotification[]
  unreadCount: number
  isNotificationConnected: boolean
  onMarkRead: (id: number) => Promise<void>
  onMarkAllRead: () => Promise<void>
  onDeleteNotification: (id: number) => Promise<void>
  onMenuToggle?: () => void
}

export default function DashboardHeader({
  theme,
  isDarkMode,
  setIsDarkMode,
  data,
  analysisId,
  analysisStatus,
  analysisProgress,
  isAnalysisRunning,
  isAdmin,
  currentUserName,
  currentAvatarUrl,
  showUserMenu,
  setShowUserMenu,
  setActiveCategory,
  onStartAnalysis,
  onStopAnalysis,
  onPauseAnalysis,
  onResumeAnalysis,
  onRefreshData,
  onReset,
  onDeleteClick,
  notifications,
  unreadCount,
  isNotificationConnected,
  onMarkRead,
  onMarkAllRead,
  onDeleteNotification,
  onMenuToggle,
}: DashboardHeaderProps) {
  return (
    <header className={`${theme.glass} border-b ${theme.glassBorder} sticky top-0 z-30`}>
      <div className="flex items-center justify-between px-4 md:px-6 py-4">
        {/* Hamburger button — mobile only */}
        <button
          onClick={onMenuToggle}
          className={`md:hidden mr-3 p-2 rounded-xl transition-all duration-200 ${theme.glassHover} border ${theme.glassBorder}`}
          aria-label="Open navigation menu"
        >
          <Menu className={`h-5 w-5 ${theme.text.primary}`} />
        </button>

        {/* Logo and Title */}
        <button
          onClick={() => {
            setActiveCategory('overview')
            window.scrollTo(0, 0)
          }}
          className="flex items-center space-x-4 cursor-pointer hover:opacity-80 transition-opacity"
        >
          <div className="p-3 bg-gradient-to-br from-teal-500/80 to-cyan-500/80 backdrop-blur-xl rounded-xl border border-white/20 shadow-xl">
            <Dna className="h-7 w-7 text-white" />
          </div>
          <div className="text-left">
            <h1 className={`text-base md:text-xl font-bold ${theme.text.primary}`}>
              <span className="hidden sm:inline">Epigenic | Genetic Analysis Toolkit</span>
              <span className="sm:hidden">epigenic.xyz</span>
            </h1>
            <p className={`text-xs md:text-sm ${theme.text.muted}`}>
              {data?.summary?.total_variants || 0} DNA variants
            </p>
          </div>
        </button>

        <div className="flex-1"></div>

        {/* Right side actions */}
        <div className="flex items-center space-x-2 md:space-x-4">

          {/* Notification Bell */}
          <NotificationBell
            theme={theme}
            isDarkMode={isDarkMode}
            notifications={notifications}
            unreadCount={unreadCount}
            isConnected={isNotificationConnected}
            onMarkRead={onMarkRead}
            onMarkAllRead={onMarkAllRead}
            onDelete={onDeleteNotification}
          />

          {/* User Menu */}
          <div className="relative">
            <button
              onClick={() => setShowUserMenu(!showUserMenu)}
              className={`flex items-center space-x-2 md:space-x-3 ${theme.glass} border ${theme.glassBorder} px-2.5 md:px-4 py-2 md:py-2.5 rounded-xl text-sm font-medium transition-all duration-300 ${theme.glassHover}`}
            >
              {currentAvatarUrl ? (
                <img src={currentAvatarUrl} alt="" className="w-7 h-7 rounded-full object-cover" />
              ) : (
                <div className="w-7 h-7 bg-gradient-to-br from-teal-500 to-cyan-500 rounded-full flex items-center justify-center shadow-lg shrink-0">
                  <span className="text-white text-sm font-bold">{(currentUserName || 'U')[0].toUpperCase()}</span>
                </div>
              )}
              <span className={`hidden md:inline ${theme.text.primary}`}>{currentUserName}</span>
              <ChevronDown className={`hidden md:block h-4 w-4 ${theme.text.secondary}`} />
            </button>

            {showUserMenu && (
              <div
                className={`absolute right-0 mt-3 w-56 rounded-xl shadow-2xl py-2 z-50 ${
                  isDarkMode ? 'bg-slate-800 border border-slate-700' : 'bg-white border border-gray-200'
                }`}
              >
                {/* Analysis status */}
                {analysisId && (
                  <div className={`mx-3 mb-1 px-3 py-2 rounded-lg text-xs font-medium ${
                    analysisStatus === 'completed'
                      ? 'bg-green-500/15 text-green-600 dark:text-green-400'
                      : analysisStatus === 'processing'
                        ? 'bg-blue-500/15 text-blue-600 dark:text-blue-400'
                        : analysisStatus === 'failed'
                          ? 'bg-red-500/15 text-red-600 dark:text-red-400'
                          : 'bg-gray-500/10 text-gray-600 dark:text-gray-400'
                  }`}>
                    {analysisStatus === 'processing' ? (
                      <span className="flex items-center gap-1.5">
                        <span className={`w-2 h-2 rounded-full animate-spin border border-t-transparent ${
                          isDarkMode ? 'border-blue-400' : 'border-blue-600'
                        }`} />
                        Processing {analysisProgress}%
                      </span>
                    ) : analysisStatus === 'completed' ? (
                      '✓ Analysis complete'
                    ) : analysisStatus === 'paused' ? (
                      `⏸ Paused at ${analysisProgress}%`
                    ) : analysisStatus === 'stopped' ? (
                      `⏹ Stopped at ${analysisProgress}%`
                    ) : analysisStatus === 'failed' ? (
                      '✗ Analysis failed'
                    ) : (
                      analysisStatus
                    )}
                  </div>
                )}

                {/* Analysis actions */}
                {(analysisStatus === 'processing' || isAnalysisRunning) ? (
                  <>
                    <button
                      onClick={() => { onPauseAnalysis(); setShowUserMenu(false) }}
                      className={`w-full text-left px-4 py-3 text-sm flex items-center space-x-3 transition-all duration-200 ${
                        isDarkMode ? 'text-orange-400 hover:bg-orange-500/10' : 'text-orange-600 hover:bg-orange-50'
                      }`}
                    >
                      <Pause className="h-4 w-4" />
                      <span>Pause Analysis</span>
                    </button>
                    <button
                      onClick={() => { onStopAnalysis(); setShowUserMenu(false) }}
                      className={`w-full text-left px-4 py-3 text-sm flex items-center space-x-3 transition-all duration-200 ${
                        isDarkMode ? 'text-red-400 hover:bg-red-500/10' : 'text-red-600 hover:bg-red-50'
                      }`}
                    >
                      <Square className="h-4 w-4" />
                      <span>Stop Analysis</span>
                    </button>
                  </>
                ) : (analysisStatus === 'stopped' || analysisStatus === 'paused') ? (
                  <button
                    onClick={() => { onResumeAnalysis(); setShowUserMenu(false) }}
                    disabled={!analysisId}
                    className={`w-full text-left px-4 py-3 text-sm flex items-center space-x-3 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed ${
                      isDarkMode ? 'text-blue-400 hover:bg-blue-500/10' : 'text-blue-600 hover:bg-blue-50'
                    }`}
                  >
                    <Play className="h-4 w-4" />
                    <span>Resume Analysis</span>
                  </button>
                ) : (
                  <button
                    onClick={() => { onStartAnalysis(); setShowUserMenu(false) }}
                    disabled={!analysisId}
                    className={`w-full text-left px-4 py-3 text-sm flex items-center space-x-3 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed ${
                      isDarkMode ? 'text-green-400 hover:bg-green-500/10' : 'text-green-600 hover:bg-green-50'
                    }`}
                  >
                    <Activity className="h-4 w-4" />
                    <span>{analysisStatus === 'completed' ? 'Restart Analysis' : 'Start Analysis'}</span>
                  </button>
                )}
                <button
                  onClick={() => { onRefreshData(); setShowUserMenu(false) }}
                  className={`w-full text-left px-4 py-3 text-sm ${theme.text.primary} ${theme.glassHover} flex items-center space-x-3 transition-all duration-200`}
                >
                  <BarChart3 className="h-4 w-4" />
                  <span>Refresh Data</span>
                </button>
                <button
                  onClick={() => { onReset(); setShowUserMenu(false) }}
                  className={`w-full text-left px-4 py-3 text-sm ${theme.text.primary} ${theme.glassHover} flex items-center space-x-3 transition-all duration-200`}
                >
                  <Upload className="h-4 w-4" />
                  <span>Upload New File</span>
                </button>

                <hr className={`my-2 ${theme.glassBorder} border-t`} />

                {/* App settings */}
                <button
                  onClick={() => {
                    setIsDarkMode(!isDarkMode)
                    setShowUserMenu(false)
                  }}
                  className={`w-full text-left px-4 py-3 text-sm ${theme.text.primary} ${theme.glassHover} flex items-center space-x-3 transition-all duration-200`}
                >
                  {isDarkMode ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
                  <span>{isDarkMode ? 'Light Mode' : 'Dark Mode'}</span>
                </button>
                {isAdmin && (
                  <button
                    onClick={() => {
                      setActiveCategory('admin')
                      setShowUserMenu(false)
                    }}
                    className={`w-full text-left px-4 py-3 text-sm ${theme.text.primary} ${theme.glassHover} flex items-center space-x-3 transition-all duration-200`}
                  >
                    <Shield className="h-4 w-4" />
                    <span>Admin Panel</span>
                  </button>
                )}
                <button
                  onClick={() => {
                    setActiveCategory('settings')
                    setShowUserMenu(false)
                  }}
                  className={`w-full text-left px-4 py-3 text-sm ${theme.text.primary} ${theme.glassHover} flex items-center space-x-3 transition-all duration-200`}
                >
                  <Settings className="h-4 w-4" />
                  <span>Profile</span>
                </button>

                <hr className={`my-2 ${theme.glassBorder} border-t`} />

                <button
                  onClick={onDeleteClick}
                  className="w-full text-left px-4 py-3 text-sm text-red-500 hover:bg-red-500/10 flex items-center space-x-3 transition-all duration-200"
                >
                  <Trash2 className="h-4 w-4" />
                  <span>Delete Data</span>
                </button>
                <button
                  onClick={() => { onReset(); setShowUserMenu(false) }}
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
  )
}
