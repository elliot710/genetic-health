import React, { useState, useEffect } from 'react'
import { Brain, Heart, Users, Target, Zap, Palette, ChevronRight, CheckCircle } from 'lucide-react'
import { Badge } from '../ui/badge'
import { TraitRadarChart } from './GenomicCharts'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  StatusBadge,
  VariantLinks,
  advantageToSeverity,
  MasonryLayout,
  cleanCondition,
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
  const [personalityData, setPersonalityData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchPersonalityData = async () => {
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
          setPersonalityData(dashboardData)
        }
      } catch (error) {
        // silently handle fetch errors
      } finally {
        setLoading(false)
      }
    }

    fetchPersonalityData()
  }, [token])

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
    if (personalityData?.personality_traits && personalityData.personality_traits.length > 0) {
      return personalityData.personality_traits.map((trait: PersonalityTraitData) => {
        const name = trait.trait || 'Unknown Trait'
        const styles = getTraitStyles(name)
        return {
          trait: name,
          score: typeof trait.score === 'number' ? trait.score : (parseInt(trait.confidence) || 50),
          gene: trait.gene || 'Multiple markers',
          description: trait.description || 'Analysis based on genetic markers',
          icon: getTraitIcon(name),
          bgColor: styles.bgColor,
          characteristics: trait.characteristics || [],
        }
      })
    }

    return []
  }

  const personalityTraits = getPersonalityTraits()

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

  if (personalityTraits.length === 0 && !loading) {
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

      <SectionCard title="Personality Profile" theme={theme}>
        <MasonryLayout>
          {personalityTraits.map((trait: PersonalityTrait, index: number) => {
            const IconComponent = trait.icon
            const itemKey = `personality-${index}`
            const isExpanded = selectedItem === itemKey
            const scoreLabel = trait.score >= 75 ? 'high' : trait.score >= 50 ? 'moderate' : 'low'
            return (
              <div
                key={index}
                className={`${theme.glass} border ${theme.border} rounded-xl p-5 cursor-pointer hover:border-pink-500/50 transition-all duration-300`}
                onClick={() => setSelectedItem(isExpanded ? null : itemKey)}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${trait.bgColor}`}>
                      <IconComponent className="h-5 w-5" />
                    </div>
                    <h4 className={`font-bold text-lg ${theme.textPrimary}`}>{cleanCondition(trait.trait)}</h4>
                    <StatusBadge
                      label={`${trait.score}%`}
                      severity={advantageToSeverity(scoreLabel)}
                    />
                  </div>
                  <ChevronRight className={`h-5 w-5 ${theme.textSecondary} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {trait.gene?.startsWith('rs') && <Badge variant="secondary" className="text-xs">{trait.gene}</Badge>}
                  {!trait.gene?.startsWith('rs') && trait.gene && trait.gene !== 'Multiple markers' && <Badge variant="outline" className="text-xs">{trait.gene}</Badge>}
                </div>

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

                    <VariantLinks rsid={trait.gene?.startsWith('rs') ? trait.gene : undefined} gene={!trait.gene?.startsWith('rs') ? trait.gene : undefined} token={token} isDarkMode={isDarkMode} alphaMissense={trait.gene?.startsWith('rs') ? data?.alpha_missense_map?.[trait.gene] : undefined} clinvarCount={trait.gene?.startsWith('rs') ? data?.clinvar_count_map?.[trait.gene] : undefined} />
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
