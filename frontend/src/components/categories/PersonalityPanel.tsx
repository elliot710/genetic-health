import React, { useState, useMemo, useCallback } from 'react'
import { Brain, Heart, Users, Target, Zap, Palette, ChevronRight, CheckCircle, Search, Filter } from 'lucide-react'
import SmartInsights from '../SmartInsights'
import { Badge } from '../ui/badge'
import { TraitRadarChart } from './GenomicCharts'
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
  AlphaFoldDetailBox,
  GeneBurdenStrip,
  ZygosityBadge,
  advantageToSeverity,
  MasonryLayout,
  cleanCondition,
  useGrouping,
  GroupHeader,
  GroupBySelect,
} from './shared'
import type { CategoryPanelProps, DashboardData, PersonalityTraitData } from './types'
import type { LucideIcon } from 'lucide-react'


interface PersonalityTrait {
  trait: string
  score: number
  gene: string
  description: string
  icon: LucideIcon
  bgColor: string
  characteristics: string[]
}

export default function PersonalityPanel({ isDarkMode = false, data, token }: CategoryPanelProps) {
  const theme = useThemeClasses(isDarkMode)
  const [selectedItem, setSelectedItem] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [scoreFilter, setScoreFilter] = useState<string>('all')
  const [groupBy, setGroupBy] = useState('none')

  const getTraitIcon = (traitName: string) => {
    const name = traitName?.toLowerCase() || ''
    if (name.includes('open') || name.includes('creative')) return Palette
    if (name.includes('extra') || name.includes('social')) return Users
    if (name.includes('conscient') || name.includes('organized')) return Target
    if (name.includes('neurot') || name.includes('emotion')) return Zap
    if (name.includes('agree') || name.includes('empathy')) return Heart
    if (name.includes('risk') || name.includes('adventure')) return Target
    return Brain
  }

  const getTraitStyles = (traitName: string) => {
    const name = traitName?.toLowerCase() || ''
    if (name.includes('open') || name.includes('creative'))
      return { bgColor: 'bg-purple-500/10' }
    if (name.includes('extra') || name.includes('social'))
      return { bgColor: 'bg-blue-500/10' }
    if (name.includes('conscient') || name.includes('organized'))
      return { bgColor: 'bg-green-500/10' }
    if (name.includes('neurot') || name.includes('emotion'))
      return { bgColor: 'bg-yellow-500/10' }
    if (name.includes('agree') || name.includes('empathy'))
      return { bgColor: 'bg-pink-500/10' }
    return { bgColor: 'bg-gray-500/10' }
  }

  const getPersonalityTraits = (): PersonalityTrait[] => {
    if (data?.personality_traits && data.personality_traits.length > 0) {
      return data.personality_traits.map((trait: PersonalityTraitData) => {
        const name = trait.trait || 'Unknown Trait'
        const styles = getTraitStyles(name)
        return {
          trait: name,
          score: typeof trait.score === 'number' ? trait.score : (parseInt(trait.confidence) || 50),
          gene: trait.gene || 'Multiple markers',
          description: trait.description || 'Analysis based on genetic markers',
          icon: getTraitIcon(name),
          bgColor: styles.bgColor,
          characteristics: Array.isArray(trait.characteristics) ? trait.characteristics : (trait.characteristics ? [trait.characteristics] : []),
        }
      })
    }

    return []
  }

  const personalityTraits = getPersonalityTraits()

  const filteredTraits = useMemo(() => {
    let list = personalityTraits
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      list = list.filter(t => t.trait.toLowerCase().includes(q) || t.gene.toLowerCase().includes(q))
    }
    if (scoreFilter !== 'all') {
      list = list.filter(t => {
        const level = t.score >= 75 ? 'high' : t.score >= 50 ? 'moderate' : 'low'
        return level === scoreFilter
      })
    }
    return list
  }, [personalityTraits, searchQuery, scoreFilter])

  const allCharacteristics = useMemo(() => {
    const seen = new Set<string>()
    const result: string[] = []
    for (const t of personalityTraits) {
      for (const c of t.characteristics) {
        const key = c.toLowerCase().trim()
        if (!seen.has(key) && key) { seen.add(key); result.push(c) }
      }
    }
    return result
  }, [personalityTraits])

  const PERSONALITY_GROUP_OPTIONS: Record<string, string> = { none: 'No Grouping', score: 'Score Level' }
  const getGroupKey = useCallback((t: PersonalityTrait): string => {
    if (groupBy === 'score') return t.score >= 75 ? 'High Score' : t.score >= 50 ? 'Moderate Score' : 'Low Score'
    return 'all'
  }, [groupBy])
  const { groups, collapsedGroups, toggleGroup, resetCollapsed } = useGrouping(filteredTraits, groupBy, getGroupKey, 'All Traits')

  const headerProps = {
    icon: Palette,
    iconColorClass: 'text-pink-400',
    gradientFrom: 'from-pink-500/20',
    gradientTo: 'to-purple-500/20',
    borderColor: 'border-pink-500/30',
    title: 'Personality Traits',
    description: 'Genetic influences on your behavioral tendencies',
    count: personalityTraits.length,
    countLabel: personalityTraits.length === 1 ? 'Trait' : 'Traits',
    theme,
  }

  if (personalityTraits.length === 0) {
    return (
      <div className="space-y-6">
        <CategoryHeader {...headerProps} />
        <EmptyState
          icon={Palette}
          iconColorClass="text-pink-400"
          gradientFrom="from-pink-500/20"
          gradientTo="to-purple-500/20"
          borderColor="border-pink-500/30"
          title="No Personality Data Available"
          description="Personality trait analysis is not yet available for your genetic data. This analysis requires specific behavioral-related variants that may be added in future updates."
          theme={theme}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <CategoryHeader {...headerProps} />

      {personalityTraits.length >= 3 && (
        <SectionCard title="Trait Overview" theme={theme}>
          <TraitRadarChart data={personalityTraits.map(t => ({ label: t.trait, value: t.score, fullMark: 100 }))} isDarkMode={isDarkMode} height={300} fillColor={isDarkMode ? 'rgba(236,72,153,0.2)' : 'rgba(219,39,119,0.15)'} strokeColor={isDarkMode ? '#ec4899' : '#db2777'} />
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
            className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} placeholder:${theme.textSecondary} focus:outline-none focus:ring-2 focus:ring-pink-500/40 text-sm`}
          />
        </div>        <div className="relative min-w-40">
          <Filter className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
          <select
            value={scoreFilter}
            onChange={e => setScoreFilter(e.target.value)}
            className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} focus:outline-none focus:ring-2 focus:ring-pink-500/40 text-sm appearance-none cursor-pointer`}
          >
            <option value="all">All Score Levels</option>
            <option value="high">High (\u226575%)</option>
            <option value="moderate">Moderate (50\u201374%)</option>
            <option value="low">Low (&lt;50%)</option>
          </select>
        </div>        <GroupBySelect value={groupBy} onChange={v => { setGroupBy(v); resetCollapsed() }} options={PERSONALITY_GROUP_OPTIONS} theme={theme} />
      </div>

      <SectionCard title={`Personality Profile${filteredTraits.length !== personalityTraits.length ? ` (${filteredTraits.length} of ${personalityTraits.length})` : ''}`} theme={theme}>
        {groups.map(({ key, label, items }) => (
          <div key={key} className="space-y-3">
            {groupBy !== 'none' && (
              <GroupHeader groupKey={key} label={label} count={items.length} isCollapsed={collapsedGroups.has(key)} onToggle={toggleGroup} theme={theme} />
            )}
            {!collapsedGroups.has(key) && (
        <MasonryLayout>
          {items.map((trait: PersonalityTrait, index: number) => {
            const IconComponent = trait.icon
            const itemKey = `personality-${index}`
            const isExpanded = selectedItem === itemKey
            const scoreLabel = trait.score >= 75 ? 'high' : trait.score >= 50 ? 'moderate' : 'low'
            const scoreDisplay = scoreLabel.charAt(0).toUpperCase() + scoreLabel.slice(1)
            const rsid = trait.gene?.startsWith('rs') ? trait.gene : undefined
            const gene = !trait.gene?.startsWith('rs') ? trait.gene : undefined
            return (
              <div
                key={index}
                className={`${theme.glass} border ${theme.border} rounded-xl p-3 sm:p-4 cursor-pointer hover:border-pink-500/50 transition-all duration-300`}
                onClick={() => setSelectedItem(isExpanded ? null : itemKey)}
              >
                <div className="flex items-start justify-between mb-1 gap-1">
                  <div className="flex items-start gap-1.5 flex-1 min-w-0">
                    <div className={`p-1.5 rounded-lg ${trait.bgColor} shrink-0`}>
                      <IconComponent className="h-4 w-4" />
                    </div>
                    <h4 className={`font-semibold text-sm ${theme.textPrimary} leading-snug`}>{cleanCondition(trait.trait)}</h4>
                  </div>
                  <ChevronRight className={`h-4 w-4 shrink-0 mt-0.5 ${theme.textSecondary} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                </div>

                <div className="flex flex-wrap gap-1">
                  <StatusBadge
                    label={scoreDisplay}
                    severity={advantageToSeverity(scoreLabel)}
                  />
                  {trait.gene?.startsWith('rs') && <Badge variant="secondary" className="text-xs font-mono">{trait.gene}{data?.genotype_map?.[trait.gene] ? ` ${data.genotype_map[trait.gene]}` : ''}</Badge>}
                  {trait.gene?.startsWith('rs') && <ZygosityBadge genotype={data?.genotype_map?.[trait.gene]} />}
                  {!trait.gene?.startsWith('rs') && trait.gene && trait.gene !== 'Multiple markers' && <Badge variant="outline" className="text-xs">{trait.gene}</Badge>}
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

                    {trait.characteristics.length > 0 && (
                      <div className="space-y-2">
                        <span className={`text-xs font-semibold ${theme.textSecondary} uppercase tracking-wider`}>Insights</span>
                        {trait.characteristics.map((char: string, charIndex: number) => (
                          <div key={charIndex} className={`flex items-start gap-2 text-sm ${theme.textSecondary}`}>
                            <CheckCircle className="h-4 w-4 text-pink-400 mt-0.5 shrink-0" />
                            <span>{char}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    <VariantInfoBox rsid={trait.gene?.startsWith('rs') ? trait.gene : undefined} gene={!trait.gene?.startsWith('rs') ? trait.gene : undefined} token={token} isDarkMode={isDarkMode} alphaMissense={trait.gene?.startsWith('rs') ? data?.alpha_missense_map?.[trait.gene] : undefined} clinvarCount={trait.gene?.startsWith('rs') ? data?.clinvar_count_map?.[trait.gene] : undefined} genotype={trait.gene?.startsWith('rs') ? data?.genotype_map?.[trait.gene] : undefined} pathogenicityMap={data?.pathogenicity_map} theme={theme} />
                    <GeneContextBox gene={!trait.gene?.startsWith('rs') ? trait.gene : undefined} stats={trait.gene && !trait.gene.startsWith('rs') ? data?.gene_stats_map?.[trait.gene] : undefined} theme={theme} />
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

      {allCharacteristics.length > 0 && (
        <SectionCard title="Key Insights" theme={theme}>
          <div className="space-y-2">
            {allCharacteristics.map((c, i) => (
              <div key={i} className={`flex items-start gap-2 text-sm ${theme.textSecondary}`}>
                <CheckCircle className="h-4 w-4 text-pink-400 mt-0.5 shrink-0" />
                <span>{c}</span>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      <SmartInsights isDarkMode={isDarkMode} token={token} section="personality" title="AI Personality Analysis" />

      <DisclaimerCard theme={theme} />
    </div>
  )
}
