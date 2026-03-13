import React, { useState, useEffect } from 'react'
import { Zap, Eye, Ruler, Palette, Sun, ChevronRight } from 'lucide-react'
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
import type { CategoryPanelProps, PhysicalTrait } from './types'

export default function PhysicalTraitsPanel({ isDarkMode = false, data, token }: CategoryPanelProps) {
  const theme = useThemeClasses(isDarkMode)
  const [selectedItem, setSelectedItem] = useState<string | null>(null)

  const [realPhysicalTraits, setRealPhysicalTraits] = useState<PhysicalTrait[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const loadPhysicalTraits = async () => {
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
          const traits = dashboardData.physical_traits || dashboardData.analysis_results?.physical_traits || []
          setRealPhysicalTraits(traits)
        }
      } catch (error) {
        // silently handle fetch errors
      } finally {
        setLoading(false)
      }
    }

    loadPhysicalTraits()
  }, [token])

  const getPhysicalTraits = () => {
    if (realPhysicalTraits.length > 0) {
      return realPhysicalTraits.map((trait: PhysicalTrait) => ({
        category: trait.trait_name || trait.category,
        trait: trait.genetic_result || trait.trait_value || trait.result,
        gene: trait.associated_variants?.[0] || trait.associated_gene || 'Multiple',
        probability: trait.confidence === 'high' ? 85 : trait.confidence === 'moderate' ? 65 : 45,
        description: trait.description || `Genetic analysis shows predisposition for ${trait.trait_name || trait.category}`,
        confidence: trait.confidence || 'moderate',
      }))
    }

    if (data?.physical_traits && data.physical_traits.length > 0) {
      return data.physical_traits.map((trait: PhysicalTrait) => ({
        category: trait.trait_name || trait.category,
        trait: trait.genetic_result || trait.trait_value || trait.result,
        gene: trait.associated_variants?.[0] || trait.associated_gene || 'Multiple',
        probability: trait.confidence === 'high' ? 85 : trait.confidence === 'moderate' ? 65 : 45,
        description: trait.description || `Genetic analysis shows predisposition for ${trait.trait_name || trait.category}`,
        confidence: trait.confidence || 'moderate',
      }))
    }

    if (loading) {
      return [{
        category: 'Loading Physical Traits...',
        trait: 'Processing',
        gene: 'Multiple',
        probability: 0,
        description: 'Loading your genetic physical trait analysis...',
        confidence: 'pending',
      }]
    }

    return []
  }

  const physicalTraits = getPhysicalTraits()

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

  if (physicalTraits.length === 0 && !loading) {
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

      <SectionCard title="Physical Characteristics" theme={theme}>
        <MasonryLayout>
          {physicalTraits.map((trait, index) => {
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
                    <h4 className={`font-bold text-lg ${theme.textPrimary}`}>{trait.category}</h4>
                    <StatusBadge
                      label={formatLabel(trait.trait || 'Detected')}
                      severity={advantageToSeverity(trait.confidence || 'moderate')}
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
                    <VariantLinks rsid={rsid} gene={gene} token={token} isDarkMode={isDarkMode} />
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
