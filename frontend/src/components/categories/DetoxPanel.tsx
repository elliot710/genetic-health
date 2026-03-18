'use client'

import React, { useState, useMemo } from 'react'
import { Shield, ChevronRight, CheckCircle, Search, Filter } from 'lucide-react'
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
  sensitivityToSeverity,
  VariantLinks,
  PathogenicityBar,
  ZygosityBadge,
  formatLabel,
  MasonryLayout,
} from './shared'
import type { CategoryPanelProps, DetoxProfile } from './types'

const PHASE_LABELS: Record<string, string> = {
  phase1: 'Phase I',
  phase2: 'Phase II',
  phase3: 'Phase III',
  antioxidant: 'Antioxidant',
  peroxisomal: 'Peroxisomal',
  coenzyme_a: 'CoA Biosynthesis',
}

const PHASE_ORDER = ['phase1', 'phase2', 'phase3', 'antioxidant', 'peroxisomal', 'coenzyme_a']

export default function DetoxPanel({ isDarkMode = false, data, token }: CategoryPanelProps) {
  const [expandedGene, setExpandedGene] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [phaseFilter, setPhaseFilter] = useState<string>('all')
  const [capacityFilter, setCapacityFilter] = useState<string>('all')
  const theme = useThemeClasses(isDarkMode)

  const profiles: DetoxProfile[] = data?.detoxification_profiles || []

  const formatPhase = (phase: string): string =>
    PHASE_LABELS[phase] || formatLabel(phase)

  const capacityOptions = useMemo(() => {
    const set = new Set<string>()
    for (const p of profiles) set.add(p.detox_capacity || 'normal')
    return Array.from(set).sort()
  }, [profiles])

  const phaseOptions = useMemo(() => {
    const set = new Set<string>()
    for (const p of profiles) set.add(p.detox_phase || 'other')
    return Array.from(set).sort()
  }, [profiles])

  const filteredProfiles = useMemo(() => {
    let list = profiles
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      list = list.filter(p =>
        p.gene?.toLowerCase().includes(q) ||
        p.associated_variants?.some(v => v.toLowerCase().includes(q)) ||
        p.support_recommendations?.some(r => r.toLowerCase().includes(q))
      )
    }
    if (phaseFilter !== 'all') {
      list = list.filter(p => (p.detox_phase || 'other') === phaseFilter)
    }
    if (capacityFilter !== 'all') {
      list = list.filter(p => (p.detox_capacity || 'normal') === capacityFilter)
    }
    return list
  }, [profiles, searchQuery, phaseFilter, capacityFilter])

  const grouped = useMemo(() => {
    const map: Record<string, DetoxProfile[]> = {}
    for (const p of filteredProfiles) {
      const phase = p.detox_phase || 'other'
      if (!map[phase]) map[phase] = []
      map[phase].push(p)
    }
    const sorted = PHASE_ORDER
      .filter(k => map[k])
      .map(k => ({ phase: k, items: map[k] }))
    const extra = Object.keys(map)
      .filter(k => !PHASE_ORDER.includes(k))
      .map(k => ({ phase: k, items: map[k] }))
    return [...sorted, ...extra]
  }, [profiles])

  const allRecommendations = useMemo(() => {
    const seen = new Set<string>()
    const result: string[] = []
    for (const p of profiles) {
      for (const rec of p.support_recommendations || []) {
        const key = rec.toLowerCase().trim()
        if (!seen.has(key)) {
          seen.add(key)
          result.push(rec)
        }
      }
    }
    return result
  }, [profiles])

  const headerProps = {
    icon: Shield,
    iconColorClass: 'text-green-400',
    gradientFrom: 'from-green-500/20',
    gradientTo: 'to-emerald-500/20',
    borderColor: 'border-green-500/30',
    title: 'Detox Capacity',
    description: 'Your genetic detoxification pathway analysis',
    count: profiles.length,
    countLabel: profiles.length === 1 ? 'Marker' : 'Markers',
    theme,
  }

  if (profiles.length === 0) {
    return (
      <div className="space-y-6">
        <CategoryHeader {...headerProps} />
        <EmptyState
          icon={Shield}
          iconColorClass="text-green-400"
          gradientFrom="from-green-500/20"
          gradientTo="to-emerald-500/20"
          borderColor="border-green-500/30"
          title="No Detox Data Available"
          description="Detoxification pathway analysis is not yet available for your genetic data."
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
            className={`w-full pl-9 pr-3 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} placeholder:${theme.textSecondary} text-sm focus:outline-none focus:ring-2 focus:ring-green-500/40`}
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className={`h-4 w-4 ${theme.textSecondary}`} />
          <select
            value={phaseFilter}
            onChange={e => setPhaseFilter(e.target.value)}
            className={`px-3 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} text-sm focus:outline-none focus:ring-2 focus:ring-green-500/40`}
          >
            <option value="all">All Phases</option>
            {phaseOptions.map(p => (
              <option key={p} value={p}>{formatPhase(p)}</option>
            ))}
          </select>
          <select
            value={capacityFilter}
            onChange={e => setCapacityFilter(e.target.value)}
            className={`px-3 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} text-sm focus:outline-none focus:ring-2 focus:ring-green-500/40`}
          >
            <option value="all">All Capacities</option>
            {capacityOptions.map(c => (
              <option key={c} value={c}>{formatLabel(c)}</option>
            ))}
          </select>
        </div>
        {(searchQuery || phaseFilter !== 'all' || capacityFilter !== 'all') && (
          <span className={`text-xs ${theme.textSecondary} self-center`}>
            {filteredProfiles.length} of {profiles.length}
          </span>
        )}
      </div>

      {profiles.length >= 3 && (
        <SectionCard title="Detox Capacity Overview" theme={theme}>
          <CapacityChart data={profiles.map(p => ({ name: p.gene, capacity: p.detox_capacity || 'normal' }))} isDarkMode={isDarkMode} height={200} />
        </SectionCard>
      )}

      {grouped.map(({ phase, items }) => (
        <SectionCard key={phase} title={formatPhase(phase)} theme={theme}>
          <div className="flex items-center gap-2 -mt-2 mb-4">
            <Badge variant="outline" className="text-xs">{items.length}</Badge>
          </div>
          <MasonryLayout>
            {items.map((item: DetoxProfile, idx: number) => {
              const key = `${phase}-${item.gene}-${idx}`
              const isExpanded = expandedGene === key
              const capacity = item.detox_capacity || 'normal'
              const sensitivity = item.toxin_sensitivity

              return (
                <div
                  key={key}
                  className={`${theme.glass} border ${theme.border} rounded-xl p-5 hover:border-green-500/50 transition-all duration-300 cursor-pointer`}
                  onClick={() => setExpandedGene(isExpanded ? null : key)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 flex-wrap">
                      <h4 className={`font-bold text-base ${theme.textPrimary}`}>{item.gene}</h4>
                      <StatusBadge
                        label={formatLabel(capacity)}
                        severity={capacityToSeverity(capacity)}
                      />
                      {sensitivity && (
                        <StatusBadge
                          label={`Sensitivity: ${formatLabel(sensitivity)}`}
                          severity={sensitivityToSeverity(sensitivity)}
                          showIcon={false}
                        />
                      )}
                    </div>
                    <ChevronRight className={`h-5 w-5 ${theme.textSecondary} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                  </div>

                  {item.associated_variants?.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      {item.associated_variants.map((v: string) => (
                        <React.Fragment key={v}>
                          <Badge variant="secondary" className="text-xs font-mono">{v}{data?.genotype_map?.[v] ? ` ${data.genotype_map[v]}` : ''}</Badge>
                          <ZygosityBadge genotype={data?.genotype_map?.[v]} />
                        </React.Fragment>
                      ))}
                    </div>
                  )}

                  {item.support_recommendations?.[0] && (
                    <p className={`text-sm ${theme.textSecondary} mt-2 line-clamp-2`}>{item.support_recommendations[0]}</p>
                  )}

                  {isExpanded && (
                    <div className={`mt-4 pt-4 border-t ${theme.border} space-y-4`}>
                      {item.support_recommendations?.length > 0 && (
                        <div>
                          <h5 className={`text-sm font-semibold ${theme.textPrimary} mb-2`}>Support Recommendations</h5>
                          <div className="space-y-2">
                            {item.support_recommendations.map((rec: string, i: number) => (
                              <div key={i} className="flex items-start gap-2">
                                <CheckCircle className="h-4 w-4 text-green-400 mt-0.5 shrink-0" />
                                <span className={`text-sm ${theme.textSecondary}`}>{rec}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {item.associated_variants?.[0] && <PathogenicityBar rsid={item.associated_variants[0]} pathogenicityMap={data?.pathogenicity_map} theme={theme} />}
                      <VariantLinks
                        rsid={item.associated_variants?.[0]}
                        gene={item.gene}
                        token={token}
                        isDarkMode={isDarkMode}
                        alphaMissense={item.associated_variants?.[0] ? data?.alpha_missense_map?.[item.associated_variants[0]] : undefined}
                        clinvarCount={item.associated_variants?.[0] ? data?.clinvar_count_map?.[item.associated_variants[0]] : undefined}
                        genotype={item.associated_variants?.[0] ? data?.genotype_map?.[item.associated_variants[0]] : undefined}
                      />
                    </div>
                  )}
                </div>
              )
            })}
          </MasonryLayout>
        </SectionCard>
      ))}

      {allRecommendations.length > 0 && (
        <SectionCard title="Detox Support" theme={theme}>
          <div className="space-y-3">
            {allRecommendations.map((rec, i) => (
              <div key={i} className={`${theme.glass} border ${theme.border} rounded-lg p-4`}>
                <div className="flex items-start gap-3">
                  <CheckCircle className="h-5 w-5 text-green-400 mt-0.5 shrink-0" />
                  <span className={`font-medium ${theme.textPrimary}`}>{rec}</span>
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