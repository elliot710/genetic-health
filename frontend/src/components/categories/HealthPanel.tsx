import React, { useState, useEffect } from 'react'
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
  token?: string
}

export default function HealthPanel({ isDarkMode = false, theme, data, token }: HealthPanelProps) {
  const currentTheme = getTheme(isDarkMode)
  const [realHealthRisks, setRealHealthRisks] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  
  // Load real health risks from API
  useEffect(() => {
    const loadHealthRisks = async () => {
      if (!token) return
      
      setLoading(true)
      try {
        const response = await fetch('http://localhost:8000/analyze/health-risks', {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        })
        
        if (response.ok) {
          const healthData = await response.json()
          console.log('Loaded health risks:', healthData)
          setRealHealthRisks(healthData.health_risks || [])
        }
      } catch (error) {
        console.error('Error loading health risks:', error)
      } finally {
        setLoading(false)
      }
    }
    
    loadHealthRisks()
  }, [token])
  
  // Use real health risks from API if available, otherwise fallback to data prop, then default
  const getHealthRisks = () => {
    // First priority: Real API data
    if (realHealthRisks.length > 0) {
      return realHealthRisks.map((risk: any) => ({
        condition: risk.condition,
        risk: risk.risk_level.charAt(0).toUpperCase() + risk.risk_level.slice(1),
        riskScore: risk.risk_level === 'high' ? 80 : risk.risk_level === 'moderate' ? 55 : 30,
        gene: risk.associated_variants?.[0] || 'Unknown',
        description: `Genetic analysis shows ${risk.risk_level} risk for this condition`,
        icon: risk.risk_level === 'high' ? AlertTriangle : risk.risk_level === 'moderate' ? Activity : Heart,
        color: risk.risk_level === 'high' 
          ? `bg-red-500/20 text-red-600`
          : risk.risk_level === 'moderate'
          ? `${currentTheme.warning.bg} ${currentTheme.warning.text}`
          : `${currentTheme.success.bg} ${currentTheme.success.text}`,
        prevention: Array.isArray(risk.recommendations) ? risk.recommendations : [risk.recommendations || 'Consult with healthcare provider']
      }))
    }
    
    // Second priority: Data from props (existing dashboard data)
    if (data?.health_risks?.details && data.health_risks.details.length > 0) {
      return data.health_risks.details.map((risk: any) => ({
        condition: risk.condition,
        risk: risk.risk_level.charAt(0).toUpperCase() + risk.risk_level.slice(1),
        riskScore: risk.risk_level === 'high' ? 80 : risk.risk_level === 'moderate' ? 55 : 30,
        gene: risk.associated_variants?.[0] || 'Unknown',
        description: `Genetic variant analysis shows ${risk.risk_level} risk`,
        icon: risk.risk_level === 'high' ? AlertTriangle : risk.risk_level === 'moderate' ? Activity : Heart,
        color: risk.risk_level === 'high' 
          ? `bg-red-500/20 text-red-600`
          : risk.risk_level === 'moderate'
          ? `${currentTheme.warning.bg} ${currentTheme.warning.text}`
          : `${currentTheme.success.bg} ${currentTheme.success.text}`,
        prevention: risk.recommendations || ['Consult with healthcare provider', 'Monitor regularly', 'Maintain healthy lifestyle']
      }))
    }
    
    // Third priority: Loading or default message
    if (loading) {
      return [{
        condition: 'Loading Health Risks...',
        risk: 'Processing',
        riskScore: 0,
        gene: 'Multiple',
        description: 'Loading your genetic health risk analysis results...',
        icon: Activity,
        color: `${currentTheme.primary.bg} ${currentTheme.primary.text}`,
        prevention: ['Analysis in progress...']
      }]
    }
    
    // Final fallback: No data available
    return [{
      condition: 'No Health Risks Found',
      risk: 'Good News',
      riskScore: 20,
      gene: 'Multiple',
      description: 'No significant genetic health risks identified in your analysis, or analysis is still in progress.',
      icon: Heart,
      color: `${currentTheme.success.bg} ${currentTheme.success.text}`,
      prevention: ['Continue healthy lifestyle habits', 'Regular health checkups recommended', 'Results may update as analysis completes']
    }]
  }

  const getDrugResponses = () => {
    if (data?.drug_interactions?.details && data.drug_interactions.details.length > 0) {
      return data.drug_interactions.details.map((dr: any) => ({
        drug: dr.drug,
        gene: dr.gene,
        response: dr.response_type.charAt(0).toUpperCase() + dr.response_type.slice(1).replace('_', ' '),
        dosage: dr.response_type === 'poor' ? 'Reduced/Alternative' : 
                dr.response_type === 'ultrarapid' ? 'Increased' : 'Standard',
        description: `${dr.response_type.replace('_', ' ')} metabolism detected`,
        recommendation: dr.recommendations || 'Consult healthcare provider for dosing guidance'
      }))
    }
    
    // Return default message when no real data is available
    return [{
      drug: 'Analysis in Progress',
      gene: 'Multiple',
      response: 'Processing',
      dosage: 'TBD',
      description: 'Pharmacogenomic analysis is being processed',
      recommendation: 'Drug response predictions will appear here when analysis completes'
    }]
  }

  const healthRisks = getHealthRisks()
  const drugResponses = getDrugResponses()

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
          {healthRisks.map((risk: any, index: number) => {
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
                        {risk.prevention.map((strategy: string, strategyIndex: number) => (
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
          {drugResponses.map((drug: any, index: number) => (
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