import React from 'react'
import { Globe, MapPin, Users, Clock, Dna } from 'lucide-react'
import { Badge } from '../ui/badge'
import { AncestryDonutChart } from './GenomicCharts'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  ScoreBar,
} from './shared'
import type { CategoryPanelProps } from './types'

interface AncestryRegion {
  region: string
  percentage: number
  color?: string
}

export default function AncestryPanel({ isDarkMode = false, data }: CategoryPanelProps) {
  const theme = useThemeClasses(isDarkMode)

  const getRegionIcon = (region: string) => {
    const name = region.toLowerCase()
    if (name.includes('europe')) return '🌍'
    if (name.includes('africa')) return '🌍'
    if (name.includes('asia') || name.includes('east')) return '🌏'
    if (name.includes('america')) return '🌎'
    if (name.includes('oceania') || name.includes('pacific')) return '🌊'
    if (name.includes('middle east') || name.includes('west asia')) return '🏛️'
    return '🧬'
  }

  const getRegionColor = (region: string) => {
    const name = region.toLowerCase()
    if (name.includes('europe')) return { bg: 'bg-blue-500/20', bar: 'bg-gradient-to-r from-blue-500 to-blue-400', text: 'text-blue-400' }
    if (name.includes('africa')) return { bg: 'bg-amber-500/20', bar: 'bg-gradient-to-r from-amber-500 to-amber-400', text: 'text-amber-400' }
    if (name.includes('east asia')) return { bg: 'bg-red-500/20', bar: 'bg-gradient-to-r from-red-500 to-red-400', text: 'text-red-400' }
    if (name.includes('south asia')) return { bg: 'bg-orange-500/20', bar: 'bg-gradient-to-r from-orange-500 to-orange-400', text: 'text-orange-400' }
    if (name.includes('america')) return { bg: 'bg-green-500/20', bar: 'bg-gradient-to-r from-green-500 to-green-400', text: 'text-green-400' }
    if (name.includes('oceania') || name.includes('pacific')) return { bg: 'bg-cyan-500/20', bar: 'bg-gradient-to-r from-cyan-500 to-cyan-400', text: 'text-cyan-400' }
    if (name.includes('middle east') || name.includes('west asia')) return { bg: 'bg-purple-500/20', bar: 'bg-gradient-to-r from-purple-500 to-purple-400', text: 'text-purple-400' }
    return { bg: 'bg-teal-500/20', bar: 'bg-gradient-to-r from-teal-500 to-teal-400', text: 'text-teal-400' }
  }

  const getAncestryData = () => {
    const results = data?.ancestry_results
    const hasRealData = !!results && results.length > 0
    const ancestryData = hasRealData ? results[0] : null

    return {
      hasRealData,
      ancestryComposition: ancestryData?.composition || [],
      maternalHaplogroup: ancestryData?.maternal_haplogroup || null,
      paternalHaplogroup: ancestryData?.paternal_haplogroup || null,
      neanderthalVariants: ancestryData?.neanderthal_variants || null,
    }
  }

  const { hasRealData, ancestryComposition, maternalHaplogroup, paternalHaplogroup, neanderthalVariants } = getAncestryData()
  const hasHaplogroupData = maternalHaplogroup || paternalHaplogroup

  const headerProps = {
    icon: Globe,
    iconColorClass: 'text-blue-400',
    gradientFrom: 'from-blue-500/20',
    gradientTo: 'to-cyan-500/20',
    borderColor: 'border-blue-500/30',
    title: 'Ancestry & Heritage',
    description: 'Explore your genetic ancestry composition',
    count: ancestryComposition.length,
    countLabel: ancestryComposition.length === 1 ? 'Region' : 'Regions',
    theme,
  }

  if (!hasRealData) {
    return (
      <div className="space-y-6">
        <CategoryHeader {...headerProps} />
        <EmptyState
          icon={Globe}
          iconColorClass="text-blue-400"
          gradientFrom="from-blue-500/20"
          gradientTo="to-cyan-500/20"
          borderColor="border-blue-500/30"
          title="No Ancestry Data Available"
          description="Ancestry composition analysis is not yet available for your genetic data. Upload genetic data to see your ancestry results."
          theme={theme}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <CategoryHeader {...headerProps} />

      <SectionCard title="Ancestry Composition" theme={theme}>
        {ancestryComposition.length >= 2 && (
          <div className="mb-6">
            <AncestryDonutChart data={ancestryComposition.map(r => ({ population: r.region, percentage: r.percentage }))} isDarkMode={isDarkMode} height={280} />
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {ancestryComposition.map((region: AncestryRegion, index: number) => {
            const regionColor = getRegionColor(region.region)
            const regionIcon = getRegionIcon(region.region)
            return (
              <div key={index} className={`${theme.glass} border ${theme.border} rounded-xl p-4`}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className={`p-2 ${regionColor.bg} rounded-lg text-lg`}>
                      {regionIcon}
                    </div>
                    <span className={`font-bold ${theme.textPrimary}`}>{region.region}</span>
                  </div>
                  <Badge variant="outline" className="text-sm">{region.percentage}%</Badge>
                </div>
                <div className={`w-full ${theme.progressBg} rounded-full h-2`}>
                  <div
                    className={`${region.color || regionColor.bar} h-2 rounded-full transition-all duration-1000`}
                    style={{ width: `${region.percentage}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      </SectionCard>

      {hasHaplogroupData && (
        <SectionCard title="Genetic Lineage" description="Notable ancestry markers and lineage information" theme={theme}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Maternal Haplogroup */}
            <div className={`${theme.glass} border ${theme.border} rounded-xl p-5`}>
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-pink-500/20 rounded-lg">
                  <Dna className="h-5 w-5 text-pink-500" />
                </div>
                <h4 className={`text-lg font-semibold ${theme.textPrimary}`}>Maternal Lineage</h4>
              </div>
              <div className="space-y-3">
                <span className={`text-2xl font-bold ${theme.textPrimary}`}>
                  {maternalHaplogroup?.haplogroup || 'Not Available'}
                </span>
                {maternalHaplogroup ? (
                  <>
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <MapPin className="h-4 w-4 text-gray-400" />
                        <span className={`text-sm ${theme.textSecondary}`}>Origin: {maternalHaplogroup.origin}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Users className="h-4 w-4 text-gray-400" />
                        <span className={`text-sm ${theme.textSecondary}`}>Frequency: {maternalHaplogroup.frequency}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Clock className="h-4 w-4 text-gray-400" />
                        <span className={`text-sm ${theme.textSecondary}`}>Age: {maternalHaplogroup.age}</span>
                      </div>
                    </div>
                    <p className={`text-sm ${theme.textSecondary} leading-relaxed`}>{maternalHaplogroup.description}</p>
                  </>
                ) : (
                  <p className={`text-sm ${theme.textSecondary}`}>Maternal haplogroup analysis not yet available</p>
                )}
              </div>
            </div>

            {/* Paternal Haplogroup */}
            <div className={`${theme.glass} border ${theme.border} rounded-xl p-5`}>
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-blue-500/20 rounded-lg">
                  <Dna className="h-5 w-5 text-blue-500" />
                </div>
                <h4 className={`text-lg font-semibold ${theme.textPrimary}`}>Paternal Lineage</h4>
              </div>
              <div className="space-y-3">
                <span className={`text-2xl font-bold ${theme.textPrimary}`}>
                  {paternalHaplogroup?.haplogroup || 'Not Available'}
                </span>
                {paternalHaplogroup ? (
                  <>
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <MapPin className="h-4 w-4 text-gray-400" />
                        <span className={`text-sm ${theme.textSecondary}`}>Origin: {paternalHaplogroup.origin}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Users className="h-4 w-4 text-gray-400" />
                        <span className={`text-sm ${theme.textSecondary}`}>Frequency: {paternalHaplogroup.frequency}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Clock className="h-4 w-4 text-gray-400" />
                        <span className={`text-sm ${theme.textSecondary}`}>Age: {paternalHaplogroup.age}</span>
                      </div>
                    </div>
                    <p className={`text-sm ${theme.textSecondary} leading-relaxed`}>{paternalHaplogroup.description}</p>
                  </>
                ) : (
                  <p className={`text-sm ${theme.textSecondary}`}>Paternal haplogroup analysis not yet available</p>
                )}
              </div>
            </div>
          </div>
        </SectionCard>
      )}

      <SectionCard title="Neanderthal Ancestry" theme={theme}>
        {neanderthalVariants ? (
          <div className="grid md:grid-cols-3 gap-6">
            <div className="text-center">
              <div className={`text-3xl font-bold ${theme.textPrimary} mb-2`}>{neanderthalVariants.percentage}%</div>
              <div className={`text-sm ${theme.textSecondary}`}>Neanderthal DNA</div>
            </div>
            <div className="text-center">
              <div className={`text-3xl font-bold ${theme.textPrimary} mb-2`}>{neanderthalVariants.variants}</div>
              <div className={`text-sm ${theme.textSecondary}`}>Variants</div>
            </div>
            <div className="text-center">
              <div className={`text-sm ${theme.textSecondary} mb-2`}>You have {neanderthalVariants.moreOrLess} Neanderthal DNA</div>
              <div className={`text-sm ${theme.textSecondary}`}>{neanderthalVariants.comparison}</div>
            </div>
          </div>
        ) : (
          <div className="text-center py-8">
            <p className={theme.textSecondary}>Neanderthal ancestry analysis not yet available</p>
          </div>
        )}
        <div className="mt-4 p-4 bg-amber-500/10 border border-amber-500/20 rounded-lg">
          <p className={`text-sm ${theme.textSecondary} leading-relaxed`}>
            Neanderthals were ancient human relatives who lived in Europe and Asia.
            Modern humans of non-African descent typically have 1-4% Neanderthal DNA.
          </p>
        </div>
      </SectionCard>
    </div>
  )
}
