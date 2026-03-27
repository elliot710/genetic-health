import React, { useState, useMemo, useCallback } from 'react'
import { Pill, Info, ChevronRight, CheckCircle, Search, Filter } from 'lucide-react'
import { Badge } from '../ui/badge'
import { DrugResponseChart } from './GenomicCharts'
import SmartInsights from '../SmartInsights'
import {
  useThemeClasses,
  CategoryHeader,
  SectionCard,
  StatusBadge,
  DisclaimerCard,
  VariantLinks,
  PathogenicityBar,
  VariantInfoBox,
  riskToSeverity,
  MasonryLayout,
  useGrouping,
  GroupHeader,
  GroupBySelect,
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
  const [searchQuery, setSearchQuery] = useState('')
  const [riskFilter, setRiskFilter] = useState<string>('all')
  const [groupBy, setGroupBy] = useState('none')

  const getDrugResponses = () => {
    const drugResponses = Array.isArray(data?.drug_responses) ? data.drug_responses as DrugResponse[] : []
    if (drugResponses.length > 0) {
      return drugResponses
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

  const riskOptions = useMemo(() => {
    const set = new Set<string>()
    for (const d of drugResponses) if (d.risk) set.add(d.risk.toLowerCase())
    return Array.from(set).sort()
  }, [drugResponses])

  const filteredDrugs = useMemo(() => {
    let list = drugResponses
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      list = list.filter(d => d.drug.toLowerCase().includes(q) || d.gene.toLowerCase().includes(q) || d.response.toLowerCase().includes(q))
    }
    if (riskFilter !== 'all') {
      list = list.filter(d => (d.risk || '').toLowerCase() === riskFilter)
    }
    return list
  }, [drugResponses, searchQuery, riskFilter])

  const DRUG_GROUP_OPTIONS: Record<string, string> = { none: 'No Grouping', gene: 'Gene', risk: 'Risk Level' }
  const getGroupKey = useCallback((d: MappedDrugResponse): string => {
    switch (groupBy) {
      case 'gene': return d.gene || 'Unknown Gene'
      case 'risk': return d.risk ? `${d.risk.charAt(0).toUpperCase()}${d.risk.slice(1)} Risk` : 'Unknown'
      default: return 'all'
    }
  }, [groupBy])
  const { groups, collapsedGroups, toggleGroup, resetCollapsed } = useGrouping(filteredDrugs, groupBy, getGroupKey, 'All Drugs')

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

      {drugResponses.length >= 3 && (
        <SectionCard title="Response Distribution" theme={theme}>
          <DrugResponseChart data={drugResponses.map(d => ({ gene: d.gene, drug: d.drug, response_type: d.response }))} isDarkMode={isDarkMode} height={220} />
        </SectionCard>
      )}

      {/* Filter Bar */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-50">
          <Search className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
          <input
            type="text"
            placeholder="Search drugs, genes, or responses…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} placeholder:${theme.textSecondary} focus:outline-none focus:ring-2 focus:ring-blue-500/40 text-sm`}
          />
        </div>
        <div className="relative min-w-40">
          <Filter className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
          <select
            value={riskFilter}
            onChange={e => setRiskFilter(e.target.value)}
            className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} focus:outline-none focus:ring-2 focus:ring-blue-500/40 text-sm appearance-none cursor-pointer`}
          >
            <option value="all">All Risk Levels</option>
            {riskOptions.map(s => (
              <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
            ))}
          </select>
        </div>
        <GroupBySelect value={groupBy} onChange={v => { setGroupBy(v); resetCollapsed() }} options={DRUG_GROUP_OPTIONS} theme={theme} />
      </div>

      <SectionCard title={`Drug Interactions${filteredDrugs.length !== drugResponses.length ? ` (${filteredDrugs.length} of ${drugResponses.length})` : ''}`} theme={theme}>
        {groups.map(({ key, label, items }) => (
          <div key={key} className="space-y-3">
            {groupBy !== 'none' && (
              <GroupHeader groupKey={key} label={label} count={items.length} isCollapsed={collapsedGroups.has(key)} onToggle={toggleGroup} theme={theme} />
            )}
            {!collapsedGroups.has(key) && (
        <MasonryLayout>
          {items.map((drug: MappedDrugResponse, index: number) => {
            const itemKey = `drug-${index}`
            const isExpanded = selectedItem === itemKey
            return (
              <div
                key={index}
                className={`${theme.glass} border ${theme.border} rounded-xl p-3 sm:p-4 cursor-pointer hover:border-blue-500/50 transition-all duration-300`}
                onClick={() => setSelectedItem(isExpanded ? null : itemKey)}
              >
                <div className="flex items-start justify-between mb-1 gap-1">
                  <h4 className={`font-semibold text-sm ${theme.textPrimary} leading-snug flex-1 min-w-0`}>{drug.drug}</h4>
                  <ChevronRight className={`h-4 w-4 shrink-0 mt-0.5 ${theme.textSecondary} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                </div>

                <div className="flex flex-wrap gap-1">
                  <StatusBadge
                    label={`${(drug.risk?.charAt(0).toUpperCase() + drug.risk?.slice(1)) || 'Unknown'} Risk`}
                    severity={riskToSeverity(drug.risk)}
                  />
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

                    <VariantInfoBox rsid={drug.variants?.[0]} gene={drug.gene} token={token} isDarkMode={isDarkMode} alphaMissense={drug.variants?.[0] ? data?.alpha_missense_map?.[drug.variants[0]] : undefined} clinvarCount={drug.variants?.[0] ? data?.clinvar_count_map?.[drug.variants[0]] : undefined} genotype={drug.variants?.[0] ? data?.genotype_map?.[drug.variants[0]] : undefined} pathogenicityMap={data?.pathogenicity_map} theme={theme} />
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

      <DisclaimerCard
        icon={Info}
        title="Important Disclaimer"
        text="This pharmacogenomic information is for educational purposes only and should not replace professional medical advice. Always consult with your healthcare provider before making any changes to your medication regimen."
        theme={theme}
      />

      <SmartInsights isDarkMode={isDarkMode} token={token} section="drug_responses" title="AI Drug Interaction Analysis" />
    </div>
  )
}