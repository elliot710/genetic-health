'use client'

import { useState } from 'react'
import { Dna, TrendingUp, AlertTriangle, CheckCircle, Info, ChevronRight } from 'lucide-react'
import { getGlassBackground, getTextPrimary, getTextSecondary } from '../../utils/theme'

interface MethylationPanelProps {
  data: any
  isDarkMode: boolean
  theme?: any
}

export default function MethylationPanel({ data, isDarkMode, theme }: MethylationPanelProps) {
  const [selectedGene, setSelectedGene] = useState<string | null>(null)

  // Check if methylation data is available from the database
  const hasRealData = data?.methylation_profiles && data.methylation_profiles.length > 0
  const methylationData = hasRealData ? data.methylation_profiles[0] : null

  const glassBackground = getGlassBackground(isDarkMode)
  const textPrimary = getTextPrimary(isDarkMode)
  const textSecondary = getTextSecondary(isDarkMode)
  const borderColor = isDarkMode ? 'border-gray-700/50' : 'border-gray-200/50'

  // If no real data is available, show message
  if (!hasRealData) {
    return (
      <div className="space-y-6">
        {/* Header */}
        <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8`}>
          <div className="flex items-center space-x-4 mb-6">
            <div className="p-3 bg-gradient-to-br from-purple-500/20 to-pink-500/20 backdrop-blur-xl rounded-xl border border-purple-500/30">
              <Dna className="h-7 w-7 text-purple-400" />
            </div>
            <div>
              <h2 className={`text-2xl font-bold ${textPrimary}`}>
                Methylation Analysis
              </h2>
              <p className={`text-sm ${textSecondary}`}>
                Your genetic methylation capacity and recommendations
              </p>
            </div>
          </div>
        </div>

        {/* No Data Available */}
        <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8 text-center`}>
          <div className="flex flex-col items-center space-y-4">
            <div className="p-4 bg-gradient-to-br from-purple-500/20 to-pink-500/20 backdrop-blur-xl rounded-xl border border-purple-500/30">
              <Info className="h-8 w-8 text-purple-400" />
            </div>
            <div>
              <h3 className={`text-xl font-bold ${textPrimary} mb-2`}>
                Methylation Analysis in Progress
              </h3>
              <p className={`${textSecondary} max-w-md mx-auto`}>
                Methylation pathway analysis is not yet available for your genetic data. 
                This analysis requires specific genetic variants that may be added in future updates.
              </p>
            </div>
          </div>
        </div>

        {/* Information Panel */}
        <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8`}>
          <h3 className={`text-xl font-bold ${textPrimary} mb-6`}>
            About Methylation Analysis
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 className={`text-lg font-semibold ${textPrimary} mb-4`}>What is Methylation?</h4>
              <p className={`${textSecondary} leading-relaxed`}>
                Methylation is a crucial biochemical process that affects gene expression, 
                detoxification, neurotransmitter production, and overall cellular function. 
                Genetic variants in methylation genes can impact how efficiently your body 
                processes nutrients and eliminates toxins.
              </p>
            </div>
            <div>
              <h4 className={`text-lg font-semibold ${textPrimary} mb-4`}>Key Genes Analyzed</h4>
              <ul className={`${textSecondary} space-y-2`}>
                <li>• <strong>MTHFR:</strong> Folate metabolism and methylfolate production</li>
                <li>• <strong>COMT:</strong> Dopamine breakdown and stress response</li>
                <li>• <strong>MTR/MTRR:</strong> B12 metabolism and recycling</li>
                <li>• <strong>CBS:</strong> Homocysteine metabolism</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    )
  }

  const methylationGenes = [
    {
      gene: 'MTHFR',
      variant: 'C677T/A1298C',
      status: methylationData?.mthfr_status || 'Unknown',
      impact: 'Folate metabolism',
      description: 'Affects conversion of folate to active methylfolate',
      risk: methylationData?.mthfr_status === 'Variant' ? 'high' : 'low'
    },
    {
      gene: 'COMT',
      variant: 'Val158Met',
      status: methylationData?.comt_status || 'Unknown',
      impact: 'Dopamine metabolism',
      description: 'Affects breakdown of dopamine and stress response',
      risk: methylationData?.comt_status === 'Slow' ? 'moderate' : 'low'
    },
    {
      gene: 'MTR',
      variant: 'A2756G',
      status: methylationData?.mtr_status || 'Unknown',
      impact: 'B12 metabolism',
      description: 'Affects methionine synthase activity',
      risk: 'low'
    },
    {
      gene: 'MTRR',
      variant: 'A66G',
      status: methylationData?.mtrr_status || 'Unknown',
      impact: 'B12 recycling',
      description: 'Affects methionine synthase reductase activity',
      risk: 'low'
    }
  ]

  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'high': return 'text-red-400'
      case 'moderate': return 'text-yellow-400'
      default: return 'text-green-400'
    }
  }

  const getRiskBg = (risk: string) => {
    switch (risk) {
      case 'high': return 'bg-red-500/20'
      case 'moderate': return 'bg-yellow-500/20'
      default: return 'bg-green-500/20'
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8`}>
        <div className="flex items-center space-x-4 mb-6">
          <div className="p-3 bg-gradient-to-br from-purple-500/20 to-pink-500/20 backdrop-blur-xl rounded-xl border border-purple-500/30">
            <Dna className="h-7 w-7 text-purple-400" />
          </div>
          <div>
            <h2 className={`text-2xl font-bold ${textPrimary}`}>
              Methylation Analysis
            </h2>
            <p className={`text-sm ${textSecondary}`}>
              Your genetic methylation capacity and recommendations
            </p>
          </div>
        </div>

        {/* Overall Status */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className={`${glassBackground} border ${borderColor} rounded-xl p-6`}>
            <div className="flex items-center space-x-3 mb-3">
              <TrendingUp className="h-5 w-5 text-blue-400" />
              <span className={`text-sm font-medium ${textSecondary}`}>Overall Capacity</span>
            </div>
            <div className={`text-2xl font-bold ${textPrimary} mb-2`}>
              {methylationData?.overall_methylation_capacity || 'Unknown'}
            </div>
            <div className={`text-xs ${textSecondary}`}>
              Based on key gene variants
            </div>
          </div>

          <div className={`${glassBackground} border ${borderColor} rounded-xl p-6`}>
            <div className="flex items-center space-x-3 mb-3">
              <AlertTriangle className="h-5 w-5 text-yellow-400" />
              <span className={`text-sm font-medium ${textSecondary}`}>Pathways Affected</span>
            </div>
            <div className={`text-2xl font-bold ${textPrimary} mb-2`}>
              {methylationData?.detox_pathways_affected || 0}
            </div>
            <div className={`text-xs ${textSecondary}`}>
              Detoxification pathways impacted
            </div>
          </div>

          <div className={`${glassBackground} border ${borderColor} rounded-xl p-6`}>
            <div className="flex items-center space-x-3 mb-3">
              <CheckCircle className="h-5 w-5 text-green-400" />
              <span className={`text-sm font-medium ${textSecondary}`}>Supplements</span>
            </div>
            <div className={`text-2xl font-bold ${textPrimary} mb-2`}>
              {methylationData?.supplements_recommended?.length || 0}
            </div>
            <div className={`text-xs ${textSecondary}`}>
              Recommended supplements
            </div>
          </div>
        </div>
      </div>

      {/* Gene Analysis */}
      <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8`}>
        <h3 className={`text-xl font-bold ${textPrimary} mb-6`}>
          Key Methylation Genes
        </h3>
        
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {methylationGenes.map((gene, index) => (
            <div key={index} className={`${glassBackground} border ${borderColor} rounded-xl p-6 hover:border-purple-500/50 transition-all duration-300 cursor-pointer`}
                 onClick={() => setSelectedGene(selectedGene === gene.gene ? null : gene.gene)}>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-3">
                  <div className={`w-3 h-3 rounded-full ${getRiskBg(gene.risk)} ${getRiskColor(gene.risk)}`}></div>
                  <h4 className={`text-lg font-bold ${textPrimary}`}>{gene.gene}</h4>
                </div>
                <ChevronRight className={`h-5 w-5 ${textSecondary} transition-transform duration-300 ${selectedGene === gene.gene ? 'rotate-90' : ''}`} />
              </div>
              
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className={`text-sm ${textSecondary}`}>Variant:</span>
                  <span className={`text-sm font-medium ${textPrimary}`}>{gene.variant}</span>
                </div>
                <div className="flex justify-between">
                  <span className={`text-sm ${textSecondary}`}>Status:</span>
                  <span className={`text-sm font-medium ${getRiskColor(gene.risk)}`}>{gene.status}</span>
                </div>
                <div className="flex justify-between">
                  <span className={`text-sm ${textSecondary}`}>Impact:</span>
                  <span className={`text-sm font-medium ${textPrimary}`}>{gene.impact}</span>
                </div>
              </div>

              {selectedGene === gene.gene && (
                <div className={`mt-4 pt-4 border-t ${borderColor}`}>
                  <p className={`text-sm ${textSecondary} leading-relaxed`}>
                    {gene.description}
                  </p>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Recommendations */}
      <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8`}>
        <h3 className={`text-xl font-bold ${textPrimary} mb-6`}>
          Personalized Recommendations
        </h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <h4 className={`text-lg font-semibold ${textPrimary} mb-4`}>Recommended Supplements</h4>
            <div className="space-y-3">
              {(methylationData?.supplements_recommended || ['No specific recommendations available']).map((supplement: string, index: number) => (
                <div key={index} className={`${glassBackground} border ${borderColor} rounded-lg p-4`}>
                  <div className="flex items-center space-x-3">
                    <CheckCircle className="h-5 w-5 text-green-400" />
                    <span className={`font-medium ${textPrimary}`}>{supplement}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
          
          <div>
            <h4 className={`text-lg font-semibold ${textPrimary} mb-4`}>Lifestyle Recommendations</h4>
            <div className="space-y-3">
              {[
                'Reduce alcohol consumption',
                'Manage stress levels',
                'Regular exercise',
                'Adequate sleep (7-9 hours)'
              ].map((recommendation, index) => (
                <div key={index} className={`${glassBackground} border ${borderColor} rounded-lg p-4`}>
                  <div className="flex items-center space-x-3">
                    <Info className="h-5 w-5 text-blue-400" />
                    <span className={`font-medium ${textPrimary}`}>{recommendation}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}