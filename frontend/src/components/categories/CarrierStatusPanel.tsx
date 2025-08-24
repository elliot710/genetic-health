import React from 'react'
import { AlertTriangle, CheckCircle, Info, User, Heart, Eye } from 'lucide-react'

interface CarrierStatusPanelProps {
  data: any
  isDarkMode?: boolean
}

export default function CarrierStatusPanel({ data, isDarkMode = false }: CarrierStatusPanelProps) {
  const theme = {
    glass: isDarkMode 
      ? 'bg-black/20 backdrop-blur-xl border-white/10' 
      : 'bg-white/30 backdrop-blur-xl border-white/30',
    text: {
      primary: isDarkMode ? 'text-white' : 'text-gray-900',
      secondary: isDarkMode ? 'text-gray-300' : 'text-gray-700',
      muted: isDarkMode ? 'text-gray-400' : 'text-gray-500',
    }
  }

  const carrierConditions = [
    {
      condition: 'Cystic Fibrosis',
      gene: 'CFTR',
      status: 'Not a Carrier',
      inheritance: 'Autosomal Recessive',
      frequency: '1 in 25 carriers',
      risk: 'low',
      description: 'A genetic disorder affecting the lungs and digestive system'
    },
    {
      condition: 'Sickle Cell Disease',
      gene: 'HBB',
      status: 'Not a Carrier',
      inheritance: 'Autosomal Recessive',
      frequency: '1 in 13 African Americans',
      risk: 'low',
      description: 'A blood disorder causing misshapen red blood cells'
    },
    {
      condition: 'Tay-Sachs Disease',
      gene: 'HEXA',
      status: 'Not a Carrier',
      inheritance: 'Autosomal Recessive',
      frequency: '1 in 30 Ashkenazi Jews',
      risk: 'low',
      description: 'A rare disorder affecting nerve cells in the brain and spinal cord'
    },
    {
      condition: 'Spinal Muscular Atrophy',
      gene: 'SMN1',
      status: 'Carrier',
      inheritance: 'Autosomal Recessive',
      frequency: '1 in 40-60 carriers',
      risk: 'medium',
      description: 'A genetic disorder affecting motor neurons and muscle strength'
    },
    {
      condition: 'Hemochromatosis',
      gene: 'HFE',
      status: 'Carrier',
      inheritance: 'Autosomal Recessive',
      frequency: '1 in 9 Northern Europeans',
      risk: 'medium',
      description: 'A condition causing excess iron absorption'
    }
  ]

  const summary = {
    totalTested: carrierConditions.length,
    carrier: carrierConditions.filter(c => c.status === 'Carrier').length,
    notCarrier: carrierConditions.filter(c => c.status === 'Not a Carrier').length
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
          <h2 className={`text-2xl font-bold ${theme.text.primary} mb-2`}>
            Carrier Status
          </h2>
          <p className={theme.text.secondary}>
            Genetic variants that could be passed to your children
          </p>
        </div>
        <div className={`${theme.glass} rounded-xl p-4`}>
          <div className="flex items-center space-x-3">
            <User className="h-8 w-8 text-blue-500" />
            <div>
              <div className={`text-2xl font-bold ${theme.text.primary}`}>
                {summary.totalTested}
              </div>
              <div className={`text-sm ${theme.text.muted}`}>
                Conditions Tested
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className={`${theme.glass} rounded-xl p-4 border border-white/10`}>
          <div className="text-center">
            <div className={`text-2xl font-bold text-green-500 mb-1`}>
              {summary.notCarrier}
            </div>
            <div className={`text-sm ${theme.text.muted}`}>
              Not a Carrier
            </div>
          </div>
        </div>
        <div className={`${theme.glass} rounded-xl p-4 border border-white/10`}>
          <div className="text-center">
            <div className={`text-2xl font-bold text-yellow-500 mb-1`}>
              {summary.carrier}
            </div>
            <div className={`text-sm ${theme.text.muted}`}>
              Carrier
            </div>
          </div>
        </div>
        <div className={`${theme.glass} rounded-xl p-4 border border-white/10`}>
          <div className="text-center">
            <div className={`text-2xl font-bold ${theme.text.primary} mb-1`}>
              {summary.totalTested}
            </div>
            <div className={`text-sm ${theme.text.muted}`}>
              Total Tested
            </div>
          </div>
        </div>
      </div>

      {/* Conditions List */}
      <div className="space-y-4">
        {carrierConditions.map((condition, index) => {
          const StatusIcon = getStatusIcon(condition.status)
          return (
            <div key={index} className={`${theme.glass} rounded-xl p-6 border border-white/10`}>
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className={`text-lg font-semibold ${theme.text.primary} mb-1`}>
                    {condition.condition}
                  </h3>
                  <p className={`text-sm ${theme.text.muted}`}>
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

              <p className={`text-sm ${theme.text.secondary} mb-4`}>
                {condition.description}
              </p>

              <div className="grid md:grid-cols-2 gap-4">
                <div>
                  <h4 className={`text-sm font-medium ${theme.text.secondary} mb-1`}>
                    Population Frequency
                  </h4>
                  <p className={`text-sm ${theme.text.primary}`}>
                    {condition.frequency}
                  </p>
                </div>
                <div>
                  <h4 className={`text-sm font-medium ${theme.text.secondary} mb-1`}>
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
      <div className={`${theme.glass} rounded-xl p-6 border border-blue-500/20 bg-blue-500/5`}>
        <div className="flex items-start space-x-3">
          <Info className="h-5 w-5 text-blue-500 mt-0.5" />
          <div>
            <h3 className={`font-semibold ${theme.text.primary} mb-2`}>
              Understanding Carrier Status
            </h3>
            <div className={`text-sm ${theme.text.secondary} space-y-2`}>
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