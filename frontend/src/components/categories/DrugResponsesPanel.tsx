import React from 'react'
import { Pill, AlertTriangle, CheckCircle, Clock, Info } from 'lucide-react'

interface DrugResponsesPanelProps {
  data: any
  isDarkMode?: boolean
}

export default function DrugResponsesPanel({ data, isDarkMode = false }: DrugResponsesPanelProps) {
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

  const drugResponses = [
    {
      drug: 'Warfarin',
      gene: 'CYP2C9, VKORC1',
      response: 'Reduced Metabolism',
      recommendation: 'Lower starting dose recommended',
      risk: 'high',
      genotype: 'CYP2C9*1/*3, VKORC1 A/G'
    },
    {
      drug: 'Clopidogrel',
      gene: 'CYP2C19',
      response: 'Normal Metabolism',
      recommendation: 'Standard dosing',
      risk: 'low',
      genotype: 'CYP2C19*1/*1'
    },
    {
      drug: 'Metformin',
      gene: 'OCT1',
      response: 'Enhanced Response',
      recommendation: 'May be more effective',
      risk: 'low',
      genotype: 'OCT1 rs622342 A/A'
    },
    {
      drug: 'Simvastatin',
      gene: 'SLCO1B1',
      response: 'Increased Risk',
      recommendation: 'Monitor for muscle toxicity',
      risk: 'medium',
      genotype: 'SLCO1B1*5/*15'
    },
    {
      drug: 'Codeine',
      gene: 'CYP2D6',
      response: 'Poor Metabolizer',
      recommendation: 'Alternative analgesic recommended',
      risk: 'high',
      genotype: 'CYP2D6*4/*4'
    }
  ]

  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'high': return 'text-red-500 bg-red-500/10 border-red-500/20'
      case 'medium': return 'text-yellow-500 bg-yellow-500/10 border-yellow-500/20'
      case 'low': return 'text-green-500 bg-green-500/10 border-green-500/20'
      default: return 'text-gray-500 bg-gray-500/10 border-gray-500/20'
    }
  }

  const getRiskIcon = (risk: string) => {
    switch (risk) {
      case 'high': return AlertTriangle
      case 'medium': return Clock
      case 'low': return CheckCircle
      default: return Info
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className={`text-2xl font-bold ${theme.text.primary} mb-2`}>
            Drug Response Analysis
          </h2>
          <p className={theme.text.secondary}>
            Pharmacogenomic insights based on your genetic variants
          </p>
        </div>
        <div className={`${theme.glass} rounded-xl p-4`}>
          <div className="flex items-center space-x-3">
            <Pill className="h-8 w-8 text-blue-500" />
            <div>
              <div className={`text-2xl font-bold ${theme.text.primary}`}>
                {drugResponses.length}
              </div>
              <div className={`text-sm ${theme.text.muted}`}>
                Analyzed Drugs
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-4">
        {drugResponses.map((drug, index) => {
          const RiskIcon = getRiskIcon(drug.risk)
          return (
            <div key={index} className={`${theme.glass} rounded-xl p-6 border border-white/10`}>
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className={`text-lg font-semibold ${theme.text.primary} mb-1`}>
                    {drug.drug}
                  </h3>
                  <p className={`text-sm ${theme.text.muted}`}>
                    Gene: {drug.gene}
                  </p>
                </div>
                <div className={`px-3 py-1 rounded-full border ${getRiskColor(drug.risk)}`}>
                  <div className="flex items-center space-x-2">
                    <RiskIcon className="h-4 w-4" />
                    <span className="text-sm font-medium capitalize">{drug.risk} Risk</span>
                  </div>
                </div>
              </div>

              <div className="grid md:grid-cols-3 gap-4">
                <div>
                  <h4 className={`text-sm font-medium ${theme.text.secondary} mb-2`}>
                    Response Type
                  </h4>
                  <p className={`text-sm ${theme.text.primary} font-medium`}>
                    {drug.response}
                  </p>
                </div>
                <div>
                  <h4 className={`text-sm font-medium ${theme.text.secondary} mb-2`}>
                    Genotype
                  </h4>
                  <p className={`text-sm ${theme.text.primary} font-mono`}>
                    {drug.genotype}
                  </p>
                </div>
                <div>
                  <h4 className={`text-sm font-medium ${theme.text.secondary} mb-2`}>
                    Recommendation
                  </h4>
                  <p className={`text-sm ${theme.text.primary}`}>
                    {drug.recommendation}
                  </p>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      <div className={`${theme.glass} rounded-xl p-6 border border-blue-500/20 bg-blue-500/5`}>
        <div className="flex items-start space-x-3">
          <Info className="h-5 w-5 text-blue-500 mt-0.5" />
          <div>
            <h3 className={`font-semibold ${theme.text.primary} mb-2`}>
              Important Disclaimer
            </h3>
            <p className={`text-sm ${theme.text.secondary} leading-relaxed`}>
              This pharmacogenomic information is for educational purposes only and should not replace 
              professional medical advice. Always consult with your healthcare provider before making 
              any changes to your medication regimen.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}