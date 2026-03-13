import React, { useState } from 'react'
import { ShieldCheck, ChevronRight } from 'lucide-react'
import { Badge } from '../ui/badge'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  StatusBadge,
  DisclaimerCard,
  VariantLinks,
  carrierStatusToSeverity,
  MasonryLayout,
} from './shared'
import type { CategoryPanelProps, CarrierCondition } from './types'

interface MappedCarrier {
  condition: string
  gene: string
  status: string
  inheritance: string
  frequency: string
  risk: string
  description: string
}

export default function CarrierStatusPanel({ isDarkMode = false, data }: CategoryPanelProps) {
  const theme = useThemeClasses(isDarkMode)
  const [selectedItem, setSelectedItem] = useState<string | null>(null)

  const carrierData = data?.carrier_status ?? []
  const hasRealData = carrierData.length > 0

  const getCarrierConditions = () => {
    if (!hasRealData) return []
    return carrierData.map((carrier: CarrierCondition) => ({
      condition: carrier.condition,
      gene: carrier.gene,
      status: carrier.carrier_status || 'Unknown',
      inheritance: carrier.inheritance_pattern || 'Unknown',
      frequency: carrier.population_frequency || 'Unknown',
      risk: carrier.risk_level || 'low',
      description: carrier.description || 'No description available',
    }))
  }

  const carrierConditions = getCarrierConditions()

  const summary = {
    totalTested: carrierConditions.length,
    carrier: carrierConditions.filter((c: MappedCarrier) => c.status === 'Carrier').length,
    notCarrier: carrierConditions.filter((c: MappedCarrier) => c.status === 'Not a Carrier' || c.status === 'Non-Carrier').length,
    affected: carrierConditions.filter((c: MappedCarrier) => c.status === 'Affected').length,
  }

  const headerProps = {
    icon: ShieldCheck,
    iconColorClass: 'text-teal-400',
    gradientFrom: 'from-teal-500/20',
    gradientTo: 'to-green-500/20',
    borderColor: 'border-teal-500/30',
    title: 'Carrier Status',
    description: 'Genetic carrier screening for inherited conditions',
    count: carrierConditions.length,
    countLabel: carrierConditions.length === 1 ? 'Condition' : 'Conditions',
    theme,
  }

  if (!hasRealData) {
    return (
      <div className="space-y-6">
        <CategoryHeader {...headerProps} />
        <EmptyState
          icon={ShieldCheck}
          iconColorClass="text-teal-400"
          gradientFrom="from-teal-500/20"
          gradientTo="to-green-500/20"
          borderColor="border-teal-500/30"
          title="No Carrier Status Data Available"
          description="Carrier status analysis is not yet available for your genetic data. This analysis requires specific disease-associated variants that may be added in future updates."
          theme={theme}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <CategoryHeader {...headerProps} />

      <SectionCard title="Carrier Screening Results" theme={theme}>
        <MasonryLayout>
          {carrierConditions.map((condition: MappedCarrier, index: number) => {
            const itemKey = `carrier-${index}`
            const isExpanded = selectedItem === itemKey
            return (
              <div
                key={index}
                className={`${theme.glass} border ${theme.border} rounded-xl p-5 cursor-pointer hover:border-teal-500/50 transition-all duration-300`}
                onClick={() => setSelectedItem(isExpanded ? null : itemKey)}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <h4 className={`font-bold text-lg ${theme.textPrimary}`}>{condition.condition}</h4>
                    <StatusBadge
                      label={condition.status}
                      severity={carrierStatusToSeverity(condition.status)}
                    />
                  </div>
                  <ChevronRight className={`h-5 w-5 ${theme.textSecondary} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                </div>

                <div className="flex flex-wrap gap-1.5">
                  <Badge variant="secondary" className="text-xs">{condition.gene}</Badge>
                </div>

                {isExpanded && (
                  <div className={`mt-4 pt-4 border-t ${theme.border} space-y-3`}>
                    <p className={`text-sm ${theme.textSecondary} leading-relaxed`}>{condition.description}</p>

                    <div className={`text-sm ${theme.textSecondary}`}>
                      <span className="font-medium">Inheritance:</span> {condition.inheritance}
                    </div>

                    {condition.frequency && condition.frequency !== 'Unknown' && (
                      <div className={`text-sm ${theme.textSecondary}`}>
                        <span className="font-medium">Population Frequency:</span> {condition.frequency}
                      </div>
                    )}

                    <VariantLinks gene={condition.gene} />
                  </div>
                )}
              </div>
            )
          })}
        </MasonryLayout>
      </SectionCard>

      <SectionCard title="Screening Summary" theme={theme}>
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center">
            <div className="text-2xl font-bold text-yellow-500 mb-1">{summary.carrier}</div>
            <div className={`text-sm ${theme.textSecondary}`}>Carrier</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-green-500 mb-1">{summary.notCarrier}</div>
            <div className={`text-sm ${theme.textSecondary}`}>Non-Carrier</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-red-500 mb-1">{summary.affected}</div>
            <div className={`text-sm ${theme.textSecondary}`}>Affected</div>
          </div>
        </div>
      </SectionCard>
    </div>
  )
}
