'use client'

import { useState, useMemo } from 'react'
import { AlertTriangle, Shield, Info, ChevronRight, ChevronDown, CheckCircle, Search, Filter, LayoutGrid } from 'lucide-react'
import SmartInsights from '../SmartInsights'
import { Badge } from '../ui/badge'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  StatusBadge,
  DisclaimerCard,
  VariantLinks,
  PathogenicityBar,
  ZygosityBadge,
  clinicalSignificanceToSeverity,
  formatLabel,
  MasonryLayout,
  cleanCondition,
} from './shared'
import type { CategoryPanelProps, RareMutation } from './types'

type GroupByOption = 'none' | 'gene' | 'disease' | 'significance' | 'mutation_type' | 'inheritance'

const GROUP_BY_LABELS: Record<GroupByOption, string> = {
  none: 'No Grouping',
  gene: 'Gene',
  disease: 'Disease',
  significance: 'Clinical Significance',
  mutation_type: 'Mutation Type',
  inheritance: 'Inheritance Pattern',
}

export default function RareMutationsPanel({ data, isDarkMode = false, token }: CategoryPanelProps) {
  const [selectedMutation, setSelectedMutation] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [significanceFilter, setSignificanceFilter] = useState<string>('all')
  const [mutationTypeFilter, setMutationTypeFilter] = useState<string>('all')
  const [groupBy, setGroupBy] = useState<GroupByOption>('none')
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())
  const theme = useThemeClasses(isDarkMode)

  const processRareMutations = (): RareMutation[] => {
    if (!data || typeof data !== 'object') return []
    if ('rare_mutations' in data && Array.isArray(data.rare_mutations) && data.rare_mutations.length > 0) {
      return data.rare_mutations
    }
    return []
  }

  const rareMutations = processRareMutations()

  const getRsid = (m: RareMutation) =>
    m.rsid || m.associated_variants?.[0] || m.mutation_name || undefined

  const getDisplayGene = (m: RareMutation) =>
    m.gene && m.gene !== 'Unknown' ? m.gene : undefined

  const getTitle = (m: RareMutation) => {
    const disease = m.disease_association
    if (disease && disease !== 'Under investigation' && disease !== 'No known disease association') {
      return disease
    }
    return getDisplayGene(m) || getRsid(m) || 'Unknown Variant'
  }

  const significanceOptions = useMemo(() => {
    const set = new Set<string>()
    for (const m of rareMutations) set.add(m.clinical_significance || 'unknown')
    return Array.from(set).sort()
  }, [rareMutations])

  const mutationTypeOptions = useMemo(() => {
    const set = new Set<string>()
    for (const m of rareMutations) if (m.mutation_type) set.add(m.mutation_type)
    return Array.from(set).sort()
  }, [rareMutations])

  const filteredMutations = useMemo(() => {
    let list = rareMutations
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      list = list.filter(m =>
        m.gene?.toLowerCase().includes(q) ||
        getRsid(m)?.toLowerCase().includes(q) ||
        m.disease_association?.toLowerCase().includes(q) ||
        m.mutation_name?.toLowerCase().includes(q) ||
        m.mutation_type?.toLowerCase().includes(q)
      )
    }
    if (significanceFilter !== 'all') {
      list = list.filter(m => (m.clinical_significance || 'unknown') === significanceFilter)
    }
    if (mutationTypeFilter !== 'all') {
      list = list.filter(m => m.mutation_type === mutationTypeFilter)
    }
    return list
  }, [rareMutations, searchQuery, significanceFilter, mutationTypeFilter])

  /** Group key extractor for each mutation */
  const getGroupKey = (m: RareMutation): string => {
    switch (groupBy) {
      case 'gene': return getDisplayGene(m) || 'Unknown Gene'
      case 'disease': {
        const d = m.disease_association
        if (!d || d === 'Under investigation' || d === 'No known disease association') return 'Unassociated'
        // Use first disease if semicolon-separated
        return cleanCondition(d.split(';')[0].trim())
      }
      case 'significance': return formatLabel(m.clinical_significance || 'unknown')
      case 'mutation_type': return formatLabel(m.mutation_type || 'unknown')
      case 'inheritance': return formatLabel(m.inheritance_pattern || 'unknown')
      default: return 'all'
    }
  }

  /** Grouped mutations — sorted by group size descending */
  const groupedMutations = useMemo(() => {
    if (groupBy === 'none') return [{ key: 'all', label: 'All Mutations', items: filteredMutations }]

    const groups = new Map<string, RareMutation[]>()
    for (const m of filteredMutations) {
      const key = getGroupKey(m)
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push(m)
    }
    return Array.from(groups.entries())
      .map(([key, items]) => ({ key, label: key, items }))
      .sort((a, b) => b.items.length - a.items.length)
  }, [filteredMutations, groupBy])

  const toggleGroup = (key: string) => {
    setCollapsedGroups(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  const headerProps = {
    icon: AlertTriangle,
    iconColorClass: 'text-red-400',
    gradientFrom: 'from-red-500/20',
    gradientTo: 'to-orange-500/20',
    borderColor: 'border-red-500/30',
    title: 'Rare Mutations',
    description: 'Uncommon genetic variants with potential clinical significance',
    count: rareMutations.length,
    countLabel: rareMutations.length === 1 ? 'Mutation' : 'Mutations',
    theme,
  }

  if (rareMutations.length === 0) {
    return (
      <div className="space-y-6">
        <CategoryHeader {...headerProps} />
        <EmptyState
          icon={Shield}
          iconColorClass="text-green-400"
          gradientFrom="from-green-500/20"
          gradientTo="to-blue-500/20"
          borderColor="border-green-500/30"
          title="No Rare Mutations Found"
          description="No rare genetic mutations with high clinical significance were identified in your genetic data."
          theme={theme}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <CategoryHeader {...headerProps} />

      {/* Filter Bar */}
      <div className={`${theme.glass} border ${theme.border} rounded-xl p-4 flex flex-col gap-3`}>
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
            <input
              type="text"
              placeholder="Search by gene, rsid, condition..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className={`w-full pl-9 pr-3 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} placeholder:${theme.textSecondary} text-sm focus:outline-none focus:ring-2 focus:ring-red-500/40`}
            />
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Filter className={`h-4 w-4 ${theme.textSecondary} shrink-0`} />
            <select
              value={significanceFilter}
              onChange={e => setSignificanceFilter(e.target.value)}
              className={`px-3 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} text-sm focus:outline-none focus:ring-2 focus:ring-red-500/40`}
            >
              <option value="all">All Significance</option>
              {significanceOptions.map(s => (
                <option key={s} value={s}>{formatLabel(s)}</option>
              ))}
            </select>
            {mutationTypeOptions.length > 1 && (
              <select
                value={mutationTypeFilter}
                onChange={e => setMutationTypeFilter(e.target.value)}
                className={`px-3 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} text-sm focus:outline-none focus:ring-2 focus:ring-red-500/40`}
              >
                <option value="all">All Types</option>
                {mutationTypeOptions.map(t => (
                  <option key={t} value={t}>{formatLabel(t)}</option>
                ))}
              </select>
            )}
            <div className="flex items-center gap-1.5">
              <LayoutGrid className={`h-4 w-4 ${theme.textSecondary} shrink-0`} />
              <select
                value={groupBy}
                onChange={e => { setGroupBy(e.target.value as GroupByOption); setCollapsedGroups(new Set()) }}
                className={`px-3 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} text-sm focus:outline-none focus:ring-2 focus:ring-red-500/40`}
              >
                {Object.entries(GROUP_BY_LABELS).map(([key, label]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
        {(searchQuery || significanceFilter !== 'all' || mutationTypeFilter !== 'all') && (
          <div className="flex items-center gap-2">
            <span className={`text-xs ${theme.textSecondary}`}>
              {filteredMutations.length} of {rareMutations.length} mutations
              {groupBy !== 'none' && ` · ${groupedMutations.length} groups`}
            </span>
            <button
              onClick={() => { setSearchQuery(''); setSignificanceFilter('all'); setMutationTypeFilter('all') }}
              className="text-xs text-red-400 hover:text-red-300 underline"
            >
              Clear filters
            </button>
          </div>
        )}
      </div>

      <SectionCard title="Rare Variant Analysis" theme={theme}>
        {groupedMutations.map(group => {
          const isGroupCollapsed = collapsedGroups.has(group.key)
          return (
            <div key={group.key} className="mb-4 last:mb-0">
              {/* Group header — only show when actually grouped */}
              {groupBy !== 'none' && (
                <button
                  onClick={() => toggleGroup(group.key)}
                  className={`w-full flex items-center gap-2 px-3 py-2.5 rounded-lg ${theme.glass} border ${theme.border} mb-3 hover:border-red-500/40 transition-colors`}
                >
                  {isGroupCollapsed
                    ? <ChevronRight className={`h-4 w-4 ${theme.textSecondary}`} />
                    : <ChevronDown className={`h-4 w-4 ${theme.textSecondary}`} />
                  }
                  <span className={`font-semibold text-sm ${theme.textPrimary}`}>{group.label}</span>
                  <Badge variant="secondary" className="text-xs ml-auto">{group.items.length}</Badge>
                </button>
              )}

              {!isGroupCollapsed && (
                <MasonryLayout>
                  {group.items.map((mutation: RareMutation, index: number) => {
            const rsid = getRsid(mutation)
            const gene = getDisplayGene(mutation)
            const title = getTitle(mutation)
            const mutationId = `mutation-${index}`
            const isExpanded = selectedMutation === mutationId

            return (
              <div
                key={index}
                className={`${theme.glass} border ${theme.border} rounded-xl p-3 sm:p-4 cursor-pointer hover:border-red-500/50 transition-all duration-300`}
                onClick={() => setSelectedMutation(isExpanded ? null : mutationId)}
              >
                <div className="flex items-start justify-between mb-2 gap-2">
                  <h4 className={`font-semibold text-base ${theme.textPrimary} leading-snug flex-1 min-w-0`}>{cleanCondition(title)}</h4>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <StatusBadge
                      label={formatLabel(mutation.clinical_significance)}
                      severity={clinicalSignificanceToSeverity(mutation.clinical_significance)}
                    />
                    <ChevronRight className={`h-5 w-5 ${theme.textSecondary} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                  </div>
                </div>

                <div className="flex flex-wrap gap-1">
                  {gene && <Badge variant="secondary" className="text-xs">{gene}</Badge>}
                  {rsid && <Badge variant="outline" className="text-xs font-mono">{rsid}{data?.genotype_map?.[rsid] ? ` ${data.genotype_map[rsid]}` : ''}</Badge>}
                  {rsid && <ZygosityBadge genotype={data?.genotype_map?.[rsid]} />}
                  {mutation.mutation_type && (
                    <Badge variant="outline" className="text-xs">{formatLabel(mutation.mutation_type)}</Badge>
                  )}
                </div>

                {/* Show disease as description only when it wasn't used as the title */}
                {title !== mutation.disease_association && mutation.disease_association && mutation.disease_association !== 'Under investigation' && mutation.disease_association !== 'No known disease association' && (
                  <p className={`text-sm ${theme.textSecondary} mt-2 line-clamp-2`}>{cleanCondition(mutation.disease_association)}</p>
                )}
                {(!mutation.disease_association || mutation.disease_association === 'Under investigation') && mutation.effect && (
                  <p className={`text-sm ${theme.textSecondary} mt-2 line-clamp-2`}>{cleanCondition(mutation.effect)}</p>
                )}

                {isExpanded && (
                  <div className={`mt-4 pt-4 border-t ${theme.border} space-y-3`}>
                    {mutation.genotype && (
                      <p className={`text-sm ${theme.textSecondary}`}>
                        <strong>Genotype:</strong>{' '}
                        <span className="font-mono">{mutation.genotype}</span>
                      </p>
                    )}

                    <p className={`text-sm ${theme.textSecondary}`}>
                      {cleanCondition(mutation.disease_association || mutation.effect || 'Under investigation')}
                    </p>

                    <div className="flex items-center gap-4">
                      <span className={`text-xs ${theme.textSecondary}`}>
                        Frequency: {(mutation.population_frequency * 100).toFixed(1)}%
                      </span>
                      {mutation.mutation_type && (
                        <span className={`text-xs ${theme.textSecondary}`}>
                          Type: {formatLabel(mutation.mutation_type)}
                        </span>
                      )}
                    </div>

                    {mutation.penetrance && mutation.penetrance !== 'unknown' && (
                      <p className={`text-sm ${theme.textSecondary}`}>
                        <strong>Penetrance:</strong> {formatLabel(mutation.penetrance)}
                      </p>
                    )}

                    {mutation.inheritance_pattern && (
                      <p className={`text-sm ${theme.textSecondary}`}>
                        <strong>Inheritance:</strong> {formatLabel(mutation.inheritance_pattern)}
                      </p>
                    )}

                    {mutation.clinical_actions && mutation.clinical_actions.length > 0 && (
                      <div className="space-y-2">
                        <span className={`text-xs font-semibold ${theme.textSecondary} uppercase tracking-wider`}>Clinical Actions</span>
                        {mutation.clinical_actions.map((action: string, i: number) => (
                          <div key={i} className={`flex items-start gap-2 text-sm ${theme.textSecondary}`}>
                            <CheckCircle className="h-4 w-4 text-blue-400 mt-0.5 shrink-0" />
                            <span>{action}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {mutation.monitoring_recommendations && mutation.monitoring_recommendations.length > 0 && (
                      <div className="space-y-2">
                        <span className={`text-xs font-semibold ${theme.textSecondary} uppercase tracking-wider`}>Recommendations</span>
                        {mutation.monitoring_recommendations.map((rec: string, i: number) => (
                          <div key={i} className={`flex items-start gap-2 text-sm ${theme.textSecondary}`}>
                            <CheckCircle className="h-4 w-4 text-green-400 mt-0.5 shrink-0" />
                            <span>{rec}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="flex gap-2 flex-wrap">
                      {mutation.genetic_counseling_urgent && (
                        <Badge variant="outline" className="bg-red-500/10 text-red-500 border-red-500/20 text-xs">
                          Counseling Urgent
                        </Badge>
                      )}
                      {mutation.family_screening_recommended && (
                        <Badge variant="outline" className="bg-blue-500/10 text-blue-500 border-blue-500/20 text-xs">
                          Family Screening
                        </Badge>
                      )}
                    </div>

                    {rsid && <PathogenicityBar rsid={rsid} pathogenicityMap={data?.pathogenicity_map} theme={theme} />}
                    <VariantLinks rsid={rsid} gene={gene} token={token} isDarkMode={isDarkMode} alphaMissense={rsid ? data?.alpha_missense_map?.[rsid] : undefined} clinvarCount={rsid ? data?.clinvar_count_map?.[rsid] : undefined} genotype={rsid ? data?.genotype_map?.[rsid] : undefined} />
                  </div>
                )}
              </div>
            )
          })}
                </MasonryLayout>
              )}
            </div>
          )
        })}
      </SectionCard>

      <SmartInsights isDarkMode={isDarkMode} token={token} section="rare_mutations" title="AI Rare Mutations Analysis" />

      <DisclaimerCard
        icon={Info}
        title="Clinical Notes"
        text="This analysis identifies potentially significant rare genetic variants but is not a diagnostic test. All findings require confirmation through clinical genetic testing. Rare variants are found in less than 1% of the population and may have significant health implications. Consult a genetic counselor or physician before making medical decisions based on these results."
        borderColorClass="border-red-500/20"
        bgTintClass="bg-red-500/5"
        theme={theme}
      />
    </div>
  )
}
