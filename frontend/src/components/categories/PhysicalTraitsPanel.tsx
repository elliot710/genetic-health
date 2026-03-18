import React, { useState, useMemo, useCallback } from 'react'
import { Zap, Eye, Ruler, Palette, Sun, ChevronRight, Search, Filter } from 'lucide-react'
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
  ZygosityBadge,
  advantageToSeverity,
  formatLabel,
  MasonryLayout,
  cleanCondition,
  useGrouping,
  GroupHeader,
  GroupBySelect,
} from './shared'
import type { CategoryPanelProps, PhysicalTrait } from './types'


export default function PhysicalTraitsPanel({ isDarkMode = false, data, token }: CategoryPanelProps) {
  const theme = useThemeClasses(isDarkMode)
  const [selectedItem, setSelectedItem] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [confidenceFilter, setConfidenceFilter] = useState<string>('all')
  const [groupBy, setGroupBy] = useState('none')

  const getPhysicalTraits = () => {
    const physicalTraits = Array.isArray(data?.physical_traits) ? data.physical_traits as PhysicalTrait[] : []
    if (physicalTraits.length > 0) {
      return physicalTraits.map((trait: PhysicalTrait) => ({
        category: trait.trait_name || trait.category,
        trait: trait.genetic_result || trait.trait_value || trait.result,
        gene: trait.associated_variants?.[0] || trait.associated_gene || 'Multiple',
        probability: trait.confidence === 'high' ? 85 : trait.confidence === 'moderate' ? 65 : 45,
        description: trait.description || `Genetic analysis shows predisposition for ${trait.trait_name || trait.category}`,
        confidence: trait.confidence || 'moderate',
      }))
    }

    return []
  }

  const physicalTraits = getPhysicalTraits()

  const confidenceOptions = useMemo(() => {
    const set = new Set<string>()
    for (const t of physicalTraits) set.add((t.confidence || 'moderate').toLowerCase())
    return Array.from(set).sort()
  }, [physicalTraits])

  const filteredTraits = useMemo(() => {
    let list = physicalTraits
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      list = list.filter(t => t.category.toLowerCase().includes(q) || t.gene.toLowerCase().includes(q) || (t.trait || '').toLowerCase().includes(q))
    }
    if (confidenceFilter !== 'all') {
      list = list.filter(t => (t.confidence || 'moderate').toLowerCase() === confidenceFilter)
    }
    return list
  }, [physicalTraits, searchQuery, confidenceFilter])

  const PHYSICAL_GROUP_OPTIONS: Record<string, string> = { none: 'No Grouping', confidence: 'Confidence Level', category: 'Trait Category' }
  const getGroupKey = useCallback((t: typeof physicalTraits[0]): string => {
    switch (groupBy) {
      case 'confidence': return `${(t.confidence || 'moderate').charAt(0).toUpperCase()}${(t.confidence || 'moderate').slice(1)} Confidence`
      case 'category': {
        const c = (t.category || '').toLowerCase()
        if (c.includes('eye')) return 'Eye Traits'
        if (c.includes('hair')) return 'Hair Traits'
        if (c.includes('skin') || c.includes('pigment')) return 'Skin & Pigmentation'
        if (c.includes('height') || c.includes('build')) return 'Body Structure'
        return 'Other'
      }
      default: return 'all'
    }
  }, [groupBy])
  const { groups, collapsedGroups, toggleGroup, resetCollapsed } = useGrouping(filteredTraits, groupBy, getGroupKey, 'All Physical Traits')

  const getTraitIcon = (category: string) => {
    const categoryLower = category.toLowerCase()
    if (categoryLower.includes('eye')) return Eye
    if (categoryLower.includes('hair')) return Palette
    if (categoryLower.includes('skin') || categoryLower.includes('pigment')) return Sun
    if (categoryLower.includes('height') || categoryLower.includes('build')) return Ruler
    return Zap
  }

  const getTraitColor = (category: string) => {
    const categoryLower = category.toLowerCase()
    if (categoryLower.includes('eye')) return { bg: 'bg-blue-500/10', bar: 'bg-gradient-to-r from-blue-500 to-cyan-500' }
    if (categoryLower.includes('hair')) return { bg: 'bg-amber-500/10', bar: 'bg-gradient-to-r from-amber-500 to-orange-500' }
    if (categoryLower.includes('skin') || categoryLower.includes('pigment')) return { bg: 'bg-yellow-500/10', bar: 'bg-gradient-to-r from-yellow-500 to-orange-500' }
    if (categoryLower.includes('height') || categoryLower.includes('build')) return { bg: 'bg-green-500/10', bar: 'bg-gradient-to-r from-green-500 to-emerald-500' }
    return { bg: 'bg-purple-500/10', bar: 'bg-gradient-to-r from-purple-500 to-pink-500' }
  }

  const headerProps = {
    icon: Ruler,
    iconColorClass: 'text-purple-400',
    gradientFrom: 'from-purple-500/20',
    gradientTo: 'to-pink-500/20',
    borderColor: 'border-purple-500/30',
    title: 'Physical Traits',
    description: 'Your genetic physical characteristics',
    count: physicalTraits.length,
    countLabel: physicalTraits.length === 1 ? 'Trait' : 'Traits',
    theme,
  }

  if (physicalTraits.length === 0) {
    return (
      <div className="space-y-6">
        <CategoryHeader {...headerProps} />
        <EmptyState
          icon={Ruler}
          iconColorClass="text-purple-400"
          gradientFrom="from-purple-500/20"
          gradientTo="to-pink-500/20"
          borderColor="border-purple-500/30"
          title="No Physical Traits Data Available"
          description="Physical traits analysis is not yet available for your genetic data."
          theme={theme}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <CategoryHeader {...headerProps} />

      {physicalTraits.length >= 3 && (
        <SectionCard title="Confidence Distribution" theme={theme}>
          <CapacityChart data={physicalTraits.map(t => ({ name: t.category, capacity: t.confidence || 'moderate' }))} isDarkMode={isDarkMode} />
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
            className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} placeholder:${theme.textSecondary} focus:outline-none focus:ring-2 focus:ring-purple-500/40 text-sm`}
          />
        </div>
        <div className="relative min-w-40">
          <Filter className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
          <select
            value={confidenceFilter}
            onChange={e => setConfidenceFilter(e.target.value)}
            className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} focus:outline-none focus:ring-2 focus:ring-purple-500/40 text-sm appearance-none cursor-pointer`}
          >
            <option value="all">All Confidence</option>
            {confidenceOptions.map(s => (
              <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
            ))}
          </select>
        </div>
        <GroupBySelect value={groupBy} onChange={v => { setGroupBy(v); resetCollapsed() }} options={PHYSICAL_GROUP_OPTIONS} theme={theme} />
      </div>

      <SectionCard title={`Physical Characteristics${filteredTraits.length !== physicalTraits.length ? ` (${filteredTraits.length} of ${physicalTraits.length})` : ''}`} theme={theme}>
        {groups.map(({ key, label, items }) => (
          <div key={key} className="space-y-3">
            {groupBy !== 'none' && (
              <GroupHeader groupKey={key} label={label} count={items.length} isCollapsed={collapsedGroups.has(key)} onToggle={toggleGroup} theme={theme} />
            )}
            {!collapsedGroups.has(key) && (
        <MasonryLayout>
          {items.map((trait, index) => {
            const itemKey = `trait-${index}`
            const isExpanded = selectedItem === itemKey
            const rsid = trait.gene?.startsWith('rs') ? trait.gene : undefined
            const gene = !trait.gene?.startsWith('rs') ? trait.gene : undefined
            return (
              <div
                key={index}
                className={`${theme.glass} border ${theme.border} rounded-xl p-5 cursor-pointer hover:border-purple-500/50 transition-all duration-300`}
                onClick={() => setSelectedItem(isExpanded ? null : itemKey)}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <h4 className={`font-bold text-lg ${theme.textPrimary}`}>{cleanCondition(trait.category)}</h4>
                    <StatusBadge
                      label={formatLabel(trait.trait || 'Detected')}
                      severity={advantageToSeverity(trait.confidence || 'moderate')}
                    />
                  </div>
                  <ChevronRight className={`h-5 w-5 ${theme.textSecondary} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {rsid && <Badge variant="secondary" className="text-xs font-mono">{rsid}{data?.genotype_map?.[rsid] ? ` ${data.genotype_map[rsid]}` : ''}</Badge>}
                  {rsid && <ZygosityBadge genotype={data?.genotype_map?.[rsid]} />}
                  {gene && <Badge variant="outline" className="text-xs">{gene}</Badge>}
                </div>

                {isExpanded && (
                  <div className={`mt-4 pt-4 border-t ${theme.border} space-y-3`}>
                    <p className={`text-sm ${theme.textSecondary} leading-relaxed`}>{cleanCondition(trait.description)}</p>
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
        ))}
      </SectionCard>

      <DisclaimerCard theme={theme} />
    </div>
  )
}
