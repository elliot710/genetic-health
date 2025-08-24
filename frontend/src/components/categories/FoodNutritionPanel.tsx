import React from 'react'
import { Apple, Coffee, Utensils, Wheat, ChefHat } from 'lucide-react'

interface AnalysisData {
  summary?: any
  health_risks?: any
  drug_interactions?: any
  recommendations?: string[]
}

interface FoodNutritionPanelProps {
  data: AnalysisData
}

export default function FoodNutritionPanel({ data }: FoodNutritionPanelProps) {
  // Mock data for food and nutrition traits
  const nutritionTraits = [
    {
      trait: 'Caffeine Metabolism',
      gene: 'CYP1A2',
      status: 'Fast Metabolizer',
      description: 'Can handle higher caffeine intake without side effects',
      icon: Coffee,
      color: 'bg-brown-50 text-brown-700',
      recommendation: 'Up to 400mg caffeine daily is likely well-tolerated'
    },
    {
      trait: 'Lactose Tolerance',
      gene: 'LCT',
      status: 'Tolerant',
      description: 'Continues to produce lactase enzyme into adulthood',
      icon: Apple,
      color: 'bg-blue-50 text-blue-700',
      recommendation: 'Dairy products are well-tolerated'
    },
    {
      trait: 'Alcohol Metabolism',
      gene: 'ALDH2',
      status: 'Normal',
      description: 'Standard alcohol processing capability',
      icon: Utensils,
      color: 'bg-green-50 text-green-700',
      recommendation: 'Moderate alcohol consumption guidelines apply'
    },
    {
      trait: 'Gluten Sensitivity',
      gene: 'HLA-DQ',
      status: 'Low Risk',
      description: 'Low genetic predisposition to celiac disease',
      icon: Wheat,
      color: 'bg-yellow-50 text-yellow-700',
      recommendation: 'Gluten-containing foods are likely well-tolerated'
    },
    {
      trait: 'Vitamin D Absorption',
      gene: 'VDR',
      status: 'Enhanced',
      description: 'Efficient vitamin D receptor function',
      icon: ChefHat,
      color: 'bg-orange-50 text-orange-700',
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
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <div className="flex items-center mb-4">
          <Apple className="h-8 w-8 text-green-600 mr-3" />
          <div>
            <h2 className="text-2xl font-bold text-gray-900">Food & Nutrition</h2>
            <p className="text-gray-600">Your genetic response to food and nutrients</p>
          </div>
        </div>
      </div>

      {/* Nutrition Traits */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Metabolic Traits</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {nutritionTraits.map((trait, index) => {
            const Icon = trait.icon
            return (
              <div key={index} className="border rounded-lg p-4 hover:shadow-md transition-shadow">
                <div className="flex items-start space-x-3">
                  <div className={`p-2 rounded-lg ${trait.color}`}>
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="flex-1">
                    <div className="flex justify-between items-start mb-2">
                      <h4 className="font-medium text-gray-900">{trait.trait}</h4>
                      <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded">
                        {trait.gene}
                      </span>
                    </div>
                    <p className="text-sm font-medium text-gray-700 mb-1">{trait.status}</p>
                    <p className="text-xs text-gray-600 mb-2">{trait.description}</p>
                    <p className="text-xs text-blue-600 bg-blue-50 p-2 rounded">
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
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Diet Compatibility</h3>
        <div className="space-y-4">
          {dietaryRecommendations.map((diet, index) => (
            <div key={index} className="border rounded-lg p-4">
              <div className="flex justify-between items-center mb-2">
                <h4 className="font-medium text-gray-900">{diet.type}</h4>
                <div className="flex items-center space-x-2">
                  <div className="w-24 bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-green-500 h-2 rounded-full"
                      style={{ width: `${diet.suitability}%` }}
                    ></div>
                  </div>
                  <span className="text-sm font-medium text-gray-700">{diet.suitability}%</span>
                </div>
              </div>
              <p className="text-sm text-gray-600">{diet.reason}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Nutritional Focus Areas */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Personalized Nutrition Focus</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-4 bg-green-50 rounded-lg">
            <h4 className="font-medium text-green-900 mb-2">Prioritize</h4>
            <ul className="text-sm text-green-700 space-y-1">
              <li>• Omega-3 fatty acids</li>
              <li>• Antioxidant-rich foods</li>
              <li>• Complex carbohydrates</li>
              <li>• Lean proteins</li>
            </ul>
          </div>
          <div className="p-4 bg-yellow-50 rounded-lg">
            <h4 className="font-medium text-yellow-900 mb-2">Moderate</h4>
            <ul className="text-sm text-yellow-700 space-y-1">
              <li>• Saturated fats</li>
              <li>• Simple sugars</li>
              <li>• Processed foods</li>
              <li>• Caffeine intake</li>
            </ul>
          </div>
          <div className="p-4 bg-red-50 rounded-lg">
            <h4 className="font-medium text-red-900 mb-2">Consider Avoiding</h4>
            <ul className="text-sm text-red-700 space-y-1">
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