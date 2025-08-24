import React from 'react'
import { Apple, Coffee, Utensils, Wheat, ChefHat } from 'lucide-react'
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

interface FoodNutritionPanelProps {
  isDarkMode?: boolean
  theme?: any
  data: AnalysisData
}

export default function FoodNutritionPanel({ isDarkMode = false, theme, data }: FoodNutritionPanelProps) {
  const glassBackground = getGlassBackground(isDarkMode);
  const glassBorder = getGlassBorder(isDarkMode);
  const textPrimary = getTextPrimary(isDarkMode);
  const textSecondary = getTextSecondary(isDarkMode);
  const tagClass = getTagClass(isDarkMode);
  const progressBarBg = getProgressBarBg(isDarkMode);
  const cardBackground = getThemeClass('bg-gray-50', isDarkMode);
  
  // Mock data for food and nutrition traits
  const nutritionTraits = [
    {
      trait: 'Caffeine Metabolism',
      gene: 'CYP1A2',
      status: 'Fast Metabolizer',
      description: 'Can handle higher caffeine intake without side effects',
      icon: Coffee,
      color: getThemeClass('bg-brown-50', isDarkMode) + ' ' + getThemeClass('text-brown-700', isDarkMode),
      recommendation: 'Up to 400mg caffeine daily is likely well-tolerated'
    },
    {
      trait: 'Lactose Tolerance',
      gene: 'LCT',
      status: 'Tolerant',
      description: 'Continues to produce lactase enzyme into adulthood',
      icon: Apple,
      color: getThemeClass('bg-blue-50', isDarkMode) + ' ' + getThemeClass('text-blue-700', isDarkMode),
      recommendation: 'Dairy products are well-tolerated'
    },
    {
      trait: 'Alcohol Metabolism',
      gene: 'ALDH2',
      status: 'Normal',
      description: 'Standard alcohol processing capability',
      icon: Utensils,
      color: getThemeClass('bg-green-50', isDarkMode) + ' ' + getThemeClass('text-green-700', isDarkMode),
      recommendation: 'Moderate alcohol consumption guidelines apply'
    },
    {
      trait: 'Gluten Sensitivity',
      gene: 'HLA-DQ',
      status: 'Low Risk',
      description: 'Low genetic predisposition to celiac disease',
      icon: Wheat,
      color: getThemeClass('bg-yellow-50', isDarkMode) + ' ' + getThemeClass('text-yellow-700', isDarkMode),
      recommendation: 'Gluten-containing foods are likely well-tolerated'
    },
    {
      trait: 'Vitamin D Absorption',
      gene: 'VDR',
      status: 'Enhanced',
      description: 'Efficient vitamin D receptor function',
      icon: ChefHat,
      color: getThemeClass('bg-orange-50', isDarkMode) + ' ' + getThemeClass('text-orange-700', isDarkMode),
      recommendation: 'Standard vitamin D supplementation sufficient'
    }
  ]

  const dietaryRecommendations = [
    {
      type: 'Mediterranean Diet',
      suitability: 95,
      reason: 'High genetic compatibility with anti-inflammatory foods'
    },
    {
      type: 'Low-Carb Diet',
      suitability: 75,
      reason: 'Good fat metabolism, moderate carb sensitivity'
    },
    {
      type: 'Plant-Based Diet',
      suitability: 85,
      reason: 'Efficient plant nutrient absorption'
    },
    {
      type: 'Intermittent Fasting',
      suitability: 80,
      reason: 'Favorable insulin sensitivity genes'
    }
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <div className="flex items-center mb-4">
          <Apple className={`h-8 w-8 ${getThemeClass('text-green-600', isDarkMode)} mr-3`} />
          <div>
            <h2 className={`text-2xl font-bold ${textPrimary}`}>Food & Nutrition</h2>
            <p className={`${textSecondary}`}>Your genetic response to food and nutrients</p>
          </div>
        </div>
      </div>

      {/* Nutrition Traits */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Metabolic Traits</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {nutritionTraits.map((trait, index) => {
            const Icon = trait.icon
            return (
              <div key={index} className={`${cardBackground} border ${glassBorder} rounded-lg p-4 hover:shadow-md transition-shadow`}>
                <div className="flex items-start space-x-3">
                  <div className={`p-2 rounded-lg ${trait.color}`}>
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="flex-1">
                    <div className="flex justify-between items-start mb-2">
                      <h4 className={`font-medium ${textPrimary}`}>{trait.trait}</h4>
                      <span className={`text-xs px-2 py-1 rounded ${tagClass}`}>
                        {trait.gene}
                      </span>
                    </div>
                    <p className={`text-sm font-medium ${textSecondary} mb-1`}>{trait.status}</p>
                    <p className={`text-xs ${textSecondary} mb-2`}>{trait.description}</p>
                    <p className={`text-xs p-2 rounded ${getThemeClass('text-blue-600', isDarkMode)} ${getThemeClass('bg-blue-50', isDarkMode)}`}>
                      💡 {trait.recommendation}
                    </p>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Diet Compatibility */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Diet Compatibility</h3>
        <div className="space-y-4">
          {dietaryRecommendations.map((diet, index) => (
            <div key={index} className={`${cardBackground} border ${glassBorder} rounded-lg p-4`}>
              <div className="flex justify-between items-center mb-2">
                <h4 className={`font-medium ${textPrimary}`}>{diet.type}</h4>
                <div className="flex items-center space-x-2">
                  <div className={`w-24 rounded-full h-2 ${progressBarBg}`}>
                    <div 
                      className="bg-green-500 h-2 rounded-full"
                      style={{ width: `${diet.suitability}%` }}
                    ></div>
                  </div>
                  <span className={`text-sm font-medium ${textSecondary}`}>{diet.suitability}%</span>
                </div>
              </div>
              <p className={`text-sm ${textSecondary}`}>{diet.reason}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Nutritional Focus Areas */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Personalized Nutrition Focus</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className={`p-4 ${getThemeClass('bg-green-50', isDarkMode)} rounded-lg`}>
            <h4 className={`font-medium ${getThemeClass('text-green-900', isDarkMode)} mb-2`}>Prioritize</h4>
            <ul className={`text-sm ${getThemeClass('text-green-700', isDarkMode)} space-y-1`}>
              <li>• Omega-3 fatty acids</li>
              <li>• Antioxidant-rich foods</li>
              <li>• Complex carbohydrates</li>
              <li>• Lean proteins</li>
            </ul>
          </div>
          <div className={`p-4 ${getThemeClass('bg-yellow-50', isDarkMode)} rounded-lg`}>
            <h4 className={`font-medium ${getThemeClass('text-yellow-900', isDarkMode)} mb-2`}>Moderate</h4>
            <ul className={`text-sm ${getThemeClass('text-yellow-700', isDarkMode)} space-y-1`}>
              <li>• Saturated fats</li>
              <li>• Simple sugars</li>
              <li>• Processed foods</li>
              <li>• Caffeine intake</li>
            </ul>
          </div>
          <div className={`p-4 ${getThemeClass('bg-red-50', isDarkMode)} rounded-lg`}>
            <h4 className={`font-medium ${getThemeClass('text-red-900', isDarkMode)} mb-2`}>Consider Avoiding</h4>
            <ul className={`text-sm ${getThemeClass('text-red-700', isDarkMode)} space-y-1`}>
              <li>• Trans fats</li>
              <li>• Excessive alcohol</li>
              <li>• High sodium foods</li>
              <li>• Ultra-processed foods</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  )
}