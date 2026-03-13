'use client'

import { useState } from 'react'
import { AlertTriangle, Shield, Info, ChevronRight, CheckCircle } from 'lucide-react'
import { Badge } from '../ui/badge'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  StatusBadge,
  DisclaimerCard,
  VariantLinks,
  clinicalSignificanceToSeverity,
  formatLabel,
  MasonryLayout,
} from './shared'
import type { CategoryPanelProps, RareMutation } from './types'

export default function RareMutationsPanel({ data, isDarkMode = false, token }: CategoryPanelProps) {
  const [selectedMutation, setSelectedMutation] = useState<string | null>(null)
  const theme = useThemeClasses(isDarkMode)

  const processRareMutations = (): RareMutation[] => {
    if (!data || typeof data !== 'object') return []
    if ('rare_mutations' in data && Array.isArray(data.rare_mutations) && data.rare_mutations.length > 0) {
      return data.rare_mutations
    }
    return []
  }

  const rareMutations = processRareMutations()

  const getRsid = (m: RareMutation) =>
    m.rsid || m.associated_variants?.[0] || m.mutation_name || undefined

  const getDisplayGene = (m: RareMutation) =>
    m.gene && m.gene !== 'Unknown' ? m.gene : undefined

  const getTitle = (m: RareMutation) =>
    getDisplayGene(m) || getRsid(m) || 'Unknown Variant'

  const headerProps = {
    icon: AlertTriangle,
    iconColorClass: 'text-red-400',
    gradientFrom: 'from-red-500/20',
    gradientTo: 'to-orange-500/20',
    borderColor: 'border-red-500/30',
    title: 'Rare Mutations',
    description: 'Uncommon genetic variants with potential clinical significance',
    count: rareMutations.length,
    countLabel: rareMutations.length === 1 ? 'Mutation' : 'Mutations',
    theme,
  }

  if (rareMutations.length === 0) {
    return (
      <div className="space-y-6">
        <CategoryHeader {...headerProps} />
        <EmptyState
          icon={Shield}
          iconColorClass="text-green-400"
          gradientFrom="from-green-500/20"
          gradientTo="to-blue-500/20"
          borderColor="border-green-500/30"
          title="No Rare Mutations Found"
          description="No rare genetic mutations with high clinical significance were identified in your genetic data."
          theme={theme}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <CategoryHeader {...headerProps} />

      <SectionCard title="Rare Variant Analysis" theme={theme}>
        <MasonryLayout>
          {rareMutations.map((mutation: RareMutation, index: number) => {
            const rsid = getRsid(mutation)
            const gene = getDisplayGene(mutation)
            const title = getTitle(mutation)
            const mutationId = `mutation-${index}`
            const isExpanded = selectedMutation === mutationId

            return (
              <div
                key={index}
                className={`${theme.glass} border ${theme.border} rounded-xl p-5 cursor-pointer hover:border-red-500/50 transition-all duration-300`}
                onClick={() => setSelectedMutation(isExpanded ? null : mutationId)}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <h4 className={`font-bold text-lg ${theme.textPrimary}`}>{title}</h4>
                    <StatusBadge
                      label={formatLabel(mutation.clinical_significance)}
                      severity={clinicalSignificanceToSeverity(mutation.clinical_significance)}
                    />
                  </div>
                  <ChevronRight className={`h-5 w-5 ${theme.textSecondary} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {rsid && title !== rsid && <Badge variant="secondary" className="text-xs">{rsid}</Badge>}
                  {gene && title !== gene && <Badge variant="outline" className="text-xs">{gene}</Badge>}
                  {mutation.mutation_type && (
                    <Badge variant="outline" className="text-xs">{formatLabel(mutation.mutation_type)}</Badge>
                  )}
                </div>

                {mutation.disease_association && mutation.disease_association !== 'Under investigation' && (
                  <p className={`text-sm ${theme.textSecondary} mt-1`}>{mutation.disease_association}</p>
                )}

                {isExpanded && (
                  <div className={`mt-4 pt-4 border-t ${theme.border} space-y-3`}>
                    {mutation.genotype && (
                      <p className={`text-sm ${theme.textSecondary}`}>
                        <strong>Genotype:</strong>{' '}
                        <span className="font-mono">{mutation.genotype}</span>
                      </p>
                    )}

                    <p className={`text-sm ${theme.textSecondary}`}>
                      {mutation.disease_association || mutation.effect || 'Under investigation'}
                    </p>

                    <div className="flex items-center gap-4">
                      <span className={`text-xs ${theme.textSecondary}`}>
                        Frequency: {(mutation.population_frequency * 100).toFixed(1)}%
                      </span>
                      {mutation.mutation_type && (
                        <span className={`text-xs ${theme.textSecondary}`}>
                          Type: {formatLabel(mutation.mutation_type)}
                        </span>
                      )}
                    </div>

                    {mutation.penetrance && mutation.penetrance !== 'unknown' && (
                      <p className={`text-sm ${theme.textSecondary}`}>
                        <strong>Penetrance:</strong> {formatLabel(mutation.penetrance)}
                      </p>
                    )}

                    {mutation.inheritance_pattern && (
                      <p className={`text-sm ${theme.textSecondary}`}>
                        <strong>Inheritance:</strong> {formatLabel(mutation.inheritance_pattern)}
                      </p>
                    )}

                    {mutation.clinical_actions && mutation.clinical_actions.length > 0 && (
                      <div className="space-y-2">
                        <span className={`text-xs font-semibold ${theme.textSecondary} uppercase tracking-wider`}>Clinical Actions</span>
                        {mutation.clinical_actions.map((action: string, i: number) => (
                          <div key={i} className={`flex items-start gap-2 text-sm ${theme.textSecondary}`}>
                            <CheckCircle className="h-4 w-4 text-blue-400 mt-0.5 shrink-0" />
                            <span>{action}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {mutation.monitoring_recommendations && mutation.monitoring_recommendations.length > 0 && (
                      <div className="space-y-2">
                        <span className={`text-xs font-semibold ${theme.textSecondary} uppercase tracking-wider`}>Recommendations</span>
                        {mutation.monitoring_recommendations.map((rec: string, i: number) => (
                          <div key={i} className={`flex items-start gap-2 text-sm ${theme.textSecondary}`}>
                            <CheckCircle className="h-4 w-4 text-green-400 mt-0.5 shrink-0" />
                            <span>{rec}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="flex gap-2 flex-wrap">
                      {mutation.genetic_counseling_urgent && (
                        <Badge variant="outline" className="bg-red-500/10 text-red-500 border-red-500/20 text-xs">
                          Counseling Urgent
                        </Badge>
                      )}
                      {mutation.family_screening_recommended && (
                        <Badge variant="outline" className="bg-blue-500/10 text-blue-500 border-blue-500/20 text-xs">
                          Family Screening
                        </Badge>
                      )}
                    </div>

                    <VariantLinks rsid={rsid} gene={gene} token={token} isDarkMode={isDarkMode} alphaMissense={rsid ? data?.alpha_missense_map?.[rsid] : undefined} clinvarCount={rsid ? data?.clinvar_count_map?.[rsid] : undefined} />
                  </div>
                )}
              </div>
            )
          })}
        </MasonryLayout>
      </SectionCard>

      <DisclaimerCard
        icon={Info}
        title="Clinical Notes"
        text="This analysis identifies potentially significant rare genetic variants but is not a diagnostic test. All findings require confirmation through clinical genetic testing. Rare variants are found in less than 1% of the population and may have significant health implications. Consult a genetic counselor or physician before making medical decisions based on these results."
        borderColorClass="border-red-500/20"
        bgTintClass="bg-red-500/5"
        theme={theme}
      />
    </div>
  )
}
