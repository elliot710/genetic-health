'use client'

import React, { useState, useMemo, useCallback } from 'react'
import { Dna, ChevronRight, CheckCircle, Search, Filter } from 'lucide-react'
import SmartInsights from '../SmartInsights'
import { CapacityChart } from './GenomicCharts'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  StatusBadge,
  DisclaimerCard,
  capacityToSeverity,
  VariantInfoBox,
  GeneContextBox,
  AlphaFoldDetailBox,
  AlphaFoldBadge,
  GeneBurdenStrip,
  ZygosityBadge,
  ClickableRsidBadge,
  formatLabel,
  MasonryLayout,
  useGrouping,
  GroupHeader,
  GroupBySelect,
} from './shared'
import type { CategoryPanelProps, MethylationProfile } from './types'

export default function MethylationPanel({ isDarkMode = false, data, token }: CategoryPanelProps) {
  const [selectedGene, setSelectedGene] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [capacityFilter, setCapacityFilter] = useState<string>('all')
  const [groupBy, setGroupBy] = useState('none')
  const theme = useThemeClasses(isDarkMode)

  const profiles: MethylationProfile[] = data?.methylation_profiles || []

  const allSupplements = useMemo(() => {
    const seen = new Set<string>()
    const result: string[] = []
    for (const profile of profiles) {
      for (const rec of (Array.isArray(profile.supplement_recommendations) ? profile.supplement_recommendations : [])) {
        const key = rec.toLowerCase().trim()
        if (!seen.has(key)) {
          seen.add(key)
          result.push(rec)
        }
      }
    }
    return result
  }, [profiles])

  const capacityOptions = useMemo(() => {
    const set = new Set<string>()
    for (const p of profiles) set.add(p.methylation_capacity || 'normal')
    return Array.from(set).sort()
  }, [profiles])

  const filteredProfiles = useMemo(() => {
    let list = profiles
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      list = list.filter(p =>
        p.gene?.toLowerCase().includes(q) ||
        p.variant?.toLowerCase().includes(q) ||
        p.associated_variants?.some(v => v.toLowerCase().includes(q)) ||
        p.supplement_recommendations?.some(r => r.toLowerCase().includes(q))
      )
    }
    if (capacityFilter !== 'all') {
      list = list.filter(p => (p.methylation_capacity || 'normal') === capacityFilter)
    }
    return list
  }, [profiles, searchQuery, capacityFilter])

  const METHYL_GROUP_OPTIONS: Record<string, string> = { none: 'No Grouping', capacity: 'Methylation Capacity', gene: 'Gene' }
  const getGroupKey = useCallback((p: MethylationProfile): string => {
    switch (groupBy) {
      case 'capacity': return formatLabel(p.methylation_capacity || 'normal')
      case 'gene': return p.gene || 'Unknown'
      default: return 'all'
    }
  }, [groupBy])
  const { groups, collapsedGroups, toggleGroup, resetCollapsed } = useGrouping(filteredProfiles, groupBy, getGroupKey, 'All Markers')

  const headerProps = {
    icon: Dna,
    iconColorClass: 'text-purple-400',
    gradientFrom: 'from-purple-500/20',
    gradientTo: 'to-indigo-500/20',
    borderColor: 'border-purple-500/30',
    title: 'Methylation Profile',
    description: 'Your genetic methylation cycle analysis',
    count: profiles.length,
    countLabel: profiles.length === 1 ? 'Marker' : 'Markers',
    theme,
  }

  if (profiles.length === 0) {
    return (
      <div className="space-y-6">
        <CategoryHeader {...headerProps} />
        <EmptyState
          icon={Dna}
          iconColorClass="text-purple-400"
          gradientFrom="from-purple-500/20"
          gradientTo="to-indigo-500/20"
          borderColor="border-purple-500/30"
          title="No Methylation Data Available"
          description="Methylation pathway analysis is not yet available for your genetic data."
          theme={theme}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <CategoryHeader {...headerProps} />

      {/* Filter Bar */}
      <div className={`${theme.glass} border ${theme.border} rounded-xl p-4 flex flex-col sm:flex-row gap-3`}>
        <div className="relative flex-1">
          <Search className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
          <input
            type="text"
            placeholder="Search by gene, rsid, or keyword..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className={`w-full pl-9 pr-3 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} placeholder:${theme.textSecondary} text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/40`}
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className={`h-4 w-4 ${theme.textSecondary}`} />
          <select
            value={capacityFilter}
            onChange={e => setCapacityFilter(e.target.value)}
            className={`px-3 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/40`}
          >
            <option value="all">All Capacities</option>
            {capacityOptions.map(c => (
              <option key={c} value={c}>{formatLabel(c)}</option>
            ))}
          </select>
        </div>
        <GroupBySelect value={groupBy} onChange={v => { setGroupBy(v); resetCollapsed() }} options={METHYL_GROUP_OPTIONS} theme={theme} />
        {(searchQuery || capacityFilter !== 'all') && (
          <span className={`text-xs ${theme.textSecondary} self-center`}>
            {filteredProfiles.length} of {profiles.length}
          </span>
        )}
      </div>

      {profiles.length >= 3 && (
        <SectionCard title="Capacity Distribution" theme={theme}>
          <CapacityChart data={profiles.map(p => ({ name: p.gene, capacity: p.methylation_capacity || 'normal' }))} isDarkMode={isDarkMode} height={200} />
        </SectionCard>
      )}

      <SectionCard title="Methylation Markers" theme={theme}>
        {groups.map(({ key, label, items }) => (
          <div key={key} className="space-y-3">
            {groupBy !== 'none' && (
              <GroupHeader groupKey={key} label={label} count={items.length} isCollapsed={collapsedGroups.has(key)} onToggle={toggleGroup} theme={theme} />
            )}
            {!collapsedGroups.has(key) && (
        <MasonryLayout>
          {items.map((item, index) => {
            const rsid = item.associated_variants?.[0] || item.variant
            const capacity = item.methylation_capacity || 'normal'
            const geneKey = `${item.gene}-${index}`
            const isExpanded = selectedGene === geneKey

            return (
              <div
                key={geneKey}
                className={`${theme.glass} border ${theme.border} rounded-xl p-3 sm:p-4 hover:border-purple-500/50 transition-all duration-300 cursor-pointer`}
                onClick={() => setSelectedGene(isExpanded ? null : geneKey)}
              >
                <div className="flex items-start justify-between mb-1 gap-1">
                  <div className="flex-1 min-w-0">
                    <h4 className={`font-semibold text-sm ${theme.textPrimary} leading-snug`}>{item.gene}</h4>
                  </div>
                  <ChevronRight className={`h-4 w-4 shrink-0 mt-0.5 ${theme.textSecondary} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                </div>

                <div className="flex flex-wrap gap-1 mb-2">
                  <StatusBadge
                    label={formatLabel(capacity)}
                    severity={capacityToSeverity(capacity)}
                  />
                  {rsid && (
                    <>
                      <ClickableRsidBadge rsid={rsid} gene={item.gene} genotype={data?.genotype_map?.[rsid]} alleleString={data?.allele_string_map?.[rsid]} token={token} isDarkMode={isDarkMode} />
                    </>
                  )}
                  <AlphaFoldBadge
                    confidence={data?.alphafold_map?.[rsid]?.confidence}
                    highPct={data?.alphafold_map?.[rsid]?.high_confidence_pct}
                    lowPct={data?.alphafold_map?.[rsid]?.low_confidence_pct}
                  />
                </div>
                {item.gene && data?.gene_stats_map?.[item.gene] && (
                  <GeneBurdenStrip gene={item.gene} stats={data.gene_stats_map[item.gene]} theme={theme} />
                )}

                {isExpanded && (
                  <div className={`mt-4 pt-4 border-t ${theme.border} space-y-3`}>
                    {Array.isArray(item.supplement_recommendations) && item.supplement_recommendations.length > 0 && (
                      <div className="space-y-2">
                        <span className={`text-xs font-semibold ${theme.textSecondary} uppercase tracking-wider`}>Recommendations</span>
                        {item.supplement_recommendations.map((rec: string, i: number) => (
                          <div key={i} className={`flex items-start gap-2 text-sm ${theme.textSecondary}`}>
                            <CheckCircle className="h-4 w-4 text-green-400 mt-0.5 shrink-0" />
                            <span>{rec}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    <VariantInfoBox rsid={rsid} gene={item.gene} token={token} isDarkMode={isDarkMode} alphaMissense={rsid ? data?.alpha_missense_map?.[rsid] : undefined} clinvarCount={rsid ? data?.clinvar_count_map?.[rsid] : undefined} genotype={rsid ? data?.genotype_map?.[rsid] : undefined} pathogenicityMap={data?.pathogenicity_map} theme={theme} />
                    <GeneContextBox gene={item.gene} stats={item.gene ? data?.gene_stats_map?.[item.gene] : undefined} theme={theme} />
                    {rsid && data?.alphafold_map?.[rsid] && (
                      <AlphaFoldDetailBox
                        rsid={rsid}
                        alphafoldData={data.alphafold_map[rsid]}
                        theme={theme}
                      />
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

      {allSupplements.length > 0 && (
        <SectionCard title="Methylation Support" theme={theme}>
          <h4 className={`text-sm font-semibold ${theme.textPrimary} mb-3`}>Supplement Recommendations</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {allSupplements.map((supplement, index) => (
              <div key={index} className={`${theme.glass} border ${theme.border} rounded-lg p-4`}>
                <div className="flex items-start gap-3">
                  <CheckCircle className="h-5 w-5 text-green-400 mt-0.5 shrink-0" />
                  <span className={`font-medium ${theme.textPrimary}`}>{supplement}</span>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      <SmartInsights isDarkMode={isDarkMode} token={token} section="methylation" title="AI Methylation Analysis" />

      <DisclaimerCard theme={theme} />
    </div>
  )
}