'use client'

import { useState } from 'react'
import { 
  Apple, Brain, Dumbbell, Heart, Zap, Palette, 
  ChevronDown, TrendingUp, AlertTriangle, CheckCircle, 
  Settings, Download, Trash2, Info, Shield, Search,
  Upload, Dna, Activity, BarChart3, Sparkles, Target,
  Award, Lightbulb, Star, Flame, Sun, Moon, Users,
  MessageSquare, Bell, Menu, X, LogOut, Plus, Home
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

export default function ModernDashboard({ data, onReset, token, onRefresh }: ModernDashboardProps) {
  const [activeCategory, setActiveCategory] = useState('overview')
  const [showUserMenu, setShowUserMenu] = useState(false)
  const [isDarkMode, setIsDarkMode] = useState(false)

  // Glassmorphism theme configuration
  const theme = {
    background: isDarkMode ? 'bg-slate-900' : 'bg-gray-50',
    glass: isDarkMode ? 'bg-slate-800/30 backdrop-blur-xl' : 'bg-white/40 backdrop-blur-xl',
    glassBorder: isDarkMode ? 'border-white/10' : 'border-gray-200/30',
    glassHover: isDarkMode ? 'hover:bg-slate-800/50' : 'hover:bg-white/60',
    secondary: isDarkMode ? 'bg-slate-800/20' : 'bg-white/20',
    border: isDarkMode ? 'border-white/10' : 'border-gray-200/30',
    text: {
      primary: isDarkMode ? 'text-white' : 'text-slate-900',
      secondary: isDarkMode ? 'text-slate-300' : 'text-slate-600',
      muted: isDarkMode ? 'text-slate-400' : 'text-slate-500'
    },
    hover: isDarkMode ? 'hover:bg-slate-800/30' : 'hover:bg-white/50'
  }

  const categories = [
    {
      id: 'overview',
      title: 'Overview',
      icon: Home,
    },
    {
      id: 'food-nutrition',
      title: 'Food & Nutrition',
      icon: Apple,
    },
    {
      id: 'intelligence',
      title: 'Intelligence',
      icon: Brain,
    },
    {
      id: 'physical-traits',
      title: 'Physical Traits',
      icon: Target,
    },
    {
      id: 'personality',
      title: 'Personality',
      icon: Palette,
    },
    {
      id: 'sports',
      title: 'Sports & Fitness',
      icon: Dumbbell,
    },
    {
      id: 'health',
      title: 'Health & Wellness',
      icon: Heart,
    },
    {
      id: 'variant-search',
      title: 'Variant Search',
      icon: Search,
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
          <div className="space-y-12">
            {/* Stats Row - Glassmorphism Cards */}
            <div className="grid grid-cols-3 gap-8">
              {stats.map((stat, index) => {
                const Icon = stat.icon
                return (
                  <div key={index} className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-8 ${theme.glassHover} transition-all duration-300 group cursor-pointer`}>
                    <div className="flex items-center justify-between mb-6">
                      <div className={`p-4 ${stat.bgColor} rounded-xl group-hover:scale-110 transition-transform duration-300`}>
                        <Icon className={`h-7 w-7 ${stat.color}`} />
                      </div>
                      <div className={`text-xs ${theme.text.muted} font-semibold uppercase tracking-wider`}>
                        {stat.title}
                      </div>
                    </div>
                    <div className={`text-4xl font-bold ${theme.text.primary} group-hover:scale-105 transition-transform duration-300`}>
                      {stat.value}
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Main Content Grid - Full Width */}
            <div className="grid grid-cols-3 gap-16">
              {/* Quick Insights - Glassmorphism Cards */}
              <div className="col-span-2">
                <div className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-8`}>
                  <div className="flex items-center space-x-4 mb-8">
                    <div className="p-3 bg-gradient-to-br from-blue-500/20 to-purple-500/20 backdrop-blur-xl rounded-xl border border-blue-500/30">
                      <Sparkles className="h-7 w-7 text-blue-500" />
                    </div>
                    <h3 className={`text-2xl font-bold ${theme.text.primary}`}>
                      Quick Insights
                    </h3>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-6">
                    {quickInsights.map((insight, index) => {
                      const Icon = insight.icon
                      return (
                        <div key={index} className={`${theme.glass} border ${theme.glassBorder} rounded-xl p-6 ${theme.glassHover} transition-all duration-300 group`}>
                          <div className="flex items-center space-x-3 mb-4">
                            <div className={`p-3 ${insight.bgColor} rounded-xl group-hover:scale-110 transition-transform duration-300`}>
                              <Icon className={`h-5 w-5 ${insight.color}`} />
                            </div>
                            <h4 className={`font-bold ${theme.text.primary}`}>
                              {insight.category}
                            </h4>
                          </div>
                          <p className={`${theme.text.secondary} text-sm leading-relaxed`}>
                            {insight.insight}
                          </p>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>

              {/* Data Overview - Glassmorphism Card */}
              <div className="col-span-1">
                <div className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-8`}>
                  <div className="flex items-center space-x-4 mb-8">
                    <div className="p-3 bg-gradient-to-br from-green-500/20 to-emerald-500/20 backdrop-blur-xl rounded-xl border border-green-500/30">
                      <Dna className="h-7 w-7 text-green-600" />
                    </div>
                    <h3 className={`text-xl font-bold ${theme.text.primary}`}>
                      Your Data
                    </h3>
                  </div>
                  
                  <div className="space-y-6">
                    {data.real_data?.variants && data.real_data.variants.length > 0 ? (
                      <>
                        <div className={`${theme.glass} border ${theme.glassBorder} rounded-xl p-6 text-center`}>
                          <div className="text-3xl font-bold text-green-600 mb-2">
                            {data.real_data.variants.length}
                          </div>
                          <div className={`text-sm ${theme.text.secondary}`}>Variants Analyzed</div>
                        </div>
                        
                        <div className="space-y-4">
                          {[
                            { label: 'File', value: data.real_data.upload_result?.filename || 'Unknown' },
                            { label: 'Analysis ID', value: data.summary?.analysis_id || 'N/A' },
                            { label: 'File Size', value: data.real_data.upload_result?.file_size ? `${Math.round(data.real_data.upload_result.file_size / 1024)}KB` : 'N/A' }
                          ].map((item, index) => (
                            <div key={index} className={`flex justify-between items-center p-4 ${theme.glass} border ${theme.glassBorder} rounded-xl`}>
                              <span className={`text-sm ${theme.text.secondary}`}>{item.label}</span>
                              <span className={`text-sm font-medium ${theme.text.primary}`}>{item.value}</span>
                            </div>
                          ))}
                        </div>
                      </>
                    ) : (
                      <div className={`${theme.glass} border ${theme.glassBorder} rounded-xl p-8 text-center`}>
                        <Upload className={`h-12 w-12 ${theme.text.muted} mx-auto mb-4`} />
                        <h4 className={`font-medium ${theme.text.primary} mb-2`}>No Data Uploaded</h4>
                        <p className={`text-sm ${theme.text.secondary} mb-6`}>Upload your genetic data to get started</p>
                        <button
                          onClick={onReset}
                          className="bg-gradient-to-r from-blue-500/80 to-purple-500/80 hover:from-blue-600/80 hover:to-purple-600/80 backdrop-blur-xl text-white px-6 py-3 rounded-xl text-sm font-medium transition-all duration-300 border border-white/20 shadow-lg"
                        >
                          Upload Data
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Sample Variants Table - Glassmorphism */}
            {data.real_data?.variants && data.real_data.variants.length > 0 && (
              <div className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-8`}>
                <h4 className={`font-bold ${theme.text.primary} mb-6 text-xl`}>Sample Genetic Variants</h4>
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
                      {data.real_data.variants.slice(0, 8).map((variant: any, index: number) => (
                        <tr key={index} className={`${theme.glassBorder} border-b ${theme.glassHover} transition-all duration-200`}>
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
                  {data.real_data.variants.length > 8 && (
                    <div className={`text-center mt-6 ${theme.text.muted} text-sm`}>
                      Showing 8 of {data.real_data.variants.length} variants
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )
    }
  }

  return (
    <div className={`min-h-screen ${theme.background} relative overflow-hidden`}>
      {/* Glassmorphism Background Elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className={`absolute -top-40 -right-40 w-96 h-96 ${isDarkMode ? 'bg-gradient-to-br from-blue-500/30 to-purple-500/20' : 'bg-gradient-to-br from-blue-300/40 to-purple-300/30'} rounded-full filter blur-3xl animate-float`}></div>
        <div className={`absolute top-1/3 -left-40 w-80 h-80 ${isDarkMode ? 'bg-gradient-to-br from-purple-500/25 to-pink-500/20' : 'bg-gradient-to-br from-purple-300/35 to-pink-300/25'} rounded-full filter blur-3xl animate-float-delayed`}></div>
        <div className={`absolute bottom-0 right-1/3 w-72 h-72 ${isDarkMode ? 'bg-gradient-to-br from-teal-500/20 to-cyan-500/15' : 'bg-gradient-to-br from-teal-300/30 to-cyan-300/20'} rounded-full filter blur-3xl animate-float-slow`}></div>
        <div className={`absolute top-1/2 left-1/2 w-64 h-64 ${isDarkMode ? 'bg-gradient-to-br from-indigo-500/15 to-blue-500/10' : 'bg-gradient-to-br from-indigo-300/25 to-blue-300/15'} rounded-full filter blur-3xl animate-float-reverse`}></div>
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
                {data.summary?.total_variants || 0} variants analyzed
              </p>
            </div>
          </div>

          {/* Navigation - Clean like Dimension */}
          <nav className="hidden md:flex items-center space-x-6">
            <a href="#" className={`${theme.text.secondary} hover:${theme.text.primary} text-sm font-medium transition-colors`}>About</a>
            <a href="#" className={`${theme.text.secondary} hover:${theme.text.primary} text-sm font-medium transition-colors`}>Careers</a>
            <a href="#" className={`${theme.text.secondary} hover:${theme.text.primary} text-sm font-medium transition-colors`}>Blog</a>
            <a href="#" className={`${theme.text.secondary} hover:${theme.text.primary} text-sm font-medium transition-colors`}>Changelog</a>
          </nav>

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

            {onRefresh && (
              <button
                onClick={handleRefreshData}
                className="bg-gradient-to-r from-green-500/80 to-emerald-500/80 hover:from-green-600/80 hover:to-emerald-600/80 backdrop-blur-xl text-white px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-300 flex items-center space-x-2 border border-white/20 shadow-lg"
              >
                <Activity className="h-4 w-4" />
                <span>Refresh Data</span>
              </button>
            )}
            
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
                <span className={theme.text.primary}>Victoria</span>
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
                    onClick={handleDeleteData}
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
                        : `${theme.text.secondary} ${theme.glassHover} border border-transparent`
                    }`}
                  >
                    <Icon className={`h-5 w-5 ${isActive ? 'text-white' : theme.text.muted}`} />
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
    </div>
  )
}