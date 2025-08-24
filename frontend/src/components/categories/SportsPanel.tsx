import React from 'react'
import { Dumbbell, Zap, Timer, Trophy, Heart } from 'lucide-react'

interface AnalysisData {
  summary?: any
  health_risks?: any
  drug_interactions?: any
  recommendations?: string[]
}

interface SportsPanelProps {
  data: AnalysisData
}

export default function SportsPanel({ data }: SportsPanelProps) {
  const athleticTraits = [
    {
      trait: 'Power vs Endurance',
      gene: 'ACTN3',
      result: 'Power-oriented',
      score: 75,
      description: 'Genetic advantage for explosive movements and strength',
      icon: Zap,
      color: 'bg-red-50 text-red-700',
      recommendation: 'Focus on sprinting, weightlifting, and power sports'
    },
    {
      trait: 'VO2 Max Potential',
      gene: 'ACE',
      result: 'High',
      score: 85,
      description: 'Excellent genetic capacity for aerobic fitness',
      icon: Heart,
      color: 'bg-blue-50 text-blue-700',
      recommendation: 'Great potential for endurance sports and cardio training'
    },
    {
      trait: 'Recovery Speed',
      gene: 'CKM',
      result: 'Fast',
      score: 78,
      description: 'Enhanced ability to recover between training sessions',
      icon: Timer,
      color: 'bg-green-50 text-green-700',
      recommendation: 'Can handle more frequent, intense training sessions'
    },
    {
      trait: 'Injury Resistance',
      gene: 'COL1A1',
      result: 'Moderate',
      score: 65,
      description: 'Average genetic protection against soft tissue injuries',
      icon: Dumbbell,
      color: 'bg-yellow-50 text-yellow-700',
      recommendation: 'Focus on proper warm-up and injury prevention'
    },
    {
      trait: 'Muscle Fiber Type',
      gene: 'ACTN3',
      result: 'Mixed',
      score: 70,
      description: 'Balanced fast and slow twitch muscle fibers',
      icon: Trophy,
      color: 'bg-purple-50 text-purple-700',
      recommendation: 'Versatile for both power and endurance activities'
    }
  ]

  const sportsRecommendations = [
    {
      category: 'Highly Recommended',
      sports: ['Weightlifting', 'Sprinting', 'Basketball', 'Tennis'],
      reason: 'Power-oriented genetics with good recovery',
      color: 'bg-green-50 border-green-200 text-green-800'
    },
    {
      category: 'Well Suited',
      sports: ['Soccer', 'Swimming', 'Cycling', 'Boxing'],
      reason: 'Good endurance capacity with mixed fiber types',
      color: 'bg-blue-50 border-blue-200 text-blue-800'
    },
    {
      category: 'Consider With Training',
      sports: ['Marathon Running', 'Rock Climbing', 'Martial Arts'],
      reason: 'Requires focused endurance development',
      color: 'bg-yellow-50 border-yellow-200 text-yellow-800'
    }
  ]

  const trainingOptimization = [
    {
      aspect: 'Training Frequency',
      recommendation: '5-6 days per week',
      reason: 'Fast recovery allows for frequent sessions',
      details: ['2-3 strength sessions', '2-3 cardio sessions', '1-2 active recovery days']
    },
    {
      aspect: 'Intensity Distribution',
      recommendation: '80/20 Rule',
      reason: 'Mix of high and moderate intensity',
      details: ['80% moderate intensity', '20% high intensity', 'Periodized training blocks']
    },
    {
      aspect: 'Recovery Protocol',
      recommendation: 'Active Recovery',
      reason: 'Good natural recovery genes',
      details: ['Light activity on rest days', '7-8 hours sleep', 'Proper hydration']
    }
  ]

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-green-600'
    if (score >= 60) return 'text-yellow-600'
    return 'text-red-600'
  }

  const getScoreBg = (score: number) => {
    if (score >= 80) return 'bg-green-500'
    if (score >= 60) return 'bg-yellow-500'
    return 'bg-red-500'
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <div className="flex items-center mb-4">
          <Dumbbell className="h-8 w-8 text-red-600 mr-3" />
          <div>
            <h2 className="text-2xl font-bold text-gray-900">Sports & Fitness</h2>
            <p className="text-gray-600">Your genetic athletic potential and training optimization</p>
          </div>
        </div>
      </div>

      {/* Athletic Traits */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Athletic Genetic Profile</h3>
        <div className="space-y-6">
          {athleticTraits.map((trait, index) => {
            const Icon = trait.icon
            return (
              <div key={index} className="border rounded-lg p-4">
                <div className="flex items-start space-x-4">
                  <div className={`p-3 rounded-lg ${trait.color}`}>
                    <Icon className="h-6 w-6" />
                  </div>
                  <div className="flex-1">
                    <div className="flex justify-between items-start mb-3">
                      <div>
                        <h4 className="font-medium text-gray-900 text-lg">{trait.trait}</h4>
                        <p className="text-sm font-medium text-gray-700">{trait.result}</p>
                      </div>
                      <div className="text-right">
                        <span className={`text-xl font-bold ${getScoreColor(trait.score)}`}>
                          {trait.score}%
                        </span>
                        <p className="text-xs text-gray-500">{trait.gene}</p>
                      </div>
                    </div>
                    <div className="mb-3">
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div 
                          className={`h-2 rounded-full ${getScoreBg(trait.score)}`}
                          style={{ width: `${trait.score}%` }}
                        ></div>
                      </div>
                    </div>
                    <p className="text-sm text-gray-600 mb-2">{trait.description}</p>
                    <div className="bg-blue-50 p-2 rounded text-sm text-blue-700">
                      💡 {trait.recommendation}
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Sports Recommendations */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Recommended Sports</h3>
        <div className="space-y-4">
          {sportsRecommendations.map((category, index) => (
            <div key={index} className={`border rounded-lg p-4 ${category.color}`}>
              <h4 className="font-medium text-lg mb-2">{category.category}</h4>
              <div className="flex flex-wrap gap-2 mb-3">
                {category.sports.map((sport, sportIndex) => (
                  <span 
                    key={sportIndex}
                    className="px-3 py-1 bg-white bg-opacity-60 rounded-full text-sm font-medium"
                  >
                    {sport}
                  </span>
                ))}
              </div>
              <p className="text-sm opacity-80">{category.reason}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Training Optimization */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Training Optimization</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {trainingOptimization.map((training, index) => (
            <div key={index} className="border rounded-lg p-4">
              <h4 className="font-medium text-gray-900 mb-2">{training.aspect}</h4>
              <p className="text-lg font-bold text-blue-600 mb-2">{training.recommendation}</p>
              <p className="text-sm text-gray-600 mb-3">{training.reason}</p>
              <ul className="text-sm text-gray-700 space-y-1">
                {training.details.map((detail, detailIndex) => (
                  <li key={detailIndex}>• {detail}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      {/* Performance Metrics */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Expected Performance Ranges</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <h4 className="font-medium text-gray-900">Strength Metrics</h4>
            <div className="space-y-3">
              <div className="flex justify-between items-center p-3 bg-red-50 rounded-lg">
                <span className="font-medium text-red-900">1-Rep Max Potential</span>
                <span className="text-red-700">Above Average</span>
              </div>
              <div className="flex justify-between items-center p-3 bg-orange-50 rounded-lg">
                <span className="font-medium text-orange-900">Power Output</span>
                <span className="text-orange-700">High</span>
              </div>
              <div className="flex justify-between items-center p-3 bg-yellow-50 rounded-lg">
                <span className="font-medium text-yellow-900">Muscle Growth Rate</span>
                <span className="text-yellow-700">Good</span>
              </div>
            </div>
          </div>
          
          <div className="space-y-4">
            <h4 className="font-medium text-gray-900">Endurance Metrics</h4>
            <div className="space-y-3">
              <div className="flex justify-between items-center p-3 bg-blue-50 rounded-lg">
                <span className="font-medium text-blue-900">VO2 Max Ceiling</span>
                <span className="text-blue-700">High</span>
              </div>
              <div className="flex justify-between items-center p-3 bg-teal-50 rounded-lg">
                <span className="font-medium text-teal-900">Lactate Threshold</span>
                <span className="text-teal-700">Moderate</span>
              </div>
              <div className="flex justify-between items-center p-3 bg-green-50 rounded-lg">
                <span className="font-medium text-green-900">Fat Oxidation</span>
                <span className="text-green-700">Good</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Nutrition for Athletes */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Athletic Nutrition Recommendations</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-3">
            <h4 className="font-medium text-gray-900">Pre-Workout</h4>
            <div className="bg-blue-50 p-3 rounded-lg">
              <p className="text-sm text-blue-700">
                • Complex carbs 2-3 hours before<br/>
                • Moderate caffeine (good metabolism)<br/>
                • Adequate hydration
              </p>
            </div>
          </div>
          <div className="space-y-3">
            <h4 className="font-medium text-gray-900">Post-Workout</h4>
            <div className="bg-green-50 p-3 rounded-lg">
              <p className="text-sm text-green-700">
                • Protein within 30 minutes<br/>
                • Carb replenishment for glycogen<br/>
                • Anti-inflammatory foods
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}