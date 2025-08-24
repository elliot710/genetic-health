import React from 'react'
import { Zap, Eye, Ruler, Palette, Sun } from 'lucide-react'
import { 
  getThemeClass, 
  getGlassBackground, 
  getGlassBorder, 
  getTextPrimary, 
  getTextSecondary, 
  getTagClass, 
  getProgressBarBg 
} from '../../utils/theme'

interface AnalysisData {
  summary?: any
  health_risks?: any
  drug_interactions?: any
  recommendations?: string[]
}

interface PhysicalTraitsPanelProps {
  isDarkMode?: boolean
  theme?: any
  data: AnalysisData
}

export default function PhysicalTraitsPanel({ isDarkMode = false, theme, data }: PhysicalTraitsPanelProps) {
  const glassBackground = getGlassBackground(isDarkMode);
  const glassBorder = getGlassBorder(isDarkMode);
  const textPrimary = getTextPrimary(isDarkMode);
  const textSecondary = getTextSecondary(isDarkMode);
  const tagClass = getTagClass(isDarkMode);
  const progressBarBg = getProgressBarBg(isDarkMode);
  const cardBackground = getThemeClass('bg-gray-50', isDarkMode);
  
  const physicalTraits = [
    {
      category: 'Eye Color',
      trait: 'Brown Eyes',
      gene: 'HERC2/OCA2',
      probability: 85,
      description: 'High likelihood of brown eye pigmentation',
      icon: Eye,
      color: getThemeClass('bg-amber-50', isDarkMode) + ' ' + getThemeClass('text-amber-700', isDarkMode)
    },
    {
      category: 'Hair Texture',
      trait: 'Straight Hair',
      gene: 'TCHH',
      probability: 70,
      description: 'Genetic predisposition to straight hair texture',
      icon: Palette,
      color: getThemeClass('bg-purple-50', isDarkMode) + ' ' + getThemeClass('text-purple-700', isDarkMode)
    },
    {
      category: 'Height Potential',
      trait: 'Above Average',
      gene: 'HMGA2',
      probability: 75,
      description: 'Genetic variants associated with increased height',
      icon: Ruler,
      color: getThemeClass('bg-blue-50', isDarkMode) + ' ' + getThemeClass('text-blue-700', isDarkMode)
    },
    {
      category: 'Skin Pigmentation',
      trait: 'Medium Tone',
      gene: 'MC1R',
      probability: 80,
      description: 'Moderate melanin production capacity',
      icon: Sun,
      color: getThemeClass('bg-orange-50', isDarkMode) + ' ' + getThemeClass('text-orange-700', isDarkMode)
    },
    {
      category: 'Muscle Fiber Type',
      trait: 'Fast Twitch',
      gene: 'ACTN3',
      probability: 65,
      description: 'Enhanced power and strength muscle composition',
      icon: Zap,
      color: getThemeClass('bg-red-50', isDarkMode) + ' ' + getThemeClass('text-red-700', isDarkMode)
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
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <div className="flex items-center mb-4">
          <Zap className={`h-8 w-8 ${getThemeClass('text-orange-600', isDarkMode)} mr-3`} />
          <div>
            <h2 className={`text-2xl font-bold ${textPrimary}`}>Physical Traits</h2>
            <p className={`${textSecondary}`}>Your genetic physical characteristics and appearance</p>
          </div>
        </div>
      </div>

      {/* Major Physical Traits */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Primary Characteristics</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {physicalTraits.map((trait, index) => {
            const Icon = trait.icon
            return (
              <div key={index} className={`${cardBackground} border ${glassBorder} rounded-lg p-4 hover:shadow-md transition-shadow`}>
                <div className="flex items-start space-x-3">
                  <div className={`p-2 rounded-lg ${trait.color}`}>
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="flex-1">
                    <div className="flex justify-between items-start mb-2">
                      <div>
                        <h4 className={`font-medium ${textPrimary}`}>{trait.category}</h4>
                        <p className={`text-sm ${textSecondary}`}>{trait.trait}</p>
                      </div>
                      <span className={`text-xs px-2 py-1 rounded ${tagClass}`}>
                        {trait.gene}
                      </span>
                    </div>
                    <div className="flex items-center space-x-3 mb-2">
                      <div className={`w-20 rounded-full h-2 ${progressBarBg}`}>
                        <div 
                          className={`h-2 rounded-full ${getProbabilityBg(trait.probability)}`}
                          style={{ width: `${trait.probability}%` }}
                        ></div>
                      </div>
                      <span className={`text-sm font-medium ${getProbabilityColor(trait.probability)}`}>
                        {trait.probability}%
                      </span>
                    </div>
                    <p className={`text-xs ${textSecondary}`}>{trait.description}</p>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Additional Features */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Additional Features</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {appearanceFeatures.map((feature, index) => (
            <div key={index} className={`${cardBackground} border ${glassBorder} rounded-lg p-4`}>
              <div className="flex justify-between items-start mb-2">
                <h4 className={`font-medium ${textPrimary}`}>{feature.feature}</h4>
                <span className={`text-xs px-2 py-1 rounded ${tagClass}`}>
                  {feature.gene}
                </span>
              </div>
              <p className={`text-sm font-medium ${textSecondary} mb-1`}>{feature.likelihood}</p>
              <p className={`text-xs ${textSecondary}`}>{feature.description}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Body Composition */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Body Composition Genetics</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className={`text-center p-4 rounded-lg ${getThemeClass('bg-blue-50', isDarkMode)} border ${getThemeClass('border-blue-200', isDarkMode)}`}>
            <div className={`text-2xl font-bold ${getThemeClass('text-blue-600', isDarkMode)} mb-2`}>72%</div>
            <h4 className={`font-medium mb-1 ${getThemeClass('text-blue-900', isDarkMode)}`}>Muscle Building</h4>
            <p className={`text-sm ${getThemeClass('text-blue-700', isDarkMode)}`}>Good response to strength training</p>
          </div>
          <div className={`text-center p-4 rounded-lg ${getThemeClass('bg-green-50', isDarkMode)} border ${getThemeClass('border-green-200', isDarkMode)}`}>
            <div className={`text-2xl font-bold ${getThemeClass('text-green-600', isDarkMode)} mb-2`}>68%</div>
            <h4 className={`font-medium mb-1 ${getThemeClass('text-green-900', isDarkMode)}`}>Fat Metabolism</h4>
            <p className={`text-sm ${getThemeClass('text-green-700', isDarkMode)}`}>Moderate fat burning efficiency</p>
          </div>
          <div className={`text-center p-4 rounded-lg ${getThemeClass('bg-purple-50', isDarkMode)} border ${getThemeClass('border-purple-200', isDarkMode)}`}>
            <div className={`text-2xl font-bold ${getThemeClass('text-purple-600', isDarkMode)} mb-2`}>85%</div>
            <h4 className={`font-medium mb-1 ${getThemeClass('text-purple-900', isDarkMode)}`}>Bone Density</h4>
            <p className={`text-sm ${getThemeClass('text-purple-700', isDarkMode)}`}>Strong genetic bone health</p>
          </div>
        </div>
      </div>

      {/* Age-Related Changes */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Age-Related Considerations</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <h4 className={`font-medium ${textPrimary}`}>Hair & Skin</h4>
            <div className="space-y-3">
              <div className={`p-3 rounded-lg ${cardBackground}`}>
                <h5 className={`font-medium ${textPrimary}`}>Male Pattern Baldness</h5>
                <p className={`text-sm ${textSecondary}`}>Moderate genetic risk (AR gene)</p>
              </div>
              <div className={`p-3 rounded-lg ${getThemeClass('bg-yellow-50', isDarkMode)} border ${getThemeClass('border-yellow-200', isDarkMode)}`}>
                <h5 className={`font-medium ${getThemeClass('text-yellow-900', isDarkMode)}`}>Skin Aging</h5>
                <p className={`text-sm ${getThemeClass('text-yellow-700', isDarkMode)}`}>Average collagen degradation rate</p>
              </div>
            </div>
          </div>
          
          <div className="space-y-4">
            <h4 className={`font-medium ${textPrimary}`}>Body Changes</h4>
            <div className="space-y-3">
              <div className={`p-3 rounded-lg ${getThemeClass('bg-blue-50', isDarkMode)}`}>
                <h5 className={`font-medium ${getThemeClass('text-blue-900', isDarkMode)}`}>Muscle Maintenance</h5>
                <p className={`text-sm ${getThemeClass('text-blue-700', isDarkMode)}`}>Good genetic preservation with activity</p>
              </div>
              <div className={`p-3 rounded-lg ${getThemeClass('bg-green-50', isDarkMode)}`}>
                <h5 className={`font-medium ${getThemeClass('text-green-900', isDarkMode)}`}>Weight Management</h5>
                <p className={`text-sm ${getThemeClass('text-green-700', isDarkMode)}`}>Moderate tendency for weight gain</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}