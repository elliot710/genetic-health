import React, { useState, useEffect } from 'react'
import { Dumbbell, ChevronRight, CheckCircle } from 'lucide-react'
import { Badge } from '../ui/badge'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  StatusBadge,
  VariantLinks,
  advantageToSeverity,
  formatLabel,
  MasonryLayout,
} from './shared'
import type { CategoryPanelProps, SportsPerformance } from './types'

export default function SportsPanel({ isDarkMode = false, data, token }: CategoryPanelProps) {
  const theme = useThemeClasses(isDarkMode)
  const [selectedItem, setSelectedItem] = useState<string | null>(null)

  const [realSportsData, setRealSportsData] = useState<SportsPerformance[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const loadSportsData = async () => {
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
          const sports = dashboardData.sports_performance || dashboardData.analysis_results?.sports_performance || []
          setRealSportsData(sports)
        }
      } catch (error) {
        // silently handle fetch errors
      } finally {
        setLoading(false)
      }
    }

    loadSportsData()
  }, [token])

  const getAthleticTraits = () => {
    if (realSportsData.length > 0) {
      return realSportsData.map((trait: SportsPerformance) => ({
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

    if (loading) {
      return [{
        trait: 'Loading Sports Analysis...',
        gene: 'Multiple',
        result: 'Processing',
        score: 0,
        description: 'Loading your genetic sports performance analysis...',
        recommendation: 'Analysis in progress...',
      }]
    }

    return []
  }

  const athleticTraits = getAthleticTraits()

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

  if (athleticTraits.length === 0 && !loading) {
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

      <SectionCard title="Athletic Traits" theme={theme}>
        <MasonryLayout>
          {athleticTraits.map((trait, index) => {
            const itemKey = `sport-${index}`
            const isExpanded = selectedItem === itemKey
            const rsid = trait.gene?.startsWith('rs') ? trait.gene : undefined
            const gene = !trait.gene?.startsWith('rs') ? trait.gene : undefined
            return (
              <div
                key={index}
                className={`${theme.glass} border ${theme.border} rounded-xl p-5 cursor-pointer hover:border-orange-500/50 transition-all duration-300`}
                onClick={() => setSelectedItem(isExpanded ? null : itemKey)}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <h4 className={`font-bold text-lg ${theme.textPrimary}`}>{formatLabel(trait.trait)}</h4>
                    <StatusBadge
                      label={formatLabel(trait.result || 'Detected')}
                      severity={advantageToSeverity(trait.result || 'moderate')}
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
                    <p className={`text-sm ${theme.textSecondary} leading-relaxed`}>{trait.description}</p>
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
                    <VariantLinks rsid={rsid} gene={gene} />
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
