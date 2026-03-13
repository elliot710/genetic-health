import React, { useState, useEffect } from 'react'
import { Heart, AlertTriangle, ChevronRight, CheckCircle } from 'lucide-react'
import { Badge } from '../ui/badge'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  StatusBadge,
  ScoreBar,
  DisclaimerCard,
  VariantLinks,
  riskToSeverity,
  getRiskBarColor,
  MasonryLayout,
} from './shared'
import { getThemeClass } from '../../utils/theme'
import type { CategoryPanelProps, HealthRisk } from './types'

interface VariantAnnotation {
  clinical_significance?: string
  allele_frequency?: string
  consequence?: string
  alpha_missense?: {
    found: boolean
    am_pathogenicity?: number
    am_class?: string
    protein_variant?: string
    disclaimer?: string
  }
}

interface MappedHealthRisk {
  condition: string
  risk: string
  riskScore: number
  gene: string
  description: string
  variantInfo: string[]
  clinicalSignificance: string
  riskLevel: string
  prevention: string[]
}

export default function HealthPanel({ isDarkMode = false, data, token }: CategoryPanelProps) {
  const theme = useThemeClasses(isDarkMode)
  const [selectedItem, setSelectedItem] = useState<string | null>(null)

  const [realHealthRisks, setRealHealthRisks] = useState<HealthRisk[]>([])
  const [variantAnnotations, setVariantAnnotations] = useState<Record<string, VariantAnnotation>>({})
  const [loading, setLoading] = useState(false)

  const cleanConditionName = (condition: string) => {
    return condition
      .replace(/Genetic Variant\s*\([^)]+\)\s*/gi, '')
      .replace(/\([^)]*rs\d+[^)]*\)/gi, '')
      .replace(/\s*\(Protein-affecting\)/gi, '')
      .trim()
  }

  const getVariantDescription = (rsid: string, condition: string, gene: string) => {
    const variantDescriptions: {[key: string]: string} = {
      'rs369162678': 'This variant in the RELN gene affects neuronal migration and synaptic function. It is associated with increased susceptibility to epilepsy, particularly temporal lobe epilepsy, and may influence cognitive development and neurological health.',
      'rs143577179': 'A protein-affecting variant that modifies enzyme function or protein structure, potentially impacting cellular processes and metabolic pathways related to health conditions.',
      'rs185185944': 'This variant requires further research to establish clinical significance. Current data suggests potential involvement in cellular mechanisms, but more studies are needed to determine health implications.',
    }

    if (variantDescriptions[rsid]) {
      return variantDescriptions[rsid]
    }

    if (gene && gene !== 'Unknown' && condition) {
      return `This genetic variant in the ${gene} gene has been associated with ${condition.toLowerCase()}. The variant may influence gene expression, protein function, or cellular processes that contribute to disease risk or therapeutic response.`
    }

    return `This genetic variant has been identified in your analysis and may contribute to your genetic risk profile for ${condition.toLowerCase()}. Further research may provide more specific information about its biological mechanisms and health implications.`
  }

  const getVariantAnnotations = async (rsid: string) => {
    if (!token || !rsid || rsid === 'Unknown' || variantAnnotations[rsid]) return null

    try {
      const response = await fetch(`http://localhost:8000/api/annotations/clinical-summary`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ rsid })
      })

      if (response.ok) {
        const annotationData = await response.json()
        setVariantAnnotations(prev => ({ ...prev, [rsid]: annotationData }))
        return annotationData
      }
    } catch {
      // silently handle annotation fetch errors
    }
    return null
  }



  useEffect(() => {
    const loadHealthRisks = async () => {
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
          const healthData = await response.json()
          setRealHealthRisks(healthData.health_risks || [])

          if (healthData.health_risks) {
            healthData.health_risks.forEach((risk: HealthRisk) => {
              if (risk.associated_variants && risk.associated_variants.length > 0) {
                risk.associated_variants.forEach((variant: string) => {
                  if (variant && variant !== 'Unknown') {
                    getVariantAnnotations(variant)
                  }
                })
              }
            })
          }
        }
      } catch {
        // silently handle fetch errors
      } finally {
        setLoading(false)
      }
    }

    loadHealthRisks()
  }, [token])

  const getRiskLevel = (level: string) => {
    return level.charAt(0).toUpperCase() + level.slice(1)
  }

  const getRiskColor = (risk: string): string => {
    switch (risk.toLowerCase()) {
      case 'high': return isDarkMode ? 'text-red-400' : 'text-red-600'
      case 'moderate': return isDarkMode ? 'text-yellow-400' : 'text-yellow-600'
      case 'low': return isDarkMode ? 'text-green-400' : 'text-green-600'
      default: return theme.textSecondary
    }
  }

  const getHealthRisks = () => {
    if (realHealthRisks.length > 0) {
      return realHealthRisks
        .map((risk: HealthRisk) => ({
          condition: cleanConditionName(risk.condition),
          risk: getRiskLevel(risk.risk_level),
          riskScore: risk.risk_level === 'high' ? 85 : risk.risk_level === 'moderate' ? 65 : risk.risk_level === 'low' ? 35 : 20,
          gene: risk.associated_variants?.[0] || 'Unknown',
          description: `Genetic analysis shows ${risk.risk_level} risk for this condition`,
          variantInfo: risk.associated_variants || [],
          clinicalSignificance: risk.clinical_significance || 'Under research',
          riskLevel: risk.risk_level,
          prevention: Array.isArray(risk.recommendations) ? risk.recommendations : [risk.recommendations || 'Consult with healthcare provider']
        }))
        .sort((a: MappedHealthRisk, b: MappedHealthRisk) => {
          const riskOrder = { 'high': 1, 'moderate': 2, 'low': 3, 'unconfirmed': 4, 'unknown': 4 }
          return (riskOrder[a.riskLevel as keyof typeof riskOrder] || 5) - (riskOrder[b.riskLevel as keyof typeof riskOrder] || 5)
        })
    }

    const healthRisksObj = data?.health_risks as { details?: HealthRisk[] } | undefined
    if (healthRisksObj?.details && healthRisksObj.details.length > 0) {
      return healthRisksObj.details
        .map((risk: HealthRisk) => ({
          condition: cleanConditionName(risk.condition),
          risk: getRiskLevel(risk.risk_level),
          riskScore: risk.risk_level === 'high' ? 85 : risk.risk_level === 'moderate' ? 65 : risk.risk_level === 'low' ? 35 : 20,
          gene: risk.associated_variants?.[0] || 'Unknown',
          description: `Genetic variant analysis shows ${risk.risk_level} risk`,
          variantInfo: risk.associated_variants || [],
          clinicalSignificance: risk.clinical_significance || 'Under research',
          riskLevel: risk.risk_level,
          prevention: risk.recommendations || ['Consult with healthcare provider', 'Monitor regularly', 'Maintain healthy lifestyle']
        }))
        .sort((a: MappedHealthRisk, b: MappedHealthRisk) => {
          const riskOrder = { 'high': 1, 'moderate': 2, 'low': 3, 'unconfirmed': 4, 'unknown': 4 }
          return (riskOrder[a.riskLevel as keyof typeof riskOrder] || 5) - (riskOrder[b.riskLevel as keyof typeof riskOrder] || 5)
        })
    }

    if (loading) {
      return [{
        condition: 'Loading Health Risks...',
        risk: 'Processing',
        riskScore: 0,
        gene: 'Multiple',
        description: 'Loading your genetic health risk analysis results...',
        variantInfo: [] as string[],
        clinicalSignificance: 'Processing',
        riskLevel: 'unknown',
        prevention: ['Analysis in progress...']
      }]
    }

    return []
  }

  const healthRisks = getHealthRisks()

  const highRiskItems = healthRisks.filter((r: MappedHealthRisk) => r.riskLevel === 'high')
  const moderateRiskItems = healthRisks.filter((r: MappedHealthRisk) => r.riskLevel === 'moderate')

  const headerProps = {
    icon: Heart,
    iconColorClass: 'text-red-400',
    gradientFrom: 'from-red-500/20',
    gradientTo: 'to-pink-500/20',
    borderColor: 'border-red-500/30',
    title: 'Health Risks',
    description: 'Genetic health risk assessment based on your variants',
    count: healthRisks.length,
    countLabel: healthRisks.length === 1 ? 'Risk' : 'Risks',
    theme,
  }

  if (healthRisks.length === 0 && !loading) {
    return (
      <div className="space-y-6">
        <CategoryHeader {...headerProps} />
        <EmptyState
          icon={Heart}
          iconColorClass="text-red-400"
          gradientFrom="from-red-500/20"
          gradientTo="to-pink-500/20"
          borderColor="border-red-500/30"
          title="No Health Data Available"
          description="Health risk analysis is not yet available. Upload genetic data to see your results."
          theme={theme}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <CategoryHeader {...headerProps} />

      <SectionCard title="Health Risk Assessment" theme={theme}>
        <MasonryLayout>
          {healthRisks.map((risk: MappedHealthRisk, index: number) => {
            const itemKey = `health-${index}`
            const isExpanded = selectedItem === itemKey
            return (
              <div
                key={index}
                className={`${theme.glass} border ${theme.border} rounded-xl p-5 cursor-pointer hover:border-red-500/50 transition-all duration-300`}
                onClick={() => setSelectedItem(isExpanded ? null : itemKey)}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <h4 className={`font-bold text-lg ${theme.textPrimary}`}>{risk.condition}</h4>
                    <StatusBadge
                      label={`${risk.risk} Risk`}
                      severity={riskToSeverity(risk.riskLevel)}
                    />
                  </div>
                  <ChevronRight className={`h-5 w-5 ${theme.textSecondary} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {risk.gene && risk.gene !== 'Unknown' && (
                    <Badge variant="secondary" className="text-xs">{risk.gene}</Badge>
                  )}
                  {risk.clinicalSignificance && (
                    <Badge variant="outline" className="text-xs">{risk.clinicalSignificance}</Badge>
                  )}
                </div>

                {isExpanded && (
                  <div className={`mt-4 pt-4 border-t ${theme.border} space-y-3`}>
                    <p className={`text-sm ${theme.textSecondary} leading-relaxed`}>{risk.description}</p>

                    <ScoreBar
                      label="Lifetime Risk"
                      value={risk.riskScore}
                      colorClass={getRiskBarColor(risk.riskScore)}
                      theme={theme}
                    />

                    {risk.variantInfo && risk.variantInfo.length > 0 && (
                      <div>
                        <h5 className={`text-sm font-medium ${theme.textPrimary} mb-2`}>Associated Variants</h5>
                        <div className="space-y-2">
                          {risk.variantInfo.map((variant: string, variantIndex: number) => {
                            const annotation = variantAnnotations[variant]
                            const description = getVariantDescription(variant, risk.condition, risk.gene)

                            return (
                              <div key={variantIndex} className={`${getThemeClass('bg-gray-50', isDarkMode)} rounded-lg p-3 border ${getThemeClass('border-gray-200', isDarkMode)}`}>
                                <p className={`text-xs ${theme.textSecondary} leading-relaxed mb-2`}>{description}</p>

                                {annotation && (
                                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs mb-2">
                                    {annotation.clinical_significance && annotation.clinical_significance !== 'unknown' && (
                                      <div>
                                        <span className={`font-medium ${theme.textPrimary}`}>Significance:</span>
                                        <div className={theme.textSecondary}>{annotation.clinical_significance.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())}</div>
                                      </div>
                                    )}
                                    {annotation.allele_frequency && (
                                      <div>
                                        <span className={`font-medium ${theme.textPrimary}`}>Frequency:</span>
                                        <div className={theme.textSecondary}>{annotation.allele_frequency}</div>
                                      </div>
                                    )}
                                    {annotation.consequence && (
                                      <div>
                                        <span className={`font-medium ${theme.textPrimary}`}>Effect:</span>
                                        <div className={theme.textSecondary}>{annotation.consequence}</div>
                                      </div>
                                    )}
                                    {annotation.alpha_missense?.found && (
                                      <div>
                                        <span className={`font-medium ${theme.textPrimary}`}>AI Pathogenicity:</span>
                                        <div className="flex items-center gap-1.5">
                                          <span className={`font-mono ${
                                            (annotation.alpha_missense.am_pathogenicity ?? 0) > 0.564 ? 'text-red-400' :
                                            (annotation.alpha_missense.am_pathogenicity ?? 0) < 0.34 ? 'text-green-400' : 'text-amber-400'
                                          }`}>
                                            {annotation.alpha_missense.am_pathogenicity?.toFixed(3)}
                                          </span>
                                          <Badge variant="outline" className={`text-[10px] px-1 py-0 ${
                                            annotation.alpha_missense.am_class === 'likely_pathogenic' ? 'bg-red-500/15 text-red-400 border-red-500/30' :
                                            annotation.alpha_missense.am_class === 'likely_benign' ? 'bg-green-500/15 text-green-400 border-green-500/30' :
                                            'bg-amber-500/15 text-amber-400 border-amber-500/30'
                                          }`}>
                                            {annotation.alpha_missense.am_class?.replace(/_/g, ' ')}
                                          </Badge>
                                        </div>
                                        <div className={`text-[10px] ${theme.textSecondary} mt-0.5 italic`}>AI prediction — not clinically validated</div>
                                      </div>
                                    )}
                                  </div>
                                )}

                                <VariantLinks rsid={variant} gene={risk.gene} token={token} isDarkMode={isDarkMode} alphaMissense={variant ? data?.alpha_missense_map?.[variant] : undefined} clinvarCount={variant ? data?.clinvar_count_map?.[variant] : undefined} />
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    )}

                    {risk.prevention.length > 0 && (
                      <div className="space-y-2">
                        <span className={`text-xs font-semibold ${theme.textSecondary} uppercase tracking-wider`}>Prevention Strategies</span>
                        {risk.prevention.map((strategy: string, i: number) => (
                          <div key={i} className={`flex items-start gap-2 text-sm ${theme.textSecondary}`}>
                            <CheckCircle className="h-4 w-4 text-green-400 mt-0.5 shrink-0" />
                            <span>{strategy}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </MasonryLayout>
      </SectionCard>

      {(highRiskItems.length > 0 || moderateRiskItems.length > 0) && (
        <SectionCard title="Key Recommendations" theme={theme}>
          <div className="space-y-3">
            {highRiskItems.length > 0 && (
              <div className={`${getThemeClass('bg-red-50', isDarkMode)} p-4 rounded-lg border-l-4 border-red-500`}>
                <h4 className={`font-medium ${getThemeClass('text-red-700', isDarkMode)} mb-2`}>High Priority Actions</h4>
                <ul className={`${getThemeClass('text-red-700', isDarkMode)} text-sm space-y-1`}>
                  <li>• Schedule consultation with healthcare provider</li>
                  <li>• Discuss genetic testing results and family history</li>
                  <li>• Consider specialized screening programs</li>
                  {highRiskItems.map((risk: MappedHealthRisk, i: number) => (
                    <li key={i}>• Monitor: {risk.condition}</li>
                  ))}
                </ul>
              </div>
            )}

            {moderateRiskItems.length > 0 && (
              <div className={`${getThemeClass('bg-yellow-50', isDarkMode)} p-4 rounded-lg border-l-4 border-yellow-500`}>
                <h4 className={`font-medium ${getThemeClass('text-yellow-700', isDarkMode)} mb-2`}>Moderate Risk Management</h4>
                <ul className={`${getThemeClass('text-yellow-700', isDarkMode)} text-sm space-y-1`}>
                  <li>• Maintain regular health checkups</li>
                  <li>• Focus on preventive lifestyle measures</li>
                  {moderateRiskItems.map((risk: MappedHealthRisk, i: number) => (
                    <li key={i}>• Watch: {risk.condition}</li>
                  ))}
                </ul>
              </div>
            )}

            <DisclaimerCard
              icon={AlertTriangle}
              title="Important Notice"
              text="This genetic analysis is for informational purposes only. Always consult with qualified healthcare providers before making medical decisions based on genetic information."
              theme={theme}
            />
          </div>
        </SectionCard>
      )}
    </div>
  )
}