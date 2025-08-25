'use client'

import { useState } from 'react'
import { Shield, Zap, AlertTriangle, CheckCircle, Flame, ChevronRight } from 'lucide-react'
import { getGlassBackground, getTextPrimary, getTextSecondary } from '../../utils/theme'

interface DetoxPanelProps {
  data: any
  isDarkMode: boolean
  theme?: any
}

export default function DetoxPanel({ data, isDarkMode, theme }: DetoxPanelProps) {
  const [selectedPhase, setSelectedPhase] = useState<string | null>(null)

  // Check if detoxification data is available from the database
  const hasRealData = data?.detoxification_profiles && data.detoxification_profiles.length > 0
  const detoxData = hasRealData ? data.detoxification_profiles[0] : null

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
            <div className="p-3 bg-gradient-to-br from-green-500/20 to-blue-500/20 backdrop-blur-xl rounded-xl border border-green-500/30">
              <Shield className="h-7 w-7 text-green-400" />
            </div>
            <div>
              <h2 className={`text-2xl font-bold ${textPrimary}`}>
                Detoxification Analysis
              </h2>
              <p className={`text-sm ${textSecondary}`}>
                Your genetic detoxification capacity and support needs
              </p>
            </div>
          </div>
        </div>

        {/* No Data Available */}
        <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8 text-center`}>
          <div className="flex flex-col items-center space-y-4">
            <div className="p-4 bg-gradient-to-br from-green-500/20 to-blue-500/20 backdrop-blur-xl rounded-xl border border-green-500/30">
              <Shield className="h-8 w-8 text-green-400" />
            </div>
            <div>
              <h3 className={`text-xl font-bold ${textPrimary} mb-2`}>
                Detoxification Analysis in Progress
              </h3>
              <p className={`${textSecondary} max-w-md mx-auto`}>
                Detoxification pathway analysis is not yet available for your genetic data. 
                This analysis requires specific genetic variants that may be added in future updates.
              </p>
            </div>
          </div>
        </div>

        {/* Information Panel */}
        <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8`}>
          <h3 className={`text-xl font-bold ${textPrimary} mb-6`}>
            About Detoxification Analysis
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <h4 className={`text-lg font-semibold ${textPrimary} mb-4`}>Phase I Detox</h4>
              <p className={`${textSecondary} leading-relaxed`}>
                Phase I detoxification involves cytochrome P450 enzymes that convert toxins 
                into intermediate metabolites through oxidation, reduction, and hydrolysis reactions.
              </p>
            </div>
            <div>
              <h4 className={`text-lg font-semibold ${textPrimary} mb-4`}>Phase II Detox</h4>
              <p className={`${textSecondary} leading-relaxed`}>
                Phase II conjugation reactions neutralize Phase I metabolites through 
                glucuronidation, sulfation, and glutathione conjugation pathways.
              </p>
            </div>
            <div>
              <h4 className={`text-lg font-semibold ${textPrimary} mb-4`}>Phase III Detox</h4>
              <p className={`${textSecondary} leading-relaxed`}>
                Phase III elimination involves transport proteins that move conjugated 
                toxins out of cells for final elimination from the body.
              </p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  const detoxPhases = [
    {
      phase: 'Phase I',
      name: 'Oxidation',
      capacity: detoxData?.phase1_capacity || 'Unknown',
      genes: ['CYP1A1', 'CYP1A2', 'CYP2E1', 'CYP3A4'],
      description: 'Converts toxins into intermediate metabolites using cytochrome P450 enzymes',
      function: 'Oxidation, reduction, hydrolysis',
      risk: detoxData?.phase1_capacity === 'Fast' ? 'moderate' : 'low'
    },
    {
      phase: 'Phase II',
      name: 'Conjugation',
      capacity: detoxData?.phase2_capacity || 'Unknown',
      genes: ['GSTM1', 'GSTT1', 'GSTP1', 'UGT1A1', 'SULT1A1'],
      description: 'Neutralizes Phase I metabolites through conjugation reactions',
      function: 'Glucuronidation, sulfation, glutathione conjugation',
      risk: detoxData?.phase2_capacity === 'Slow' ? 'high' : 'low'
    },
    {
      phase: 'Phase III',
      name: 'Elimination',
      capacity: detoxData?.phase3_capacity || 'Unknown',
      genes: ['ABCB1', 'ABCC2', 'ABCG2'],
      description: 'Transports conjugated toxins out of cells for elimination',
      function: 'Active transport, elimination',
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

  const getCapacityColor = (capacity: string) => {
    switch (capacity.toLowerCase()) {
      case 'fast': return 'text-orange-400'
      case 'slow': return 'text-red-400'
      default: return 'text-green-400'
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8`}>
        <div className="flex items-center space-x-4 mb-6">
          <div className="p-3 bg-gradient-to-br from-green-500/20 to-blue-500/20 backdrop-blur-xl rounded-xl border border-green-500/30">
            <Shield className="h-7 w-7 text-green-400" />
          </div>
          <div>
            <h2 className={`text-2xl font-bold ${textPrimary}`}>
              Detoxification Analysis
            </h2>
            <p className={`text-sm ${textSecondary}`}>
              Your genetic detoxification capacity and support needs
            </p>
          </div>
        </div>

        {/* Overall Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div className={`${glassBackground} border ${borderColor} rounded-xl p-6`}>
            <div className="flex items-center space-x-3 mb-3">
              <Zap className="h-5 w-5 text-blue-400" />
              <span className={`text-sm font-medium ${textSecondary}`}>Detox Score</span>
            </div>
            <div className={`text-2xl font-bold ${textPrimary} mb-2`}>
              {detoxData?.overall_detox_score || 'N/A'}/100
            </div>
            <div className={`text-xs ${textSecondary}`}>
              Overall capacity
            </div>
          </div>

          <div className={`${glassBackground} border ${borderColor} rounded-xl p-6`}>
            <div className="flex items-center space-x-3 mb-3">
              <Flame className="h-5 w-5 text-orange-400" />
              <span className={`text-sm font-medium ${textSecondary}`}>Phase I</span>
            </div>
            <div className={`text-lg font-bold ${getCapacityColor(detoxData?.phase1_capacity || 'Unknown')} mb-2`}>
              {detoxData?.phase1_capacity || 'Unknown'}
            </div>
            <div className={`text-xs ${textSecondary}`}>
              Oxidation capacity
            </div>
          </div>

          <div className={`${glassBackground} border ${borderColor} rounded-xl p-6`}>
            <div className="flex items-center space-x-3 mb-3">
              <Shield className="h-5 w-5 text-green-400" />
              <span className={`text-sm font-medium ${textSecondary}`}>Phase II</span>
            </div>
            <div className={`text-lg font-bold ${getCapacityColor(detoxData?.phase2_capacity || 'Unknown')} mb-2`}>
              {detoxData?.phase2_capacity || 'Unknown'}
            </div>
            <div className={`text-xs ${textSecondary}`}>
              Conjugation capacity
            </div>
          </div>

          <div className={`${glassBackground} border ${borderColor} rounded-xl p-6`}>
            <div className="flex items-center space-x-3 mb-3">
              <AlertTriangle className="h-5 w-5 text-yellow-400" />
              <span className={`text-sm font-medium ${textSecondary}`}>Sensitivity</span>
            </div>
            <div className={`text-lg font-bold ${textPrimary} mb-2`}>
              {detoxData?.toxin_sensitivity || 'Unknown'}
            </div>
            <div className={`text-xs ${textSecondary}`}>
              To environmental toxins
            </div>
          </div>
        </div>
      </div>

      {/* Detox Phases */}
      <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8`}>
        <h3 className={`text-xl font-bold ${textPrimary} mb-6`}>
          Detoxification Phases
        </h3>
        
        <div className="space-y-4">
          {detoxPhases.map((phase, index) => (
            <div key={index} className={`${glassBackground} border ${borderColor} rounded-xl p-6 hover:border-green-500/50 transition-all duration-300 cursor-pointer`}
                 onClick={() => setSelectedPhase(selectedPhase === phase.phase ? null : phase.phase)}>
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-4">
                  <div className={`w-4 h-4 rounded-full ${getRiskBg(phase.risk)} ${getRiskColor(phase.risk)}`}></div>
                  <div>
                    <h4 className={`text-lg font-bold ${textPrimary}`}>{phase.phase} - {phase.name}</h4>
                    <p className={`text-sm ${textSecondary}`}>{phase.function}</p>
                  </div>
                </div>
                <div className="flex items-center space-x-3">
                  <span className={`text-sm font-medium ${getCapacityColor(phase.capacity)}`}>
                    {phase.capacity}
                  </span>
                  <ChevronRight className={`h-5 w-5 ${textSecondary} transition-transform duration-300 ${selectedPhase === phase.phase ? 'rotate-90' : ''}`} />
                </div>
              </div>

              {selectedPhase === phase.phase && (
                <div className={`mt-4 pt-4 border-t ${borderColor} space-y-4`}>
                  <p className={`text-sm ${textSecondary} leading-relaxed`}>
                    {phase.description}
                  </p>
                  
                  <div>
                    <h5 className={`text-sm font-semibold ${textPrimary} mb-2`}>Key Genes:</h5>
                    <div className="flex flex-wrap gap-2">
                      {phase.genes.map((gene, geneIndex) => (
                        <span key={geneIndex} className={`px-3 py-1 ${glassBackground} border ${borderColor} rounded-full text-xs font-medium ${textPrimary}`}>
                          {gene}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Risk Genes */}
      <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8`}>
        <h3 className={`text-xl font-bold ${textPrimary} mb-6`}>
          Risk Gene Variants
        </h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {(detoxData?.risk_genes || ['No specific risk genes identified']).map((gene: string, index: number) => (
            <div key={index} className={`${glassBackground} border ${borderColor} rounded-xl p-6`}>
              <div className="flex items-center space-x-3 mb-3">
                <AlertTriangle className="h-5 w-5 text-red-400" />
                <h4 className={`text-lg font-bold ${textPrimary}`}>{gene}</h4>
              </div>
              <p className={`text-sm ${textSecondary} mb-3`}>
                {gene === 'No specific risk genes identified' 
                  ? 'Analysis in progress or no significant variants found'
                  : 'Null variant detected - reduced detoxification capacity'
                }
              </p>
              <div className={`px-3 py-1 ${gene === 'No specific risk genes identified' ? 'bg-blue-500/20 text-blue-400' : 'bg-red-500/20 text-red-400'} rounded-full text-xs font-medium inline-block`}>
                {gene === 'No specific risk genes identified' ? 'Analysis Pending' : 'High Risk'}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Recommendations */}
      <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8`}>
        <h3 className={`text-xl font-bold ${textPrimary} mb-6`}>
          Detox Support Recommendations
        </h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <h4 className={`text-lg font-semibold ${textPrimary} mb-4`}>Recommended Supplements</h4>
            <div className="space-y-3">
              {(detoxData?.recommended_support || ['No specific recommendations available']).map((supplement: string, index: number) => (
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
                'Reduce exposure to environmental toxins',
                'Support liver health with cruciferous vegetables',
                'Stay well hydrated',
                'Regular sauna or sweating',
                'Avoid alcohol and processed foods'
              ].map((recommendation, index) => (
                <div key={index} className={`${glassBackground} border ${borderColor} rounded-lg p-4`}>
                  <div className="flex items-center space-x-3">
                    <Zap className="h-5 w-5 text-blue-400" />
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