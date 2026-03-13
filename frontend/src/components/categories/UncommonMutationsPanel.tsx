import React, { useState, useEffect } from 'react'
import { Search, ChevronRight } from 'lucide-react'
import { Badge } from '../ui/badge'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  StatusBadge,
  VariantLinks,
  clinicalSignificanceToSeverity,
  formatLabel,
  MasonryLayout,
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

interface UncommonMutationsPanelProps {
  isDarkMode?: boolean
  data?: Record<string, unknown>
  token?: string
}

export default function UncommonMutationsPanel({ isDarkMode = false, data, token }: UncommonMutationsPanelProps) {
  const theme = useThemeClasses(isDarkMode)
  const [selectedItem, setSelectedItem] = useState<string | null>(null)

  const [realMutations, setRealMutations] = useState<UncommonMutation[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const loadUncommonMutations = async () => {
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
          const dashboardData = await response.json()
          const mutations = dashboardData.uncommon_mutations || dashboardData.analysis_results?.uncommon_mutations || []
          setRealMutations(mutations)
        }
      } catch {
        // silently handle fetch errors
      } finally {
        setLoading(false)
      }
    }

    loadUncommonMutations()
  }, [token])

  const processUncommonMutations = (): UncommonMutation[] => {
    if (realMutations.length > 0) return realMutations
    if (data?.uncommon_mutations && Array.isArray(data.uncommon_mutations) && data.uncommon_mutations.length > 0) {
      return data.uncommon_mutations
    }
    return []
  }

  const mutations = processUncommonMutations()

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

  if (mutations.length === 0 && !loading) {
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

      <SectionCard title="Uncommon Variant Analysis" theme={theme}>
        <MasonryLayout>
          {mutations.map((mutation, index) => {
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
                  {mutation.rsid && <Badge variant="secondary" className="text-xs">{mutation.rsid}</Badge>}
                  {mutation.effect_size && <Badge variant="outline" className="text-xs">Effect: {mutation.effect_size}</Badge>}
                </div>

                {isExpanded && (
                  <div className={`mt-4 pt-4 border-t ${theme.border} space-y-3`}>
                    <p className={`text-sm ${theme.textSecondary} leading-relaxed`}>{mutation.effect}</p>

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

                    <VariantLinks rsid={mutation.rsid} gene={mutation.gene} token={token} isDarkMode={isDarkMode} />
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
    </div>
  )
}
