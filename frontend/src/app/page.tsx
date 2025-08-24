'use client'

import { useState, useEffect, useCallback } from 'react'
import { Dna, LogOut, Upload } from 'lucide-react'
import Dashboard from '@/components/ModernDashboard'
import FileUpload from '@/components/ModernFileUpload'
import AuthForm from '@/components/AuthForm'
import { getTheme } from '@/utils/theme'

interface AnalysisData {
  summary?: {
    total_variants?: number
    data_sources?: string[]
    analysis_id?: string
    upload_info?: Record<string, unknown>
  }
  health_risks?: Record<string, unknown>
  drug_interactions?: Record<string, unknown>
  recommendations?: string[]
  real_data?: Record<string, unknown>
}

interface User {
  id?: string
  email?: string
  username?: string
  full_name?: string
}

export default function Home() {
  const [analysisData, setAnalysisData] = useState<AnalysisData | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [isHydrated, setIsHydrated] = useState(false)
  
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
    }
  }, [isDarkMode])

  // Get theme object
  const theme = getTheme(isDarkMode)

  const loadExistingData = useCallback(async (authToken: string) => {
    console.log('Loading existing data...')
    try {
      // Get user's data summary to see if they have uploaded files
      const summaryResponse = await fetch('http://localhost:8000/upload/data-summary', {
        headers: {
          'Authorization': `Bearer ${authToken}`
        }
      })
      
      console.log('Summary response status:', summaryResponse.status)
      
      if (summaryResponse.ok) {
        const summary = await summaryResponse.json()
        console.log('Summary data:', summary)
        
        // If user has uploaded files, load the most recent analysis
        if (summary.analyses && summary.analyses.length > 0) {
          console.log('Found analyses:', summary.analyses.length)
          // Sort by upload date to get the most recent
          const sortedAnalyses = summary.analyses.sort((a: Record<string, unknown>, b: Record<string, unknown>) => 
            new Date(b.upload_date as string).getTime() - new Date(a.upload_date as string).getTime()
          )
          const mostRecentAnalysis = sortedAnalyses[0]
          
          console.log('Loading analysis:', mostRecentAnalysis.id, mostRecentAnalysis.filename)
          
          // Fetch detailed analysis results
          const analysisResponse = await fetch(
            `http://localhost:8000/upload/analysis/${mostRecentAnalysis.id}`,
            {
              headers: {
                'Authorization': `Bearer ${authToken}`
              }
            }
          )
          
          if (analysisResponse.ok) {
            const analysisResult = await analysisResponse.json()
            
            // Transform to dashboard format
            const totalVariants = analysisResult.sample_variants?.length || 0
            const healthRisks = analysisResult.health_risks || []
            const highRiskVariants = healthRisks.filter((risk: Record<string, unknown>) => risk.risk_level === 'high').length
            const moderateRiskVariants = healthRisks.filter((risk: Record<string, unknown>) => risk.risk_level === 'moderate').length
            
            const dashboardData: AnalysisData = {
              summary: {
                total_variants: totalVariants,
                data_sources: [mostRecentAnalysis.filename as string],
                analysis_id: mostRecentAnalysis.id as string,
                upload_info: mostRecentAnalysis
              },
              health_risks: {
                overall_score: healthRisks.length > 0 ? Math.max(100 - (highRiskVariants * 20) - (moderateRiskVariants * 10), 60) : 85,
                risk_categories: healthRisks.reduce((acc: Record<string, unknown>, risk: Record<string, unknown>) => {
                  acc[risk.condition as string] = {
                    score: risk.risk_level === 'high' ? 90 : risk.risk_level === 'moderate' ? 60 : 30,
                    variants: risk.associated_variants || []
                  }
                  return acc
                }, {})
              },
              drug_interactions: {
                high_risk_genes: analysisResult.drug_responses?.filter((dr: Record<string, unknown>) => dr.response_type === 'poor_metabolizer').map((dr: Record<string, unknown>) => dr.gene) || [],
                moderate_risk_genes: analysisResult.drug_responses?.filter((dr: Record<string, unknown>) => dr.response_type === 'intermediate_metabolizer').map((dr: Record<string, unknown>) => dr.gene) || []
              },
              recommendations: [
                `Analysis of ${mostRecentAnalysis.filename} completed`,
                `${totalVariants} genetic variants analyzed`,
                `${healthRisks.length} health associations identified`
              ],
              real_data: {
                variants: analysisResult.sample_variants || [],
                analysis: analysisResult.analysis,
                upload_result: mostRecentAnalysis
              }
            }
            
            console.log('Setting analysis data:', dashboardData)
            setAnalysisData(dashboardData)
            console.log('Analysis data set successfully')
          } else {
            console.error('Failed to load analysis data:', analysisResponse.status)
          }
        } else {
          console.log('No analyses found for user')
        }
      } else {
        console.error('Failed to load data summary:', summaryResponse.status)
      }
    } catch (error) {
      console.error('Error loading existing data:', error)
    }
  }, [])

  const verifyToken = useCallback(async (tokenToVerify: string) => {
    try {
      const response = await fetch('http://localhost:8000/auth/me', {
        headers: {
          'Authorization': `Bearer ${tokenToVerify}`
        }
      })
      
      if (response.ok) {
        const userData = await response.json()
        setToken(tokenToVerify)
        setUser(userData)
        
        // Check if user has existing data and load it
        await loadExistingData(tokenToVerify)
      } else {
        localStorage.removeItem('token')
      }
    } catch (error) {
      console.error('Token verification failed:', error)
      localStorage.removeItem('token')
    } finally {
      setLoading(false)
    }
  }, [loadExistingData])

  useEffect(() => {
    // Check for stored token on component mount
    const storedToken = localStorage.getItem('token')
    if (storedToken) {
      verifyToken(storedToken)
    } else {
      setLoading(false)
    }
  }, [verifyToken])

  const handleLogin = (newToken: string) => {
    setToken(newToken)
    verifyToken(newToken)
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    setToken(null)
    setUser(null)
    setAnalysisData(null)
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
  console.log('Render - will show upload screen?', !analysisData)

  return (
    <main className="min-h-screen bg-white">
      {!analysisData ? (
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
            <div className="text-center mb-8">
              <div className={`backdrop-blur-xl border rounded-3xl p-8 max-w-2xl mx-auto ${theme.glass} ${theme.glassBorder}`}>
                <div className="mb-6">
                  <div className={`inline-flex items-center justify-center w-16 h-16 ${theme.primary.gradient} rounded-2xl mb-4`}>
                    <Upload className="w-8 h-8 text-white" />
                  </div>
                  <h2 className={`text-2xl font-bold mb-2 ${theme.text.primary}`}>
                    Upload Your Genetic Data
                  </h2>
                  <p className={theme.text.secondary}>
                    Discover health insights and personalized recommendations from your genetic information
                  </p>
                </div>
              </div>
            </div>
            
            <FileUpload onAnalysisComplete={setAnalysisData} token={token || ''} isDarkMode={isHydrated ? isDarkMode : false} />
          </div>
        </div>
      ) : (
        <Dashboard 
          token={token || undefined}
          analysisData={analysisData}
        />
      )}
    </main>
  )
}
