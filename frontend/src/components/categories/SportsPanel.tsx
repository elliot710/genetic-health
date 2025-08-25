import React, { useState, useEffect } from 'react'
import { Dumbbell, Heart, Zap, Timer, Trophy } from 'lucide-react'
import { 
  getThemeClass, 
  getGlassBackground, 
  getGlassBorder, 
  getTextPrimary, 
  getTextSecondary, 
  getTagClass, 
  getProgressBarBg 
} from '../../utils/theme'

interface SportsPanelProps {
  isDarkMode?: boolean
  theme?: any
  data?: any
  token?: string
}

export default function SportsPanel({ isDarkMode = false, theme, data, token }: SportsPanelProps) {
  const glassBackground = getGlassBackground(isDarkMode)
  const glassBorder = getGlassBorder(isDarkMode)
  const textPrimary = getTextPrimary(isDarkMode)
  const textSecondary = getTextSecondary(isDarkMode)
  const tagClass = getTagClass(isDarkMode)
  const progressBarBg = getProgressBarBg(isDarkMode)
  const cardBackground = getThemeClass('bg-gray-50', isDarkMode)
  
  const [realSportsData, setRealSportsData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  
  // Load real sports performance data from dashboard API
  useEffect(() => {
    const loadSportsData = async () => {
      if (!token) return
      
      setLoading(true)
      try {
        const response = await fetch('http://localhost:8000/analyze/dashboard-data', {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        })
        
        if (response.ok) {
          const dashboardData = await response.json()
          console.log('Loaded dashboard data for sports:', dashboardData)
          const sports = dashboardData.sports_performance || dashboardData.analysis_results?.sports_performance || []
          setRealSportsData(sports)
        }
      } catch (error) {
        console.error('Error loading sports data:', error)
      } finally {
        setLoading(false)
      }
    }
    
    loadSportsData()
  }, [token])
  
  const getAthleticTraits = () => {
    if (realSportsData.length > 0) {
      return realSportsData.map((trait: any) => ({
        trait: trait.performance_category || trait.trait_name,
        gene: trait.associated_variants?.[0] || 'Multiple',
        result: trait.genetic_advantage || trait.genetic_result,
        score: trait.genetic_advantage === 'high' ? 85 : trait.genetic_advantage === 'moderate' ? 65 : 45,
        description: trait.description || `Genetic analysis for ${trait.performance_category || trait.trait_name}`,
        recommendation: Array.isArray(trait.sport_recommendations) 
          ? trait.sport_recommendations.join(', ') 
          : trait.sport_recommendations || trait.training_advice || 'Consult with sports trainer'
      }))
    }
    
    if (loading) {
      return [{
        trait: 'Loading Sports Analysis...',
        gene: 'Multiple',
        result: 'Processing',
        score: 0,
        description: 'Loading your genetic sports performance analysis...',
        recommendation: 'Analysis in progress...'
      }]
    }
    
    return []
  }
  
  const athleticTraits = getAthleticTraits()
  
  if (athleticTraits.length === 0 && !loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className={`text-2xl font-bold ${textPrimary} mb-2`}>
              Sports & Fitness
            </h2>
            <p className={textSecondary}>
              Genetic insights for athletic performance
            </p>
          </div>
          <div className={`${glassBackground} border ${glassBorder} rounded-xl p-4`}>
            <div className="flex items-center space-x-3">
              <Dumbbell className={`h-8 w-8 ${getThemeClass('text-orange-500', isDarkMode)}`} />
              <div>
                <div className={`text-2xl font-bold ${textPrimary}`}>0</div>
                <div className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>Traits</div>
              </div>
            </div>
          </div>
        </div>

        <div className={`${glassBackground} border ${glassBorder} rounded-xl p-8 text-center`}>
          <div className="flex flex-col items-center space-y-4">
            <div className="p-4 bg-gradient-to-br from-orange-500/20 to-red-500/20 backdrop-blur-xl rounded-xl border border-orange-500/30">
              <Dumbbell className="h-8 w-8 text-orange-400" />
            </div>
            <div>
              <h3 className={`text-xl font-bold ${textPrimary} mb-2`}>
                Sports Analysis in Progress
              </h3>
              <p className={`${textSecondary} max-w-md mx-auto`}>
                Sports performance analysis is not yet available for your genetic data. 
                This analysis requires specific athletic performance variants that may be added in future updates.
              </p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className={`text-2xl font-bold ${textPrimary} mb-2`}>
            Sports & Fitness
          </h2>
          <p className={textSecondary}>
            Genetic insights for athletic performance
          </p>
        </div>
        <div className={`${glassBackground} border ${glassBorder} rounded-xl p-4`}>
          <div className="flex items-center space-x-3">
            <Dumbbell className={`h-8 w-8 ${getThemeClass('text-orange-500', isDarkMode)}`} />
            <div>
              <div className={`text-2xl font-bold ${textPrimary}`}>{athleticTraits.length}</div>
              <div className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>Traits</div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {athleticTraits.map((trait, index) => (
          <div 
            key={index}
            className={`${glassBackground} border ${glassBorder} rounded-xl p-6 hover:shadow-lg transition-all duration-300`}
          >
            <div className="flex items-start justify-between mb-4">
              <div className="flex items-center space-x-3">
                <div className="p-3 rounded-xl bg-orange-50 text-orange-700">
                  <Dumbbell className="h-6 w-6" />
                </div>
                <div>
                  <h3 className={`font-bold text-lg ${textPrimary}`}>{trait.trait}</h3>
                  <p className={`text-sm ${getThemeClass('text-gray-500', isDarkMode)}`}>Gene: {trait.gene}</p>
                </div>
              </div>
            </div>
            
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className={`font-semibold ${textPrimary}`}>Result:</span>
                <span className={`font-bold ${textPrimary}`}>{trait.result}</span>
              </div>
              
              <p className={`text-sm ${textSecondary} leading-relaxed`}>
                {trait.description}
              </p>
              
              <div className={`mt-4 p-3 ${getThemeClass('bg-blue-50/50', isDarkMode)} rounded-lg border-l-4 border-blue-400`}>
                <h4 className={`text-sm font-semibold ${textPrimary} mb-1`}>Recommendation</h4>
                <p className={`text-sm ${textSecondary}`}>{trait.recommendation}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
