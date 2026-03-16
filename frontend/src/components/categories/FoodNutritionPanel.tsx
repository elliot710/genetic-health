import React, { useState, useMemo, useCallback } from 'react'
import { Apple, Coffee, Utensils, Wheat, ChefHat, ChevronRight, CheckCircle, Search, Filter } from 'lucide-react'
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
  sensitivityToSeverity,
  formatLabel,
  MasonryLayout,
  cleanCondition,
  useGrouping,
  GroupHeader,
  GroupBySelect,
} from './shared'
import type { CategoryPanelProps, NutritionTrait } from './types'


export default function FoodNutritionPanel({ isDarkMode = false, data, token }: CategoryPanelProps) {
  const theme = useThemeClasses(isDarkMode)
  const [selectedItem, setSelectedItem] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [sensitivityFilter, setSensitivityFilter] = useState<string>('all')
  const [groupBy, setGroupBy] = useState('none')



  const getTraitIcon = (trait: string) => {
    const traitLower = trait.toLowerCase()
    if (traitLower.includes('caffeine')) return Coffee
    if (traitLower.includes('lactose') || traitLower.includes('dairy')) return Apple
    if (traitLower.includes('alcohol')) return Utensils
    if (traitLower.includes('gluten') || traitLower.includes('wheat')) return Wheat
    return ChefHat
  }

  const getNutritionTraits = () => {
    const nutritionTraits = Array.isArray(data?.nutrition_traits) ? data.nutrition_traits as NutritionTrait[] : []
    if (nutritionTraits.length > 0) {
      return nutritionTraits.map((trait: NutritionTrait) => ({
        trait: trait.nutrient || trait.trait_name || 'Unknown',
        gene: trait.associated_variants?.[0] || 'Multiple',
        status: trait.metabolism_type || trait.genetic_result || 'normal',
        sensitivity: trait.sensitivity_level || 'moderate',
        description: trait.description || `Genetic analysis for ${trait.nutrient || trait.trait_name}`,
        recommendations: Array.isArray(trait.dietary_recommendations)
          ? trait.dietary_recommendations
          : trait.dietary_recommendations ? [trait.dietary_recommendations] : [],
        icon: getTraitIcon(trait.nutrient || trait.trait_name || ''),
      }))
    }

    return []
  }

  const nutritionTraits = getNutritionTraits()

  const sensitivityOptions = useMemo(() => {
    const set = new Set<string>()
    for (const t of nutritionTraits) set.add((t.sensitivity || 'moderate').toLowerCase())
    return Array.from(set).sort()
  }, [nutritionTraits])

  const filteredTraits = useMemo(() => {
    let list = nutritionTraits
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      list = list.filter(t => t.trait.toLowerCase().includes(q) || t.gene.toLowerCase().includes(q))
    }
    if (sensitivityFilter !== 'all') {
      list = list.filter(t => (t.sensitivity || 'moderate').toLowerCase() === sensitivityFilter)
    }
    return list
  }, [nutritionTraits, searchQuery, sensitivityFilter])

  const NUTRITION_GROUP_OPTIONS: Record<string, string> = { none: 'No Grouping', sensitivity: 'Sensitivity Level' }
  const getGroupKey = useCallback((trait: { sensitivity: string }) => {
    if (groupBy === 'sensitivity') {
      const s = (trait.sensitivity || 'moderate').toLowerCase()
      return s.charAt(0).toUpperCase() + s.slice(1) + ' Sensitivity'
    }
    return 'All'
  }, [groupBy])
  const { groups, collapsedGroups, toggleGroup, resetCollapsed } = useGrouping(filteredTraits, groupBy, getGroupKey)

  const allRecommendations = useMemo(() => {
    const seen = new Set<string>()
    const result: string[] = []
    for (const t of nutritionTraits) {
      for (const rec of t.recommendations) {
        const key = rec.toLowerCase().trim()
        if (!seen.has(key) && key) { seen.add(key); result.push(rec) }
      }
    }
    return result
  }, [nutritionTraits])

  const headerProps = {
    icon: Apple,
    iconColorClass: 'text-green-400',
    gradientFrom: 'from-green-500/20',
    gradientTo: 'to-emerald-500/20',
    borderColor: 'border-green-500/30',
    title: 'Food & Nutrition',
    description: 'Genetic insights for personalized nutrition',
    count: nutritionTraits.length,
    countLabel: nutritionTraits.length === 1 ? 'Trait' : 'Traits',
    theme,
  }

  if (nutritionTraits.length === 0) {
    return (
      <div className="space-y-6">
        <CategoryHeader {...headerProps} />
        <EmptyState
          icon={Apple}
          iconColorClass="text-green-400"
          gradientFrom="from-green-500/20"
          gradientTo="to-emerald-500/20"
          borderColor="border-green-500/30"
          title="No Nutrition Data Available"
          description="Nutrition trait analysis is not yet available for your genetic data."
          theme={theme}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <CategoryHeader {...headerProps} />

      {nutritionTraits.length >= 3 && (
        <SectionCard title="Sensitivity Distribution" theme={theme}>
          <CapacityChart data={nutritionTraits.map(t => ({ name: t.trait, capacity: t.sensitivity || 'moderate' }))} isDarkMode={isDarkMode} />
        </SectionCard>
      )}

      {/* Filter Bar */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-50">
          <Search className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
          <input
            type="text"
            placeholder="Search nutrients or genes…"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} placeholder:${theme.textSecondary} focus:outline-none focus:ring-2 focus:ring-green-500/40 text-sm`}
          />
        </div>
        <div className="relative min-w-40">
          <Filter className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
          <select
            value={sensitivityFilter}
            onChange={e => setSensitivityFilter(e.target.value)}
            className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} focus:outline-none focus:ring-2 focus:ring-green-500/40 text-sm appearance-none cursor-pointer`}
          >
            <option value="all">All Sensitivities</option>
            {sensitivityOptions.map(s => (
              <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>
            ))}
          </select>
        </div>
        <GroupBySelect options={NUTRITION_GROUP_OPTIONS} value={groupBy} onChange={v => { setGroupBy(v); resetCollapsed() }} theme={theme} />
      </div>

      <SectionCard title={`Metabolic Traits${filteredTraits.length !== nutritionTraits.length ? ` (${filteredTraits.length} of ${nutritionTraits.length})` : ''}`} theme={theme}>
        {groups.map(({ key, label, items }) => (
          <div key={key}>
            {groupBy !== 'none' && <GroupHeader groupKey={key} label={label} count={items.length} isCollapsed={collapsedGroups.has(key)} onToggle={toggleGroup} theme={theme} />}
            {!collapsedGroups.has(key) && (
        <MasonryLayout>
          {items.map((trait, index) => {
            const Icon = trait.icon
            const itemKey = `nutrition-${index}`
            const isExpanded = selectedItem === itemKey
            const rsid = trait.gene?.startsWith('rs') ? trait.gene : undefined
            const gene = !trait.gene?.startsWith('rs') ? trait.gene : undefined
            return (
              <div
                key={index}
                className={`${theme.glass} border ${theme.border} rounded-xl p-5 cursor-pointer hover:border-green-500/50 transition-all duration-300`}
                onClick={() => setSelectedItem(isExpanded ? null : itemKey)}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <div className="p-2 rounded-lg bg-green-500/10">
                      <Icon className="h-5 w-5 text-green-400" />
                    </div>
                    <h4 className={`font-bold text-lg ${theme.textPrimary}`}>{cleanCondition(trait.trait)}</h4>
                    <StatusBadge
                      label={formatLabel(trait.status)}
                      severity={sensitivityToSeverity(trait.sensitivity)}
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
                    {trait.recommendations.length > 0 && (
                      <div className="space-y-2">
                        <span className={`text-xs font-semibold ${theme.textSecondary} uppercase tracking-wider`}>Dietary Recommendations</span>
                        {trait.recommendations.map((rec: string, i: number) => (
                          <div key={i} className={`flex items-start gap-2 text-sm ${theme.textSecondary}`}>
                            <CheckCircle className="h-4 w-4 text-green-400 mt-0.5 shrink-0" />
                            <span>{rec}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {rsid && <PathogenicityBar rsid={rsid} pathogenicityMap={data?.pathogenicity_map} theme={theme} />}
                    <VariantLinks rsid={rsid} gene={gene} token={token} isDarkMode={isDarkMode} alphaMissense={rsid ? data?.alpha_missense_map?.[rsid] : undefined} clinvarCount={rsid ? data?.clinvar_count_map?.[rsid] : undefined} />
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

      {allRecommendations.length > 0 && (
        <SectionCard title="Dietary Recommendations" theme={theme}>
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
