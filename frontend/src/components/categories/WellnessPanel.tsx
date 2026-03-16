import React, { useState, useMemo, useEffect } from 'react'
import { Activity, ChevronRight, CheckCircle, Search, Filter } from 'lucide-react'
import { Badge } from '../ui/badge'
import { WellnessScoreChart } from './GenomicCharts'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  StatusBadge,
  DisclaimerCard,
  VariantLinks,
  capacityToSeverity,
  formatLabel,
  MasonryLayout,
  cleanCondition,
} from './shared'
import type { CategoryPanelProps } from './types'
import { apiUrl } from '@/lib/api'

interface WellnessTrait {
  name: string
  category: string
  value: string
  gene: string
  confidence: string
  recommendations: string[]
  associated_variants?: string[]
}

export default function WellnessPanel({ isDarkMode = false, data, token }: CategoryPanelProps) {
  const theme = useThemeClasses(isDarkMode)
  const [selectedItem, setSelectedItem] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [wellnessTraits, setWellnessTraits] = useState<WellnessTrait[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchWellnessData = async () => {
      if (!token) {
        setLoading(false)
        return
      }

      try {
        const response = await fetch(apiUrl('/api/analysis/dashboard-data'), {
          credentials: 'include',
        })

        if (response.ok) {
          const dashboardData = await response.json()
          const traits = dashboardData.wellness_traits || []
          setWellnessTraits(traits.map((t: Record<string, unknown>) => ({
            name: (t.trait || 'Unknown Trait') as string,
            category: (t.category || 'General') as string,
            value: (t.value || 'Normal') as string,
            gene: (t.gene || 'Multiple') as string,
            confidence: (t.confidence || 'Medium') as string,
            recommendations: Array.isArray(t.recommendations) ? t.recommendations as string[] : [],
            associated_variants: Array.isArray(t.associated_variants) ? t.associated_variants as string[] : [],
          })))
        }
      } catch {
        // silently handle fetch errors
      } finally {
        setLoading(false)
      }
    }

    fetchWellnessData()
  }, [token])

  const headerProps = {
    icon: Activity,
    iconColorClass: 'text-green-400',
    gradientFrom: 'from-green-500/20',
    gradientTo: 'to-teal-500/20',
    borderColor: 'border-green-500/30',
    title: 'Wellness & Lifestyle',
    description: 'Personalized wellness insights from your genetic profile',
    count: wellnessTraits.length,
    countLabel: wellnessTraits.length === 1 ? 'Trait' : 'Traits',
    theme,
  }

  const categoryOptions = useMemo(() => {
    const set = new Set<string>()
    for (const t of wellnessTraits) set.add(t.category)
    return Array.from(set).sort()
  }, [wellnessTraits])

  const filteredTraits = useMemo(() => {
    let list = wellnessTraits
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      list = list.filter(t => t.name.toLowerCase().includes(q) || t.gene.toLowerCase().includes(q) || t.category.toLowerCase().includes(q))
    }
    if (categoryFilter !== 'all') {
      list = list.filter(t => t.category === categoryFilter)
    }
    return list
  }, [wellnessTraits, searchQuery, categoryFilter])

  const allRecommendations = useMemo(() => {
    const seen = new Set<string>()
    const result: string[] = []
    for (const t of wellnessTraits) {
      for (const rec of t.recommendations) {
        const key = rec.toLowerCase().trim()
        if (!seen.has(key) && key) { seen.add(key); result.push(rec) }
      }
    }
    return result.slice(0, 8)
  }, [wellnessTraits])

  if (wellnessTraits.length === 0 && !loading) {
    return (
      <div className="space-y-6">
        <CategoryHeader {...headerProps} />
        <EmptyState
          icon={Activity}
          iconColorClass="text-green-400"
          gradientFrom="from-green-500/20"
          gradientTo="to-teal-500/20"
          borderColor="border-green-500/30"
          title="No Wellness Data Available"
          description="Wellness analysis is not yet available. Upload your genetic data to get personalized insights."
          theme={theme}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <CategoryHeader {...headerProps} />

      {wellnessTraits.length >= 3 && (
        <SectionCard title="Wellness Scores Overview" theme={theme}>
          <WellnessScoreChart data={wellnessTraits.map(t => ({ metric: t.name, score: t.value === 'normal' ? 80 : t.value === 'variant_detected' || t.value === 'reduced' ? 50 : t.value === 'impaired' ? 25 : 65 }))} isDarkMode={isDarkMode} height={220} />
        </SectionCard>
      )}

      {/* Filter Bar */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-50">
          <Search className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
          <input
            type="text"
            placeholder="Search traits, genes, or categories…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} placeholder:${theme.textSecondary} focus:outline-none focus:ring-2 focus:ring-green-500/40 text-sm`}
          />
        </div>
        {categoryOptions.length > 1 && (
          <div className="relative min-w-40">
            <Filter className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
            <select
              value={categoryFilter}
              onChange={e => setCategoryFilter(e.target.value)}
              className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} focus:outline-none focus:ring-2 focus:ring-green-500/40 text-sm appearance-none cursor-pointer`}
            >
              <option value="all">All Categories</option>
              {categoryOptions.map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      <SectionCard title={`Wellness Markers${filteredTraits.length !== wellnessTraits.length ? ` (${filteredTraits.length} of ${wellnessTraits.length})` : ''}`} theme={theme}>
        <MasonryLayout>
          {filteredTraits.map((trait, index) => {
            const itemKey = `wellness-${index}`
            const isExpanded = selectedItem === itemKey
            return (
              <div
                key={index}
                className={`${theme.glass} border ${theme.border} rounded-xl p-5 cursor-pointer hover:border-green-500/50 transition-all duration-300`}
                onClick={() => setSelectedItem(isExpanded ? null : itemKey)}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <h4 className={`font-bold text-lg ${theme.textPrimary}`}>{cleanCondition(trait.name)}</h4>
                    <StatusBadge
                      label={formatLabel(trait.value)}
                      severity={capacityToSeverity(trait.value)}
                    />
                  </div>
                  <ChevronRight className={`h-5 w-5 ${theme.textSecondary} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {trait.associated_variants && trait.associated_variants.length > 0
                    ? trait.associated_variants.map((v, i) => (
                        <Badge key={i} variant="secondary" className="text-xs font-mono">{v}{data?.genotype_map?.[v] ? ` ${data.genotype_map[v]}` : ''}</Badge>
                      ))
                    : trait.gene && trait.gene !== 'Multiple' && (
                        <Badge variant="secondary" className="text-xs">{trait.gene}</Badge>
                      )
                  }
                  <Badge variant="outline" className="text-xs">{trait.category}</Badge>
                </div>

                {isExpanded && (
                  <div className={`mt-4 pt-4 border-t ${theme.border} space-y-3`}>
                    <div className={`text-sm ${theme.textSecondary}`}>
                      <span className="font-medium">Confidence:</span> {trait.confidence}
                    </div>

                    {trait.recommendations.length > 0 && (
                      <div className="space-y-2">
                        <span className={`text-xs font-semibold ${theme.textSecondary} uppercase tracking-wider`}>Recommendations</span>
                        {trait.recommendations.map((rec: string, i: number) => (
                          <div key={i} className={`flex items-start gap-2 text-sm ${theme.textSecondary}`}>
                            <CheckCircle className="h-4 w-4 text-green-400 mt-0.5 shrink-0" />
                            <span>{rec}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    <VariantLinks rsid={trait.associated_variants?.[0]} gene={trait.gene !== 'Multiple' ? trait.gene : undefined} token={token} isDarkMode={isDarkMode} alphaMissense={trait.associated_variants?.[0] ? data?.alpha_missense_map?.[trait.associated_variants[0]] : undefined} clinvarCount={trait.associated_variants?.[0] ? data?.clinvar_count_map?.[trait.associated_variants[0]] : undefined} />
                  </div>
                )}
              </div>
            )
          })}
        </MasonryLayout>
      </SectionCard>

      {allRecommendations.length > 0 && (
        <SectionCard title="Wellness Recommendations" theme={theme}>
          <div className="space-y-2">
            {allRecommendations.map((rec, i) => (
              <div key={i} className={`flex items-start gap-2 text-sm ${theme.textSecondary}`}>
                <CheckCircle className="h-4 w-4 text-green-400 mt-0.5 shrink-0" />
                <span>{rec}</span>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      <DisclaimerCard theme={theme} />
    </div>
  )
}
