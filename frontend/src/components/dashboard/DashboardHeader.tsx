'use client'

import {
  Dna, Activity, BarChart3, Upload, Pause, Square, Play,
  ChevronDown, Sun, Moon, Shield, Settings, Trash2, LogOut,
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
}: DashboardHeaderProps) {
  return (
    <header className={`${theme.glass} border-b ${theme.glassBorder} sticky top-0 z-30`}>
      <div className="flex items-center justify-between px-6 py-4">
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
            <h1 className={`text-xl font-bold ${theme.text.primary}`}>
              Genetic Health Analysis Toolkit
            </h1>
            <p className={`text-sm ${theme.text.muted}`}>
              {data?.summary?.total_variants || 0} DNA variants
            </p>
          </div>
        </button>

        <div className="flex-1"></div>

        {/* Right side actions */}
        <div className="flex items-center space-x-4">
          {/* Analysis Controls */}
          <div className="flex items-center space-x-2">
            {/* Analysis Status Indicator */}
            {analysisId && (
              <div
                className={`px-3 py-1.5 rounded-lg text-xs font-medium border ${
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
                }`}
              >
                {analysisStatus === 'processing' ? (
                  <div className="flex items-center space-x-2">
                    <div
                      className={`w-2 h-2 border rounded-full animate-spin ${
                        isDarkMode ? 'border-blue-400 border-t-transparent' : 'border-blue-600 border-t-transparent'
                      }`}
                    ></div>
                    <span>Processing {analysisProgress}%</span>
                  </div>
                ) : analysisStatus === 'stopped' ? (
                  <div className="flex items-center space-x-2">
                    <Square className="w-2 h-2" />
                    <span>{analysisProgress >= 100 ? 'Completed' : `Stopped at ${analysisProgress}%`}</span>
                  </div>
                ) : analysisStatus === 'paused' ? (
                  <div className="flex items-center space-x-2">
                    <Pause className="w-2 h-2" />
                    <span>Paused at {analysisProgress}%</span>
                  </div>
                ) : analysisStatus === 'completed' ? (
                  <span>✓ Completed</span>
                ) : (
                  analysisStatus
                )}
              </div>
            )}

            {/* Compact Analysis Control Buttons */}
            <div
              className={`flex items-center border rounded-lg backdrop-blur-xl ${
                isDarkMode ? 'border-white/20 bg-white/10' : 'border-gray-300 bg-white/90 shadow-sm'
              }`}
            >
              {analysisStatus === 'processing' || isAnalysisRunning ? (
                <>
                  <button
                    onClick={onPauseAnalysis}
                    className={`px-3 py-2 text-xs font-medium transition-all duration-200 flex items-center space-x-1 ${
                      isDarkMode ? 'text-orange-400 hover:bg-orange-500/10' : 'text-orange-600 hover:bg-orange-50'
                    }`}
                    title="Pause Analysis"
                  >
                    <Pause className="h-3 w-3" />
                    <span className="hidden sm:inline">Pause</span>
                  </button>
                  <button
                    onClick={onStopAnalysis}
                    className={`px-3 py-2 text-xs font-medium transition-all duration-200 flex items-center space-x-1 rounded-r-lg border-l ${
                      isDarkMode ? 'text-red-400 hover:bg-red-500/10 border-white/10' : 'text-red-600 hover:bg-red-50 border-gray-200'
                    }`}
                    title="Stop Analysis"
                  >
                    <Square className="h-3 w-3" />
                    <span className="hidden sm:inline">Stop</span>
                  </button>
                </>
              ) : analysisStatus === 'stopped' || analysisStatus === 'paused' ? (
                <button
                  onClick={onResumeAnalysis}
                  disabled={!analysisId}
                  className={`px-3 py-2 text-xs font-medium transition-all duration-200 flex items-center space-x-1 rounded-l-lg disabled:opacity-50 disabled:cursor-not-allowed ${
                    isDarkMode ? 'text-blue-400 hover:bg-blue-500/10' : 'text-blue-600 hover:bg-blue-50'
                  }`}
                  title="Resume Analysis"
                >
                  <Play className="h-3 w-3" />
                  <span className="hidden sm:inline">Resume</span>
                </button>
              ) : (
                <button
                  onClick={onStartAnalysis}
                  disabled={!analysisId}
                  className={`px-3 py-2 text-xs font-medium transition-all duration-200 flex items-center space-x-1 rounded-l-lg disabled:opacity-50 disabled:cursor-not-allowed ${
                    isDarkMode ? 'text-green-400 hover:bg-green-500/10' : 'text-green-600 hover:bg-green-50'
                  }`}
                  title={analysisStatus === 'completed' ? 'Restart Analysis' : 'Start Analysis'}
                >
                  <Activity className="h-3 w-3" />
                  <span className="hidden sm:inline">{analysisStatus === 'completed' ? 'Restart' : 'Start'}</span>
                </button>
              )}

              {/* Refresh Data */}
              <button
                onClick={onRefreshData}
                className={`px-3 py-2 text-xs font-medium transition-all duration-200 flex items-center space-x-1 border-l ${
                  isDarkMode ? 'text-white hover:bg-white/10 border-white/20' : 'text-gray-700 hover:bg-gray-100 border-gray-300'
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
                  isDarkMode ? 'text-white hover:bg-white/10 border-white/20' : 'text-gray-700 hover:bg-gray-100 border-gray-300'
                }`}
                title="Upload New File"
              >
                <Upload className="h-3 w-3" />
                <span className="hidden sm:inline">Upload</span>
              </button>
            </div>
          </div>

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
              <div
                className={`absolute right-0 mt-3 w-52 rounded-xl shadow-2xl py-2 z-50 ${
                  isDarkMode ? 'bg-slate-800 border border-slate-700' : 'bg-white border border-gray-200'
                }`}
              >
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
                <button
                  onClick={onDeleteClick}
                  className="w-full text-left px-4 py-3 text-sm text-red-500 hover:bg-red-500/10 flex items-center space-x-3 transition-all duration-200"
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
  )
}
