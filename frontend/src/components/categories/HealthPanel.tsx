import React, { useState, useMemo, useCallback } from 'react'
import { Heart, AlertTriangle, ChevronRight, CheckCircle, Search, Filter, Shield, FlaskConical } from 'lucide-react'
import { Badge } from '../ui/badge'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  StatusBadge,
  VariantInfoBox,
  GeneContextBox,
  AlphaFoldDetailBox,
  GeneBurdenStrip,
  AlphaFoldBadge,
  DisclaimerCard,
  ClickableRsidBadge,
  EvidenceBadge,
  reviewStatusStars,
  riskToSeverity,
  MasonryLayout,
  cleanCondition,
  useGrouping,
  GroupHeader,
  GroupBySelect,
} from './shared'
import { getThemeClass } from '../../utils/theme'
import { RiskDistributionChart } from './GenomicCharts'
import SmartInsights from '../SmartInsights'
import type { CategoryPanelProps, HealthRisk } from './types'

interface MappedHealthRisk {
  condition: string
  risk: string
  riskScore: number
  gene: string
  geneSymbol: string | null  // distinct gene symbol when available (FE-01)
  description: string
  variantInfo: string[]
  clinicalSignificance: string
  riskLevel: string
  prevention: string[]
  reviewStatus: string | null   // ClinVar review status (FE-02/03)
  pathogenicityClassification: string | null
}

