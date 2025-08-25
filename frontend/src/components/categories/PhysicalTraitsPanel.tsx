import React, { useState, useEffect } from 'react'
import { Zap, Eye, Ruler, Palette, Sun } from 'lucide-react'
import { 
  getThemeClass, 
  getGlassBackground, 
  getGlassBorder, 
  getTextPrimary, 
  getTextSecondary, 
  getTagClass, 
  getProgressBarBg 
} from '../../utils/theme'

interface AnalysisData {
  summary?: any
  health_risks?: any
  drug_interactions?: any
  recommendations?: string[]
  physical_traits?: any[]
}

interface PhysicalTraitsPanelProps {
  isDarkMode?: boolean
  theme?: any
  data: AnalysisData
  token?: string
}

export default function PhysicalTraitsPanel({ isDarkMode = false, theme, data, token }: PhysicalTraitsPanelProps) {
  const glassBackground = getGlassBackground(isDarkMode);
  const glassBorder = getGlassBorder(isDarkMode);
  const textPrimary = getTextPrimary(isDarkMode);
  const textSecondary = getTextSecondary(isDarkMode);
  const tagClass = getTagClass(isDarkMode);
  const progressBarBg = getProgressBarBg(isDarkMode);
  const cardBackground = getThemeClass('bg-gray-50', isDarkMode);
  
  const [realPhysicalTraits, setRealPhysicalTraits] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  
  // Load real physical traits from dashboard API
  useEffect(() => {
    const loadPhysicalTraits = async () => {
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
          console.log('Loaded dashboard data for physical traits:', dashboardData)
          // Physical traits might be in the analysis results or a specific section
          const traits = dashboardData.physical_traits || dashboardData.analysis_results?.physical_traits || []
          setRealPhysicalTraits(traits)
        }
      } catch (error) {
        console.error('Error loading physical traits:', error)
      } finally {
        setLoading(false)
      }
    }
    
    loadPhysicalTraits()
  }, [token])
  
  // Use real physical traits data if available, otherwise fallback to data prop
  const getPhysicalTraits = () => {
    // First priority: Real API data
    if (realPhysicalTraits.length > 0) {
      return realPhysicalTraits.map((trait: any) => ({
        category: trait.trait_name || trait.category,
        trait: trait.genetic_result || trait.trait_value || trait.result,
        gene: trait.associated_variants?.[0] || trait.associated_gene || 'Multiple',
        probability: trait.confidence === 'high' ? 85 : trait.confidence === 'moderate' ? 65 : 45,
        description: trait.description || `Genetic analysis shows predisposition for ${trait.trait_name || trait.category}`,
        confidence: trait.confidence || 'moderate'
      }))
    }
    
    // Second priority: Data from props
    if (data?.physical_traits && data.physical_traits.length > 0) {
      return data.physical_traits.map((trait: any) => ({
        category: trait.trait_name || trait.category,
        trait: trait.genetic_result || trait.trait_value || trait.result,
        gene: trait.associated_variants?.[0] || trait.associated_gene || 'Multiple',
        probability: trait.confidence === 'high' ? 85 : trait.confidence === 'moderate' ? 65 : 45,
        description: trait.description || `Genetic analysis shows predisposition for ${trait.trait_name || trait.category}`,
        confidence: trait.confidence || 'moderate'
      }))
    }
    
    // Loading state
    if (loading) {
      return [{
        category: 'Loading Physical Traits...',
        trait: 'Processing',
        gene: 'Multiple',
        probability: 0,
        description: 'Loading your genetic physical trait analysis...',
        confidence: 'pending'
      }]
    }
    
    // No data available
    return []
  }
  
  const physicalTraits = getPhysicalTraits()
  
  // Check if physical traits data is available
  const hasRealData = physicalTraits.length > 0 && !loading

  // If no real data is available, show message
  if (!hasRealData) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className={`text-2xl font-bold ${textPrimary} mb-2`}>
              Physical Traits
            </h2>
            <p className={textSecondary}>
              Genetic predispositions for physical characteristics
            </p>
          </div>
          <div className={`${glassBackground} border ${glassBorder} rounded-xl p-4`}>
            <div className="flex items-center space-x-3">
              <Ruler className={`h-8 w-8 ${getThemeClass('text-purple-500', isDarkMode)}`} />
              <div>
                <div className={`text-2xl font-bold ${textPrimary}`}>
                  0
                </div>
                <div className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>
                  Traits
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* No Data Available */}
        <div className={`${glassBackground} border ${glassBorder} rounded-xl p-8 text-center`}>
          <div className="flex flex-col items-center space-y-4">
            <div className="p-4 bg-gradient-to-br from-purple-500/20 to-pink-500/20 backdrop-blur-xl rounded-xl border border-purple-500/30">
              <Ruler className="h-8 w-8 text-purple-400" />
            </div>
            <div>
              <h3 className={`text-xl font-bold ${textPrimary} mb-2`}>
                Physical Traits Analysis in Progress
              </h3>
              <p className={`${textSecondary} max-w-md mx-auto`}>
                Physical traits analysis is not yet available for your genetic data. 
                This analysis requires specific trait-associated variants that may be added in future updates.
              </p>
            </div>
          </div>
        </div>

        {/* Information Panel */}
        <div className={`${glassBackground} border ${glassBorder} rounded-xl p-8`}>
          <h3 className={`text-xl font-bold ${textPrimary} mb-6`}>
            About Physical Traits Analysis
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 className={`text-lg font-semibold ${textPrimary} mb-4`}>Analyzed Traits</h4>
              <ul className={`${textSecondary} space-y-2`}>
                <li>• <strong>Eye Color:</strong> Brown, blue, green, hazel variations</li>
                <li>• <strong>Hair Characteristics:</strong> Color, texture, and curl pattern</li>
                <li>• <strong>Height Predisposition:</strong> Genetic height potential</li>
                <li>• <strong>Skin Pigmentation:</strong> Melanin production and sun sensitivity</li>
              </ul>
            </div>
            <div>
              <h4 className={`text-lg font-semibold ${textPrimary} mb-4`}>Understanding Results</h4>
              <p className={`${textSecondary} leading-relaxed`}>
                Physical trait predictions are based on known genetic variants but are influenced 
                by multiple genes and environmental factors. Results represent genetic predispositions 
                rather than definitive outcomes.
              </p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Use real physical traits data when available  
  const traits = physicalTraits

  const getTraitIcon = (category: string) => {
    const categoryLower = category.toLowerCase()
    if (categoryLower.includes('eye')) return Eye
    if (categoryLower.includes('hair')) return Palette
    if (categoryLower.includes('skin') || categoryLower.includes('pigment')) return Sun
    if (categoryLower.includes('height') || categoryLower.includes('build')) return Ruler
    return Zap
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <div className="flex items-center mb-4">
          <Ruler className={`h-8 w-8 ${getThemeClass('text-purple-600', isDarkMode)} mr-3`} />
          <div>
            <h2 className={`text-2xl font-bold ${textPrimary}`}>Physical Traits</h2>
            <p className={`${textSecondary}`}>Your genetic physical characteristics and appearance</p>
          </div>
        </div>
      </div>

      {/* Physical Traits */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Genetic Traits</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {traits.map((trait: any, index: number) => {
            const TraitIcon = getTraitIcon(trait.category)
            return (
              <div key={index} className={`${cardBackground} border ${glassBorder} rounded-lg p-4`}>
                <div className="flex items-start space-x-3">
                  <div className="p-2 rounded-lg bg-purple-50 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">
                    <TraitIcon className="h-5 w-5" />
                  </div>
                  <div className="flex-1">
                    <div className="flex justify-between items-start mb-2">
                      <div>
                        <h4 className={`font-medium ${textPrimary}`}>{trait.category}</h4>
                        <p className={`text-sm ${textSecondary}`}>{trait.trait}</p>
                      </div>
                      <span className={`text-xs px-2 py-1 rounded ${tagClass}`}>
                        {trait.gene}
                      </span>
                    </div>
                    <div className="flex items-center space-x-3 mb-2">
                      <div className={`w-20 rounded-full h-2 ${progressBarBg}`}>
                        <div 
                          className="h-2 rounded-full bg-purple-500"
                          style={{ width: `${trait.probability}%` }}
                        ></div>
                      </div>
                      <span className="text-sm font-medium text-purple-600">
                        {Math.round(trait.probability)}%
                      </span>
                    </div>
                    <p className={`text-xs ${textSecondary}`}>{trait.description}</p>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}