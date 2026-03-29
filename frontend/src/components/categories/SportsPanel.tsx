import React, { useState, useMemo, useCallback } from 'react'
import { Dumbbell, ChevronRight, CheckCircle, Search, Filter } from 'lucide-react'
import SmartInsights from '../SmartInsights'
import { Badge } from '../ui/badge'
import { CapacityChart } from './GenomicCharts'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  StatusBadge,
  DisclaimerCard,
  VariantLinks,
  PathogenicityBar,
  VariantInfoBox,
  GeneContextBox,
  GeneBurdenStrip,
  ZygosityBadge,
  advantageToSeverity,
  formatLabel,
  MasonryLayout,
  cleanCondition,
  useGrouping,
  GroupHeader,
  GroupBySelect,
} from './shared'
import type { CategoryPanelProps, SportsPerformance } from './types'


export default function SportsPanel({ isDarkMode = false, data, token }: CategoryPanelProps) {
  const theme = useThemeClasses(isDarkMode)
  const [selectedItem, setSelectedItem] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [advantageFilter, setAdvantageFilter] = useState<string>('all')
  const [groupBy, setGroupBy] = useState('none')

  const getAthleticTraits = () => {
    const sportsData = Array.isArray(data?.sports_performance) ? data.sports_performance as SportsPerformance[] : []
    if (sportsData.length > 0) {
      return sportsData.map((trait: SportsPerformance) => ({
        trait: trait.performance_category || trait.trait_name || trait.category,
        gene: trait.associated_variants?.[0] || 'Multiple',
        result: trait.genetic_advantage || trait.genetic_result,
        score: trait.genetic_advantage === 'high' ? 85 : trait.genetic_advantage === 'moderate' ? 65 : 45,
        description: trait.description || `Genetic analysis for ${trait.performance_category || trait.trait_name}`,
        recommendation: Array.isArray(trait.sport_recommendations)
          ? trait.sport_recommendations.join(', ')
          : trait.sport_recommendations || trait.training_advice || 'Consult with sports trainer',
      }))
    }

    return []
  }

  const athleticTraits = getAthleticTraits()

  const advantageOptions = useMemo(() => {
    const set = new Set<string>()
    for (const t of athleticTraits) set.add((t.result || 'moderate').toLowerCase())
    return Array.from(set).sort()
  }, [athleticTraits])

  const filteredTraits = useMemo(() => {
    let list = athleticTraits
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      list = list.filter(t => t.trait.toLowerCase().includes(q) || t.gene.toLowerCase().includes(q))
    }
    if (advantageFilter !== 'all') {
      list = list.filter(t => (t.result || 'moderate').toLowerCase() === advantageFilter)
    }
    return list
  }, [athleticTraits, searchQuery, advantageFilter])

  const SPORTS_GROUP_OPTIONS: Record<string, string> = { none: 'No Grouping', advantage: 'Genetic Advantage' }
  const getGroupKey = useCallback((trait: { result: string }) => {
    if (groupBy === 'advantage') {
      const r = (trait.result || 'moderate').toLowerCase()
      return r.charAt(0).toUpperCase() + r.slice(1) + ' Advantage'
    }
    return 'All'
  }, [groupBy])
  const { groups, collapsedGroups, toggleGroup, resetCollapsed } = useGrouping(filteredTraits, groupBy, getGroupKey)

  const allRecommendations = useMemo(() => {
    const seen = new Set<string>()
    const result: string[] = []
    for (const t of athleticTraits) {
      if (t.recommendation) {
        for (const rec of t.recommendation.split(', ')) {
          const key = rec.toLowerCase().trim()
          if (!seen.has(key) && key) { seen.add(key); result.push(rec) }
        }
      }
    }
    return result
  }, [athleticTraits])

  const headerProps = {
    icon: Dumbbell,
    iconColorClass: 'text-orange-400',
    gradientFrom: 'from-orange-500/20',
    gradientTo: 'to-red-500/20',
    borderColor: 'border-orange-500/30',
    title: 'Sports & Fitness',
    description: 'Genetic insights for athletic performance',
    count: athleticTraits.length,
    countLabel: athleticTraits.length === 1 ? 'Trait' : 'Traits',
    theme,
  }

  if (athleticTraits.length === 0) {
    return (
      <div className="space-y-6">
        <CategoryHeader {...headerProps} />
        <EmptyState
          icon={Dumbbell}
          iconColorClass="text-orange-400"
          gradientFrom="from-orange-500/20"
          gradientTo="to-red-500/20"
          borderColor="border-orange-500/30"
          title="No Sports Data Available"
          description="Sports performance analysis is not yet available."
          theme={theme}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <CategoryHeader {...headerProps} />

      {athleticTraits.length >= 3 && (
        <SectionCard title="Advantage Distribution" theme={theme}>
          <CapacityChart data={athleticTraits.map(t => ({ name: t.trait, capacity: t.result || 'moderate' }))} isDarkMode={isDarkMode} />
        </SectionCard>
      )}

      {/* Filter Bar */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-50">
          <Search className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
          <input
            type="text"
            placeholder="Search traits or genes…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} placeholder:${theme.textSecondary} focus:outline-none focus:ring-2 focus:ring-orange-500/40 text-sm`}
          />
        </div>
        <div className="relative min-w-40">
          <Filter className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
          <select
            value={advantageFilter}
            onChange={e => setAdvantageFilter(e.target.value)}
            className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} focus:outline-none focus:ring-2 focus:ring-orange-500/40 text-sm appearance-none cursor-pointer`}
          >
            <option value="all">All Advantages</option>
            {advantageOptions.map(s => (
              <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
            ))}
          </select>
        </div>
        <GroupBySelect options={SPORTS_GROUP_OPTIONS} value={groupBy} onChange={v => { setGroupBy(v); resetCollapsed() }} theme={theme} />
      </div>

      <SectionCard title={`Athletic Traits${filteredTraits.length !== athleticTraits.length ? ` (${filteredTraits.length} of ${athleticTraits.length})` : ''}`} theme={theme}>
        {groups.map(({ key, label, items }) => (
          <div key={key}>
            {groupBy !== 'none' && <GroupHeader groupKey={key} label={label} count={items.length} isCollapsed={collapsedGroups.has(key)} onToggle={toggleGroup} theme={theme} />}
            {!collapsedGroups.has(key) && (
        <MasonryLayout>
          {items.map((trait, index) => {
            const itemKey = `sport-${index}`
            const isExpanded = selectedItem === itemKey
            const rsid = trait.gene?.startsWith('rs') ? trait.gene : undefined
            const gene = !trait.gene?.startsWith('rs') ? trait.gene : undefined
            return (
              <div
                key={index}
                className={`${theme.glass} border ${theme.border} rounded-xl p-3 sm:p-4 cursor-pointer hover:border-orange-500/50 transition-all duration-300`}
                onClick={() => setSelectedItem(isExpanded ? null : itemKey)}
              >
                <div className="flex items-start justify-between mb-1 gap-1">
                  <h4 className={`font-semibold text-sm ${theme.textPrimary} leading-snug flex-1 min-w-0`}>{cleanCondition(trait.trait)}</h4>
                  <ChevronRight className={`h-4 w-4 shrink-0 mt-0.5 ${theme.textSecondary} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                </div>

                <div className="flex flex-wrap gap-1">
                  <StatusBadge
                    label={formatLabel(trait.result || 'Detected')}
                    severity={advantageToSeverity(trait.result || 'moderate')}
                  />
                  {rsid && <Badge variant="secondary" className="text-xs font-mono">{rsid}{data?.genotype_map?.[rsid] ? ` ${data.genotype_map[rsid]}` : ''}</Badge>}
                  {rsid && <ZygosityBadge genotype={data?.genotype_map?.[rsid]} />}
                  {gene && <Badge variant="outline" className="text-xs">{gene}</Badge>}
                </div>

                {isExpanded && (
                  <div className={`mt-4 pt-4 border-t ${theme.border} space-y-3`}>
                    <p className={`text-sm ${theme.textSecondary} leading-relaxed`}>{cleanCondition(trait.description)}</p>
                    {trait.recommendation && (
                      <div className="space-y-2">
                        <span className={`text-xs font-semibold ${theme.textSecondary} uppercase tracking-wider`}>Recommendations</span>
                        {trait.recommendation.split(', ').map((rec: string, i: number) => (
                          <div key={i} className={`flex items-start gap-2 text-sm ${theme.textSecondary}`}>
                            <CheckCircle className="h-4 w-4 text-green-400 mt-0.5 shrink-0" />
                            <span>{rec}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    <VariantInfoBox rsid={rsid} gene={gene} token={token} isDarkMode={isDarkMode} alphaMissense={rsid ? data?.alpha_missense_map?.[rsid] : undefined} clinvarCount={rsid ? data?.clinvar_count_map?.[rsid] : undefined} genotype={rsid ? data?.genotype_map?.[rsid] : undefined} pathogenicityMap={data?.pathogenicity_map} theme={theme} />
                    <GeneContextBox gene={gene} stats={gene ? data?.gene_stats_map?.[gene] : undefined} theme={theme} />
                  </div>
            )}
          </div>
        ))}
      </SectionCard>

      {allRecommendations.length > 0 && (
        <SectionCard title="Training Recommendations" theme={theme}>
          <div className="space-y-2">
            {allRecommendations.map((rec, i) => (
              <div key={i} className={`flex items-start gap-2 text-sm ${theme.textSecondary}`}>
                <CheckCircle className="h-4 w-4 text-orange-400 mt-0.5 shrink-0" />
                <span>{rec}</span>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      <SmartInsights isDarkMode={isDarkMode} token={token} section="sports" title="AI Sports Analysis" />

      <DisclaimerCard theme={theme} />
    </div>
  )
}
