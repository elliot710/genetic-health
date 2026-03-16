'use client'

import React, { useState, useMemo } from 'react'
import { Dna, ChevronRight, CheckCircle, Search, Filter } from 'lucide-react'
import { Badge } from '../ui/badge'
import { CapacityChart } from './GenomicCharts'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  StatusBadge,
  DisclaimerCard,
  capacityToSeverity,
  VariantLinks,
  PathogenicityBar,
  ZygosityBadge,
  formatLabel,
  MasonryLayout,
} from './shared'
import type { CategoryPanelProps, MethylationProfile } from './types'

export default function MethylationPanel({ isDarkMode = false, data, token }: CategoryPanelProps) {
  const [selectedGene, setSelectedGene] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [capacityFilter, setCapacityFilter] = useState<string>('all')
  const theme = useThemeClasses(isDarkMode)

  const profiles: MethylationProfile[] = data?.methylation_profiles || []

  const allSupplements = useMemo(() => {
    const seen = new Set<string>()
    const result: string[] = []
    for (const profile of profiles) {
      for (const rec of profile.supplement_recommendations || []) {
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
        <MasonryLayout>
          {filteredProfiles.map((item, index) => {
            const rsid = item.associated_variants?.[0] || item.variant
            const capacity = item.methylation_capacity || 'normal'
            const geneKey = `${item.gene}-${index}`
            const isExpanded = selectedGene === geneKey
            const description = item.supplement_recommendations?.[0] || ''

            return (
              <div
                key={geneKey}
                className={`${theme.glass} border ${theme.border} rounded-xl p-5 hover:border-purple-500/50 transition-all duration-300 cursor-pointer`}
                onClick={() => setSelectedGene(isExpanded ? null : geneKey)}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <h4 className={`font-bold text-lg ${theme.textPrimary}`}>{item.gene}</h4>
                    <StatusBadge
                      label={formatLabel(capacity)}
                      severity={capacityToSeverity(capacity)}
                    />
                  </div>
                  <ChevronRight className={`h-5 w-5 ${theme.textSecondary} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                </div>

                {rsid && (
                  <>
                    <Badge variant="secondary" className="text-xs font-mono">{rsid}{data?.genotype_map?.[rsid] ? ` ${data.genotype_map[rsid]}` : ''}</Badge>
                    <ZygosityBadge genotype={data?.genotype_map?.[rsid]} />
                  </>
                )}

                {description && (
                  <p className={`text-sm ${theme.textSecondary} mt-2 line-clamp-2`}>{description}</p>
                )}

                {isExpanded && (
                  <div className={`mt-4 pt-4 border-t ${theme.border} space-y-3`}>
                    {item.supplement_recommendations?.length > 0 && (
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
                    {rsid && <PathogenicityBar rsid={rsid} pathogenicityMap={data?.pathogenicity_map} theme={theme} />}
                    <VariantLinks rsid={rsid} gene={item.gene} token={token} isDarkMode={isDarkMode} alphaMissense={rsid ? data?.alpha_missense_map?.[rsid] : undefined} clinvarCount={rsid ? data?.clinvar_count_map?.[rsid] : undefined} />
                  </div>
                )}
              </div>
            )
          })}
        </MasonryLayout>
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

      <DisclaimerCard theme={theme} />
    </div>
  )
}