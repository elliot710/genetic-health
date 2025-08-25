'use client'

import { useState } from 'react'
import { AlertTriangle, Shield, FileText, Users, Clock, ChevronRight, Info } from 'lucide-react'
import { getGlassBackground, getTextPrimary, getTextSecondary } from '../../utils/theme'

interface RareMutationsPanelProps {
  data: any
  isDarkMode: boolean
  theme?: any
}

export default function RareMutationsPanel({ data, isDarkMode, theme }: RareMutationsPanelProps) {
  const [selectedMutation, setSelectedMutation] = useState<string | null>(null)

  // Check if rare mutation data is available from the database
  const hasRealData = data?.rare_mutations && data.rare_mutations.length > 0
  const rareMutationData = hasRealData ? data.rare_mutations : []

  const glassBackground = getGlassBackground(isDarkMode)
  const textPrimary = getTextPrimary(isDarkMode)
  const textSecondary = getTextSecondary(isDarkMode)
  const borderColor = isDarkMode ? 'border-gray-700/50' : 'border-gray-200/50'

  const getSignificanceColor = (significance: string) => {
    switch (significance.toLowerCase()) {
      case 'very_high':
        return isDarkMode ? 'text-red-400 bg-red-500/20 border-red-500/30' : 'text-red-700 bg-red-100/80 border-red-200'
      case 'high':
        return isDarkMode ? 'text-orange-400 bg-orange-500/20 border-orange-500/30' : 'text-orange-700 bg-orange-100/80 border-orange-200'
      case 'moderate':
        return isDarkMode ? 'text-yellow-400 bg-yellow-500/20 border-yellow-500/30' : 'text-yellow-700 bg-yellow-100/80 border-yellow-200'
      default:
        return isDarkMode ? 'text-gray-400 bg-gray-500/20 border-gray-500/30' : 'text-gray-700 bg-gray-100/80 border-gray-200'
    }
  }

  const getPenetranceColor = (penetrance: string) => {
    switch (penetrance.toLowerCase()) {
      case 'very_high':
        return isDarkMode ? 'text-red-300' : 'text-red-600'
      case 'high':
        return isDarkMode ? 'text-orange-300' : 'text-orange-600'
      case 'moderate':
        return isDarkMode ? 'text-yellow-300' : 'text-yellow-600'
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
            <div className="p-3 bg-gradient-to-br from-red-500/20 to-orange-500/20 backdrop-blur-xl rounded-xl border border-red-500/30">
              <AlertTriangle className="h-7 w-7 text-red-400" />
            </div>
            <div>
              <h2 className={`text-2xl font-bold ${textPrimary}`}>
                Rare Mutations Analysis
              </h2>
              <p className={`text-sm ${textSecondary}`}>
                High-impact genetic variants requiring clinical attention
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
                No Rare Mutations Detected
              </h3>
              <p className={`${textSecondary} max-w-md mx-auto`}>
                Great news! Our analysis did not identify any rare genetic mutations 
                with high clinical significance in your genetic data. This is a positive finding.
              </p>
            </div>
          </div>
        </div>

        {/* Information Panel */}
        <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8`}>
          <h3 className={`text-xl font-bold ${textPrimary} mb-6`}>
            About Rare Mutations Analysis
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 className={`text-lg font-semibold ${textPrimary} mb-4`}>What are Rare Mutations?</h4>
              <p className={`${textSecondary} leading-relaxed`}>
                Rare mutations are genetic variants found in less than 0.1% of the population 
                that can have significant health implications. These mutations often affect 
                critical genes and may predispose individuals to hereditary diseases or syndromes.
              </p>
            </div>
            <div>
              <h4 className={`text-lg font-semibold ${textPrimary} mb-4`}>Clinical Significance</h4>
              <p className={`${textSecondary} leading-relaxed`}>
                Our analysis screens for pathogenic and likely pathogenic variants in genes 
                associated with hereditary cancer syndromes, metabolic disorders, and other 
                high-penetrance genetic conditions that may require medical management.
              </p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Show rare mutations data
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8`}>
        <div className="flex items-center space-x-4 mb-6">
          <div className="p-3 bg-gradient-to-br from-red-500/20 to-orange-500/20 backdrop-blur-xl rounded-xl border border-red-500/30">
            <AlertTriangle className="h-7 w-7 text-red-400" />
          </div>
          <div>
            <h2 className={`text-2xl font-bold ${textPrimary}`}>
              Rare Mutations Analysis
            </h2>
            <p className={`text-sm ${textSecondary}`}>
              {rareMutationData.length} rare mutation{rareMutationData.length !== 1 ? 's' : ''} detected requiring clinical attention
            </p>
          </div>
        </div>

        {/* Summary Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className={`${glassBackground} border ${borderColor} rounded-xl p-4`}>
            <div className="flex items-center space-x-3">
              <AlertTriangle className="h-5 w-5 text-red-400" />
              <div>
                <p className={`text-sm ${textSecondary}`}>Very High Significance</p>
                <p className={`text-lg font-bold ${textPrimary}`}>
                  {rareMutationData.filter(m => m.clinical_significance === 'very_high').length}
                </p>
              </div>
            </div>
          </div>
          <div className={`${glassBackground} border ${borderColor} rounded-xl p-4`}>
            <div className="flex items-center space-x-3">
              <Users className="h-5 w-5 text-blue-400" />
              <div>
                <p className={`text-sm ${textSecondary}`}>Family Screening</p>
                <p className={`text-lg font-bold ${textPrimary}`}>
                  {rareMutationData.filter(m => m.family_screening_recommended).length}
                </p>
              </div>
            </div>
          </div>
          <div className={`${glassBackground} border ${borderColor} rounded-xl p-4`}>
            <div className="flex items-center space-x-3">
              <FileText className="h-5 w-5 text-green-400" />
              <div>
                <p className={`text-sm ${textSecondary}`}>Counseling Needed</p>
                <p className={`text-lg font-bold ${textPrimary}`}>
                  {rareMutationData.filter(m => m.genetic_counseling_urgent).length}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Mutations List */}
      <div className={`${glassBackground} border ${borderColor} rounded-2xl p-8`}>
        <h3 className={`text-xl font-bold ${textPrimary} mb-6`}>
          Detected Rare Mutations
        </h3>
        <div className="space-y-4">
          {rareMutationData.map((mutation: any, index: number) => (
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
                    <strong>Disease Association:</strong> {mutation.disease_association}
                  </p>
                  <div className="flex items-center space-x-6 text-sm">
                    <span className={`${getPenetranceColor(mutation.penetrance)}`}>
                      <strong>Penetrance:</strong> {mutation.penetrance.replace('_', ' ')}
                    </span>
                    <span className={textSecondary}>
                      <strong>Inheritance:</strong> {mutation.inheritance_pattern.replace('_', ' ')}
                    </span>
                    <span className={textSecondary}>
                      <strong>Frequency:</strong> {(mutation.population_frequency * 100).toFixed(3)}%
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
                    {/* Clinical Actions */}
                    <div>
                      <h5 className={`text-md font-semibold ${textPrimary} mb-3 flex items-center`}>
                        <FileText className="h-4 w-4 mr-2 text-blue-400" />
                        Clinical Actions Required
                      </h5>
                      <ul className="space-y-2">
                        {mutation.clinical_actions.map((action: string, idx: number) => (
                          <li key={idx} className={`text-sm ${textSecondary} flex items-start`}>
                            <span className="text-blue-400 mr-2">•</span>
                            {action}
                          </li>
                        ))}
                      </ul>
                    </div>

                    {/* Monitoring Recommendations */}
                    <div>
                      <h5 className={`text-md font-semibold ${textPrimary} mb-3 flex items-center`}>
                        <Clock className="h-4 w-4 mr-2 text-orange-400" />
                        Monitoring Recommendations
                      </h5>
                      <ul className="space-y-2">
                        {mutation.monitoring_recommendations.map((rec: string, idx: number) => (
                          <li key={idx} className={`text-sm ${textSecondary} flex items-start`}>
                            <span className="text-orange-400 mr-2">•</span>
                            {rec}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  {/* Important Notices */}
                  <div className="mt-6 p-4 bg-gradient-to-r from-red-500/10 to-orange-500/10 rounded-xl border border-red-500/20">
                    <div className="flex items-start space-x-3">
                      <AlertTriangle className="h-5 w-5 text-red-400 mt-0.5" />
                      <div>
                        <h6 className={`font-semibold ${textPrimary} mb-2`}>
                          Important Clinical Considerations
                        </h6>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                          {mutation.genetic_counseling_urgent && (
                            <div className={textSecondary}>
                              <strong className="text-red-400">Urgent:</strong> Genetic counseling consultation recommended
                            </div>
                          )}
                          {mutation.family_screening_recommended && (
                            <div className={textSecondary}>
                              <strong className="text-blue-400">Family:</strong> Cascade testing for family members advised
                            </div>
                          )}
                          {mutation.specialist_referral && (
                            <div className={textSecondary}>
                              <strong className="text-green-400">Referral:</strong> Specialist consultation indicated
                            </div>
                          )}
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

      {/* Clinical Disclaimer */}
      <div className={`${glassBackground} border ${borderColor} rounded-2xl p-6`}>
        <div className="flex items-start space-x-3">
          <Info className="h-6 w-6 text-blue-400 mt-1" />
          <div>
            <h4 className={`text-lg font-semibold ${textPrimary} mb-2`}>
              Important Medical Disclaimer
            </h4>
            <p className={`${textSecondary} text-sm leading-relaxed`}>
              This analysis identifies potentially significant genetic variants but is not a diagnostic test. 
              All findings require confirmation through clinical genetic testing and interpretation by qualified 
              medical professionals. Please consult with a genetic counselor or physician before making any 
              medical decisions based on these results.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}