export default function HealthPanel({ isDarkMode = false, data, token }: CategoryPanelProps) {
  const theme = useThemeClasses(isDarkMode)
  const [selectedItem, setSelectedItem] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [riskFilter, setRiskFilter] = useState<string>('all')
  const [evidenceFilter, setEvidenceFilter] = useState<number>(0)  // min ClinVar stars (FE-03)
  const [pathFilter, setPathFilter] = useState<string>('non-benign')
  const [groupBy, setGroupBy] = useState('none')

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

  const healthRisks = useMemo((): MappedHealthRisk[] => {
    const rawRisks = Array.isArray(data?.health_risks) ? data.health_risks as HealthRisk[] : []
    if (rawRisks.length > 0) {
      return rawRisks
        .map((risk: HealthRisk) => {
          // Find max pathogenicity score from associated variants
          const variants = risk.associated_variants || []
          const pathScores = variants
            .map(v => data?.pathogenicity_map?.[v]?.score)
            .filter((s): s is number => s != null)
          const pathScore = pathScores.length > 0 ? Math.max(...pathScores) : null

          const rsid = risk.associated_variants?.[0] || ''
          return {
          condition: cleanCondition(risk.condition),
          risk: getRiskLevel(risk.risk_level),
          riskScore: pathScore ?? (risk.risk_level === 'high' ? 85 : risk.risk_level === 'moderate' ? 65 : risk.risk_level === 'low' ? 35 : 20),
          gene: rsid || 'Unknown',
          geneSymbol: risk.gene || null,
          description: `Genetic analysis shows ${risk.risk_level} risk for this condition`,
          variantInfo: risk.associated_variants || [],
          clinicalSignificance: risk.clinical_significance || 'Under research',
          riskLevel: risk.risk_level,
          prevention: Array.isArray(risk.recommendations) ? risk.recommendations : [risk.recommendations || 'Consult with healthcare provider'],
          reviewStatus: risk.review_status ?? null,
          pathogenicityClassification: risk.pathogenicity_classification ?? null,
          }
        })
        .sort((a: MappedHealthRisk, b: MappedHealthRisk) => {
          const riskOrder = { 'high': 1, 'moderate': 2, 'low': 3, 'unconfirmed': 4, 'unknown': 4 }
          return (riskOrder[a.riskLevel as keyof typeof riskOrder] || 5) - (riskOrder[b.riskLevel as keyof typeof riskOrder] || 5)
        })
    }

    const healthRisksObj = data?.health_risks as { details?: HealthRisk[] } | undefined
    if (healthRisksObj?.details && healthRisksObj.details.length > 0) {
      return healthRisksObj.details
        .map((risk: HealthRisk) => {
          const variants = risk.associated_variants || []
          const pathScores = variants
            .map(v => data?.pathogenicity_map?.[v]?.score)
            .filter((s): s is number => s != null)
          const pathScore = pathScores.length > 0 ? Math.max(...pathScores) : null
          const rsid = risk.associated_variants?.[0] || ''
          return {
          condition: cleanCondition(risk.condition),
          risk: getRiskLevel(risk.risk_level),
          riskScore: pathScore ?? (risk.risk_level === 'high' ? 85 : risk.risk_level === 'moderate' ? 65 : risk.risk_level === 'low' ? 35 : 20),
          gene: rsid || 'Unknown',
          geneSymbol: risk.gene || null,
          description: `Genetic variant analysis shows ${risk.risk_level} risk`,
          variantInfo: risk.associated_variants || [],
          clinicalSignificance: risk.clinical_significance || 'Under research',
          riskLevel: risk.risk_level,
          prevention: risk.recommendations || ['Consult with healthcare provider', 'Monitor regularly', 'Maintain healthy lifestyle'],
          reviewStatus: risk.review_status ?? null,
          pathogenicityClassification: risk.pathogenicity_classification ?? null,
          }
        })
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
        geneSymbol: null,
        description: 'Loading your genetic health risk analysis results...',
        variantInfo: [] as string[],
        clinicalSignificance: 'Processing',
        riskLevel: 'unknown',
        prevention: ['Analysis in progress...'],
        reviewStatus: null,
        pathogenicityClassification: null,
      }]
    }

    return []
  }, [data])

  const riskOptions = useMemo(() => {
    const set = new Set<string>()
    for (const r of healthRisks) set.add(r.riskLevel)
    return Array.from(set).sort()
  }, [healthRisks])

  const filteredRisks = useMemo(() => {
    let list = healthRisks
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      list = list.filter(r =>
        r.condition.toLowerCase().includes(q) ||
        r.gene.toLowerCase().includes(q) ||
        (r.geneSymbol?.toLowerCase().includes(q) ?? false)
      )
    }
    if (riskFilter !== 'all') {
      list = list.filter(r => r.riskLevel === riskFilter)
    }
    if (evidenceFilter > 0) {
      list = list.filter(r => reviewStatusStars(r.reviewStatus) >= evidenceFilter)
    }
    if (pathFilter === 'non-benign') {
      list = list.filter(r => !r.pathogenicityClassification || !['benign', 'likely_benign'].includes(r.pathogenicityClassification))
    } else if (pathFilter === 'benign-only') {
      list = list.filter(r => r.pathogenicityClassification && ['benign', 'likely_benign'].includes(r.pathogenicityClassification))
    } else if (pathFilter === 'pathogenic') {
      list = list.filter(r => r.pathogenicityClassification && ['pathogenic', 'likely_pathogenic'].includes(r.pathogenicityClassification))
    }
    return list
  }, [healthRisks, searchQuery, riskFilter, evidenceFilter, pathFilter])

  const HEALTH_GROUP_OPTIONS: Record<string, string> = { none: 'No Grouping', riskLevel: 'Risk Level', gene: 'Gene' }
  const getGroupKey = useCallback((risk: MappedHealthRisk): string => {
    switch (groupBy) {
      case 'riskLevel': return risk.riskLevel ? `${risk.riskLevel.charAt(0).toUpperCase()}${risk.riskLevel.slice(1)} Risk` : 'Unknown'
      case 'gene': return risk.gene && risk.gene !== 'Unknown' ? risk.gene : 'Unknown Gene'
      default: return 'all'
    }
  }, [groupBy])
  const { groups, collapsedGroups, toggleGroup, resetCollapsed } = useGrouping(filteredRisks, groupBy, getGroupKey, 'All Health Risks')

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
        <div className="relative min-w-44">
          <Shield className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
          <select
            value={evidenceFilter}
            onChange={e => setEvidenceFilter(Number(e.target.value))}
            className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} focus:outline-none focus:ring-2 focus:ring-red-500/40 text-sm appearance-none cursor-pointer`}
          >
            <option value={0}>All Evidence</option>
            <option value={1}>1★ or better</option>
            <option value={2}>2★ or better</option>
            <option value={3}>3★ or better</option>
            <option value={4}>4★ Guidelines</option>
            <option value={5}>Curated only</option>
          </select>
        </div>
        <div className="relative min-w-44">
          <FlaskConical className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
          <select
            value={pathFilter}
            onChange={e => setPathFilter(e.target.value)}
            className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} focus:outline-none focus:ring-2 focus:ring-red-500/40 text-sm appearance-none cursor-pointer`}
          >
            <option value="all">All Classifications</option>
            <option value="non-benign">Exclude Benign</option>
            <option value="pathogenic">Pathogenic Only</option>
            <option value="benign-only">Benign Only</option>
          </select>
        </div>
        <GroupBySelect value={groupBy} onChange={v => { setGroupBy(v); resetCollapsed() }} options={HEALTH_GROUP_OPTIONS} theme={theme} />
      </div>

      <SectionCard title={`Health Risks${filteredRisks.length !== healthRisks.length ? ` (${filteredRisks.length} of ${healthRisks.length})` : ''}`} theme={theme}>
        {groups.map(({ key, label, items }) => (
          <div key={key} className="space-y-3">
            {groupBy !== 'none' && (
              <GroupHeader groupKey={key} label={label} count={items.length} isCollapsed={collapsedGroups.has(key)} onToggle={toggleGroup} theme={theme} />
            )}
            {!collapsedGroups.has(key) && (
        <MasonryLayout>
          {items.map((risk: MappedHealthRisk, index: number) => {
            const itemKey = `health-${index}`
            const isExpanded = selectedItem === itemKey
            return (
              <div
                key={index}
                className={`${theme.glass} border ${theme.border} rounded-xl p-3 sm:p-4 cursor-pointer hover:border-red-500/50 transition-all duration-300 overflow-hidden`}
                onClick={() => setSelectedItem(isExpanded ? null : itemKey)}
              >
                <div className="flex items-start justify-between mb-1 gap-1">
                  <h4 className={`font-semibold text-sm ${theme.textPrimary} leading-snug flex-1 min-w-0`}>{risk.condition}</h4>
                  <div className="flex items-center gap-1.5 shrink-0 mt-0.5">
                    {/* Inline pathogenicity % for quick scan */}
                    {risk.riskScore > 0 && (
                      <span className={`text-xs font-mono font-semibold tabular-nums ${
                        risk.riskScore >= 70 ? 'text-red-400' :
                        risk.riskScore >= 45 ? 'text-orange-400' :
                        risk.riskScore >= 25 ? 'text-yellow-400' : 'text-green-400'
                      }`}>{risk.riskScore}%</span>
                    )}
                    <ChevronRight className={`h-4 w-4 ${theme.textSecondary} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                  </div>
                </div>

                <div className="flex flex-wrap gap-1">
                  <StatusBadge
                    label={`${risk.risk} Risk`}
                    severity={riskToSeverity(risk.riskLevel)}
                  />
                  {risk.geneSymbol && (
                    <Badge variant="secondary" className="text-xs font-medium">
                      {risk.geneSymbol}
                    </Badge>
                  )}
                  {risk.gene && risk.gene !== 'Unknown' && risk.gene.startsWith('rs') && (
                    <ClickableRsidBadge rsid={risk.gene} genotype={data?.genotype_map?.[risk.gene]} alleleString={data?.allele_string_map?.[risk.gene]} token={token} isDarkMode={isDarkMode} />
                  )}
                  <EvidenceBadge reviewStatus={risk.reviewStatus} />
                  {risk.clinicalSignificance && risk.clinicalSignificance !== 'Under research' && (
                    <Badge variant="outline" className="text-xs">{risk.clinicalSignificance}</Badge>
                  )}
                  {risk.pathogenicityClassification && ['pathogenic', 'likely_pathogenic'].includes(risk.pathogenicityClassification) && (
                    <Badge variant="outline" className={`text-xs ${risk.pathogenicityClassification === 'pathogenic' ? 'bg-red-500/15 text-red-400 border-red-500/30' : 'bg-orange-500/15 text-orange-400 border-orange-500/30'}`}>
                      {risk.pathogenicityClassification.replace(/_/g, ' ')}
                    </Badge>
                  )}
                  {/* AlphaFold protein confidence badge */}
                  {risk.variantInfo?.[0] && data?.alphafold_map?.[risk.variantInfo[0]] && (
                    <AlphaFoldBadge
                      confidence={data.alphafold_map[risk.variantInfo[0]].confidence}
                      highPct={data.alphafold_map[risk.variantInfo[0]].high_confidence_pct}
                      lowPct={data.alphafold_map[risk.variantInfo[0]].low_confidence_pct}
                    />
                  )}
                </div>

                {/* Compact gene burden strip — only when collapsed */}
                {!isExpanded && risk.geneSymbol && data?.gene_stats_map?.[risk.geneSymbol] && (
                  <GeneBurdenStrip gene={risk.geneSymbol} stats={data.gene_stats_map[risk.geneSymbol]} theme={theme} />
                )}

                {isExpanded && (
                  <div className={`mt-4 pt-4 border-t ${theme.border} space-y-3`}>
                    {/* Description — replaced generic text with clinical significance details when available */}
                    {risk.clinicalSignificance && risk.clinicalSignificance !== 'Under research' ? (
                      <div className={`text-sm ${theme.textSecondary} leading-relaxed`}>
                        <span className="font-medium">ClinVar classification:</span>{' '}
                        {risk.clinicalSignificance}
                        {risk.pathogenicityClassification && (
                          <span className={`ml-1.5 text-xs font-medium ${
                            risk.pathogenicityClassification === 'pathogenic' ? 'text-red-400' :
                            risk.pathogenicityClassification === 'likely_pathogenic' ? 'text-orange-400' :
                            risk.pathogenicityClassification === 'uncertain' ? 'text-yellow-400' :
                            'text-green-400'
                          }`}>({risk.pathogenicityClassification.replace(/_/g, ' ')})</span>
                        )}
                      </div>
                    ) : (
                      <p className={`text-sm ${theme.textSecondary} leading-relaxed`}>{risk.description}</p>
                    )}

                    {risk.variantInfo && risk.variantInfo.length > 0 && (
                      <div className="space-y-2">
                        {risk.variantInfo.map((variant: string, variantIndex: number) => (
                          <VariantInfoBox
                            key={variantIndex}
                            rsid={variant}
                            gene={risk.geneSymbol || (risk.gene?.startsWith('rs') ? undefined : risk.gene)}
                            token={token}
                            isDarkMode={isDarkMode}
                            alphaMissense={variant ? data?.alpha_missense_map?.[variant] : undefined}
                            clinvarCount={variant ? data?.clinvar_count_map?.[variant] : undefined}
                            genotype={variant ? data?.genotype_map?.[variant] : undefined}
                            pathogenicityMap={data?.pathogenicity_map}
                            theme={theme}
                          />
                        ))}
                      </div>
                    )}

                    {/* Gene Context — burden + known diseases */}
                    {risk.geneSymbol && data?.gene_stats_map?.[risk.geneSymbol] && (
                      <GeneContextBox
                        gene={risk.geneSymbol}
                        stats={data.gene_stats_map[risk.geneSymbol]}
                        theme={theme}
                      />
                    )}
                    {risk.variantInfo?.[0] && data?.alphafold_map?.[risk.variantInfo[0]] && (
                      <AlphaFoldDetailBox
                        rsid={risk.variantInfo[0]}
                        alphafoldData={data.alphafold_map[risk.variantInfo[0]]}
                        theme={theme}
                      />
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
            )}
          </div>
        ))}
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