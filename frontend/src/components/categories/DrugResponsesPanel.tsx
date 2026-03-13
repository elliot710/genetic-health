import React, { useState, useEffect } from 'react'
import { Pill, Info, ChevronRight, CheckCircle } from 'lucide-react'
import { Badge } from '../ui/badge'
import {
  useThemeClasses,
  CategoryHeader,
  SectionCard,
  StatusBadge,
  DisclaimerCard,
  VariantLinks,
  riskToSeverity,
  MasonryLayout,
} from './shared'
import type { CategoryPanelProps, DrugResponse } from './types'

interface MappedDrugResponse {
  drug: string
  gene: string
  response: string
  recommendation: string
  risk: string
  genotype: string
  variants?: string[]
}

export default function DrugResponsesPanel({ data, isDarkMode = false, token }: CategoryPanelProps) {
  const theme = useThemeClasses(isDarkMode)
  const [selectedItem, setSelectedItem] = useState<string | null>(null)

  const [realDrugResponses, setRealDrugResponses] = useState<DrugResponse[]>([])
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
          setRealDrugResponses(drugData.drug_responses || [])
        }
      } catch (error) {
        // silently handle fetch errors
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
        .filter((dr: DrugResponse) => {
          // Filter out generic "General medications" entries
          const drugName = dr.drug || ''
          return drugName.toLowerCase() !== 'general medications'
        })
        .map((dr: DrugResponse) => ({
          drug: dr.drug,
          gene: dr.gene,
          response: dr.response_type.replace('_', ' ').replace(/\b\w/g, (l: string) => l.toUpperCase()),
          recommendation: dr.recommendations || 'Consult healthcare provider',
          risk: dr.response_type.includes('poor') || dr.response_type.includes('ultrarapid') ? 'high' : 
                dr.response_type.includes('intermediate') ? 'medium' : 'low',
          genotype: dr.variants_involved?.join(', ') || 'Multiple variants',
          variants: dr.variants_involved || []
        }))
    }
    
    // Second priority: Data from props
    const drugInteractions = data?.drug_interactions
    if (drugInteractions?.details && drugInteractions.details.length > 0) {
      return drugInteractions.details
        .filter((dr: DrugResponse) => {
          // Filter out generic "General medications" entries
          const drugName = dr.drug || ''
          return drugName.toLowerCase() !== 'general medications'
        })
        .map((dr: DrugResponse) => ({
          drug: dr.drug,
          gene: dr.gene,
          response: dr.response_type.replace('_', ' ').replace(/\b\w/g, (l: string) => l.toUpperCase()),
          recommendation: dr.recommendations || 'Consult healthcare provider',
          risk: dr.response_type.includes('poor') || dr.response_type.includes('ultrarapid') ? 'high' : 
                dr.response_type.includes('intermediate') ? 'medium' : 'low',
          genotype: dr.variants_involved?.join(', ') || 'Multiple variants',
          variants: dr.variants_involved || []
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

  const headerProps = {
    icon: Pill,
    iconColorClass: 'text-blue-400',
    gradientFrom: 'from-blue-500/20',
    gradientTo: 'to-cyan-500/20',
    borderColor: 'border-blue-500/30',
    title: 'Drug Response Analysis',
    description: 'Pharmacogenomic insights based on your genetic variants',
    count: drugResponses.length,
    countLabel: drugResponses.length === 1 ? 'Drug' : 'Drugs',
    theme,
  }

  return (
    <div className="space-y-6">
      <CategoryHeader {...headerProps} />

      <SectionCard title="Drug Interactions" theme={theme}>
        <MasonryLayout>
          {drugResponses.map((drug: MappedDrugResponse, index: number) => {
            const itemKey = `drug-${index}`
            const isExpanded = selectedItem === itemKey
            return (
              <div
                key={index}
                className={`${theme.glass} border ${theme.border} rounded-xl p-5 cursor-pointer hover:border-blue-500/50 transition-all duration-300`}
                onClick={() => setSelectedItem(isExpanded ? null : itemKey)}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <h4 className={`font-bold text-lg ${theme.textPrimary}`}>{drug.drug}</h4>
                    <StatusBadge
                      label={`${(drug.risk?.charAt(0).toUpperCase() + drug.risk?.slice(1)) || 'Unknown'} Risk`}
                      severity={riskToSeverity(drug.risk)}
                    />
                  </div>
                  <ChevronRight className={`h-5 w-5 ${theme.textSecondary} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                </div>

                <div className="flex flex-wrap gap-1.5">
                  <Badge variant="secondary" className="text-xs">{drug.gene}</Badge>
                  <Badge variant="outline" className="text-xs">{drug.response}</Badge>
                </div>

                {isExpanded && (
                  <div className={`mt-4 pt-4 border-t ${theme.border} space-y-3`}>
                    <div className={`text-sm ${theme.textSecondary}`}>
                      <span className="font-medium">Genotype:</span> <span className="font-mono">{drug.genotype}</span>
                    </div>

                    {drug.recommendation && (
                      <div className="space-y-2">
                        <span className={`text-xs font-semibold ${theme.textSecondary} uppercase tracking-wider`}>Recommendation</span>
                        <div className={`flex items-start gap-2 text-sm ${theme.textSecondary}`}>
                          <CheckCircle className="h-4 w-4 text-blue-400 mt-0.5 shrink-0" />
                          <span>{drug.recommendation}</span>
                        </div>
                      </div>
                    )}

                    <VariantLinks rsid={drug.variants?.[0]} gene={drug.gene} />
                  </div>
                )}
              </div>
            )
          })}
        </MasonryLayout>
      </SectionCard>

      <DisclaimerCard
        icon={Info}
        title="Important Disclaimer"
        text="This pharmacogenomic information is for educational purposes only and should not replace professional medical advice. Always consult with your healthcare provider before making any changes to your medication regimen."
        theme={theme}
      />
    </div>
  )
}