import React from 'react'
import { Activity, Heart, Moon, Droplets, Thermometer, Zap, Shield } from 'lucide-react'

interface WellnessPanelProps {
  data: any
  isDarkMode?: boolean
}

export default function WellnessPanel({ data, isDarkMode = false }: WellnessPanelProps) {
  const theme = {
    glass: isDarkMode 
      ? 'bg-black/20 backdrop-blur-xl border-white/10' 
      : 'bg-white/30 backdrop-blur-xl border-white/30',
    text: {
      primary: isDarkMode ? 'text-white' : 'text-gray-900',
      secondary: isDarkMode ? 'text-gray-300' : 'text-gray-700',
      muted: isDarkMode ? 'text-gray-400' : 'text-gray-500',
    }
  }

  const wellnessTraits = [
    {
      category: 'Sleep & Circadian Rhythm',
      icon: Moon,
      color: 'text-purple-500',
      bgColor: 'bg-purple-500/10',
      traits: [
        { name: 'Deep Sleep', value: 'Typical', gene: 'DEC2', confidence: 'High' },
        { name: 'Morning Person', value: 'Yes', gene: 'PER2', confidence: 'High' },
        { name: 'Sleep Duration Need', value: '7-8 hours', gene: 'CLOCK', confidence: 'Medium' }
      ]
    },
    {
      category: 'Cardiovascular Health',
      icon: Heart,
      color: 'text-red-500',
      bgColor: 'bg-red-500/10',
      traits: [
        { name: 'HDL Cholesterol Response', value: 'Good Response', gene: 'CETP', confidence: 'High' },
        { name: 'Blood Pressure', value: 'Normal Tendency', gene: 'ACE', confidence: 'Medium' },
        { name: 'Heart Rate Recovery', value: 'Fast', gene: 'ADRB1', confidence: 'High' }
      ]
    },
    {
      category: 'Inflammation & Immunity',
      icon: Shield,
      color: 'text-green-500',
      bgColor: 'bg-green-500/10',
      traits: [
        { name: 'C-Reactive Protein', value: 'Low Levels', gene: 'CRP', confidence: 'High' },
        { name: 'Immune Response', value: 'Strong', gene: 'HLA-B', confidence: 'Medium' },
        { name: 'Inflammatory Response', value: 'Moderate', gene: 'TNF-α', confidence: 'High' }
      ]
    },
    {
      category: 'Metabolic Health',
      icon: Zap,
      color: 'text-yellow-500',
      bgColor: 'bg-yellow-500/10',
      traits: [
        { name: 'Insulin Sensitivity', value: 'High', gene: 'TCF7L2', confidence: 'High' },
        { name: 'Metabolic Rate', value: 'Fast', gene: 'UCP1', confidence: 'Medium' },
        { name: 'Blood Sugar Response', value: 'Normal', gene: 'PPARG', confidence: 'High' }
      ]
    },
    {
      category: 'Hydration & Electrolytes',
      icon: Droplets,
      color: 'text-blue-500',
      bgColor: 'bg-blue-500/10',
      traits: [
        { name: 'Sodium Sensitivity', value: 'Low', gene: 'ACE', confidence: 'Medium' },
        { name: 'Hydration Needs', value: 'Standard', gene: 'AQP2', confidence: 'Low' },
        { name: 'Electrolyte Balance', value: 'Good', gene: 'SCNN1A', confidence: 'Medium' }
      ]
    },
    {
      category: 'Stress Response',
      icon: Activity,
      color: 'text-orange-500',
      bgColor: 'bg-orange-500/10',
      traits: [
        { name: 'Cortisol Response', value: 'Normal', gene: 'FKBP5', confidence: 'High' },
        { name: 'Stress Resilience', value: 'High', gene: 'COMT', confidence: 'High' },
        { name: 'Recovery Time', value: 'Fast', gene: 'BDNF', confidence: 'Medium' }
      ]
    }
  ]

  const overallScore = 78
  const improvementAreas = [
    'Consider magnesium supplementation for better sleep quality',
    'Omega-3 fatty acids may help optimize inflammation response',
    'Regular exercise timing can enhance your natural circadian rhythm'
  ]

  const getConfidenceColor = (confidence: string) => {
    switch (confidence.toLowerCase()) {
      case 'high': return 'text-green-500 bg-green-500/10 border-green-500/20'
      case 'medium': return 'text-yellow-500 bg-yellow-500/10 border-yellow-500/20'
      case 'low': return 'text-gray-500 bg-gray-500/10 border-gray-500/20'
      default: return 'text-gray-500 bg-gray-500/10 border-gray-500/20'
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className={`text-2xl font-bold ${theme.text.primary} mb-2`}>
            Wellness Reports
          </h2>
          <p className={theme.text.secondary}>
            Personalized insights for optimal health and wellbeing
          </p>
        </div>
        <div className={`${theme.glass} rounded-xl p-4`}>
          <div className="flex items-center space-x-3">
            <Activity className="h-8 w-8 text-green-500" />
            <div>
              <div className={`text-2xl font-bold ${theme.text.primary}`}>
                {overallScore}
              </div>
              <div className={`text-sm ${theme.text.muted}`}>
                Wellness Score
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Overall Wellness Score */}
      <div className={`${theme.glass} rounded-xl p-6 border border-white/10`}>
        <h3 className={`text-lg font-semibold ${theme.text.primary} mb-4`}>
          Overall Wellness Assessment
        </h3>
        <div className="flex items-center space-x-4 mb-4">
          <div className="flex-1">
            <div className="flex justify-between items-center mb-2">
              <span className={`text-sm ${theme.text.secondary}`}>Wellness Score</span>
              <span className={`text-lg font-bold ${theme.text.primary}`}>{overallScore}/100</span>
            </div>
            <div className="w-full bg-gray-700/30 rounded-full h-3">
              <div 
                className="bg-gradient-to-r from-green-500 to-blue-500 h-3 rounded-full transition-all duration-1000"
                style={{ width: `${overallScore}%` }}
              />
            </div>
          </div>
        </div>
        <div className="grid md:grid-cols-3 gap-4">
          <div className="text-center">
            <div className={`text-xl font-bold text-green-500 mb-1`}>
              12
            </div>
            <div className={`text-sm ${theme.text.muted}`}>
              Optimal Traits
            </div>
          </div>
          <div className="text-center">
            <div className={`text-xl font-bold text-yellow-500 mb-1`}>
              6
            </div>
            <div className={`text-sm ${theme.text.muted}`}>
              Moderate Traits
            </div>
          </div>
          <div className="text-center">
            <div className={`text-xl font-bold text-red-500 mb-1`}>
              0
            </div>
            <div className={`text-sm ${theme.text.muted}`}>
              Risk Traits
            </div>
          </div>
        </div>
      </div>

      {/* Wellness Categories */}
      <div className="grid gap-6">
        {wellnessTraits.map((category, categoryIndex) => {
          const Icon = category.icon
          return (
            <div key={categoryIndex} className={`${theme.glass} rounded-xl p-6 border border-white/10`}>
              <div className="flex items-center space-x-3 mb-4">
                <div className={`p-2 ${category.bgColor} rounded-lg`}>
                  <Icon className={`h-5 w-5 ${category.color}`} />
                </div>
                <h3 className={`text-lg font-semibold ${theme.text.primary}`}>
                  {category.category}
                </h3>
              </div>
              
              <div className="grid gap-3">
                {category.traits.map((trait, traitIndex) => (
                  <div key={traitIndex} className="flex items-center justify-between p-3 bg-black/10 rounded-lg">
                    <div>
                      <h4 className={`text-sm font-medium ${theme.text.primary} mb-1`}>
                        {trait.name}
                      </h4>
                      <p className={`text-xs ${theme.text.muted}`}>
                        Gene: {trait.gene}
                      </p>
                    </div>
                    <div className="text-right">
                      <div className={`text-sm font-semibold ${theme.text.primary} mb-1`}>
                        {trait.value}
                      </div>
                      <div className={`px-2 py-1 rounded-full text-xs border ${getConfidenceColor(trait.confidence)}`}>
                        {trait.confidence}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>

      {/* Personalized Recommendations */}
      <div className={`${theme.glass} rounded-xl p-6 border border-green-500/20 bg-green-500/5`}>
        <h3 className={`text-lg font-semibold ${theme.text.primary} mb-4`}>
          Personalized Recommendations
        </h3>
        <div className="space-y-3">
          {improvementAreas.map((recommendation, index) => (
            <div key={index} className="flex items-start space-x-3">
              <div className="w-2 h-2 bg-green-500 rounded-full mt-2 flex-shrink-0" />
              <p className={`text-sm ${theme.text.secondary}`}>
                {recommendation}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}