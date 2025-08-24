'use client'

import { useState, useEffect } from 'react'
import { 
  Apple, Brain, Dumbbell, Heart, Zap, Palette, 
  ChevronDown, TrendingUp, AlertTriangle, CheckCircle, 
  Settings, Download, Trash2, Info, Shield, Search,
  Upload, Dna, Activity, BarChart3, Sparkles, Target,
  Award, Lightbulb, Star, Flame, Sun, Moon, Users,
  MessageSquare, Bell, Menu, X, LogOut, Plus, Home
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
import VariantSearch from './VariantSearch'
import { getThemeClass } from '../utils/theme'

interface ModernDashboardProps {
  token?: string
  analysisData?: any
}

export default function ModernDashboard({ token, analysisData }: ModernDashboardProps) {
  console.log('Dashboard component props:', { token: !!token, analysisData })
  
  const [data, setData] = useState<any>(analysisData || null)
  const [loading, setLoading] = useState(!analysisData)
  const [activeCategory, setActiveCategory] = useState('overview')
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [currentPage, setCurrentPage] = useState(1)
  const [variantsPerPage] = useState(10)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  
  // Initialize theme from localStorage or default to false
  const [isDarkMode, setIsDarkMode] = useState(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('darkMode')
      return saved ? JSON.parse(saved) : false
    }
    return false
  })

  // Save theme preference to localStorage whenever it changes
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('darkMode', JSON.stringify(isDarkMode))
    }
  }, [isDarkMode])

  // Load sample data on component mount only if no analysisData provided
  useEffect(() => {
    if (!analysisData) {
      const loadSampleData = () => {
        setLoading(true)
        
        // Simulate API call with sample data
        setTimeout(() => {
        setData({
          summary: {
            total_variants: 847,
            analysis_id: 'ANA-2025-001',
            processed_at: new Date().toISOString()
          },
          real_data: {
            variants: Array.from({ length: 847 }, (_, i) => ({
              rsid: i % 5 === 0 ? `rs${1000000 + i}` : '-',
              chromosome: Math.floor(Math.random() * 22) + 1,
              position: Math.floor(Math.random() * 1000000) + 10000000,
              ref_allele: ['A', 'T', 'G', 'C'][Math.floor(Math.random() * 4)],
              alt_allele: ['A', 'T', 'G', 'C'][Math.floor(Math.random() * 4)],
              genotype: ['AA', 'AT', 'TT', 'GG', 'CC', 'AG', 'AC', 'TG', 'TC', 'GC'][Math.floor(Math.random() * 10)],
              allele: ['A', 'T', 'G', 'C'][Math.floor(Math.random() * 4)]
            }))
          },
          health_risks: {
            overall_score: 78,
            risk_categories: {
              diabetes: { score: 65, risk_level: 'moderate' },
              cardiovascular: { score: 45, risk_level: 'low' },
              alzheimer: { score: 85, risk_level: 'high' }
            }
          },
          drug_interactions: {
            high_risk_genes: ['CYP2D6', 'CYP2C19', 'VKORC1']
          }
        })
        setLoading(false)
      }, 1500)
    }

    loadSampleData()
    }
  }, [analysisData])

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

  // Reset pagination when changing categories
  useEffect(() => {
    setCurrentPage(1)
  }, [activeCategory])

  // Reset function for clearing data
  const onReset = () => {
    setData(null)
    setActiveCategory('overview')
  }

  // Refresh function for reloading data
  const onRefresh = async () => {
    setLoading(true)
    // Add your data fetching logic here
    setTimeout(() => {
      setLoading(false)
    }, 1000)
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
        alert('All data deleted successfully')
      } else {
        alert('Failed to delete data')
      }
    } catch (error) {
      console.error('Error deleting data:', error)
      alert('Error deleting data')
    }
  }

  const handleRefreshData = async () => {
    try {
      if (onRefresh) {
        await onRefresh()
        alert('Data refreshed successfully')
      }
    } catch (error) {
      console.error('Error refreshing data:', error)
      alert('Error refreshing data')
    }
  }

  const stats = [
    {
      title: 'Variants Analyzed',
      value: data?.summary?.total_variants || data?.real_data?.variants?.length || 0,
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
      value: data?.insights?.length || data?.analysis_results?.insights?.length || 12,
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
        return <PersonalityPanel data={data} isDarkMode={isDarkMode} theme={theme} />
      case 'sports':
        return <SportsPanel data={data} isDarkMode={isDarkMode} theme={theme} />
      case 'health':
        return <HealthPanel data={data} isDarkMode={isDarkMode} theme={theme} />
      case 'drug-responses':
        return <DrugResponsesPanel data={data} isDarkMode={isDarkMode} />
      case 'ancestry':
        return <AncestryPanel data={data} isDarkMode={isDarkMode} />
      case 'carrier-status':
        return <CarrierStatusPanel data={data} isDarkMode={isDarkMode} />
      case 'wellness':
        return <WellnessPanel data={data} isDarkMode={isDarkMode} />
      case 'variant-search':
        return <VariantSearch token={token} isDarkMode={isDarkMode} theme={theme} />
      default:
        return (
          <div className="space-y-8">
            {/* Hero Stats Row - Redesigned Compact */}
            <div className="grid grid-cols-3 gap-4">
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
                    {data && typeof data === 'object' && data.real_data && data.real_data.variants && Array.isArray(data.real_data.variants) && data.real_data.variants.length > 0 ? (
                      <>
                        <div className={`${theme.glass} border ${theme.glassBorder} rounded-xl p-4 text-center`}>
                          <div className="text-3xl font-bold text-green-600 mb-1">
                            {data?.real_data?.variants?.length || 0}
                          </div>
                          <div className={`text-sm ${theme.text.secondary}`}>Variants Analyzed</div>
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

                {/* Quick Actions */}
                <div className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-6`}>
                  <h3 className={`text-lg font-bold ${theme.text.primary} mb-6`}>
                    Quick Actions
                  </h3>
                  
                  <div className="space-y-3">
                    {[
                      { 
                        label: 'View Health Risks', 
                        icon: Heart, 
                        color: getThemeClass('text-red-600', isDarkMode), 
                        bgColor: getThemeClass('bg-red-50', isDarkMode),
                        onClick: () => setActiveCategory('health')
                      },
                      { 
                        label: 'Drug Responses', 
                        icon: Shield, 
                        color: getThemeClass('text-purple-600', isDarkMode), 
                        bgColor: getThemeClass('bg-purple-50', isDarkMode),
                        onClick: () => setActiveCategory('health')
                      },
                      { 
                        label: 'Search Variants', 
                        icon: Search, 
                        color: getThemeClass('text-blue-600', isDarkMode), 
                        bgColor: getThemeClass('bg-blue-50', isDarkMode),
                        onClick: () => setActiveCategory('variant-search')
                      },
                      { 
                        label: 'Nutrition Insights', 
                        icon: Apple, 
                        color: getThemeClass('text-green-600', isDarkMode), 
                        bgColor: getThemeClass('bg-green-50', isDarkMode),
                        onClick: () => setActiveCategory('food-nutrition')
                      }
                    ].map((action, index) => {
                      const Icon = action.icon
                      return (
                        <button
                          key={index}
                          onClick={action.onClick}
                          className={`w-full flex items-center space-x-3 p-3 ${theme.glass} border ${theme.glassBorder} rounded-lg ${theme.glassHover} transition-all duration-300 group`}
                        >
                          <div className={`p-2 ${action.bgColor} rounded-lg group-hover:scale-110 transition-transform duration-300`}>
                            <Icon className={`h-4 w-4 ${action.color}`} />
                          </div>
                          <span className={`text-sm font-medium ${theme.text.primary}`}>
                            {action.label}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              </div>
            </div>

            {/* Sample Variants Table - Glassmorphism with Pagination */}
            {data.real_data?.variants && data.real_data.variants.length > 0 && (() => {
              const totalVariants = data.real_data.variants.length
              const totalPages = Math.ceil(totalVariants / variantsPerPage)
              const startIndex = (currentPage - 1) * variantsPerPage
              const endIndex = startIndex + variantsPerPage
              const currentVariants = data.real_data.variants.slice(startIndex, endIndex)

              return (
                <div className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-8`}>
                  <div className="flex items-center justify-between mb-6">
                    <h4 className={`font-bold ${theme.text.primary} text-xl`}>Sample Genetic Variants</h4>
                    <div className={`text-sm ${theme.text.muted}`}>
                      Showing {startIndex + 1}-{Math.min(endIndex, totalVariants)} of {totalVariants} variants
                    </div>
                  </div>
                  
                  <div className="overflow-x-auto">
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
                        {currentVariants.map((variant: any, index: number) => (
                          <tr key={index} className={`${theme.glassBorder} border-b transition-all duration-200 ${isDarkMode ? 'hover:bg-slate-700/30' : 'hover:bg-gray-200/30'}`}>
                            <td className={`py-4 px-4 font-semibold ${theme.text.primary}`}>{variant.chromosome}</td>
                            <td className={`py-4 px-4 ${theme.text.secondary}`}>{variant.position?.toLocaleString()}</td>
                            <td className={`py-4 px-4 ${theme.text.secondary}`}>{variant.rsid || '-'}</td>
                            <td className={`py-4 px-4 ${theme.text.secondary}`}>{variant.ref_allele}</td>
                            <td className={`py-4 px-4 ${theme.text.secondary}`}>{variant.alt_allele}</td>
                            <td className={`py-4 px-4 ${theme.text.secondary}`}>{variant.genotype || '-'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Pagination Controls */}
                  {totalPages > 1 && (
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
                {data?.summary?.total_variants || 0} variants analyzed
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

            <button
              onClick={handleRefreshData}
              className="bg-gradient-to-r from-green-500/80 to-emerald-500/80 hover:from-green-600/80 hover:to-emerald-600/80 backdrop-blur-xl text-white px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-300 flex items-center space-x-2 border border-white/20 shadow-lg"
            >
              <Activity className="h-4 w-4" />
              <span>Refresh Data</span>
            </button>
            
            <button
              onClick={onReset}
              className="bg-gradient-to-r from-blue-500/80 to-purple-500/80 hover:from-blue-600/80 hover:to-purple-600/80 backdrop-blur-xl text-white px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-300 flex items-center space-x-2 border border-white/20 shadow-lg"
            >
              <Plus className="h-4 w-4" />
              <span>Upload New Data</span>
            </button>

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
                    <Icon className={`h-5 w-5 ${isActive ? 'text-white' : getThemeClass('text-gray-500', isDarkMode)}`} />
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
            {renderCategoryContent()}
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
    </div>
  )
}