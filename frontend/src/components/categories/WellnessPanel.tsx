import React, { useState, useEffect } from 'react'
import { Activity, ChevronRight, CheckCircle } from 'lucide-react'
import { Badge } from '../ui/badge'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  StatusBadge,
  VariantLinks,
  capacityToSeverity,
  formatLabel,
  MasonryLayout,
} from './shared'
import type { CategoryPanelProps } from './types'

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
  const [wellnessTraits, setWellnessTraits] = useState<WellnessTrait[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchWellnessData = async () => {
      if (!token) {
        setLoading(false)
        return
      }

      try {
        const response = await fetch('http://localhost:8000/api/analysis/dashboard-data', {
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
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

      <SectionCard title="Wellness Markers" theme={theme}>
        <MasonryLayout>
          {wellnessTraits.map((trait, index) => {
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
                    <h4 className={`font-bold text-lg ${theme.textPrimary}`}>{trait.name}</h4>
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
                        <Badge key={i} variant="secondary" className="text-xs">{v}</Badge>
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

                    <VariantLinks rsid={trait.associated_variants?.[0]} gene={trait.gene !== 'Multiple' ? trait.gene : undefined} token={token} isDarkMode={isDarkMode} />
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
