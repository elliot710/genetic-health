import React, { useState, useMemo, useCallback } from 'react'
import { Brain, BookOpen, Lightbulb, Target, Puzzle, ChevronRight, CheckCircle, Search, Filter } from 'lucide-react'
import SmartInsights from '../SmartInsights'
import { Badge } from '../ui/badge'
import { PercentileBarChart } from './GenomicCharts'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  StatusBadge,
  ScoreBar,
  PathogenicityBar,
  VariantInfoBox,
  GeneContextBox,
  AlphaFoldDetailBox,
  GeneBurdenStrip,
  DisclaimerCard,
  VariantLinks,
  ZygosityBadge,
  advantageToSeverity,
  formatLabel,
  MasonryLayout,
  cleanCondition,
  useGrouping,
  GroupHeader,
  GroupBySelect,
} from './shared'
import type { CategoryPanelProps, IntelligenceTrait } from './types'


export default function IntelligencePanel({ isDarkMode = false, data, token }: CategoryPanelProps) {
  const theme = useThemeClasses(isDarkMode)
  const [selectedItem, setSelectedItem] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [advantageFilter, setAdvantageFilter] = useState<string>('all')
  const [groupBy, setGroupBy] = useState('none')



  const getTraitIcon = (trait: string) => {
    const traitLower = trait.toLowerCase()
    if (traitLower.includes('memory')) return Brain
    if (traitLower.includes('processing') || traitLower.includes('speed')) return Lightbulb
    if (traitLower.includes('learning') || traitLower.includes('education')) return BookOpen
    if (traitLower.includes('focus') || traitLower.includes('attention')) return Target
    if (traitLower.includes('problem') || traitLower.includes('reasoning')) return Puzzle
    return Brain
  }

  const getCognitiveTraits = () => {
    const intelligenceData = Array.isArray(data?.intelligence) ? data.intelligence as IntelligenceTrait[] : []
    if (intelligenceData.length > 0) {
      return intelligenceData.map((trait: IntelligenceTrait) => ({
        trait: trait.cognitive_ability || trait.trait_name,
        gene: trait.associated_variants?.[0] || 'Multiple',
        result: trait.genetic_advantage || trait.genetic_result || 'moderate',
        score: trait.percentile || (trait.genetic_advantage === 'high' ? 85 : trait.genetic_advantage === 'moderate' ? 65 : 45),
        description: trait.description || `Genetic analysis for ${trait.cognitive_ability || trait.trait_name}`,
        icon: getTraitIcon(trait.cognitive_ability || trait.trait_name),
        suggestions: Array.isArray(trait.enhancement_suggestions) ? trait.enhancement_suggestions : (trait.enhancement_suggestions ? [trait.enhancement_suggestions] : []),
      }))
    }

    return []
  }

  const cognitiveTraits = getCognitiveTraits()

  const advantageOptions = useMemo(() => {
    const set = new Set<string>()
    for (const t of cognitiveTraits) set.add((t.result || 'moderate').toLowerCase())
    return Array.from(set).sort()
  }, [cognitiveTraits])

  const filteredTraits = useMemo(() => {
    let list = cognitiveTraits
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      list = list.filter(t => t.trait.toLowerCase().includes(q) || t.gene.toLowerCase().includes(q))
    }
    if (advantageFilter !== 'all') {
      list = list.filter(t => (t.result || 'moderate').toLowerCase() === advantageFilter)
    }
    return list
  }, [cognitiveTraits, searchQuery, advantageFilter])

  const INTELLIGENCE_GROUP_OPTIONS: Record<string, string> = { none: 'No Grouping', advantage: 'Genetic Advantage' }
  const getGroupKey = useCallback((trait: { result: string }) => {
    if (groupBy === 'advantage') {
      const r = (trait.result || 'moderate').toLowerCase()
      return r.charAt(0).toUpperCase() + r.slice(1) + ' Advantage'
    }
    return 'All'
  }, [groupBy])
  const { groups, collapsedGroups, toggleGroup, resetCollapsed } = useGrouping(filteredTraits, groupBy, getGroupKey)

  const allSuggestions = useMemo(() => {
    const seen = new Set<string>()
    const result: string[] = []
    for (const t of cognitiveTraits) {
      for (const s of t.suggestions) {
        const key = s.toLowerCase().trim()
        if (!seen.has(key) && key) { seen.add(key); result.push(s) }
      }
    }
    return result
  }, [cognitiveTraits])

  const headerProps = {
    icon: Brain,
    iconColorClass: 'text-purple-400',
    gradientFrom: 'from-purple-500/20',
    gradientTo: 'to-blue-500/20',
    borderColor: 'border-purple-500/30',
    title: 'Intelligence & Cognition',
    description: 'Your genetic cognitive profile and learning potential',
    count: cognitiveTraits.length,
    countLabel: cognitiveTraits.length === 1 ? 'Trait' : 'Traits',
    theme,
  }

  if (cognitiveTraits.length === 0) {
    return (
      <div className="space-y-6">
        <CategoryHeader {...headerProps} />
        <EmptyState
          icon={Brain}
          iconColorClass="text-purple-400"
          gradientFrom="from-purple-500/20"
          gradientTo="to-blue-500/20"
          borderColor="border-purple-500/30"
          title="No Intelligence Data Available"
          description="Cognitive trait analysis is not yet available for your genetic data. This analysis requires specific intelligence-related variants that may be added in future updates."
          theme={theme}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <CategoryHeader {...headerProps} />

      {cognitiveTraits.filter(t => t.score > 0).length >= 2 && (
        <SectionCard title="Cognitive Percentiles" theme={theme}>
          <PercentileBarChart data={cognitiveTraits.filter(t => t.score > 0).map(t => ({ name: t.trait, percentile: t.score }))} isDarkMode={isDarkMode} height={Math.max(200, cognitiveTraits.filter(t => t.score > 0).length * 40)} />
        </SectionCard>
      )}

      {/* Filter Bar */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-50">
          <Search className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
          <input
            type="text"
            placeholder="Search abilities or genes…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} placeholder:${theme.textSecondary} focus:outline-none focus:ring-2 focus:ring-purple-500/40 text-sm`}
          />
        </div>
        <div className="relative min-w-40">
          <Filter className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
          <select
            value={advantageFilter}
            onChange={e => setAdvantageFilter(e.target.value)}
            className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} focus:outline-none focus:ring-2 focus:ring-purple-500/40 text-sm appearance-none cursor-pointer`}
          >
            <option value="all">All Advantages</option>
            {advantageOptions.map(s => (
              <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
            ))}
          </select>
        </div>
        <GroupBySelect options={INTELLIGENCE_GROUP_OPTIONS} value={groupBy} onChange={v => { setGroupBy(v); resetCollapsed() }} theme={theme} />
      </div>

      <SectionCard title={`Cognitive Abilities${filteredTraits.length !== cognitiveTraits.length ? ` (${filteredTraits.length} of ${cognitiveTraits.length})` : ''}`} theme={theme}>
        {groups.map(({ key, label, items }) => (
          <div key={key}>
            {groupBy !== 'none' && <GroupHeader groupKey={key} label={label} count={items.length} isCollapsed={collapsedGroups.has(key)} onToggle={toggleGroup} theme={theme} />}
            {!collapsedGroups.has(key) && (
        <MasonryLayout>
          {items.map((trait, index) => {
            const Icon = trait.icon
            const itemKey = `intelligence-${index}`
            const isExpanded = selectedItem === itemKey
            const rsid = trait.gene?.startsWith('rs') ? trait.gene : undefined
            const gene = !trait.gene?.startsWith('rs') ? trait.gene : undefined
            return (
              <div
                key={index}
                className={`${theme.glass} border ${theme.border} rounded-xl p-3 sm:p-4 cursor-pointer hover:border-purple-500/50 transition-all duration-300`}
                onClick={() => setSelectedItem(isExpanded ? null : itemKey)}
              >
                <div className="flex items-start justify-between mb-1 gap-1">
                  <div className="flex items-start gap-1.5 flex-1 min-w-0">
                    <div className="p-1.5 rounded-lg bg-purple-500/10 shrink-0">
                      <Icon className="h-4 w-4 text-purple-400" />
                    </div>
                    <h4 className={`font-semibold text-sm ${theme.textPrimary} leading-snug`}>{cleanCondition(trait.trait)}</h4>
                  </div>
                  <ChevronRight className={`h-4 w-4 shrink-0 mt-0.5 ${theme.textSecondary} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                </div>

                <div className="flex flex-wrap gap-1">
                  <StatusBadge
                    label={formatLabel(trait.result)}
                    severity={advantageToSeverity(trait.result)}
                  />
                  {rsid && <Badge variant="secondary" className="text-xs font-mono">{rsid}{data?.genotype_map?.[rsid] ? ` ${data.genotype_map[rsid]}` : ''}</Badge>}
                  {rsid && <ZygosityBadge genotype={data?.genotype_map?.[rsid]} />}
                  {gene && <Badge variant="outline" className="text-xs">{gene}</Badge>}
                  <AlphaFoldBadge
                    confidence={data?.alphafold_map?.[rsid]?.confidence}
                    highPct={data?.alphafold_map?.[rsid]?.high_confidence_pct}
                    lowPct={data?.alphafold_map?.[rsid]?.low_confidence_pct}
                    theme={theme}
                  />
                </div>
                {gene && data?.gene_stats_map?.[gene] && (
                  <GeneBurdenStrip gene={gene} stats={data.gene_stats_map[gene]} theme={theme} />
                )}

                {isExpanded && (
                  <div className={`mt-4 pt-4 border-t ${theme.border} space-y-3`}>
                    <p className={`text-sm ${theme.textSecondary} leading-relaxed`}>{cleanCondition(trait.description)}</p>

                    {trait.score > 0 && (
                      <ScoreBar
                        label="Percentile"
                        value={trait.score}
                        colorClass="bg-gradient-to-r from-purple-500 to-blue-500"
                        theme={theme}
                      />
                    )}
                    {rsid && data?.alphafold_map?.[rsid] && (
                      <AlphaFoldDetailBox
                        rsid={rsid}
                        alphafoldData={data.alphafold_map[rsid]}
                        theme={theme}
                      />
                    )}

                    {trait.suggestions.length > 0 && (
                      <div className="space-y-2">
                        <span className={`text-xs font-semibold ${theme.textSecondary} uppercase tracking-wider`}>Enhancement Suggestions</span>
                        {trait.suggestions.map((suggestion: string, i: number) => (
                          <div key={i} className={`flex items-start gap-2 text-sm ${theme.textSecondary}`}>
                            <CheckCircle className="h-4 w-4 text-purple-400 mt-0.5 shrink-0" />
                            <span>{suggestion}</span>
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

      {allSuggestions.length > 0 && (
        <SectionCard title="Enhancement Suggestions" theme={theme}>
          <div className="space-y-2">
            {allSuggestions.map((s, i) => (
              <div key={i} className={`flex items-start gap-2 text-sm ${theme.textSecondary}`}>
                <CheckCircle className="h-4 w-4 text-purple-400 mt-0.5 shrink-0" />
                <span>{s}</span>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      <SmartInsights isDarkMode={isDarkMode} token={token} section="intelligence" title="AI Intelligence Analysis" />

      <DisclaimerCard theme={theme} />
    </div>
  )
}
