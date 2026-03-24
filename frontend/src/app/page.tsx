'use client'

import { useState, useEffect, useCallback } from 'react'
import { Dna, LogOut } from 'lucide-react'
import Dashboard from '@/components/Dashboard'
import FileUpload from '@/components/FileUpload'
import AuthForm from '@/components/AuthForm'
import { getTheme } from '@/utils/theme'
import { apiUrl } from '@/lib/api'
import type { DashboardData } from '@/components/categories/types'

interface User {
  id?: string
  email?: string
  username?: string
  full_name?: string
  is_admin?: boolean
  avatar_url?: string | null
}

export default function Home() {
  const [analysisData, setAnalysisData] = useState<DashboardData | null>(null)
  const [analysisId, setAnalysisId] = useState<number | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [isHydrated, setIsHydrated] = useState(false)
  const [showUpload, setShowUpload] = useState(false)
  
  // Initialize theme from localStorage or default to false
  const [isDarkMode, setIsDarkMode] = useState(false)

  // Handle hydration and theme initialization
  useEffect(() => {
    setIsHydrated(true)
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('darkMode')
      if (saved) {
        setIsDarkMode(JSON.parse(saved))
      }
    }
  }, [])

  // Save theme preference to localStorage whenever it changes
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('darkMode', JSON.stringify(isDarkMode))
      // Sync .dark class on <html> for shadcn CSS variables
      document.documentElement.classList.toggle('dark', isDarkMode)
    }
  }, [isDarkMode])

  // Get theme object
  const theme = getTheme(isDarkMode)

  const loadExistingData = useCallback(async () => {
    console.log('Loading existing data...')
    try {
      const dashboardResponse = await fetch(apiUrl('/api/analysis/dashboard-data'), {
        credentials: 'include',
      })
      
      console.log('Dashboard response status:', dashboardResponse.status)
      
      if (dashboardResponse.ok) {
        const dashboardData = await dashboardResponse.json()
        console.log('Dashboard data received:', dashboardData)
        
        const status = dashboardData.summary?.status
        if (status === 'processing' || status === 'pending') {
          // Analysis is running — show dashboard (empty panels) so user can navigate
          console.log('Analysis is', status, '— showing dashboard')
          if (dashboardData.summary.analysis_id) {
            setAnalysisId(dashboardData.summary.analysis_id)
          }
          setAnalysisData(dashboardData)
        } else if (dashboardData.summary && dashboardData.summary.total_variants > 0) {
          console.log('Found user data with', dashboardData.summary.total_variants, 'variants')
          
          if (dashboardData.summary.analysis_id) {
            setAnalysisId(dashboardData.summary.analysis_id)
            console.log('Set analysis ID:', dashboardData.summary.analysis_id)
          }
          
          setAnalysisData(dashboardData)
          console.log('Analysis data set successfully')
        } else {
          console.log('No variants found for user - may need to upload data')
          setAnalysisData(null)
        }
      } else {
        console.error('Failed to load dashboard data:', dashboardResponse.status)
        if (dashboardResponse.status === 401) {
          setToken(null)
          setUser(null)
        }
      }
    } catch (error) {
      console.error('Error loading existing data:', error)
    }
  }, [])

  const checkSession = useCallback(async (retries = 2) => {
    try {
      const response = await fetch(apiUrl('/auth/me'), {
        credentials: 'include',
      })
      
      if (response.ok) {
        const userData = await response.json()
        setToken('authenticated')
        setUser(userData)
        setLoading(false)
        // Load dashboard data in the background — don't block the spinner on it
        loadExistingData()
      } else {
        setToken(null)
        setLoading(false)
      }
    } catch (error) {
      if (retries > 0) {
        await new Promise(r => setTimeout(r, 2000))
        return checkSession(retries - 1)
      }
      console.error('Session check failed:', error)
      setToken(null)
      setLoading(false)
    }
  }, [loadExistingData])

  useEffect(() => {
    // On mount, check if we have a valid session cookie
    checkSession()
  }, [checkSession])

  const handleLogin = () => {
    setLoading(true)
    checkSession()
  }

  const handleAnalysisComplete = useCallback(async (data: DashboardData, newAnalysisId?: number) => {
    console.log('Analysis complete with data:', data, 'analysisId:', newAnalysisId)
    setShowUpload(false)
    if (newAnalysisId) {
      setAnalysisId(newAnalysisId)
      // Upload done — analysis runs in background. Load dashboard (will show as processing).
      await loadExistingData()
    } else {
      setAnalysisData(data)
    }
  }, [loadExistingData])

  const handleLogout = async () => {
    try {
      await fetch(apiUrl('/auth/logout'), { method: 'POST', credentials: 'include' })
    } catch { /* ignore */ }
    setToken(null)
    setUser(null)
    setAnalysisData(null)
    setAnalysisId(null)
  }

  if (loading || !isHydrated) {
    return (
      <div className={`min-h-screen flex items-center justify-center ${theme.background}`}>
        <div className={`border rounded-2xl p-8 text-center backdrop-blur-xl ${theme.glass} ${theme.glassBorder}`}>
          <div className={`inline-flex items-center justify-center w-16 h-16 ${theme.primary.bg} rounded-2xl mb-4`}>
            <Dna className="w-8 h-8 text-white animate-pulse" />
          </div>
          <div className={`w-8 h-8 border-2 rounded-full animate-spin mx-auto mb-4 ${
            isDarkMode 
              ? 'border-slate-600 border-t-teal-400' 
              : 'border-gray-300 border-t-teal-600'
          }`}></div>
          <p className={theme.text.secondary}>Loading your genetic profile...</p>
        </div>
      </div>
    )
  }

  if (!token) {
    return <AuthForm onLogin={handleLogin} isDarkMode={isDarkMode} isHydrated={isHydrated} />
  }

  console.log('Render - analysisData:', analysisData)

  return (
    <main className="min-h-screen bg-white">
      {showUpload ? (
        <div className={`min-h-screen ${theme.background}`}>
          {/* Background Elements */}
          <div className="absolute inset-0 overflow-hidden">
            <div className={`absolute top-0 left-1/4 w-96 h-96 ${theme.blobs.primary} rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-pulse`}></div>
            <div className={`absolute bottom-0 right-1/4 w-96 h-96 ${theme.blobs.secondary} rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-pulse animation-delay-1000`}></div>
          </div>

          {/* Header */}
          <div className={`relative z-10 backdrop-blur-sm border-b ${theme.glass} ${theme.glassBorder}`}>
            <div className="container mx-auto px-4 py-4 flex justify-between items-center">
              <div className="flex items-center space-x-3">
                <div className={`p-2 ${theme.primary.gradient} rounded-xl`}>
                  <Dna className="h-8 w-8 text-white" />
                </div>
                <h1 className={`text-2xl font-bold ${theme.text.primary}`}>
                  Genetic Health Analysis Toolkit
                </h1>
              </div>
              <div className="flex items-center space-x-4">
                {/* Theme Toggle */}
                <button
                  onClick={() => setIsDarkMode(!isDarkMode)}
                  className={`p-2 rounded-xl backdrop-blur-sm border transition-all duration-200 ${theme.glass} ${theme.glassBorder} ${theme.text.primary}`}
                  aria-label={isDarkMode ? 'Switch to light mode' : 'Switch to dark mode'}
                >
                  {isDarkMode ? (
                    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" clipRule="evenodd" />
                    </svg>
                  ) : (
                    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                      <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
                    </svg>
                  )}
                </button>
                <span className={`text-sm ${theme.text.secondary}`}>
                  Welcome, {user?.full_name || user?.username}
                </span>
                {showUpload && (
                  <button
                    onClick={() => setShowUpload(false)}
                    className={`px-4 py-2 backdrop-blur-sm border rounded-xl font-medium transition-all duration-200 flex items-center space-x-2 ${theme.glass} ${theme.glassBorder} ${theme.text.primary}`}
                  >
                    <span>← Back</span>
                  </button>
                )}
                <button
                  onClick={handleLogout}
                  className={`px-4 py-2 backdrop-blur-sm border rounded-xl font-medium transition-all duration-200 flex items-center space-x-2 ${theme.glass} ${theme.glassBorder} ${theme.text.primary}`}
                >
                  <LogOut className="h-4 w-4" />
                  <span>Logout</span>
                </button>
              </div>
            </div>
          </div>

          {/* Main Content */}
          <div className="relative z-10 container mx-auto px-4 py-8">
            
            <FileUpload onAnalysisComplete={handleAnalysisComplete} token={token || ''} isDarkMode={isHydrated ? isDarkMode : false} />
          </div>
        </div>
      ) : (
        <Dashboard 
          token={token || undefined}
          analysisData={analysisData}
          analysisId={analysisId}
          onRefresh={loadExistingData}
          onNavigateToUpload={() => { setAnalysisData(null); setAnalysisId(null); setShowUpload(true) }}
          isAdmin={user?.is_admin || false}
          userName={user?.full_name || user?.username}
          userAvatarUrl={user?.avatar_url}
        />
      )}
    </main>
  )
}
