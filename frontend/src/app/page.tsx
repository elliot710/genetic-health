'use client'

import { useState, useEffect } from 'react'
import { Dna, LogOut, Upload } from 'lucide-react'
import Dashboard from '@/components/ModernDashboard'
import FileUpload from '@/components/ModernFileUpload'
import AuthForm from '@/components/AuthForm'

export default function Home() {
  const [analysisData, setAnalysisData] = useState<any>(null)
  const [token, setToken] = useState<string | null>(null)
  const [user, setUser] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Check for stored token on component mount
    const storedToken = localStorage.getItem('token')
    if (storedToken) {
      verifyToken(storedToken)
    } else {
      setLoading(false)
    }
  }, [])

  const verifyToken = async (tokenToVerify: string) => {
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
  }

  const loadExistingData = async (authToken: string) => {
    try {
      // Get user's data summary to see if they have uploaded files
      const summaryResponse = await fetch('http://localhost:8000/upload/data-summary', {
        headers: {
          'Authorization': `Bearer ${authToken}`
        }
      })
      
      if (summaryResponse.ok) {
        const summary = await summaryResponse.json()
        
        // If user has uploaded files, load the most recent analysis
        if (summary.analyses && summary.analyses.length > 0) {
          // Sort by upload date to get the most recent
          const sortedAnalyses = summary.analyses.sort((a: any, b: any) => 
            new Date(b.upload_date).getTime() - new Date(a.upload_date).getTime()
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
            
            console.log('Analysis result:', {
              variants: analysisResult.sample_variants?.length,
              healthRisks: analysisResult.health_risks?.length,
              filename: mostRecentAnalysis.filename
            })
            
            // Transform the data for the dashboard
            const totalVariants = analysisResult.sample_variants?.length || summary.data_summary?.total_variants || 0
            const healthRisks = analysisResult.health_risks || []
            const highRiskVariants = healthRisks.filter((risk: any) => risk.risk_level === 'high').length
            const moderateRiskVariants = healthRisks.filter((risk: any) => risk.risk_level === 'moderate').length
            
            const dashboardData = {
              summary: {
                total_variants: totalVariants,
                data_sources: [mostRecentAnalysis.filename],
                analysis_id: mostRecentAnalysis.id,
                upload_info: mostRecentAnalysis,
                health_risks_identified: healthRisks.length
              },
              health_risks: {
                overall_score: healthRisks.length > 0 ? Math.max(100 - (highRiskVariants * 20) - (moderateRiskVariants * 10), 60) : 85,
                risk_categories: healthRisks.reduce((acc: any, risk: any) => {
                  acc[risk.condition] = {
                    score: risk.risk_level === 'high' ? 90 : risk.risk_level === 'moderate' ? 60 : 30,
                    variants: risk.associated_variants || [],
                    risk_score: risk.risk_score,
                    recommendations: risk.recommendations || []
                  }
                  return acc
                }, {})
              },
              drug_interactions: {
                high_risk_genes: analysisResult.drug_responses?.filter((dr: any) => dr.response_type === 'poor_metabolizer').map((dr: any) => dr.gene) || [],
                moderate_risk_genes: analysisResult.drug_responses?.filter((dr: any) => dr.response_type === 'intermediate_metabolizer').map((dr: any) => dr.gene) || [],
                affected_drug_classes: [...new Set(analysisResult.drug_responses?.map((dr: any) => dr.drug) || [])]
              },
              recommendations: [
                `Analysis of ${mostRecentAnalysis.filename} completed`,
                `${totalVariants} genetic variants analyzed`,
                `${healthRisks.length} health associations identified`,
                ...(healthRisks.flatMap((risk: any) => risk.recommendations || []).slice(0, 3)),
                "Data persisted and available for review"
              ],
              real_data: {
                variants: analysisResult.sample_variants || [],
                analysis: analysisResult.analysis,
                upload_result: {
                  ...mostRecentAnalysis,
                  genetic_variants_found: totalVariants,
                  health_risks_found: healthRisks.length
                }
              }
            }
            
            setAnalysisData(dashboardData)
          }
        }
      }
    } catch (error) {
      console.error('Failed to load existing data:', error)
      // Don't throw error, just continue without existing data
    }
  }

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

  if (loading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="bg-gray-50 border border-gray-200 rounded-2xl p-8 text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-600 rounded-2xl mb-4">
            <Dna className="w-8 h-8 text-white animate-pulse" />
          </div>
          <div className="w-8 h-8 border-2 border-gray-300 border-t-blue-600 rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-600">Loading your genetic profile...</p>
        </div>
      </div>
    )
  }

  if (!token) {
    return <AuthForm onLogin={handleLogin} />
  }

  return (
    <main className="min-h-screen bg-white">
      {!analysisData ? (
        <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
          {/* Background Elements */}
          <div className="absolute inset-0 overflow-hidden">
            <div className="absolute top-0 left-1/4 w-96 h-96 bg-purple-500 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-pulse"></div>
            <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-blue-500 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-pulse animation-delay-1000"></div>
          </div>

          {/* Header */}
          <div className="relative z-10 backdrop-blur-sm bg-white/5 border-b border-white/10">
            <div className="container mx-auto px-4 py-4 flex justify-between items-center">
              <div className="flex items-center space-x-3">
                <div className="p-2 bg-gradient-to-br from-purple-400 to-pink-400 rounded-xl">
                  <Dna className="h-8 w-8 text-white" />
                </div>
                <h1 className="text-2xl font-bold text-white">
                  Genetic Health Analysis Toolkit
                </h1>
              </div>
              <div className="flex items-center space-x-4">
                <span className="text-white/80 text-sm">
                  Welcome, {user?.full_name || user?.username}
                </span>
                <button
                  onClick={handleLogout}
                  className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-xl font-medium backdrop-blur-sm border border-white/20 transition-all duration-200 flex items-center space-x-2"
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
              <div className="backdrop-blur-xl bg-white/10 border border-white/20 rounded-3xl p-8 max-w-2xl mx-auto">
                <div className="mb-6">
                  <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-br from-purple-400 to-pink-400 rounded-2xl mb-4">
                    <Upload className="w-8 h-8 text-white" />
                  </div>
                  <h2 className="text-2xl font-bold text-white mb-2">
                    Upload Your Genetic Data
                  </h2>
                  <p className="text-white/70">
                    Discover health insights and personalized recommendations from your genetic information
                  </p>
                </div>
              </div>
            </div>
            
            <FileUpload onAnalysisComplete={setAnalysisData} token={token || ''} />
          </div>
        </div>
      ) : (
        <Dashboard 
          data={analysisData} 
          onReset={() => setAnalysisData(null)} 
          token={token || undefined}
          onRefresh={() => token && loadExistingData(token)}
        />
      )}
    </main>
  )
}
