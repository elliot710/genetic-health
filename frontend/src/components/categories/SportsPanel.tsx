import React from 'react'
import { Dumbbell, Zap, Heart, Trophy, Target, Timer } from 'lucide-react'
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

interface SportsPanelProps {
  isDarkMode?: boolean
  theme?: any
  data: AnalysisData
}

export default function SportsPanel({ isDarkMode = false, theme, data }: SportsPanelProps) {
  const glassBackground = getGlassBackground(isDarkMode);
  const glassBorder = getGlassBorder(isDarkMode);
  const textPrimary = getTextPrimary(isDarkMode);
  const textSecondary = getTextSecondary(isDarkMode);
  const tagClass = getTagClass(isDarkMode);
  const progressBarBg = getProgressBarBg(isDarkMode);
  const cardBackground = getThemeClass('bg-gray-50', isDarkMode);
  
  const athleticTraits = [
    {
      trait: 'Power vs Endurance',
      gene: 'ACTN3',
      result: 'Power-oriented',
      score: 75,
      description: 'Genetic advantage for explosive movements and strength',
      icon: Zap,
      color: getThemeClass('bg-red-50', isDarkMode) + ' ' + getThemeClass('text-red-700', isDarkMode),
      recommendation: 'Focus on sprinting, weightlifting, and power sports'
    },
    {
      trait: 'VO2 Max Potential',
      gene: 'ACE',
      result: 'High',
      score: 85,
      description: 'Excellent genetic capacity for aerobic fitness',
      icon: Heart,
      color: getThemeClass('bg-blue-50', isDarkMode) + ' ' + getThemeClass('text-blue-700', isDarkMode),
      recommendation: 'Great potential for endurance sports and cardio training'
    },
    {
      trait: 'Recovery Speed',
      gene: 'CKM',
      result: 'Fast',
      score: 78,
      description: 'Enhanced ability to recover between training sessions',
      icon: Timer,
      color: getThemeClass('bg-green-50', isDarkMode) + ' ' + getThemeClass('text-green-700', isDarkMode),
      recommendation: 'Can handle more frequent, intense training sessions'
    },
    {
      trait: 'Injury Resistance',
      gene: 'COL1A1',
      result: 'Moderate',
      score: 65,
      description: 'Average genetic protection against soft tissue injuries',
      icon: Dumbbell,
      color: getThemeClass('bg-yellow-50', isDarkMode) + ' ' + getThemeClass('text-yellow-700', isDarkMode),
      recommendation: 'Focus on proper warm-up and injury prevention'
    },
    {
      trait: 'Muscle Fiber Type',
      gene: 'ACTN3',
      result: 'Mixed',
      score: 70,
      description: 'Balanced fast and slow twitch muscle fibers',
      icon: Trophy,
      color: getThemeClass('bg-purple-50', isDarkMode) + ' ' + getThemeClass('text-purple-700', isDarkMode),
      recommendation: 'Versatile for both power and endurance activities'
    }
  ]

  const sportsRecommendations = [
    {
      category: 'Highly Recommended',
      sports: ['Weightlifting', 'Sprinting', 'Basketball', 'Tennis'],
      reason: 'Power-oriented genetics with good recovery',
      color: getThemeClass('bg-green-50', isDarkMode) + ' ' + getThemeClass('border-green-200', isDarkMode) + ' ' + getThemeClass('text-green-800', isDarkMode)
    },
    {
      category: 'Well Suited',
      sports: ['Soccer', 'Swimming', 'Cycling', 'Boxing'],
      reason: 'Good endurance capacity with mixed fiber types',
      color: getThemeClass('bg-blue-50', isDarkMode) + ' ' + getThemeClass('border-blue-200', isDarkMode) + ' ' + getThemeClass('text-blue-800', isDarkMode)
    },
    {
      category: 'Consider With Training',
      sports: ['Marathon Running', 'Rock Climbing', 'Martial Arts'],
      reason: 'Requires focused endurance development',
      color: getThemeClass('bg-yellow-50', isDarkMode) + ' ' + getThemeClass('border-yellow-200', isDarkMode) + ' ' + getThemeClass('text-yellow-800', isDarkMode)
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
    if (score >= 80) return getThemeClass('text-green-600', isDarkMode)
    if (score >= 60) return getThemeClass('text-yellow-600', isDarkMode)
    return getThemeClass('text-red-600', isDarkMode)
  }

  const getScoreBg = (score: number) => {
    if (score >= 80) return 'bg-green-500'
    if (score >= 60) return 'bg-yellow-500'
    return 'bg-red-500'
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <div className="flex items-center mb-4">
          <Dumbbell className={`h-8 w-8 ${getThemeClass('text-red-600', isDarkMode)} mr-3`} />
          <div>
            <h2 className={`text-2xl font-bold ${textPrimary}`}>Sports & Fitness</h2>
            <p className={`${textSecondary}`}>Your genetic athletic potential and training optimization</p>
          </div>
        </div>
      </div>

      {/* Athletic Traits */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Athletic Genetic Profile</h3>
        <div className="space-y-6">
          {athleticTraits.map((trait, index) => {
            const Icon = trait.icon
            return (
              <div key={index} className={`${cardBackground} border ${glassBorder} rounded-lg p-4`}>
                <div className="flex items-start space-x-4">
                  <div className={`p-3 rounded-lg ${trait.color}`}>
                    <Icon className="h-6 w-6" />
                  </div>
                  <div className="flex-1">
                    <div className="flex justify-between items-start mb-3">
                      <div>
                        <h4 className={`font-medium ${textPrimary} text-lg`}>{trait.trait}</h4>
                        <p className={`text-sm font-medium ${textSecondary}`}>{trait.result}</p>
                      </div>
                      <div className="text-right">
                        <span className={`text-xl font-bold ${getScoreColor(trait.score)}`}>
                          {trait.score}%
                        </span>
                        <p className={`text-xs ${textSecondary}`}>{trait.gene}</p>
                      </div>
                    </div>
                    <div className="mb-3">
                      <div className={`w-full rounded-full h-2 ${progressBarBg}`}>
                        <div 
                          className={`h-2 rounded-full ${getScoreBg(trait.score)}`}
                          style={{ width: `${trait.score}%` }}
                        ></div>
                      </div>
                    </div>
                    <p className={`text-sm ${textSecondary} mb-2`}>{trait.description}</p>
                    <div className={`${getThemeClass('bg-blue-50', isDarkMode)} p-2 rounded text-sm ${getThemeClass('text-blue-700', isDarkMode)}`}>
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
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Recommended Sports</h3>
        <div className="space-y-4">
          {sportsRecommendations.map((category, index) => (
            <div key={index} className={`border rounded-lg p-4 ${category.color}`}>
              <h4 className="font-medium text-lg mb-2">{category.category}</h4>
              <div className="flex flex-wrap gap-2 mb-3">
                {category.sports.map((sport, sportIndex) => (
                  <span 
                    key={sportIndex}
                    className={`px-3 py-1 rounded-full text-sm font-medium ${tagClass}`}
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
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Training Optimization</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {trainingOptimization.map((training, index) => (
            <div key={index} className={`${cardBackground} border ${glassBorder} rounded-lg p-4`}>
              <h4 className={`font-medium ${textPrimary} mb-2`}>{training.aspect}</h4>
              <p className={`text-lg font-bold ${getThemeClass('text-blue-600', isDarkMode)} mb-2`}>{training.recommendation}</p>
              <p className={`text-sm ${textSecondary} mb-3`}>{training.reason}</p>
              <ul className={`text-sm space-y-1 ${textSecondary}`}>
                {training.details.map((detail, detailIndex) => (
                  <li key={detailIndex}>• {detail}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      {/* Performance Metrics */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Expected Performance Ranges</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <h4 className={`font-medium ${textPrimary}`}>Strength Metrics</h4>
            <div className="space-y-3">
              <div className={`flex justify-between items-center p-3 ${getThemeClass('bg-red-50', isDarkMode)} rounded-lg`}>
                <span className={`font-medium ${getThemeClass('text-red-900', isDarkMode)}`}>1-Rep Max Potential</span>
                <span className={`${getThemeClass('text-red-700', isDarkMode)}`}>Above Average</span>
              </div>
              <div className={`flex justify-between items-center p-3 ${getThemeClass('bg-orange-50', isDarkMode)} rounded-lg`}>
                <span className={`font-medium ${getThemeClass('text-orange-900', isDarkMode)}`}>Power Output</span>
                <span className={`${getThemeClass('text-orange-700', isDarkMode)}`}>High</span>
              </div>
              <div className={`flex justify-between items-center p-3 ${getThemeClass('bg-yellow-50', isDarkMode)} rounded-lg`}>
                <span className={`font-medium ${getThemeClass('text-yellow-900', isDarkMode)}`}>Muscle Growth Rate</span>
                <span className={`${getThemeClass('text-yellow-700', isDarkMode)}`}>Good</span>
              </div>
            </div>
          </div>
          
          <div className="space-y-4">
            <h4 className={`font-medium ${textPrimary}`}>Endurance Metrics</h4>
            <div className="space-y-3">
              <div className={`flex justify-between items-center p-3 ${getThemeClass('bg-blue-50', isDarkMode)} rounded-lg`}>
                <span className={`font-medium ${getThemeClass('text-blue-900', isDarkMode)}`}>VO2 Max Ceiling</span>
                <span className={`${getThemeClass('text-blue-700', isDarkMode)}`}>High</span>
              </div>
              <div className={`flex justify-between items-center p-3 ${getThemeClass('bg-teal-50', isDarkMode)} rounded-lg`}>
                <span className={`font-medium ${getThemeClass('text-teal-900', isDarkMode)}`}>Lactate Threshold</span>
                <span className={`${getThemeClass('text-teal-700', isDarkMode)}`}>Moderate</span>
              </div>
              <div className={`flex justify-between items-center p-3 ${getThemeClass('bg-green-50', isDarkMode)} rounded-lg`}>
                <span className={`font-medium ${getThemeClass('text-green-900', isDarkMode)}`}>Fat Oxidation</span>
                <span className={`${getThemeClass('text-green-700', isDarkMode)}`}>Good</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Nutrition for Athletes */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Athletic Nutrition Recommendations</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-3">
            <h4 className={`font-medium ${textPrimary}`}>Pre-Workout</h4>
            <div className={`${getThemeClass('bg-blue-50', isDarkMode)} p-3 rounded-lg`}>
              <p className={`text-sm ${getThemeClass('text-blue-700', isDarkMode)}`}>
                • Complex carbs 2-3 hours before<br/>
                • Moderate caffeine (good metabolism)<br/>
                • Adequate hydration
              </p>
            </div>
          </div>
          <div className="space-y-3">
            <h4 className={`font-medium ${textPrimary}`}>Post-Workout</h4>
            <div className={`${getThemeClass('bg-green-50', isDarkMode)} p-3 rounded-lg`}>
              <p className={`text-sm ${getThemeClass('text-green-700', isDarkMode)}`}>
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