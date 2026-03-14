import React, { useState, useEffect } from 'react'
import { Apple, Coffee, Utensils, Wheat, ChefHat, ChevronRight, CheckCircle } from 'lucide-react'
import { Badge } from '../ui/badge'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  StatusBadge,
  VariantLinks,
  sensitivityToSeverity,
  formatLabel,
  MasonryLayout,
  cleanCondition,
} from './shared'
import type { CategoryPanelProps, NutritionTrait } from './types'

export default function FoodNutritionPanel({ isDarkMode = false, data, token }: CategoryPanelProps) {
  const theme = useThemeClasses(isDarkMode)
  const [selectedItem, setSelectedItem] = useState<string | null>(null)

  const [realNutritionTraits, setRealNutritionTraits] = useState<NutritionTrait[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const loadNutritionTraits = async () => {
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
          const traits = dashboardData.nutrition_traits || dashboardData.analysis_results?.nutrition_traits || []
          setRealNutritionTraits(traits)
        }
      } catch (error) {
        // silently handle fetch errors
      } finally {
        setLoading(false)
      }
    }

    loadNutritionTraits()
  }, [token])

  const getTraitIcon = (trait: string) => {
    const traitLower = trait.toLowerCase()
    if (traitLower.includes('caffeine')) return Coffee
    if (traitLower.includes('lactose') || traitLower.includes('dairy')) return Apple
    if (traitLower.includes('alcohol')) return Utensils
    if (traitLower.includes('gluten') || traitLower.includes('wheat')) return Wheat
    return ChefHat
  }

  const getNutritionTraits = () => {
    if (realNutritionTraits.length > 0) {
      return realNutritionTraits.map((trait: NutritionTrait) => ({
        trait: trait.nutrient || trait.trait_name,
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

    if (loading) {
      return [{
        trait: 'Loading Nutrition Analysis...',
        gene: 'Multiple',
        status: 'Processing',
        sensitivity: 'moderate',
        description: 'Loading your genetic nutrition analysis...',
        recommendations: [] as string[],
        icon: ChefHat,
      }]
    }

    return []
  }

  const nutritionTraits = getNutritionTraits()

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

  if (nutritionTraits.length === 0 && !loading) {
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

      <SectionCard title="Metabolic Traits" theme={theme}>
        <MasonryLayout>
          {nutritionTraits.map((trait, index) => {
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
                  {rsid && <Badge variant="secondary" className="text-xs">{rsid}</Badge>}
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
                    <VariantLinks rsid={rsid} gene={gene} token={token} isDarkMode={isDarkMode} alphaMissense={rsid ? data?.alpha_missense_map?.[rsid] : undefined} clinvarCount={rsid ? data?.clinvar_count_map?.[rsid] : undefined} />
                  </div>
                )}
              </div>
            )
          })}
        </MasonryLayout>
      </SectionCard>
    </div>
  )
}
