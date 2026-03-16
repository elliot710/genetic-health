import React, { useState, useMemo } from 'react'
import { Search, ChevronRight, Filter } from 'lucide-react'
import { Badge } from '../ui/badge'
import type { CategoryPanelProps } from './types'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  StatusBadge,
  DisclaimerCard,
  VariantLinks,
  clinicalSignificanceToSeverity,
  formatLabel,
  MasonryLayout,
  cleanCondition,
} from './shared'


interface UncommonMutation {
  rsid: string
  gene: string
  effect: string
  population_frequency: number
  effect_size: string
  research_status: string
  clinical_relevance: string
  literature_count: number
  mutation_name?: string
  mutation_type?: string
}

export default function UncommonMutationsPanel({ isDarkMode = false, data, token }: CategoryPanelProps) {
  const theme = useThemeClasses(isDarkMode)
  const [selectedItem, setSelectedItem] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [relevanceFilter, setRelevanceFilter] = useState<string>('all')

  const processUncommonMutations = (): UncommonMutation[] => {
    if (data?.uncommon_mutations && Array.isArray(data.uncommon_mutations) && data.uncommon_mutations.length > 0) {
      return data.uncommon_mutations
    }
    return []
  }

  const mutations = processUncommonMutations()

  const relevanceOptions = useMemo(() => {
    const set = new Set<string>()
    for (const m of mutations) set.add(m.clinical_relevance || 'unknown')
    return Array.from(set).sort()
  }, [mutations])

  const filteredMutations = useMemo(() => {
    let list = mutations
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      list = list.filter(m =>
        m.gene?.toLowerCase().includes(q) ||
        m.rsid?.toLowerCase().includes(q) ||
        m.effect?.toLowerCase().includes(q) ||
        m.mutation_name?.toLowerCase().includes(q)
      )
    }
    if (relevanceFilter !== 'all') {
      list = list.filter(m => (m.clinical_relevance || 'unknown') === relevanceFilter)
    }
    return list
  }, [mutations, searchQuery, relevanceFilter])

  const getSummary = () => {
    const summary: Record<string, number> = {}
    mutations.forEach((m) => {
      const key = m.clinical_relevance || 'unknown'
      summary[key] = (summary[key] || 0) + 1
    })
    return summary
  }

  const headerProps = {
    icon: Search,
    iconColorClass: 'text-blue-400',
    gradientFrom: 'from-blue-500/20',
    gradientTo: 'to-indigo-500/20',
    borderColor: 'border-blue-500/30',
    title: 'Uncommon Mutations',
    description: 'Less common genetic variants in your profile',
    count: mutations.length,
    countLabel: mutations.length === 1 ? 'Mutation' : 'Mutations',
    theme,
  }

  if (mutations.length === 0) {
    return (
      <div className="space-y-6">
        <CategoryHeader {...headerProps} />
        <EmptyState
          icon={Search}
          iconColorClass="text-blue-400"
          gradientFrom="from-blue-500/20"
          gradientTo="to-indigo-500/20"
          borderColor="border-blue-500/30"
          title="No Uncommon Mutations Found"
          description="Uncommon mutation analysis is not yet available for your genetic data."
          theme={theme}
        />
      </div>
    )
  }

  const summary = getSummary()

  return (
    <div className="space-y-6">
      <CategoryHeader {...headerProps} />

      {/* Filter Bar */}
      <div className={`${theme.glass} border ${theme.border} rounded-xl p-4 flex flex-col sm:flex-row gap-3`}>
        <div className="relative flex-1">
          <Search className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
          <input
            type="text"
            placeholder="Search by gene, rsid, or effect..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className={`w-full pl-9 pr-3 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} placeholder:${theme.textSecondary} text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40`}
          />
        </div>
        <div className="flex items-center gap-2">
          <Filter className={`h-4 w-4 ${theme.textSecondary}`} />
          <select
            value={relevanceFilter}
            onChange={e => setRelevanceFilter(e.target.value)}
            className={`px-3 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40`}
          >
            <option value="all">All Relevance</option>
            {relevanceOptions.map(r => (
              <option key={r} value={r}>{formatLabel(r)}</option>
            ))}
          </select>
        </div>
        {(searchQuery || relevanceFilter !== 'all') && (
          <span className={`text-xs ${theme.textSecondary} self-center`}>
            {filteredMutations.length} of {mutations.length}
          </span>
        )}
      </div>

      <SectionCard title="Uncommon Variant Analysis" theme={theme}>
        <MasonryLayout>
          {filteredMutations.map((mutation, index) => {
            const itemKey = `uncommon-${index}`
            const isExpanded = selectedItem === itemKey
            return (
              <div
                key={mutation.rsid || index}
                className={`${theme.glass} border ${theme.border} rounded-xl p-5 cursor-pointer hover:border-blue-500/50 transition-all duration-300`}
                onClick={() => setSelectedItem(isExpanded ? null : itemKey)}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <h4 className={`font-bold text-lg ${theme.textPrimary}`}>{mutation.gene}</h4>
                    <StatusBadge
                      label={formatLabel(mutation.clinical_relevance || 'unknown')}
                      severity={clinicalSignificanceToSeverity(mutation.clinical_relevance)}
                    />
                  </div>
                  <ChevronRight className={`h-5 w-5 ${theme.textSecondary} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {mutation.rsid && <Badge variant="secondary" className="text-xs font-mono">{mutation.rsid}{data?.genotype_map?.[mutation.rsid] ? ` ${data.genotype_map[mutation.rsid]}` : ''}</Badge>}
                  {mutation.effect_size && <Badge variant="outline" className="text-xs">Effect: {mutation.effect_size}</Badge>}
                </div>

                {mutation.effect && (
                  <p className={`text-sm ${theme.textSecondary} mt-2 line-clamp-2`}>{cleanCondition(mutation.effect)}</p>
                )}

                {isExpanded && (
                  <div className={`mt-4 pt-4 border-t ${theme.border} space-y-3`}>
                    <p className={`text-sm ${theme.textSecondary} leading-relaxed`}>{cleanCondition(mutation.effect)}</p>

                    {mutation.mutation_name && (
                      <div className={`text-sm ${theme.textSecondary}`}>
                        <span className="font-medium">Genotype:</span> {mutation.mutation_name}
                      </div>
                    )}

                    <div className="flex items-center gap-4">
                      <span className={`text-xs ${theme.textSecondary}`}>
                        Frequency: {(mutation.population_frequency * 100).toFixed(1)}%
                      </span>
                      {mutation.research_status && (
                        <span className={`text-xs ${theme.textSecondary}`}>
                          Research: {mutation.research_status}
                        </span>
                      )}
                      {mutation.literature_count > 0 && (
                        <span className={`text-xs ${theme.textSecondary}`}>
                          {mutation.literature_count} studies
                        </span>
                      )}
                    </div>

                    <VariantLinks rsid={mutation.rsid} gene={mutation.gene} token={token} isDarkMode={isDarkMode} alphaMissense={mutation.rsid ? data?.alpha_missense_map?.[mutation.rsid] : undefined} clinvarCount={mutation.rsid ? data?.clinvar_count_map?.[mutation.rsid] : undefined} />
                  </div>
                )}
              </div>
            )
          })}
        </MasonryLayout>
      </SectionCard>

      <SectionCard title="Summary" theme={theme}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Object.entries(summary).map(([category, count]) => (
            <div
              key={category}
              className={`${theme.glass} border ${theme.border} rounded-xl p-4 text-center`}
            >
              <div className={`text-2xl font-bold ${theme.textPrimary} mb-1`}>{count}</div>
              <div className={`text-sm ${theme.textSecondary} capitalize`}>{category}</div>
            </div>
          ))}
        </div>
      </SectionCard>

      <DisclaimerCard theme={theme} />
    </div>
  )
}
