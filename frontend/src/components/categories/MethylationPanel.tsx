'use client'

import React, { useState, useMemo } from 'react'
import { Dna, ChevronRight, CheckCircle } from 'lucide-react'
import { Badge } from '../ui/badge'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  StatusBadge,
  capacityToSeverity,
  VariantLinks,
  formatLabel,
  MasonryLayout,
} from './shared'
import type { CategoryPanelProps, MethylationProfile } from './types'

export default function MethylationPanel({ isDarkMode = false, data }: CategoryPanelProps) {
  const [selectedGene, setSelectedGene] = useState<string | null>(null)
  const theme = useThemeClasses(isDarkMode)

  const profiles: MethylationProfile[] = data?.methylation_profiles || []

  const allSupplements = useMemo(() => {
    const seen = new Set<string>()
    const result: string[] = []
    for (const profile of profiles) {
      for (const rec of profile.supplement_recommendations || []) {
        const key = rec.toLowerCase().trim()
        if (!seen.has(key)) {
          seen.add(key)
          result.push(rec)
        }
      }
    }
    return result
  }, [profiles])

  const headerProps = {
    icon: Dna,
    iconColorClass: 'text-purple-400',
    gradientFrom: 'from-purple-500/20',
    gradientTo: 'to-indigo-500/20',
    borderColor: 'border-purple-500/30',
    title: 'Methylation Profile',
    description: 'Your genetic methylation cycle analysis',
    count: profiles.length,
    countLabel: profiles.length === 1 ? 'Marker' : 'Markers',
    theme,
  }

  if (profiles.length === 0) {
    return (
      <div className="space-y-6">
        <CategoryHeader {...headerProps} />
        <EmptyState
          icon={Dna}
          iconColorClass="text-purple-400"
          gradientFrom="from-purple-500/20"
          gradientTo="to-indigo-500/20"
          borderColor="border-purple-500/30"
          title="No Methylation Data Available"
          description="Methylation pathway analysis is not yet available for your genetic data."
          theme={theme}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <CategoryHeader {...headerProps} />

      <SectionCard title="Methylation Markers" theme={theme}>
        <MasonryLayout>
          {profiles.map((item, index) => {
            const rsid = item.associated_variants?.[0] || item.variant
            const capacity = item.methylation_capacity || 'normal'
            const geneKey = `${item.gene}-${index}`
            const isExpanded = selectedGene === geneKey

            return (
              <div
                key={geneKey}
                className={`${theme.glass} border ${theme.border} rounded-xl p-5 hover:border-purple-500/50 transition-all duration-300 cursor-pointer`}
                onClick={() => setSelectedGene(isExpanded ? null : geneKey)}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <h4 className={`font-bold text-lg ${theme.textPrimary}`}>{item.gene}</h4>
                    <StatusBadge
                      label={formatLabel(capacity)}
                      severity={capacityToSeverity(capacity)}
                    />
                  </div>
                  <ChevronRight className={`h-5 w-5 ${theme.textSecondary} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                </div>

                {rsid && (
                  <Badge variant="secondary" className="text-xs">{rsid}</Badge>
                )}

                {isExpanded && (
                  <div className={`mt-4 pt-4 border-t ${theme.border} space-y-3`}>
                    {item.supplement_recommendations?.length > 0 && (
                      <div className="space-y-2">
                        <span className={`text-xs font-semibold ${theme.textSecondary} uppercase tracking-wider`}>Recommendations</span>
                        {item.supplement_recommendations.map((rec: string, i: number) => (
                          <div key={i} className={`flex items-start gap-2 text-sm ${theme.textSecondary}`}>
                            <CheckCircle className="h-4 w-4 text-green-400 mt-0.5 shrink-0" />
                            <span>{rec}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    <VariantLinks rsid={rsid} gene={item.gene} />
                  </div>
                )}
              </div>
            )
          })}
        </MasonryLayout>
      </SectionCard>

      {allSupplements.length > 0 && (
        <SectionCard title="Methylation Support" theme={theme}>
          <h4 className={`text-sm font-semibold ${theme.textPrimary} mb-3`}>Supplement Recommendations</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {allSupplements.map((supplement, index) => (
              <div key={index} className={`${theme.glass} border ${theme.border} rounded-lg p-4`}>
                <div className="flex items-start gap-3">
                  <CheckCircle className="h-5 w-5 text-green-400 mt-0.5 shrink-0" />
                  <span className={`font-medium ${theme.textPrimary}`}>{supplement}</span>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      )}
    </div>
  )
}