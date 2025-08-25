'use client'

import { useState } from 'react'
import { Search, TrendingUp, BookOpen, Activity, Clock, ChevronRight, Info } from 'lucide-react'
import { getGlassBackground, getTextPrimary, getTextSecondary } from '../../utils/theme'

interface UncommonMutation {
  rsid: string
  gene: string
  effect: string
  population_frequency: number
  effect_size: string
  research_status: string
  clinical_relevance: string
  literature_count: number
  variant_id?: string
  chromosome?: string
  position?: number
  ref_allele?: string
  alt_allele?: string
  mutation_name?: string
  research_findings?: string[]
  clinical_studies?: string[]
  biomarker_potential?: string
}

interface UncommonMutationData {
  uncommon_mutations: UncommonMutation[]
  analysis_summary?: {
    total_count: number
    moderate_effect_count: number
    research_priority_count: number
  }
}

interface UncommonMutationsPanelProps {
  data: UncommonMutationData | Record<string, unknown>
  isDarkMode: boolean
  theme?: Record<string, unknown>
}

export default function UncommonMutationsPanel({ data, isDarkMode, theme }: UncommonMutationsPanelProps) {
  const [selectedMutation, setSelectedMutation] = useState<string | null>(null)

  // Type guard to check if data has uncommon_mutations
  const isUncommonMutationData = (data: unknown): data is UncommonMutationData => {
    return typeof data === 'object' && data !== null && 'uncommon_mutations' in data
  }

  // Check if uncommon mutation data is available from the database
  const hasRealData = isUncommonMutationData(data) && Array.isArray(data.uncommon_mutations) && data.uncommon_mutations.length > 0
  const uncommonMutationData: UncommonMutation[] = hasRealData ? data.uncommon_mutations : []

  const glassBackground = getGlassBackground(isDarkMode)
  const textPrimary = getTextPrimary(isDarkMode)
  const textSecondary = getTextSecondary(isDarkMode)
  const borderColor = isDarkMode ? 'border-gray-700/50' : 'border-gray-200/50'

  const getEffectSizeColor = (effectSize: string) => {
    switch (effectSize.toLowerCase()) {
      case 'large':
        return isDarkMode ? 'text-red-400 bg-red-500/20 border-red-500/30' : 'text-red-700 bg-red-100/80 border-red-200'
      case 'moderate':
        return isDarkMode ? 'text-orange-400 bg-orange-500/20 border-orange-500/30' : 'text-orange-700 bg-orange-100/80 border-orange-200'
      case 'small':
        return isDarkMode ? 'text-yellow-400 bg-yellow-500/20 border-yellow-500/30' : 'text-yellow-700 bg-yellow-100/80 border-yellow-200'
      default:
        return isDarkMode ? 'text-gray-400 bg-gray-500/20 border-gray-500/30' : 'text-gray-700 bg-gray-100/80 border-gray-200'
    }
  }

  const getResearchStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'well_established':
        return isDarkMode ? 'text-green-400 bg-green-500/20' : 'text-green-700 bg-green-100/80'
      case 'emerging':
        return isDarkMode ? 'text-blue-400 bg-blue-500/20' : 'text-blue-700 bg-blue-100/80'
      case 'preliminary':
        return isDarkMode ? 'text-purple-400 bg-purple-500/20' : 'text-purple-700 bg-purple-100/80'
      case 'conflicting':
        return isDarkMode ? 'text-orange-400 bg-orange-500/20' : 'text-orange-700 bg-orange-100/80'
      default:
        return isDarkMode ? 'text-gray-400 bg-gray-500/20' : 'text-gray-700 bg-gray-100/80'
    }
  }

  if (!hasRealData) {
    return (
      <div className={`p-6 rounded-xl ${glassBackground} ${borderColor} border`}>
        <div className="flex items-center gap-3 mb-4">
          <Search className={`w-6 h-6 ${textPrimary}`} />
          <h3 className={`text-xl font-semibold ${textPrimary}`}>Uncommon Genetic Variants</h3>
        </div>
        
        <div className={`p-4 rounded-lg ${isDarkMode ? 'bg-blue-500/10 border-blue-500/20' : 'bg-blue-50/80 border-blue-200/50'} border`}>
          <div className="flex items-center gap-2 mb-2">
            <Info className={`w-5 h-5 ${isDarkMode ? 'text-blue-400' : 'text-blue-600'}`} />
            <span className={`font-medium ${isDarkMode ? 'text-blue-400' : 'text-blue-600'}`}>
              Analysis in Progress
            </span>
          </div>
          <p className={`${textSecondary} text-sm`}>
            Uncommon genetic variants (1-5% population frequency) are being analyzed. These variants may have moderate 
            effects and represent emerging research opportunities for personalized medicine.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className={`p-6 rounded-xl ${glassBackground} ${borderColor} border`}>
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <Search className={`w-6 h-6 ${textPrimary}`} />
        <h3 className={`text-xl font-semibold ${textPrimary}`}>Uncommon Genetic Variants</h3>
        <span className={`ml-auto px-3 py-1 rounded-full text-sm font-medium ${isDarkMode ? 'bg-blue-500/20 text-blue-400' : 'bg-blue-100/80 text-blue-700'}`}>
          {uncommonMutationData.length} variants (1-5% frequency)
        </span>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className={`p-4 rounded-lg ${isDarkMode ? 'bg-blue-500/10 border-blue-500/20' : 'bg-blue-50/80 border-blue-200/50'} border`}>
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className={`w-5 h-5 ${isDarkMode ? 'text-blue-400' : 'text-blue-600'}`} />
            <span className={`font-medium ${isDarkMode ? 'text-blue-400' : 'text-blue-600'}`}>Research Interest</span>
          </div>
          <div className={`text-2xl font-bold ${textPrimary} mb-1`}>
            {uncommonMutationData.filter((m: UncommonMutation) => m.research_status === 'emerging' || m.research_status === 'well_established').length}
          </div>
          <p className={`text-sm ${textSecondary}`}>
            variants with active research
          </p>
        </div>

        <div className={`p-4 rounded-lg ${isDarkMode ? 'bg-purple-500/10 border-purple-500/20' : 'bg-purple-50/80 border-purple-200/50'} border`}>
          <div className="flex items-center gap-2 mb-2">
            <BookOpen className={`w-5 h-5 ${isDarkMode ? 'text-purple-400' : 'text-purple-600'}`} />
            <span className={`font-medium ${isDarkMode ? 'text-purple-400' : 'text-purple-600'}`}>Literature Support</span>
          </div>
          <div className={`text-2xl font-bold ${textPrimary} mb-1`}>
            {Math.round(uncommonMutationData.reduce((sum, m) => sum + (m.literature_count || 0), 0) / uncommonMutationData.length)}
          </div>
          <p className={`text-sm ${textSecondary}`}>
            average studies per variant
          </p>
        </div>

        <div className={`p-4 rounded-lg ${isDarkMode ? 'bg-green-500/10 border-green-500/20' : 'bg-green-50/80 border-green-200/50'} border`}>
          <div className="flex items-center gap-2 mb-2">
            <Activity className={`w-5 h-5 ${isDarkMode ? 'text-green-400' : 'text-green-600'}`} />
            <span className={`font-medium ${isDarkMode ? 'text-green-400' : 'text-green-600'}`}>Biomarker Potential</span>
          </div>
          <div className={`text-2xl font-bold ${textPrimary} mb-1`}>
            {uncommonMutationData.filter((m: UncommonMutation) => m.biomarker_potential === 'high' || m.biomarker_potential === 'moderate').length}
          </div>
          <p className={`text-sm ${textSecondary}`}>
            variants with biomarker value
          </p>
        </div>
      </div>

      {/* Mutations List */}
      <div className="space-y-3">
        <h4 className={`font-semibold ${textPrimary} mb-3`}>Detected Variants</h4>
        
        {uncommonMutationData.map((mutation: UncommonMutation, index: number) => (
          <div key={mutation.rsid || index} className={`border rounded-lg ${borderColor} overflow-hidden`}>
            <div 
              className={`p-4 cursor-pointer hover:${isDarkMode ? 'bg-white/5' : 'bg-gray-50/80'} transition-colors`}
              onClick={() => setSelectedMutation(selectedMutation === (mutation.mutation_name || mutation.rsid) ? null : mutation.mutation_name || mutation.rsid)}
            >
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h5 className={`font-semibold ${textPrimary}`}>
                      {mutation.gene} - {mutation.mutation_name || mutation.rsid}
                    </h5>
                    <span className={`px-2 py-1 rounded text-xs font-medium border ${getEffectSizeColor(mutation.effect_size)}`}>
                      {mutation.effect_size} effect
                    </span>
                    <span className={`px-2 py-1 rounded text-xs font-medium ${getResearchStatusColor(mutation.research_status)}`}>
                      {mutation.research_status?.replace('_', ' ')}
                    </span>
                  </div>
                  <div className={`text-sm ${textSecondary} grid grid-cols-2 gap-4`}>
                    <span><strong>Effect:</strong> {mutation.effect}</span>
                    <span><strong>Frequency:</strong> {(mutation.population_frequency * 100).toFixed(1)}%</span>
                  </div>
                </div>
                <ChevronRight 
                  className={`w-5 h-5 ${textSecondary} transition-transform ${
                    selectedMutation === (mutation.mutation_name || mutation.rsid) ? 'rotate-90' : ''
                  }`} 
                />
              </div>
            </div>

            {selectedMutation === (mutation.mutation_name || mutation.rsid) && (
              <div className={`px-4 pb-4 border-t ${borderColor}`}>
                <div className="mt-4 space-y-4">
                  {/* Research Findings */}
                  <div>
                    <h6 className={`font-semibold ${textPrimary} mb-2 flex items-center gap-2`}>
                      <BookOpen className="w-4 h-4" />
                      Research Findings
                    </h6>
                    <div className="space-y-2">
                      {mutation.research_findings?.map((finding: string, idx: number) => (
                        <div key={idx} className={`p-3 rounded ${isDarkMode ? 'bg-gray-800/50' : 'bg-gray-50/80'}`}>
                          <p className={`text-sm ${textSecondary}`}>{finding}</p>
                        </div>
                      )) || (
                        <p className={`text-sm ${textSecondary} italic`}>Research findings are being compiled.</p>
                      )}
                    </div>
                  </div>

                  {/* Clinical Studies */}
                  <div>
                    <h6 className={`font-semibold ${textPrimary} mb-2 flex items-center gap-2`}>
                      <Activity className="w-4 h-4" />
                      Clinical Studies
                    </h6>
                    <div className="space-y-2">
                      {mutation.clinical_studies?.map((study: string, idx: number) => (
                        <div key={idx} className={`p-3 rounded ${isDarkMode ? 'bg-gray-800/50' : 'bg-gray-50/80'}`}>
                          <p className={`text-sm ${textSecondary}`}>{study}</p>
                        </div>
                      )) || (
                        <p className={`text-sm ${textSecondary} italic`}>Clinical study data is being gathered.</p>
                      )}
                    </div>
                  </div>

                  {/* Additional Details */}
                  <div className={`p-3 rounded ${isDarkMode ? 'bg-blue-500/10' : 'bg-blue-50/80'}`}>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <span className={`text-sm font-medium ${textPrimary}`}>Clinical Relevance:</span>
                        <p className={`text-sm ${textSecondary}`}>{mutation.clinical_relevance}</p>
                      </div>
                      <div>
                        <span className={`text-sm font-medium ${textPrimary}`}>Literature Count:</span>
                        <p className={`text-sm ${textSecondary}`}>{mutation.literature_count} studies</p>
                      </div>
                      {mutation.biomarker_potential && (
                        <div>
                          <span className={`text-sm font-medium ${textPrimary}`}>Biomarker Potential:</span>
                          <p className={`text-sm ${textSecondary}`}>{mutation.biomarker_potential}</p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Footer Info */}
      <div className={`mt-6 p-4 rounded-lg ${isDarkMode ? 'bg-gray-800/50' : 'bg-gray-50/80'}`}>
        <div className="flex items-start gap-2">
          <Info className={`w-5 h-5 ${textSecondary} mt-0.5 flex-shrink-0`} />
          <div>
            <p className={`text-sm font-medium ${textPrimary} mb-1`}>About Uncommon Variants</p>
            <p className={`text-xs ${textSecondary}`}>
              These variants occur in 1-5% of the population and may have moderate effects on health and traits. 
              While less common than typical variants, they represent important research opportunities and may become 
              clinically actionable as our understanding develops.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
