import React from 'react'
import { Zap, Eye, Ruler, Palette, Sun } from 'lucide-react'

interface AnalysisData {
  summary?: any
  health_risks?: any
  drug_interactions?: any
  recommendations?: string[]
}

interface PhysicalTraitsPanelProps {
  data: AnalysisData
}

export default function PhysicalTraitsPanel({ data }: PhysicalTraitsPanelProps) {
  const physicalTraits = [
    {
      category: 'Eye Color',
      trait: 'Brown Eyes',
      gene: 'HERC2/OCA2',
      probability: 85,
      description: 'High likelihood of brown eye pigmentation',
      icon: Eye,
      color: 'bg-amber-50 text-amber-700'
    },
    {
      category: 'Hair Texture',
      trait: 'Straight Hair',
      gene: 'TCHH',
      probability: 70,
      description: 'Genetic predisposition to straight hair texture',
      icon: Palette,
      color: 'bg-purple-50 text-purple-700'
    },
    {
      category: 'Height Potential',
      trait: 'Above Average',
      gene: 'HMGA2',
      probability: 75,
      description: 'Genetic variants associated with increased height',
      icon: Ruler,
      color: 'bg-blue-50 text-blue-700'
    },
    {
      category: 'Skin Pigmentation',
      trait: 'Medium Tone',
      gene: 'MC1R',
      probability: 80,
      description: 'Moderate melanin production capacity',
      icon: Sun,
      color: 'bg-orange-50 text-orange-700'
    },
    {
      category: 'Muscle Fiber Type',
      trait: 'Fast Twitch',
      gene: 'ACTN3',
      probability: 65,
      description: 'Enhanced power and strength muscle composition',
      icon: Zap,
      color: 'bg-red-50 text-red-700'
    }
  ]

  const appearanceFeatures = [
    {
      feature: 'Freckles',
      likelihood: 'Low',
      gene: 'IRF4',
      description: 'Reduced tendency to develop freckles'
    },
    {
      feature: 'Dimples',
      likelihood: 'Moderate',
      gene: 'Multiple',
      description: 'Some genetic factors for facial dimples present'
    },
    {
      feature: 'Widow\'s Peak',
      likelihood: 'High',
      gene: 'RSPO2',
      description: 'Strong genetic predisposition to widow\'s peak hairline'
    },
    {
      feature: 'Earwax Type',
      likelihood: 'Wet Type',
      gene: 'ABCC11',
      description: 'Wet earwax production (common in most populations)'
    }
  ]

  const getProbabilityColor = (prob: number) => {
    if (prob >= 80) return 'text-green-600'
    if (prob >= 60) return 'text-yellow-600'
    return 'text-red-600'
  }

  const getProbabilityBg = (prob: number) => {
    if (prob >= 80) return 'bg-green-500'
    if (prob >= 60) return 'bg-yellow-500'
    return 'bg-red-500'
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <div className="flex items-center mb-4">
          <Zap className="h-8 w-8 text-orange-600 mr-3" />
          <div>
            <h2 className="text-2xl font-bold text-gray-900">Physical Traits</h2>
            <p className="text-gray-600">Your genetic physical characteristics and appearance</p>
          </div>
        </div>
      </div>

      {/* Major Physical Traits */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Primary Characteristics</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {physicalTraits.map((trait, index) => {
            const Icon = trait.icon
            return (
              <div key={index} className="border rounded-lg p-4 hover:shadow-md transition-shadow">
                <div className="flex items-start space-x-3">
                  <div className={`p-2 rounded-lg ${trait.color}`}>
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="flex-1">
                    <div className="flex justify-between items-start mb-2">
                      <div>
                        <h4 className="font-medium text-gray-900">{trait.category}</h4>
                        <p className="text-sm text-gray-600">{trait.trait}</p>
                      </div>
                      <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded">
                        {trait.gene}
                      </span>
                    </div>
                    <div className="flex items-center space-x-3 mb-2">
                      <div className="w-20 bg-gray-200 rounded-full h-2">
                        <div 
                          className={`h-2 rounded-full ${getProbabilityBg(trait.probability)}`}
                          style={{ width: `${trait.probability}%` }}
                        ></div>
                      </div>
                      <span className={`text-sm font-medium ${getProbabilityColor(trait.probability)}`}>
                        {trait.probability}%
                      </span>
                    </div>
                    <p className="text-xs text-gray-600">{trait.description}</p>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Additional Features */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Additional Features</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {appearanceFeatures.map((feature, index) => (
            <div key={index} className="border rounded-lg p-4">
              <div className="flex justify-between items-start mb-2">
                <h4 className="font-medium text-gray-900">{feature.feature}</h4>
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded">
                  {feature.gene}
                </span>
              </div>
              <p className="text-sm font-medium text-gray-700 mb-1">{feature.likelihood}</p>
              <p className="text-xs text-gray-600">{feature.description}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Body Composition */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Body Composition Genetics</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="text-center p-4 bg-blue-50 rounded-lg">
            <div className="text-2xl font-bold text-blue-600 mb-2">72%</div>
            <h4 className="font-medium text-blue-900 mb-1">Muscle Building</h4>
            <p className="text-sm text-blue-700">Good response to strength training</p>
          </div>
          <div className="text-center p-4 bg-green-50 rounded-lg">
            <div className="text-2xl font-bold text-green-600 mb-2">68%</div>
            <h4 className="font-medium text-green-900 mb-1">Fat Metabolism</h4>
            <p className="text-sm text-green-700">Moderate fat burning efficiency</p>
          </div>
          <div className="text-center p-4 bg-purple-50 rounded-lg">
            <div className="text-2xl font-bold text-purple-600 mb-2">85%</div>
            <h4 className="font-medium text-purple-900 mb-1">Bone Density</h4>
            <p className="text-sm text-purple-700">Strong genetic bone health</p>
          </div>
        </div>
      </div>

      {/* Age-Related Changes */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Age-Related Considerations</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <h4 className="font-medium text-gray-900">Hair & Skin</h4>
            <div className="space-y-3">
              <div className="p-3 bg-gray-50 rounded-lg">
                <h5 className="font-medium text-gray-900">Male Pattern Baldness</h5>
                <p className="text-sm text-gray-600">Moderate genetic risk (AR gene)</p>
              </div>
              <div className="p-3 bg-yellow-50 rounded-lg">
                <h5 className="font-medium text-yellow-900">Skin Aging</h5>
                <p className="text-sm text-yellow-700">Average collagen degradation rate</p>
              </div>
            </div>
          </div>
          
          <div className="space-y-4">
            <h4 className="font-medium text-gray-900">Body Changes</h4>
            <div className="space-y-3">
              <div className="p-3 bg-blue-50 rounded-lg">
                <h5 className="font-medium text-blue-900">Muscle Maintenance</h5>
                <p className="text-sm text-blue-700">Good genetic preservation with activity</p>
              </div>
              <div className="p-3 bg-green-50 rounded-lg">
                <h5 className="font-medium text-green-900">Weight Management</h5>
                <p className="text-sm text-green-700">Moderate tendency for weight gain</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}