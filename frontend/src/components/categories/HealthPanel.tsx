import React, { useState, useMemo, useEffect } from 'react'
import { Heart, AlertTriangle, ChevronRight, CheckCircle, Search, Filter } from 'lucide-react'
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
  cleanCondition,
} from './shared'
import { getThemeClass } from '../../utils/theme'
import { RiskDistributionChart } from './GenomicCharts'
import SmartInsights from '../SmartInsights'
import type { CategoryPanelProps, HealthRisk } from './types'
import { apiUrl } from '@/lib/api'

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
  const [searchQuery, setSearchQuery] = useState('')
  const [riskFilter, setRiskFilter] = useState<string>('all')

  const [variantAnnotations, setVariantAnnotations] = useState<Record<string, VariantAnnotation>>({})



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
      const response = await fetch(apiUrl(`/api/annotations/clinical-summary`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
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



  // Fetch variant annotations when data is available
  useEffect(() => {
    if (!token || !data?.health_risks) return
    const risks = Array.isArray(data.health_risks) ? data.health_risks as HealthRisk[] : []
    risks.forEach((risk: HealthRisk) => {
      if (risk.associated_variants && risk.associated_variants.length > 0) {
        risk.associated_variants.forEach((variant: string) => {
          if (variant && variant !== 'Unknown') {
            getVariantAnnotations(variant)
          }
        })
      }
    })
  }, [token, data?.health_risks])

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
    const healthRisks = Array.isArray(data?.health_risks) ? data.health_risks as HealthRisk[] : []
    if (healthRisks.length > 0) {
      return healthRisks
        .map((risk: HealthRisk) => ({
          condition: cleanCondition(risk.condition),
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
          condition: cleanCondition(risk.condition),
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

    if (!data) {
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

  const riskOptions = useMemo(() => {
    const set = new Set<string>()
    for (const r of healthRisks) set.add(r.riskLevel)
    return Array.from(set).sort()
  }, [healthRisks])

  const filteredRisks = useMemo(() => {
    let list = healthRisks
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      list = list.filter(r => r.condition.toLowerCase().includes(q) || r.gene.toLowerCase().includes(q))
    }
    if (riskFilter !== 'all') {
      list = list.filter(r => r.riskLevel === riskFilter)
    }
    return list
  }, [healthRisks, searchQuery, riskFilter])

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

  if (healthRisks.length === 0) {
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

      {healthRisks.length >= 3 && (
        <SectionCard title="Risk Distribution" theme={theme}>
          <RiskDistributionChart data={healthRisks.map(r => ({ condition: r.condition, risk_level: r.riskLevel, risk_score: r.riskScore }))} isDarkMode={isDarkMode} height={200} />
        </SectionCard>
      )}

      {/* Filter Bar */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-50">
          <Search className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
          <input
            type="text"
            placeholder="Search conditions or variants…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} placeholder:${theme.textSecondary} focus:outline-none focus:ring-2 focus:ring-red-500/40 text-sm`}
          />
        </div>
        <div className="relative min-w-40">
          <Filter className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
          <select
            value={riskFilter}
            onChange={e => setRiskFilter(e.target.value)}
            className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} focus:outline-none focus:ring-2 focus:ring-red-500/40 text-sm appearance-none cursor-pointer`}
          >
            <option value="all">All Risk Levels</option>
            {riskOptions.map(s => (
              <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
            ))}
          </select>
        </div>
      </div>

      <SectionCard title={`Health Risk Assessment${filteredRisks.length !== healthRisks.length ? ` (${filteredRisks.length} of ${healthRisks.length})` : ''}`} theme={theme}>
        <MasonryLayout>
          {filteredRisks.map((risk: MappedHealthRisk, index: number) => {
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
                    <Badge variant={risk.gene.startsWith('rs') ? 'secondary' : 'secondary'} className={`text-xs ${risk.gene.startsWith('rs') ? 'font-mono' : ''}`}>
                      {risk.gene}{risk.gene.startsWith('rs') && data?.genotype_map?.[risk.gene] ? ` ${data.genotype_map[risk.gene]}` : ''}
                    </Badge>
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

            <SmartInsights isDarkMode={isDarkMode} token={token} section="health" title="AI Health Analysis" />
          </div>
        </SectionCard>
      )}
    </div>
  )
}