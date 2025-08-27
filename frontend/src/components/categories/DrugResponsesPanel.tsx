import React, { useState, useEffect } from 'react'
import { Pill, AlertTriangle, CheckCircle, Clock, Info } from 'lucide-react'
import { 
  getThemeClass, 
  getGlassBackground, 
  getGlassBorder, 
  getTextPrimary, 
  getTextSecondary, 
  getTagClass, 
  getProgressBarBg 
} from '../../utils/theme'

interface DrugResponsesPanelProps {
  isDarkMode?: boolean
  theme?: any
  data: any
  token?: string
}

export default function DrugResponsesPanel({ data, isDarkMode = false, token }: DrugResponsesPanelProps) {
  const glassBackground = getGlassBackground(isDarkMode);
  const glassBorder = getGlassBorder(isDarkMode);
  const textPrimary = getTextPrimary(isDarkMode);
  const textSecondary = getTextSecondary(isDarkMode);
  const tagClass = getTagClass(isDarkMode);
  const progressBarBg = getProgressBarBg(isDarkMode);

  const [realDrugResponses, setRealDrugResponses] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  
  // Load real drug responses from API
  useEffect(() => {
    const loadDrugResponses = async () => {
      if (!token) return
      
      setLoading(true)
      try {
        const response = await fetch('http://localhost:8000/api/analysis/dashboard-data', {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        })
        
        if (response.ok) {
          const drugData = await response.json()
          console.log('Loaded drug responses:', drugData)
          setRealDrugResponses(drugData.drug_responses || [])
        }
      } catch (error) {
        console.error('Error loading drug responses:', error)
      } finally {
        setLoading(false)
      }
    }
    
    loadDrugResponses()
  }, [token])

  // Use real drug response data if available
  const getDrugResponses = () => {
    // First priority: Real API data
    if (realDrugResponses.length > 0) {
      return realDrugResponses
        .filter((dr: any) => {
          // Filter out generic "General medications" entries
          const drugName = dr.drug || ''
          return drugName.toLowerCase() !== 'general medications'
        })
        .map((dr: any) => ({
          drug: dr.drug,
          gene: dr.gene,
          response: dr.response_type.replace('_', ' ').replace(/\b\w/g, (l: string) => l.toUpperCase()),
          recommendation: dr.recommendations || 'Consult healthcare provider',
          risk: dr.response_type.includes('poor') || dr.response_type.includes('ultrarapid') ? 'high' : 
                dr.response_type.includes('intermediate') ? 'medium' : 'low',
          genotype: dr.variants_involved?.join(', ') || 'Multiple variants'
        }))
    }
    
    // Second priority: Data from props
    if (data?.drug_interactions?.details && data.drug_interactions.details.length > 0) {
      return data.drug_interactions.details
        .filter((dr: any) => {
          // Filter out generic "General medications" entries
          const drugName = dr.drug || ''
          return drugName.toLowerCase() !== 'general medications'
        })
        .map((dr: any) => ({
          drug: dr.drug,
          gene: dr.gene,
          response: dr.response_type.replace('_', ' ').replace(/\b\w/g, (l: string) => l.toUpperCase()),
          recommendation: dr.recommendations || 'Consult healthcare provider',
          risk: dr.response_type.includes('poor') || dr.response_type.includes('ultrarapid') ? 'high' : 
                dr.response_type.includes('intermediate') ? 'medium' : 'low',
          genotype: dr.variants_involved?.join(', ') || 'Multiple variants'
        }))
    }
    
    // Loading state
    if (loading) {
      return [{
        drug: 'Loading Drug Responses...',
        gene: 'Multiple Genes',
        response: 'Processing pharmacogenomic analysis',
        recommendation: 'Loading your genetic drug response predictions...',
        risk: 'pending',
        genotype: 'Analyzing variants...'
      }]
    }
    
    // Show processing message when no data available
    return [{
      drug: 'No Drug Responses Found',
      gene: 'Multiple Genes',
      response: 'Analysis Complete',
      recommendation: 'No significant drug response variations identified, or analysis is still in progress',
      risk: 'pending',
      genotype: 'Standard response expected'
    }]
  }

  const drugResponses = getDrugResponses()

  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'high': return 'text-red-500 bg-red-500/10 border-red-500/20'
      case 'medium': return 'text-yellow-500 bg-yellow-500/10 border-yellow-500/20'
      case 'low': return 'text-green-500 bg-green-500/10 border-green-500/20'
      case 'pending': return 'text-blue-500 bg-blue-500/10 border-blue-500/20'
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
          <h2 className={`text-2xl font-bold ${textPrimary} mb-2`}>
            Drug Response Analysis
          </h2>
          <p className={textSecondary}>
            Pharmacogenomic insights based on your genetic variants
          </p>
        </div>
        <div className={`${glassBackground} border ${glassBorder} rounded-xl p-4`}>
          <div className="flex items-center space-x-3">
            <Pill className={`h-8 w-8 ${getThemeClass('text-blue-500', isDarkMode)}`} />
            <div>
              <div className={`text-2xl font-bold ${textPrimary}`}>
                {drugResponses.length}
              </div>
              <div className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>
                Analyzed Drugs
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-4">
        {drugResponses.map((drug: any, index: number) => {
          const RiskIcon = getRiskIcon(drug.risk)
          return (
            <div key={index} className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className={`text-lg font-semibold ${textPrimary} mb-1`}>
                    {drug.drug}
                  </h3>
                  <p className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>
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
                  <h4 className={`text-sm font-medium ${textSecondary} mb-2`}>
                    Response Type
                  </h4>
                  <p className={`text-sm ${textPrimary} font-medium`}>
                    {drug.response}
                  </p>
                </div>
                <div>
                  <h4 className={`text-sm font-medium ${textSecondary} mb-2`}>
                    Genotype
                  </h4>
                  <p className={`text-sm ${textPrimary} font-mono`}>
                    {drug.genotype}
                  </p>
                </div>
                <div>
                  <h4 className={`text-sm font-medium ${textSecondary} mb-2`}>
                    Recommendation
                  </h4>
                  <p className={`text-sm ${textPrimary}`}>
                    {drug.recommendation}
                  </p>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6 border border-blue-500/20 bg-blue-500/5`}>
        <div className="flex items-start space-x-3">
          <Info className={`h-5 w-5 ${getThemeClass('text-blue-500', isDarkMode)} mt-0.5`} />
          <div>
            <h3 className={`font-semibold ${textPrimary} mb-2`}>
              Important Disclaimer
            </h3>
            <p className={`text-sm ${textSecondary} leading-relaxed`}>
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