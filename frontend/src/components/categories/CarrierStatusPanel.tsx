import React from 'react'
import { AlertTriangle, CheckCircle, Info, User, Heart, Eye } from 'lucide-react'
import { 
  getThemeClass, 
  getGlassBackground, 
  getGlassBorder, 
  getTextPrimary, 
  getTextSecondary, 
  getTagClass, 
  getProgressBarBg 
} from '../../utils/theme'

interface CarrierStatusPanelProps {
  data: any
  isDarkMode?: boolean
}

export default function CarrierStatusPanel({ data, isDarkMode = false }: CarrierStatusPanelProps) {
  const glassBackground = getGlassBackground(isDarkMode);
  const glassBorder = getGlassBorder(isDarkMode);
  const textPrimary = getTextPrimary(isDarkMode);
  const textSecondary = getTextSecondary(isDarkMode);
  const tagClass = getTagClass(isDarkMode);
  const progressBarBg = getProgressBarBg(isDarkMode);

  // Check if carrier status data is available from the database
  const hasRealData = data?.carrier_status && data.carrier_status.length > 0
  const carrierData = hasRealData ? data.carrier_status : []

  // If no real data is available, show message
  if (!hasRealData) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className={`text-2xl font-bold ${textPrimary} mb-2`}>
              Carrier Status
            </h2>
            <p className={textSecondary}>
              Genetic carrier status for inherited conditions
            </p>
          </div>
          <div className={`${glassBackground} border ${glassBorder} rounded-xl p-4`}>
            <div className="flex items-center space-x-3">
              <User className={`h-8 w-8 ${getThemeClass('text-green-500', isDarkMode)}`} />
              <div>
                <div className={`text-2xl font-bold ${textPrimary}`}>
                  0
                </div>
                <div className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>
                  Conditions
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* No Data Available */}
        <div className={`${glassBackground} border ${glassBorder} rounded-xl p-8 text-center`}>
          <div className="flex flex-col items-center space-y-4">
            <div className="p-4 bg-gradient-to-br from-green-500/20 to-blue-500/20 backdrop-blur-xl rounded-xl border border-green-500/30">
              <User className="h-8 w-8 text-green-400" />
            </div>
            <div>
              <h3 className={`text-xl font-bold ${textPrimary} mb-2`}>
                Carrier Status Analysis in Progress
              </h3>
              <p className={`${textSecondary} max-w-md mx-auto`}>
                Carrier status analysis is not yet available for your genetic data. 
                This analysis requires specific disease-associated variants that may be added in future updates.
              </p>
            </div>
          </div>
        </div>

        {/* Information Panel */}
        <div className={`${glassBackground} border ${glassBorder} rounded-xl p-8`}>
          <h3 className={`text-xl font-bold ${textPrimary} mb-6`}>
            About Carrier Status
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 className={`text-lg font-semibold ${textPrimary} mb-4`}>What is Carrier Status?</h4>
              <p className={`${textSecondary} leading-relaxed`}>
                Carriers have one copy of a genetic variant associated with a recessive condition. 
                Carriers typically don't show symptoms but can pass the variant to their children.
              </p>
            </div>
            <div>
              <h4 className={`text-lg font-semibold ${textPrimary} mb-4`}>Inheritance Patterns</h4>
              <p className={`${textSecondary} leading-relaxed`}>
                For autosomal recessive conditions, both parents must be carriers for a child 
                to be affected. X-linked conditions follow different inheritance patterns.
              </p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Use real carrier data when available
  const carrierConditions = carrierData.map((carrier: any) => ({
    condition: carrier.condition,
    gene: carrier.gene,
    status: carrier.carrier_status,
    inheritance: carrier.inheritance_pattern || 'Unknown',
    frequency: carrier.population_frequency || 'Unknown',
    risk: carrier.risk_level || 'low',
    description: carrier.description || 'No description available'
  }))

  const summary = {
    totalTested: carrierConditions.length,
    carrier: carrierConditions.filter((c: any) => c.status === 'Carrier').length,
    notCarrier: carrierConditions.filter((c: any) => c.status === 'Not a Carrier').length
  }

  const getStatusColor = (status: string) => {
    return status === 'Carrier' 
      ? 'text-yellow-600 bg-yellow-500/10 border-yellow-500/20'
      : 'text-green-600 bg-green-500/10 border-green-500/20'
  }

  const getStatusIcon = (status: string) => {
    return status === 'Carrier' ? AlertTriangle : CheckCircle
  }

  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'high': return 'text-red-500'
      case 'medium': return 'text-yellow-500'
      case 'low': return 'text-green-500'
      default: return 'text-gray-500'
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className={`text-2xl font-bold ${textPrimary} mb-2`}>
            Carrier Status
          </h2>
          <p className={textSecondary}>
            Genetic variants that could be passed to your children
          </p>
        </div>
        <div className={`${glassBackground} border ${glassBorder} rounded-xl p-4`}>
          <div className="flex items-center space-x-3">
            <User className={`h-8 w-8 ${getThemeClass('text-blue-500', isDarkMode)}`} />
            <div>
              <div className={`text-2xl font-bold ${textPrimary}`}>
                {summary.totalTested}
              </div>
              <div className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>
                Conditions Tested
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className={`${glassBackground} border ${glassBorder} rounded-xl p-4`}>
          <div className="text-center">
            <div className={`text-2xl font-bold ${getThemeClass('text-green-500', isDarkMode)} mb-1`}>
              {summary.notCarrier}
            </div>
            <div className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>
              Not a Carrier
            </div>
          </div>
        </div>
        <div className={`${glassBackground} border ${glassBorder} rounded-xl p-4`}>
          <div className="text-center">
            <div className={`text-2xl font-bold ${getThemeClass('text-yellow-500', isDarkMode)} mb-1`}>
              {summary.carrier}
            </div>
            <div className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>
              Carrier
            </div>
          </div>
        </div>
        <div className={`${glassBackground} border ${glassBorder} rounded-xl p-4`}>
          <div className="text-center">
            <div className={`text-2xl font-bold ${textPrimary} mb-1`}>
              {summary.totalTested}
            </div>
            <div className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>
              Total Tested
            </div>
          </div>
        </div>
      </div>

      {/* Conditions List */}
      <div className="space-y-4">
        {carrierConditions.map((condition: any, index: number) => {
          const StatusIcon = getStatusIcon(condition.status)
          return (
            <div key={index} className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className={`text-lg font-semibold ${textPrimary} mb-1`}>
                    {condition.condition}
                  </h3>
                  <p className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>
                    Gene: {condition.gene} • {condition.inheritance}
                  </p>
                </div>
                <div className={`px-3 py-1 rounded-full border ${getStatusColor(condition.status)}`}>
                  <div className="flex items-center space-x-2">
                    <StatusIcon className="h-4 w-4" />
                    <span className="text-sm font-medium">{condition.status}</span>
                  </div>
                </div>
              </div>

              <p className={`text-sm ${textSecondary} mb-4`}>
                {condition.description}
              </p>

              <div className="grid md:grid-cols-2 gap-4">
                <div>
                  <h4 className={`text-sm font-medium ${textSecondary} mb-1`}>
                    Population Frequency
                  </h4>
                  <p className={`text-sm ${textPrimary}`}>
                    {condition.frequency}
                  </p>
                </div>
                <div>
                  <h4 className={`text-sm font-medium ${textSecondary} mb-1`}>
                    Risk Level
                  </h4>
                  <p className={`text-sm font-medium ${getRiskColor(condition.risk)} capitalize`}>
                    {condition.risk}
                  </p>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Educational Information */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6 border border-blue-500/20 bg-blue-500/5`}>
        <div className="flex items-start space-x-3">
          <Info className={`h-5 w-5 ${getThemeClass('text-blue-500', isDarkMode)} mt-0.5`} />
          <div>
            <h3 className={`font-semibold ${textPrimary} mb-2`}>
              Understanding Carrier Status
            </h3>
            <div className={`text-sm ${textSecondary} space-y-2`}>
              <p>
                Being a carrier means you have one copy of a genetic variant that could cause a 
                condition if paired with another copy from your partner.
              </p>
              <p>
                Carriers typically don't show symptoms but can pass the variant to their children. 
                If both parents are carriers, each child has a 25% chance of having the condition.
              </p>
              <p>
                Consider genetic counseling if you're planning a family and have carrier status 
                for any conditions.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
