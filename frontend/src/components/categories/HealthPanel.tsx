import React from 'react'
import { Heart, Shield, Pill, AlertTriangle, Activity } from 'lucide-react'

interface AnalysisData {
  summary?: any
  health_risks?: any
  drug_interactions?: any
  recommendations?: string[]
}

interface HealthPanelProps {
  data: AnalysisData
}

export default function HealthPanel({ data }: HealthPanelProps) {
  const healthRisks = [
    {
      condition: 'Type 2 Diabetes',
      risk: 'Moderate',
      riskScore: 35,
      gene: 'TCF7L2',
      description: 'Genetic variants associated with insulin sensitivity',
      icon: Activity,
      color: 'bg-yellow-50 text-yellow-700',
      prevention: ['Regular exercise', 'Low glycemic diet', 'Weight management']
    },
    {
      condition: 'Cardiovascular Disease',
      risk: 'Low-Moderate',
      riskScore: 25,
      gene: 'APOE',
      description: 'Favorable lipid metabolism genetics',
      icon: Heart,
      color: 'bg-green-50 text-green-700',
      prevention: ['Heart-healthy diet', 'Regular cardio', 'Stress management']
    },
    {
      condition: 'Hypertension',
      risk: 'Moderate',
      riskScore: 40,
      gene: 'ACE',
      description: 'Genetic predisposition to elevated blood pressure',
      icon: AlertTriangle,
      color: 'bg-orange-50 text-orange-700',
      prevention: ['Low sodium diet', 'Regular exercise', 'Meditation']
    },
    {
      condition: 'Osteoporosis',
      risk: 'Low',
      riskScore: 20,
      gene: 'VDR',
      description: 'Good bone mineral density genetics',
      icon: Shield,
      color: 'bg-blue-50 text-blue-700',
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

  const getRiskColor = (risk: string) => {
    if (risk.includes('High')) return 'text-red-600'
    if (risk.includes('Moderate')) return 'text-yellow-600'
    return 'text-green-600'
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
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <div className="flex items-center mb-4">
          <Heart className="h-8 w-8 text-teal-600 mr-3" />
          <div>
            <h2 className="text-2xl font-bold text-gray-900">Health & Wellness</h2>
            <p className="text-gray-600">Your genetic health risks and drug response profile</p>
          </div>
        </div>
      </div>

      {/* Health Risk Assessment */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Health Risk Assessment</h3>
        <div className="space-y-4">
          {healthRisks.map((risk, index) => {
            const Icon = risk.icon
            return (
              <div key={index} className="border rounded-lg p-4">
                <div className="flex items-start space-x-4">
                  <div className={`p-3 rounded-lg ${risk.color}`}>
                    <Icon className="h-6 w-6" />
                  </div>
                  <div className="flex-1">
                    <div className="flex justify-between items-start mb-3">
                      <div>
                        <h4 className="font-medium text-gray-900 text-lg">{risk.condition}</h4>
                        <p className={`text-sm font-medium ${getRiskColor(risk.risk)}`}>{risk.risk} Risk</p>
                      </div>
                      <div className="text-right">
                        <span className="text-xs text-gray-500">{risk.gene}</span>
                      </div>
                    </div>
                    <div className="mb-3">
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div 
                          className={`h-2 rounded-full ${getRiskBg(risk.riskScore)}`}
                          style={{ width: `${risk.riskScore}%` }}
                        ></div>
                      </div>
                      <p className="text-xs text-gray-500 mt-1">{risk.riskScore}% lifetime risk</p>
                    </div>
                    <p className="text-sm text-gray-600 mb-3">{risk.description}</p>
                    <div className="bg-blue-50 p-3 rounded-lg">
                      <h5 className="text-sm font-medium text-blue-900 mb-1">Prevention Strategies:</h5>
                      <ul className="text-sm text-blue-700">
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
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Pharmacogenomics - Drug Response</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {drugResponses.map((drug, index) => (
            <div key={index} className="border rounded-lg p-4">
              <div className="flex justify-between items-start mb-2">
                <h4 className="font-medium text-gray-900">{drug.drug}</h4>
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded">
                  {drug.gene}
                </span>
              </div>
              <div className="mb-2">
                <span className={`text-sm font-medium ${getResponseColor(drug.response)}`}>
                  {drug.response} Response
                </span>
                <span className="text-sm text-gray-600 ml-2">({drug.dosage} Dosage)</span>
              </div>
              <p className="text-xs text-gray-600 mb-3">{drug.description}</p>
              <div className="bg-yellow-50 p-2 rounded text-xs text-yellow-800">
                🏥 {drug.recommendation}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Preventive Recommendations */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Preventive Health Recommendations</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {preventiveRecommendations.map((category, index) => (
            <div key={index} className="space-y-3">
              <h4 className="font-medium text-gray-900">{category.category}</h4>
              <div className="space-y-2">
                {category.recommendations.map((rec, recIndex) => (
                  <div key={recIndex} className="p-2 bg-gray-50 rounded text-sm text-gray-700">
                    • {rec}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Health Score Summary */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Overall Health Profile</h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="text-center p-4 bg-green-50 rounded-lg">
            <div className="text-2xl font-bold text-green-600 mb-1">78</div>
            <div className="text-sm font-medium text-green-900">Genetic Health Score</div>
            <div className="text-xs text-green-700">Above Average</div>
          </div>
          <div className="text-center p-4 bg-blue-50 rounded-lg">
            <div className="text-2xl font-bold text-blue-600 mb-1">85%</div>
            <div className="text-sm font-medium text-blue-900">Drug Compatibility</div>
            <div className="text-xs text-blue-700">Most drugs effective</div>
          </div>
          <div className="text-center p-4 bg-yellow-50 rounded-lg">
            <div className="text-2xl font-bold text-yellow-600 mb-1">3</div>
            <div className="text-sm font-medium text-yellow-900">Risk Factors</div>
            <div className="text-xs text-yellow-700">Moderate monitoring</div>
          </div>
          <div className="text-center p-4 bg-purple-50 rounded-lg">
            <div className="text-2xl font-bold text-purple-600 mb-1">92%</div>
            <div className="text-sm font-medium text-purple-900">Prevention Potential</div>
            <div className="text-xs text-purple-700">High lifestyle impact</div>
          </div>
        </div>
      </div>

      {/* Important Disclaimer */}
      <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-6">
        <div className="flex items-start space-x-3">
          <AlertTriangle className="h-6 w-6 text-yellow-600 mt-0.5 flex-shrink-0" />
          <div>
            <h4 className="font-medium text-yellow-900 mb-2">Medical Disclaimer</h4>
            <p className="text-yellow-800 text-sm">
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