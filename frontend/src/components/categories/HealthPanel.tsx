import React from 'react'
import { Heart, Shield, Pill, AlertTriangle, Activity } from 'lucide-react'
import { getTheme } from '../../utils/theme'

interface AnalysisData {
  summary?: any
  health_risks?: any
  drug_interactions?: any
  recommendations?: string[]
}

interface HealthPanelProps {
  isDarkMode?: boolean
  theme?: any
  data: AnalysisData
}

export default function HealthPanel({ isDarkMode = false, theme, data }: HealthPanelProps) {
  const currentTheme = getTheme(isDarkMode)
  
  const healthRisks = [
    {
      condition: 'Type 2 Diabetes',
      risk: 'Moderate',
      riskScore: 35,
      gene: 'TCF7L2',
      description: 'Genetic variants associated with insulin sensitivity',
      icon: Activity,
      color: `${currentTheme.warning.bg} ${currentTheme.warning.text}`,
      prevention: ['Regular exercise', 'Low glycemic diet', 'Weight management']
    },
    {
      condition: 'Cardiovascular Disease',
      risk: 'Low-Moderate',
      riskScore: 25,
      gene: 'APOE',
      description: 'Favorable lipid metabolism genetics',
      icon: Heart,
      color: `${currentTheme.success.bg} ${currentTheme.success.text}`,
      prevention: ['Heart-healthy diet', 'Regular cardio', 'Stress management']
    },
    {
      condition: 'Hypertension',
      risk: 'Moderate',
      riskScore: 40,
      gene: 'ACE',
      description: 'Genetic predisposition to elevated blood pressure',
      icon: AlertTriangle,
      color: `${currentTheme.warning.bg} ${currentTheme.warning.text}`,
      prevention: ['Low sodium diet', 'Regular exercise', 'Meditation']
    },
    {
      condition: 'Osteoporosis',
      risk: 'Low',
      riskScore: 20,
      gene: 'VDR',
      description: 'Good bone mineral density genetics',
      icon: Shield,
      color: `${currentTheme.categories.wellness.bg} ${currentTheme.categories.wellness.text}`,
      prevention: ['Calcium intake', 'Weight-bearing exercise', 'Vitamin D']
    }
  ]

  const drugResponses = [
    {
      drug: 'Warfarin',
      gene: 'CYP2C9',
      response: 'Sensitive',
      dosage: 'Reduced',
      description: 'Slower metabolism - requires lower doses',
      recommendation: 'Start with 25% lower dose, monitor closely'
    },
    {
      drug: 'Statins',
      gene: 'SLCO1B1',
      response: 'Normal',
      dosage: 'Standard',
      description: 'Normal statin transport and efficacy',
      recommendation: 'Standard dosing protocols apply'
    },
    {
      drug: 'Clopidogrel',
      gene: 'CYP2C19',
      response: 'Enhanced',
      dosage: 'Standard',
      description: 'Good metabolizer - effective antiplatelet action',
      recommendation: 'Standard dose should be effective'
    },
    {
      drug: 'Metformin',
      gene: 'ATM',
      response: 'Good',
      dosage: 'Standard',
      description: 'Expected good response for diabetes management',
      recommendation: 'First-line choice for Type 2 diabetes'
    }
  ]

  const preventiveRecommendations = [
    {
      category: 'Screening Schedule',
      recommendations: [
        'Blood pressure: Every 6 months',
        'Cholesterol: Every 2 years',
        'Blood glucose: Annually',
        'Bone density: Every 5 years after 50'
      ]
    },
    {
      category: 'Lifestyle Priorities',
      recommendations: [
        'Mediterranean diet pattern',
        '150 min moderate exercise weekly',
        'Stress reduction techniques',
        'Quality sleep 7-9 hours'
      ]
    },
    {
      category: 'Supplement Considerations',
      recommendations: [
        'Omega-3 fatty acids',
        'Vitamin D (test levels first)',
        'Magnesium for blood pressure',
        'Probiotics for gut health'
      ]
    }
  ]

  const getRiskColor = (risk: string): string => {
    switch (risk.toLowerCase()) {
      case 'high':
        return currentTheme.error.text
      case 'moderate':
        return currentTheme.warning.text
      case 'low':
        return currentTheme.success.text
      default:
        return currentTheme.text.secondary
    }
  }

  const getRiskBg = (riskScore: number) => {
    if (riskScore >= 50) return 'bg-red-500'
    if (riskScore >= 25) return 'bg-yellow-500'
    return 'bg-green-500'
  }

  const getResponseColor = (response: string) => {
    if (response === 'Sensitive' || response === 'Poor') return 'text-red-600'
    if (response === 'Enhanced' || response === 'Good') return 'text-green-600'
    return 'text-gray-600'
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-xl p-6`}>
        <div className="flex items-center mb-4">
          <Heart className={`h-8 w-8 ${currentTheme.primary.text} mr-3`} />
          <div>
            <h2 className={`text-2xl font-bold ${currentTheme.text.primary}`}>Health & Wellness</h2>
            <p className={`${currentTheme.text.secondary}`}>Your genetic health risks and drug response profile</p>
          </div>
        </div>
      </div>

      {/* Health Risk Assessment */}
      <div className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${currentTheme.text.primary} mb-4`}>Health Risk Assessment</h3>
        <div className="space-y-4">
          {healthRisks.map((risk, index) => {
            const Icon = risk.icon
            return (
              <div key={index} className={`${currentTheme.glassSecondary} border ${currentTheme.glassBorder} rounded-lg p-4`}>
                <div className="flex items-start space-x-4">
                  <div className={`p-3 rounded-lg ${risk.color}`}>
                    <Icon className="h-6 w-6" />
                  </div>
                  <div className="flex-1">
                    <div className="flex justify-between items-start mb-3">
                      <div>
                        <h4 className={`font-medium ${currentTheme.text.primary} text-lg`}>{risk.condition}</h4>
                        <p className={`text-sm font-medium ${getRiskColor(risk.risk)}`}>{risk.risk} Risk</p>
                      </div>
                      <div className="text-right">
                        <span className={`text-xs ${currentTheme.text.secondary}`}>{risk.gene}</span>
                      </div>
                    </div>
                    <div className="mb-3">
                      <div className={`w-full rounded-full h-2 ${currentTheme.glassSecondary}`}>
                        <div 
                          className={`h-2 rounded-full ${getRiskBg(risk.riskScore)}`}
                          style={{ width: `${risk.riskScore}%` }}
                        ></div>
                      </div>
                      <p className={`text-xs ${currentTheme.text.muted} mt-1`}>{risk.riskScore}% lifetime risk</p>
                    </div>
                    <p className={`text-sm ${currentTheme.text.secondary} mb-3`}>{risk.description}</p>
                    <div className={`${currentTheme.categories.wellness.bg} p-3 rounded-lg`}>
                      <h5 className={`text-sm font-medium ${currentTheme.categories.wellness.text} mb-1`}>Prevention Strategies:</h5>
                      <ul className={`text-sm ${currentTheme.categories.wellness.text}`}>
                        {risk.prevention.map((strategy, strategyIndex) => (
                          <li key={strategyIndex}>• {strategy}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Drug Response */}
      <div className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${currentTheme.text.primary} mb-4`}>Pharmacogenomics - Drug Response</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {drugResponses.map((drug, index) => (
            <div key={index} className={`${currentTheme.glassSecondary} border ${currentTheme.glassBorder} rounded-lg p-4`}>
              <div className="flex justify-between items-start mb-2">
                <h4 className={`font-medium ${currentTheme.text.primary}`}>{drug.drug}</h4>
                <span className={`text-xs px-2 py-1 rounded ${currentTheme.glassSecondary} ${currentTheme.text.secondary}`}>
                  {drug.gene}
                </span>
              </div>
              <div className="mb-2">
                <span className={`text-sm font-medium ${getResponseColor(drug.response)}`}>
                  {drug.response} Response
                </span>
                <span className={`text-sm ${currentTheme.text.secondary} ml-2`}>({drug.dosage} Dosage)</span>
              </div>
              <p className={`text-xs ${currentTheme.text.secondary} mb-3`}>{drug.description}</p>
              <div className={`${currentTheme.warning.bg} p-2 rounded text-xs ${currentTheme.warning.text}`}>
                🏥 {drug.recommendation}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Preventive Recommendations */}
      <div className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${currentTheme.text.primary} mb-4`}>Preventive Health Recommendations</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {preventiveRecommendations.map((category, index) => (
            <div key={index} className="space-y-3">
              <h4 className={`font-medium ${currentTheme.text.primary}`}>{category.category}</h4>
              <div className="space-y-2">
                {category.recommendations.map((rec, recIndex) => (
                  <div key={recIndex} className={`p-2 rounded text-sm ${currentTheme.glassSecondary} ${currentTheme.text.secondary}`}>
                    • {rec}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Health Score Summary */}
      <div className={`${currentTheme.glass} border ${currentTheme.glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${currentTheme.text.primary} mb-4`}>Overall Health Profile</h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className={`text-center p-4 ${currentTheme.success.bg} rounded-lg`}>
            <div className={`text-2xl font-bold ${currentTheme.success.text} mb-1`}>78</div>
            <div className={`text-sm font-medium ${currentTheme.success.text}`}>Genetic Health Score</div>
            <div className={`text-xs ${currentTheme.success.text}`}>Above Average</div>
          </div>
          <div className={`text-center p-4 ${currentTheme.categories.ancestry.bg} rounded-lg`}>
            <div className={`text-2xl font-bold ${currentTheme.categories.ancestry.text} mb-1`}>85%</div>
            <div className={`text-sm font-medium ${currentTheme.categories.ancestry.text}`}>Drug Compatibility</div>
            <div className={`text-xs ${currentTheme.categories.ancestry.text}`}>Most drugs effective</div>
          </div>
          <div className={`text-center p-4 ${currentTheme.warning.bg} rounded-lg`}>
            <div className={`text-2xl font-bold ${currentTheme.warning.text} mb-1`}>3</div>
            <div className={`text-sm font-medium ${currentTheme.warning.text}`}>Risk Factors</div>
            <div className={`text-xs ${currentTheme.warning.text}`}>Moderate monitoring</div>
          </div>
          <div className={`text-center p-4 ${currentTheme.categories.wellness.bg} rounded-lg`}>
            <div className={`text-2xl font-bold ${currentTheme.categories.wellness.text} mb-1`}>92%</div>
            <div className={`text-sm font-medium ${currentTheme.categories.wellness.text}`}>Prevention Potential</div>
            <div className={`text-xs ${currentTheme.categories.wellness.text}`}>High lifestyle impact</div>
          </div>
        </div>
      </div>

      {/* Important Disclaimer */}
      <div className={`${currentTheme.warning.bg} border ${currentTheme.warning.border} rounded-xl p-6`}>
        <div className="flex items-start space-x-3">
          <AlertTriangle className={`h-6 w-6 ${currentTheme.warning.text} mt-0.5 flex-shrink-0`} />
          <div>
            <h4 className={`font-medium ${currentTheme.warning.text} mb-2`}>Medical Disclaimer</h4>
            <p className={`${currentTheme.warning.text} text-sm`}>
              This genetic analysis is for informational purposes only and should not replace professional medical advice. 
              Always consult with qualified healthcare providers before making medical decisions or changing treatments 
              based on genetic information. Genetic predisposition does not guarantee disease development.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}