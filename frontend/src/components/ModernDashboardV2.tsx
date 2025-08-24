'use client'

import { useState } from 'react'
import { 
  Apple, Brain, Dumbbell, Heart, Zap, Palette, 
  ChevronDown, TrendingUp, AlertTriangle, CheckCircle, 
  Settings, Download, Trash2, Info, Shield, Search,
  Upload, Dna, Activity, BarChart3, Sparkles, Target,
  Award, Lightbulb, Star, Flame, Sun, Moon, Users,
  MessageSquare, Bell, Menu, X, LogOut, Plus
} from 'lucide-react'

// Import category components
import FoodNutritionPanel from './categories/FoodNutritionPanel'
import IntelligencePanel from './categories/IntelligencePanel'
import PhysicalTraitsPanel from './categories/PhysicalTraitsPanel'
import PersonalityPanel from './categories/PersonalityPanel'
import SportsPanel from './categories/SportsPanel'
import HealthPanel from './categories/HealthPanel'
import VariantSearch from './VariantSearch'

interface ModernDashboardProps {
  data: any
  onReset: () => void
  token?: string
  onRefresh?: () => void
}

export default function ModernDashboardV2({ data, onReset, token, onRefresh }: ModernDashboardProps) {
  const [activeCategory, setActiveCategory] = useState('overview')
  const [showDataManagement, setShowDataManagement] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const categories = [
    {
      id: 'overview',
      title: 'Overview',
      description: 'Complete analysis summary',
      icon: Sparkles,
      color: 'text-blue-600'
    },
    {
      id: 'food-nutrition',
      title: 'Food & Nutrition',
      description: 'Dietary responses',
      icon: Apple,
      color: 'text-green-600'
    },
    {
      id: 'intelligence',
      title: 'Intelligence',
      description: 'Cognitive traits',
      icon: Brain,
      color: 'text-purple-600'
    },
    {
      id: 'physical-traits',
      title: 'Physical Traits',
      description: 'Appearance traits',
      icon: Target,
      color: 'text-orange-600'
    },
    {
      id: 'personality',
      title: 'Personality',
      description: 'Behavioral traits',
      icon: Palette,
      color: 'text-pink-600'
    },
    {
      id: 'sports',
      title: 'Sports & Fitness',
      description: 'Athletic performance',
      icon: Dumbbell,
      color: 'text-red-600'
    },
    {
      id: 'health',
      title: 'Health & Wellness',
      description: 'Disease risks',
      icon: Heart,
      color: 'text-red-500'
    },
    {
      id: 'variant-search',
      title: 'Variant Search',
      description: 'Look up variants',
      icon: Search,
      color: 'text-indigo-600'
    }
  ]

  const handleDeleteData = async () => {
    if (confirm('Are you sure you want to delete all your genetic data? This action cannot be undone.')) {
      try {
        const response = await fetch('http://localhost:8000/upload/data', {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${token}`
          }
        })

        if (response.ok) {
          alert('All data deleted successfully')
          onReset()
        } else {
          alert('Failed to delete data')
        }
      } catch (error) {
        console.error('Error deleting data:', error)
        alert('Error deleting data')
      }
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
      value: data.summary?.total_variants || data.real_data?.variants?.length || 0,
      icon: BarChart3,
      color: 'text-blue-600',
      bgColor: 'bg-blue-50'
    },
    {
      title: 'Health Score',
      value: `${Math.round(data.health_risks?.overall_score || 85)}%`,
      icon: Activity,
      color: 'text-green-600',
      bgColor: 'bg-green-50'
    },
    {
      title: 'Risk Factors',
      value: Object.keys(data.health_risks?.risk_categories || {}).length || 0,
      icon: Award,
      color: 'text-orange-600',
      bgColor: 'bg-orange-50'
    }
  ]

  const generateHealthInsights = () => {
    const insights = []
    
    if (data.health_risks?.risk_categories && Object.keys(data.health_risks.risk_categories).length > 0) {
      const highRisk = Object.values(data.health_risks.risk_categories).filter((risk: any) => risk.score > 80).length
      const moderateRisk = Object.values(data.health_risks.risk_categories).filter((risk: any) => risk.score > 60 && risk.score <= 80).length
      
      if (highRisk > 0) {
        insights.push({
          category: 'High Risk Variants',
          insight: `${highRisk} high-risk genetic variants identified requiring attention`,
          icon: AlertTriangle,
          color: 'text-red-600',
          bgColor: 'bg-red-50'
        })
      }
      
      if (moderateRisk > 0) {
        insights.push({
          category: 'Moderate Risk',
          insight: `${moderateRisk} variants show moderate risk associations`,
          icon: Info,
          color: 'text-amber-600',
          bgColor: 'bg-amber-50'
        })
      }
    }
    
    if (data.drug_interactions?.high_risk_genes?.length > 0) {
      insights.push({
        category: 'Drug Metabolism',
        insight: `${data.drug_interactions.high_risk_genes.length} genes may affect drug responses`,
        icon: Shield,
        color: 'text-purple-600',
        bgColor: 'bg-purple-50'
      })
    }
    
    if (data.real_data?.variants?.length > 0) {
      const withRsId = data.real_data.variants.filter((v: any) => v.rsid && v.rsid !== '-' && v.rsid !== 'nan').length
      const coverage = Math.round((withRsId / data.real_data.variants.length) * 100)
      
      insights.push({
        category: 'Analysis Coverage',
        insight: `${coverage}% of variants have reference IDs for clinical analysis`,
        icon: Target,
        color: 'text-green-600',
        bgColor: 'bg-green-50'
      })
    }
    
    return insights
  }

  const healthInsights = generateHealthInsights()

  const quickInsights = healthInsights.length > 0 ? healthInsights : [
    {
      category: 'Genetic Analysis',
      insight: data.real_data?.variants?.length > 0 
        ? `${data.real_data.variants.length} variants uploaded and ready for analysis`
        : 'Upload genetic data to begin analysis',
      icon: Dna,
      color: 'text-blue-600',
      bgColor: 'bg-blue-50'
    },
    {
      category: 'Processing Status',
      insight: 'Background analysis in progress - check back for updated results',
      icon: Activity,
      color: 'text-amber-600',
      bgColor: 'bg-amber-50'
    },
    {
      category: 'Data Quality',
      insight: data.summary?.analysis_id 
        ? `Analysis ID: ${data.summary.analysis_id} - Data successfully stored`
        : 'Ready to process your genetic information',
      icon: CheckCircle,
      color: 'text-green-600',
      bgColor: 'bg-green-50'
    }
  ]

  const renderCategoryContent = () => {
    switch (activeCategory) {
      case 'food-nutrition':
        return <FoodNutritionPanel data={data} />
      case 'intelligence':
        return <IntelligencePanel data={data} />
      case 'physical-traits':
        return <PhysicalTraitsPanel data={data} />
      case 'personality':
        return <PersonalityPanel data={data} />
      case 'sports':
        return <SportsPanel data={data} />
      case 'health':
        return <HealthPanel data={data} />
      case 'variant-search':
        return <VariantSearch token={token} />
      default:
        return (
          <div className="h-full space-y-6">
            {/* Top Stats Row - Full Width Clean */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {stats.map((stat, index) => {
                const Icon = stat.icon
                return (
                  <div 
                    key={index} 
                    className={`relative overflow-hidden bg-gradient-to-br ${stat.gradient} rounded-lg p-6 shadow-lg hover:shadow-xl transition-all duration-300 cursor-pointer`}
                  >
                    <div className="flex items-center justify-between mb-4">
                      <div className="p-3 bg-white/20 rounded-lg">
                        <Icon className="h-6 w-6 text-white" />
                      </div>
                      <div className="text-white/80 text-xs font-bold tracking-wider uppercase">
                        {stat.title}
                      </div>
                    </div>
                    <div className="text-3xl font-bold text-white mb-2">
                      {stat.value}
                    </div>
                    <div className="text-white/90 text-sm font-medium">
                      {stat.description}
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Main Content Grid - Full Width */}
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
              {/* Real Data Section - Full Width when present */}
              {data.real_data?.variants && data.real_data.variants.length > 0 && (
                <div className={`lg:col-span-4 ${currentTheme.card} rounded-lg p-6`}>
                  <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center space-x-3">
                      <div className="p-3 bg-gradient-to-r from-cyan-500 to-teal-500 rounded-lg">
                        <Dna className="h-6 w-6 text-white" />
                      </div>
                      <h3 className={`text-2xl font-bold ${currentTheme.text}`}>
                        Your Uploaded Data
                      </h3>
                    </div>
                    <div className="px-4 py-2 bg-emerald-100 text-emerald-800 text-sm font-bold rounded-full">
                      Successfully Processed
                    </div>
                  </div>
                  
                  {/* Upload Summary */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                    <div className={`${currentTheme.card} rounded-lg p-4 text-center`}>
                      <div className={`text-lg font-bold ${currentTheme.text}`}>
                        {data.real_data.upload_result?.filename || 'Unknown'}
                      </div>
                      <div className={`text-xs ${currentTheme.textMuted} mt-1`}>Filename</div>
                    </div>
                    <div className={`${currentTheme.card} rounded-lg p-4 text-center`}>
                      <div className="text-lg font-bold text-cyan-600">
                        {data.real_data.variants.length}
                      </div>
                      <div className={`text-xs ${currentTheme.textMuted} mt-1`}>Variants Found</div>
                    </div>
                    <div className={`${currentTheme.card} rounded-lg p-4 text-center`}>
                      <div className="text-lg font-bold text-teal-600">
                        {data.summary?.analysis_id || 'N/A'}
                      </div>
                      <div className={`text-xs ${currentTheme.textMuted} mt-1`}>Analysis ID</div>
                    </div>
                    <div className={`${currentTheme.card} rounded-lg p-4 text-center`}>
                      <div className="text-lg font-bold text-blue-600">
                        {data.real_data.upload_result?.file_size ? `${Math.round(data.real_data.upload_result.file_size / 1024)}KB` : 'N/A'}
                      </div>
                      <div className={`text-xs ${currentTheme.textMuted} mt-1`}>File Size</div>
                    </div>
                  </div>

                  {/* Sample Variants Table */}
                  <div className={`${currentTheme.card} rounded-lg p-4`}>
                    <h4 className={`font-bold ${currentTheme.text} mb-3 text-lg`}>Sample Genetic Variants</h4>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className={`border-b ${isDarkMode ? 'border-gray-700' : 'border-gray-200'}`}>
                            <th className={`text-left py-3 px-4 ${currentTheme.textMuted} font-bold`}>Chromosome</th>
                            <th className={`text-left py-3 px-4 ${currentTheme.textMuted} font-bold`}>Position</th>
                            <th className={`text-left py-3 px-4 ${currentTheme.textMuted} font-bold`}>RS ID</th>
                            <th className={`text-left py-3 px-4 ${currentTheme.textMuted} font-bold`}>Ref</th>
                            <th className={`text-left py-3 px-4 ${currentTheme.textMuted} font-bold`}>Alt</th>
                            <th className={`text-left py-3 px-4 ${currentTheme.textMuted} font-bold`}>Genotype</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.real_data.variants.slice(0, 8).map((variant: any, index: number) => (
                            <tr key={index} className={`border-b ${isDarkMode ? 'border-gray-800 hover:bg-gray-800/50' : 'border-gray-100 hover:bg-gray-50'} transition-colors duration-200`}>
                              <td className={`py-3 px-4 font-bold ${currentTheme.text}`}>{variant.chromosome}</td>
                              <td className={`py-3 px-4 ${currentTheme.textSecondary}`}>{variant.position?.toLocaleString()}</td>
                              <td className={`py-3 px-4 ${currentTheme.textSecondary}`}>{variant.rsid || '-'}</td>
                              <td className={`py-3 px-4 ${currentTheme.textSecondary}`}>{variant.ref_allele}</td>
                              <td className={`py-3 px-4 ${currentTheme.textSecondary}`}>{variant.alt_allele}</td>
                              <td className={`py-3 px-4 ${currentTheme.textSecondary}`}>{variant.genotype || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {data.real_data.variants.length > 8 && (
                        <div className={`text-center mt-3 ${currentTheme.textMuted} text-xs`}>
                          Showing 8 of {data.real_data.variants.length} variants
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Quick Insights - Takes 3 columns */}
              <div className={`lg:col-span-3 ${currentTheme.card} rounded-lg p-6`}>
                <div className="flex items-center space-x-3 mb-6">
                  <div className="p-3 bg-gradient-to-r from-cyan-500 to-teal-500 rounded-lg">
                    <Sparkles className="h-6 w-6 text-white" />
                  </div>
                  <h3 className={`text-2xl font-bold ${currentTheme.text}`}>
                    Quick Insights
                  </h3>
                </div>
                
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {quickInsights.map((insight, index) => {
                    const Icon = insight.icon
                    return (
                      <div 
                        key={index}
                        className={`${currentTheme.cardHover} rounded-lg p-4 transition-all duration-200 hover:shadow-md`}
                      >
                        <div className="flex items-center justify-between mb-3">
                          <div className={`p-2 bg-gradient-to-r ${insight.color} rounded-lg`}>
                            <Icon className="h-5 w-5 text-white" />
                          </div>
                          <div className="flex items-center space-x-2">
                            <div className={`text-xl font-bold ${currentTheme.text}`}>
                              {insight.score}%
                            </div>
                            <div className={`text-xs ${currentTheme.textMuted} font-medium`}>
                              match
                            </div>
                          </div>
                        </div>
                        <h4 className={`font-bold ${currentTheme.text} mb-2`}>
                          {insight.category}
                        </h4>
                        <p className={`${currentTheme.textSecondary} text-sm leading-relaxed mb-3`}>
                          {insight.insight}
                        </p>
                        {/* Progress Bar */}
                        <div className={`w-full ${isDarkMode ? 'bg-gray-700' : 'bg-gray-200'} rounded-full h-2`}>
                          <div 
                            className={`h-2 bg-gradient-to-r ${insight.color} rounded-full transition-all duration-1000 ease-out`}
                            style={{ width: `${insight.score}%` }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Recommendations - Takes 1 column */}
              <div className={`lg:col-span-1 ${currentTheme.card} rounded-lg p-6`}>
                <div className="flex items-center space-x-3 mb-6">
                  <div className="p-3 bg-gradient-to-r from-teal-500 to-blue-500 rounded-lg">
                    <Target className="h-6 w-6 text-white" />
                  </div>
                  <h3 className={`text-xl font-bold ${currentTheme.text}`}>
                    Recommendations
                  </h3>
                </div>
                
                <div className="space-y-4">
                  {/* Show real recommendations if available */}
                  {data.recommendations && data.recommendations.length > 0 ? (
                    data.recommendations.map((rec: string, index: number) => (
                      <div key={index} className={`flex items-start p-3 ${currentTheme.cardHover} rounded-lg`}>
                        <CheckCircle className="h-5 w-5 mr-3 mt-0.5 text-cyan-500 flex-shrink-0" />
                        <span className={`${currentTheme.textSecondary} text-sm leading-relaxed`}>{rec}</span>
                      </div>
                    ))
                  ) : (
                    [
                      { icon: CheckCircle, text: "Consult with a healthcare provider for personalized recommendations", color: "text-emerald-500" },
                      { icon: CheckCircle, text: "Consider genetic counseling if you have family history concerns", color: "text-cyan-500" },
                      { icon: CheckCircle, text: "Maintain a healthy lifestyle with regular exercise and balanced nutrition", color: "text-teal-500" },
                      { icon: Info, text: "Stay updated with the latest research in personalized medicine", color: "text-blue-500" },
                      { icon: Shield, text: "Keep your genetic data secure and private", color: "text-cyan-500" }
                    ].map((rec, index) => {
                      const Icon = rec.icon
                      return (
                        <div key={index} className={`flex items-start p-3 ${currentTheme.cardHover} rounded-lg transition-all duration-200`}>
                          <Icon className={`h-5 w-5 mr-3 mt-0.5 ${rec.color} flex-shrink-0`} />
                          <span className={`${currentTheme.textSecondary} text-sm leading-relaxed`}>{rec.text}</span>
                        </div>
                      )
                    })
                  )}
                  
                  {/* Analysis Summary */}
                  <div className={`mt-6 p-4 ${currentTheme.card} rounded-lg`}>
                    <h4 className={`font-bold ${currentTheme.text} mb-3`}>Analysis Summary</h4>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div className="text-center">
                        <div className="text-xl font-bold text-cyan-500">{dataSources}</div>
                        <div className={`${currentTheme.textMuted}`}>Data Sources</div>
                      </div>
                      <div className="text-center">
                        <div className="text-xl font-bold text-teal-500">{Math.round(riskScore)}%</div>
                        <div className={`${currentTheme.textMuted}`}>Confidence</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )
    }
  }

  return (
    <div className={`min-h-screen ${currentTheme.background} relative`}>
      <div className="h-screen flex flex-col">
        {/* Clean Header */}
        <div className={`flex-shrink-0 ${currentTheme.header}`}>
          <div className="w-full px-8 py-6">
            <div className="flex justify-between items-center">
              <div className="flex items-center space-x-4">
                <div className="p-3 bg-gradient-to-r from-cyan-500 to-teal-500 rounded-xl">
                  <Dna className="h-8 w-8 text-white" />
                </div>
                <div>
                  <h1 className={`text-3xl font-bold ${currentTheme.text}`}>
                    Your Genetic Profile
                  </h1>
                  <p className={`${currentTheme.textMuted} font-medium`}>
                    {data.summary?.total_variants || 0} variants • AI-powered insights
                  </p>
                </div>
              </div>
              <div className="flex items-center space-x-4">
                {/* Theme Toggle Button */}
                <button
                  onClick={() => setIsDarkMode(!isDarkMode)}
                  className={`${currentTheme.card} hover:${currentTheme.cardHover} px-4 py-2 rounded-lg font-medium transition-all duration-200 flex items-center space-x-2`}
                >
                  {isDarkMode ? (
                    <>
                      <Sun className={`h-5 w-5 ${currentTheme.text}`} />
                      <span className={`${currentTheme.text}`}>Light Mode</span>
                    </>
                  ) : (
                    <>
                      <Moon className={`h-5 w-5 ${currentTheme.text}`} />
                      <span className={`${currentTheme.text}`}>Dark Mode</span>
                    </>
                  )}
                </button>
                {onRefresh && (
                  <button
                    onClick={handleRefreshData}
                    className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg font-medium transition-colors duration-200 flex items-center space-x-2"
                  >
                    <Activity className="h-5 w-5" />
                    <span>Refresh Data</span>
                  </button>
                )}
                <button
                  onClick={() => setShowDataManagement(!showDataManagement)}
                  className={`${currentTheme.card} hover:${currentTheme.cardHover} ${currentTheme.text} px-4 py-2 rounded-lg font-medium transition-all duration-200 flex items-center space-x-2`}
                >
                  <Settings className="h-5 w-5" />
                  <span>Manage Data</span>
                </button>
                <button
                  onClick={onReset}
                  className="bg-cyan-600 hover:bg-cyan-700 text-white px-4 py-2 rounded-lg font-medium transition-colors duration-200 flex items-center space-x-2"
                >
                  <Upload className="h-5 w-5" />
                  <span>Upload New Data</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Data Management Panel */}
        {showDataManagement && (
          <div className={`flex-shrink-0 ${currentTheme.header}`}>
            <div className="w-full px-8 py-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-4">
                  <div className="p-3 bg-gradient-to-r from-amber-500 to-orange-500 rounded-xl">
                    <Settings className="h-6 w-6 text-white" />
                  </div>
                  <div>
                    <h3 className={`text-xl font-bold ${currentTheme.text}`}>Data Management</h3>
                    <p className={`${currentTheme.textMuted} text-sm`}>Download or delete your genetic data</p>
                  </div>
                </div>
                <div className="flex items-center space-x-4">
                  <button className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium transition-colors duration-200 flex items-center space-x-2">
                    <Download className="h-5 w-5" />
                    <span>Download</span>
                  </button>
                  <button
                    onClick={handleDeleteData}
                    className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg font-medium transition-colors duration-200 flex items-center space-x-2"
                  >
                    <Trash2 className="h-5 w-5" />
                    <span>Delete</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Main Content Area - Full Width */}
        <div className="flex-1 flex overflow-hidden">
          {/* Compact Sidebar */}
          <div className={`w-64 flex-shrink-0 ${currentTheme.sidebar} overflow-y-auto`}>
            <div className="p-6">
              <div className="flex items-center space-x-3 mb-6">
                <div className="p-2 bg-gradient-to-r from-cyan-500 to-teal-500 rounded-lg">
                  <Sparkles className="h-5 w-5 text-white" />
                </div>
                <h2 className={`text-lg font-bold ${currentTheme.text}`}>
                  Categories
                </h2>
              </div>
              
              <div className="space-y-2">
                {categories.map((category) => {
                  const Icon = category.icon
                  const isActive = activeCategory === category.id
                  return (
                    <button
                      key={category.id}
                      onClick={() => setActiveCategory(category.id)}
                      className={`w-full rounded-lg transition-all duration-200 ${
                        isActive 
                          ? `bg-gradient-to-r ${category.gradient} text-white shadow-lg` 
                          : `${currentTheme.cardHover} ${currentTheme.text} hover:shadow-md`
                      }`}
                    >
                      <div className="p-3">
                        <div className="flex items-center space-x-3">
                          <div className={`p-2 rounded-lg ${
                            isActive ? 'bg-white/20' : currentTheme.card
                          }`}>
                            <Icon className={`h-4 w-4 ${
                              isActive ? 'text-white' : currentTheme.text
                            }`} />
                          </div>
                          <div className="flex-1 text-left min-w-0">
                            <p className={`font-semibold text-sm truncate ${
                              isActive ? 'text-white' : currentTheme.text
                            }`}>
                              {category.title}
                            </p>
                            <p className={`text-xs truncate ${
                              isActive ? 'text-white/80' : currentTheme.textMuted
                            }`}>
                              {category.description}
                            </p>
                          </div>
                          <ChevronRight className={`h-4 w-4 transition-transform duration-200 ${
                            isActive 
                              ? 'rotate-90 text-white' 
                              : `${currentTheme.textMuted}`
                          }`} />
                        </div>
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>
          </div>

          {/* Main Content - Full Width */}
          <div className="flex-1 overflow-y-auto">
            <div className="p-8 h-full">
              {renderCategoryContent()}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}