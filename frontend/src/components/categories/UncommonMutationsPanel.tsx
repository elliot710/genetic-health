'use client'

import { useState } from 'react'
import { Microscope, TrendingUp, BookOpen, Activity, Clock, ChevronRight, Info } from 'lucide-react'
import { getGlassBackground, getTextPrimary, getTextSecondary } from '../../utils/theme'

interface UncommonMutationsPanelProps {
  data: any
  isDarkMode: boolean
  theme?: any
}

export default function UncommonMutationsPanel({ data, isDarkMode, theme }: UncommonMutationsPanelProps) {
  const [selectedMutation, setSelectedMutation] = useState<string | null>(null)

  // Check if uncommon mutation data is available from the database
  const hasRealData = data?.uncommon_mutations && data.uncommon_mutations.length > 0
  const uncommonMutationData = hasRealData ? data.uncommon_mutations : []

  const glassBackground = getGlassBackground(isDarkMode)
  const textPrimary = getTextPrimary(isDarkMode)
  const textSecondary = getTextSecondary(isDarkMode)
  const borderColor = isDarkMode ? 'border-gray-700/50' : 'border-gray-200/50'

  const getSignificanceColor = (significance: string) => {
    switch (significance.toLowerCase()) {
      case 'moderate':
        return isDarkMode ? 'text-yellow-400 bg-yellow-500/20 border-yellow-500/30' : 'text-yellow-700 bg-yellow-100/80 border-yellow-200'
      case 'low':
        return isDarkMode ? 'text-blue-400 bg-blue-500/20 border-blue-500/30' : 'text-blue-700 bg-blue-100/80 border-blue-200'
      case 'very_low':
        return isDarkMode ? 'text-gray-400 bg-gray-500/20 border-gray-500/30' : 'text-gray-700 bg-gray-100/80 border-gray-200'
      default:
        return isDarkMode ? 'text-gray-400 bg-gray-500/20 border-gray-500/30' : 'text-gray-700 bg-gray-100/80 border-gray-200'
    }
  }

  const getEffectSizeColor = (effectSize: string) => {
    switch (effectSize.toLowerCase()) {
      case 'large':
        return isDarkMode ? 'text-red-300' : 'text-red-600'
      case 'moderate':
        return isDarkMode ? 'text-orange-300' : 'text-orange-600'
      case 'small':
        return isDarkMode ? 'text-yellow-300' : 'text-yellow-600'
      default:
        return isDarkMode ? 'text-gray-300' : 'text-gray-600'
    }
  }

  const getResearchStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'well_studied':
        return isDarkMode ? 'text-green-300' : 'text-green-600'
      case 'emerging':
        return isDarkMode ? 'text-blue-300' : 'text-blue-600'
      case 'limited':
        return isDarkMode ? 'text-gray-300' : 'text-gray-600'
      default:
        return isDarkMode ? 'text-gray-300' : 'text-gray-600'
    }
  }

  // If no real data is available, show message
  if (!hasRealData) {
    return (
      <div className="space-y-6">
        {/* Header */}
        <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8`}>
          <div className="flex items-center space-x-4 mb-6">
            <div className="p-3 bg-gradient-to-br from-blue-500/20 to-purple-500/20 backdrop-blur-xl rounded-xl border border-blue-500/30">
              <Microscope className="h-7 w-7 text-blue-400" />
            </div>
            <div>
              <h2 className={`text-2xl font-bold ${textPrimary}`}>
                Uncommon Mutations Analysis
              </h2>
              <p className={`text-sm ${textSecondary}`}>
                Moderately rare genetic variants with research implications
              </p>
            </div>
          </div>
        </div>

        {/* No Data Available */}
        <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8 text-center`}>
          <div className="flex flex-col items-center space-y-4">
            <div className="p-4 bg-gradient-to-br from-green-500/20 to-teal-500/20 backdrop-blur-xl rounded-xl border border-green-500/30">
              <Activity className="h-8 w-8 text-green-400" />
            </div>
            <div>
              <h3 className={`text-xl font-bold ${textPrimary} mb-2`}>
                No Uncommon Mutations Detected
              </h3>
              <p className={`${textSecondary} max-w-md mx-auto`}>
                Our analysis did not identify any uncommon genetic mutations with moderate clinical 
                significance in your genetic data. This indicates typical genetic variation patterns.
              </p>
            </div>
          </div>
        </div>

        {/* Information Panel */}
        <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8`}>
          <h3 className={`text-xl font-bold ${textPrimary} mb-6`}>
            About Uncommon Mutations Analysis
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 className={`text-lg font-semibold ${textPrimary} mb-4`}>What are Uncommon Mutations?</h4>
              <p className={`${textSecondary} leading-relaxed`}>
                Uncommon mutations are genetic variants found in 0.1% to 5% of the population 
                that may have moderate health implications or research significance. These variants 
                often contribute to complex traits and may influence disease susceptibility or drug responses.
              </p>
            </div>
            <div>
              <h4 className={`text-lg font-semibold ${textPrimary} mb-4`}>Research Applications</h4>
              <p className={`${textSecondary} leading-relaxed`}>
                Our analysis identifies variants of uncertain significance (VUS) and research variants 
                that may be relevant for personalized medicine, pharmacogenomics, and participation 
                in genetic research studies or clinical trials.
              </p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Show uncommon mutations data
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8`}>
        <div className="flex items-center space-x-4 mb-6">
          <div className="p-3 bg-gradient-to-br from-blue-500/20 to-purple-500/20 backdrop-blur-xl rounded-xl border border-blue-500/30">
            <Microscope className="h-7 w-7 text-blue-400" />
          </div>
          <div>
            <h2 className={`text-2xl font-bold ${textPrimary}`}>
              Uncommon Mutations Analysis
            </h2>
            <p className={`text-sm ${textSecondary}`}>
              {uncommonMutationData.length} uncommon mutation{uncommonMutationData.length !== 1 ? 's' : ''} with research significance
            </p>
          </div>
        </div>

        {/* Summary Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className={`${glassBackground} border ${borderColor} rounded-xl p-4`}>
            <div className="flex items-center space-x-3">
              <TrendingUp className="h-5 w-5 text-yellow-400" />
              <div>
                <p className={`text-sm ${textSecondary}`}>Moderate Effect</p>
                <p className={`text-lg font-bold ${textPrimary}`}>
                  {uncommonMutationData.filter((m: any) => m.effect_size === 'moderate').length}
                </p>
              </div>
            </div>
          </div>
          <div className={`${glassBackground} border ${borderColor} rounded-xl p-4`}>
            <div className="flex items-center space-x-3">
              <BookOpen className="h-5 w-5 text-green-400" />
              <div>
                <p className={`text-sm ${textSecondary}`}>Well Studied</p>
                <p className={`text-lg font-bold ${textPrimary}`}>
                  {uncommonMutationData.filter((m: any) => m.research_status === 'well_studied').length}
                </p>
              </div>
            </div>
          </div>
          <div className={`${glassBackground} border ${borderColor} rounded-xl p-4`}>
            <div className="flex items-center space-x-3">
              <Activity className="h-5 w-5 text-blue-400" />
              <div>
                <p className={`text-sm ${textSecondary}`}>Research Eligible</p>
                <p className={`text-lg font-bold ${textPrimary}`}>
                  {uncommonMutationData.filter((m: any) => m.research_participation === 'recommended').length}
                </p>
              </div>
            </div>
          </div>
          <div className={`${glassBackground} border ${borderColor} rounded-xl p-4`}>
            <div className="flex items-center space-x-3">
              <Clock className="h-5 w-5 text-purple-400" />
              <div>
                <p className={`text-sm ${textSecondary}`}>Annual Follow-up</p>
                <p className={`text-lg font-bold ${textPrimary}`}>
                  {uncommonMutationData.filter((m: any) => m.follow_up_timeline === 'annual').length}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Mutations List */}
      <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8`}>
        <h3 className={`text-xl font-bold ${textPrimary} mb-6`}>
          Detected Uncommon Mutations
        </h3>
        <div className="space-y-4">
          {uncommonMutationData.map((mutation: any, index: number) => (
            <div
              key={index}
              className={`${glassBackground} border ${borderColor} rounded-xl p-6 cursor-pointer transition-all duration-200 hover:scale-[1.02]`}
              onClick={() => setSelectedMutation(selectedMutation === mutation.mutation_name ? null : mutation.mutation_name)}
            >
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <div className="flex items-center space-x-4 mb-3">
                    <h4 className={`text-lg font-bold ${textPrimary}`}>
                      {mutation.gene} - {mutation.mutation_name}
                    </h4>
                    <span className={`px-3 py-1 rounded-full text-xs font-semibold border ${getSignificanceColor(mutation.clinical_significance)}`}>
                      {mutation.clinical_significance.replace('_', ' ').toUpperCase()}
                    </span>
                  </div>
                  <p className={`${textSecondary} mb-2`}>
                    <strong>Trait Association:</strong> {mutation.trait_association}
                  </p>
                  <div className="flex items-center space-x-6 text-sm">
                    <span className={`${getEffectSizeColor(mutation.effect_size)}`}>
                      <strong>Effect Size:</strong> {mutation.effect_size}
                    </span>
                    <span className={`${getResearchStatusColor(mutation.research_status)}`}>
                      <strong>Research Status:</strong> {mutation.research_status.replace('_', ' ')}
                    </span>
                    <span className={textSecondary}>
                      <strong>Frequency:</strong> {(mutation.population_frequency * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>
                <ChevronRight 
                  className={`h-5 w-5 ${textSecondary} transition-transform duration-200 ${
                    selectedMutation === mutation.mutation_name ? 'rotate-90' : ''
                  }`} 
                />
              </div>

              {selectedMutation === mutation.mutation_name && (
                <div className="mt-6 pt-6 border-t border-gray-300/20">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Lifestyle Implications */}
                    <div>
                      <h5 className={`text-md font-semibold ${textPrimary} mb-3 flex items-center`}>
                        <Activity className="h-4 w-4 mr-2 text-green-400" />
                        Lifestyle Implications
                      </h5>
                      <ul className="space-y-2">
                        {mutation.lifestyle_implications.map((implication: string, idx: number) => (
                          <li key={idx} className={`text-sm ${textSecondary} flex items-start`}>
                            <span className="text-green-400 mr-2">•</span>
                            {implication}
                          </li>
                        ))}
                      </ul>
                    </div>

                    {/* Monitoring Suggestions */}
                    <div>
                      <h5 className={`text-md font-semibold ${textPrimary} mb-3 flex items-center`}>
                        <Clock className="h-4 w-4 mr-2 text-blue-400" />
                        Monitoring Suggestions
                      </h5>
                      <ul className="space-y-2">
                        {mutation.monitoring_suggestions.map((suggestion: string, idx: number) => (
                          <li key={idx} className={`text-sm ${textSecondary} flex items-start`}>
                            <span className="text-blue-400 mr-2">•</span>
                            {suggestion}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  {/* Research Information */}
                  <div className="mt-6 p-4 bg-gradient-to-r from-blue-500/10 to-purple-500/10 rounded-xl border border-blue-500/20">
                    <div className="flex items-start space-x-3">
                      <BookOpen className="h-5 w-5 text-blue-400 mt-0.5" />
                      <div>
                        <h6 className={`font-semibold ${textPrimary} mb-2`}>
                          Research & Follow-up Information
                        </h6>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                          <div className={textSecondary}>
                            <strong className="text-purple-400">Research Status:</strong><br />
                            {mutation.research_status.replace('_', ' ').charAt(0).toUpperCase() + mutation.research_status.replace('_', ' ').slice(1)}
                          </div>
                          <div className={textSecondary}>
                            <strong className="text-blue-400">Research Participation:</strong><br />
                            {mutation.research_participation.charAt(0).toUpperCase() + mutation.research_participation.slice(1)}
                          </div>
                          <div className={textSecondary}>
                            <strong className="text-green-400">Follow-up Timeline:</strong><br />
                            {mutation.follow_up_timeline.charAt(0).toUpperCase() + mutation.follow_up_timeline.slice(1)} monitoring
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Research & Clinical Information */}
      <div className={`${glassBackground} border ${borderColor} rounded-2xl p-6`}>
        <div className="flex items-start space-x-3">
          <Info className="h-6 w-6 text-blue-400 mt-1" />
          <div>
            <h4 className={`text-lg font-semibold ${textPrimary} mb-2`}>
              Research & Clinical Context
            </h4>
            <p className={`${textSecondary} text-sm leading-relaxed mb-4`}>
              These uncommon mutations represent variants of uncertain significance (VUS) or research variants 
              that may contribute to complex traits. While not immediately clinically actionable, they may be 
              relevant for personalized medicine, research participation, or future medical developments.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              <div>
                <h5 className={`font-semibold ${textPrimary} mb-2`}>Research Opportunities</h5>
                <p className={textSecondary}>
                  Consider participating in genetic research studies to advance understanding of these variants 
                  and contribute to precision medicine developments.
                </p>
              </div>
              <div>
                <h5 className={`font-semibold ${textPrimary} mb-2`}>Medical Consultation</h5>
                <p className={textSecondary}>
                  Discuss these findings with your healthcare provider to understand their relevance to your 
                  personal and family medical history.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}