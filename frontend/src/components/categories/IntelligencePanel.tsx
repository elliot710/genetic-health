import React, { useState, useEffect } from 'react'
import { Brain, BookOpen, Lightbulb, Target, Puzzle, ChevronRight, CheckCircle } from 'lucide-react'
import { Badge } from '../ui/badge'
import { PercentileBarChart } from './GenomicCharts'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  StatusBadge,
  ScoreBar,
  VariantLinks,
  advantageToSeverity,
  formatLabel,
  MasonryLayout,
  cleanCondition,
} from './shared'
import type { CategoryPanelProps, IntelligenceTrait } from './types'

export default function IntelligencePanel({ isDarkMode = false, data, token }: CategoryPanelProps) {
  const theme = useThemeClasses(isDarkMode)
  const [selectedItem, setSelectedItem] = useState<string | null>(null)

  const [realIntelligenceData, setRealIntelligenceData] = useState<IntelligenceTrait[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const loadIntelligenceData = async () => {
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
          const intelligence = dashboardData.intelligence || dashboardData.analysis_results?.intelligence || []
          setRealIntelligenceData(intelligence)
        }
      } catch (error) {
        // silently handle fetch errors
      } finally {
        setLoading(false)
      }
    }

    loadIntelligenceData()
  }, [token])

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
    if (realIntelligenceData.length > 0) {
      return realIntelligenceData.map((trait: IntelligenceTrait) => ({
        trait: trait.cognitive_ability || trait.trait_name,
        gene: trait.associated_variants?.[0] || 'Multiple',
        result: trait.genetic_advantage || trait.genetic_result || 'moderate',
        score: trait.percentile || (trait.genetic_advantage === 'high' ? 85 : trait.genetic_advantage === 'moderate' ? 65 : 45),
        description: trait.description || `Genetic analysis for ${trait.cognitive_ability || trait.trait_name}`,
        icon: getTraitIcon(trait.cognitive_ability || trait.trait_name),
        suggestions: trait.enhancement_suggestions || [],
      }))
    }

    if (loading) {
      return [{
        trait: 'Loading Intelligence Analysis...',
        gene: 'Multiple',
        result: 'processing',
        score: 0,
        description: 'Loading your genetic intelligence analysis...',
        icon: Brain,
        suggestions: [] as string[],
      }]
    }

    return []
  }

  const cognitiveTraits = getCognitiveTraits()

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

  if (cognitiveTraits.length === 0 && !loading) {
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

      <SectionCard title="Cognitive Abilities" theme={theme}>
        <MasonryLayout>
          {cognitiveTraits.map((trait, index) => {
            const Icon = trait.icon
            const itemKey = `intelligence-${index}`
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
                    <div className="p-2 rounded-lg bg-purple-500/10">
                      <Icon className="h-5 w-5 text-purple-400" />
                    </div>
                    <h4 className={`font-bold text-lg ${theme.textPrimary}`}>{cleanCondition(trait.trait)}</h4>
                    <StatusBadge
                      label={formatLabel(trait.result)}
                      severity={advantageToSeverity(trait.result)}
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

                    {trait.score > 0 && (
                      <ScoreBar
                        label="Percentile"
                        value={trait.score}
                        colorClass="bg-gradient-to-r from-purple-500 to-blue-500"
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
