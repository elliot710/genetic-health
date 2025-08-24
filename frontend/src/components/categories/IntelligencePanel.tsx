import React from 'react'
import { Brain, BookOpen, Lightbulb, Target, Puzzle } from 'lucide-react'
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

interface IntelligencePanelProps {
  isDarkMode?: boolean
  theme?: any
  data: AnalysisData
}

export default function IntelligencePanel({ isDarkMode = false, theme, data }: IntelligencePanelProps) {
  const glassBackground = getGlassBackground(isDarkMode);
  const glassBorder = getGlassBorder(isDarkMode);
  const textPrimary = getTextPrimary(isDarkMode);
  const textSecondary = getTextSecondary(isDarkMode);
  const tagClass = getTagClass(isDarkMode);
  const progressBarBg = getProgressBarBg(isDarkMode);
  const cardBackground = getThemeClass('bg-gray-50', isDarkMode);
  
  const cognitiveTraits = [
    {
      trait: 'Working Memory',
      gene: 'COMT',
      score: 82,
      description: 'Strong ability to hold and manipulate information',
      icon: Brain,
      color: `${getThemeClass('bg-purple-50', isDarkMode)} ${getThemeClass('text-purple-700', isDarkMode)}`
    },
    {
      trait: 'Processing Speed',
      gene: 'SNAP25',
      score: 75,
      description: 'Good mental processing efficiency',
      icon: Lightbulb,
      color: `${getThemeClass('bg-yellow-50', isDarkMode)} ${getThemeClass('text-yellow-700', isDarkMode)}`
    },
    {
      trait: 'Learning Ability',
      gene: 'BDNF',
      score: 88,
      description: 'Enhanced capacity for acquiring new skills',
      icon: BookOpen,
      color: `${getThemeClass('bg-blue-50', isDarkMode)} ${getThemeClass('text-blue-700', isDarkMode)}`
    },
    {
      trait: 'Focus & Attention',
      gene: 'DRD4',
      score: 70,
      description: 'Moderate sustained attention capacity',
      icon: Target,
      color: `${getThemeClass('bg-green-50', isDarkMode)} ${getThemeClass('text-green-700', isDarkMode)}`
    },
    {
      trait: 'Pattern Recognition',
      gene: 'CACNA1C',
      score: 85,
      description: 'Strong ability to identify patterns and relationships',
      icon: Puzzle,
      color: `${getThemeClass('bg-indigo-50', isDarkMode)} ${getThemeClass('text-indigo-700', isDarkMode)}`
    }
  ]

  const learningStyles = [
    {
      style: 'Visual Learning',
      effectiveness: 90,
      description: 'Strong visual processing and memory',
      tips: ['Use diagrams and charts', 'Color-code information', 'Create visual mind maps']
    },
    {
      style: 'Sequential Learning',
      effectiveness: 75,
      description: 'Benefits from step-by-step instruction',
      tips: ['Break down complex tasks', 'Follow structured approaches', 'Use checklists']
    },
    {
      style: 'Social Learning',
      effectiveness: 80,
      description: 'Enhanced learning through interaction',
      tips: ['Study in groups', 'Discuss concepts aloud', 'Teach others']
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
          <Brain className={`h-8 w-8 ${getThemeClass('text-purple-600', isDarkMode)} mr-3`} />
          <div>
            <h2 className={`text-2xl font-bold ${textPrimary}`}>Intelligence & Cognition</h2>
            <p className={`${textSecondary}`}>Your genetic cognitive profile and learning potential</p>
          </div>
        </div>
      </div>

      {/* Cognitive Traits */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Cognitive Abilities</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {cognitiveTraits.map((trait, index) => {
            const Icon = trait.icon
            return (
              <div key={index} className={`border ${glassBorder} rounded-lg p-4 hover:shadow-md transition-shadow ${cardBackground}`}>
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
                    <div className="flex items-center space-x-3 mb-2">
                      <div className={`w-20 rounded-full h-2 ${progressBarBg}`}>
                        <div 
                          className={`h-2 rounded-full ${getScoreBg(trait.score)}`}
                          style={{ width: `${trait.score}%` }}
                        ></div>
                      </div>
                      <span className={`text-sm font-medium ${getScoreColor(trait.score)}`}>
                        {trait.score}/100
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

      {/* Learning Styles */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Optimal Learning Styles</h3>
        <div className="space-y-4">
          {learningStyles.map((style, index) => (
            <div key={index} className={`${cardBackground} border ${glassBorder} rounded-lg p-4`}>
              <div className="flex justify-between items-center mb-2">
                <h4 className={`font-medium ${textPrimary}`}>{style.style}</h4>
                <div className="flex items-center space-x-2">
                  <div className={`w-24 rounded-full h-2 ${progressBarBg}`}>
                    <div 
                      className="bg-purple-500 h-2 rounded-full"
                      style={{ width: `${style.effectiveness}%` }}
                    ></div>
                  </div>
                  <span className={`text-sm font-medium ${textSecondary}`}>{style.effectiveness}%</span>
                </div>
              </div>
              <p className={`text-sm ${textSecondary} mb-3`}>{style.description}</p>
              <div className={`rounded-lg p-3 ${cardBackground}`}>
                <h5 className={`text-sm font-medium ${textPrimary} mb-2`}>Optimization Tips:</h5>
                <ul className={`text-sm ${textSecondary} space-y-1`}>
                  {style.tips.map((tip, tipIndex) => (
                    <li key={tipIndex}>• {tip}</li>
                  ))}
                </ul>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Cognitive Enhancement */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Cognitive Enhancement Strategies</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <h4 className={`font-medium ${textPrimary}`}>Brain Training</h4>
            <div className="space-y-3">
              <div className={`p-3 rounded-lg ${getThemeClass('bg-blue-50', isDarkMode)}`}>
                <h5 className={`font-medium ${getThemeClass('text-blue-700', isDarkMode)}`}>Memory Games</h5>
                <p className={`text-sm ${getThemeClass('text-blue-700', isDarkMode)}`}>Enhance working memory with targeted exercises</p>
              </div>
              <div className={`p-3 rounded-lg ${getThemeClass('bg-green-50', isDarkMode)}`}>
                <h5 className={`font-medium ${getThemeClass('text-green-700', isDarkMode)}`}>Problem Solving</h5>
                <p className={`text-sm ${getThemeClass('text-green-700', isDarkMode)}`}>Regular puzzles and logic games</p>
              </div>
              <div className={`p-3 rounded-lg ${getThemeClass('bg-purple-50', isDarkMode)}`}>
                <h5 className={`font-medium ${getThemeClass('text-purple-700', isDarkMode)}`}>Reading</h5>
                <p className={`text-sm ${getThemeClass('text-purple-700', isDarkMode)}`}>Diverse reading materials to boost comprehension</p>
              </div>
            </div>
          </div>
          
          <div className="space-y-4">
            <h4 className={`font-medium ${textPrimary}`}>Lifestyle Factors</h4>
            <div className="space-y-3">
              <div className={`p-3 rounded-lg ${getThemeClass('bg-orange-50', isDarkMode)}`}>
                <h5 className={`font-medium ${getThemeClass('text-orange-700', isDarkMode)}`}>Sleep Quality</h5>
                <p className={`text-sm ${getThemeClass('text-orange-700', isDarkMode)}`}>7-9 hours for optimal cognitive function</p>
              </div>
              <div className={`p-3 rounded-lg ${getThemeClass('bg-red-50', isDarkMode)}`}>
                <h5 className={`font-medium ${getThemeClass('text-red-700', isDarkMode)}`}>Physical Exercise</h5>
                <p className={`text-sm ${getThemeClass('text-red-700', isDarkMode)}`}>Regular cardio enhances neuroplasticity</p>
              </div>
              <div className={`p-3 rounded-lg ${getThemeClass('bg-teal-50', isDarkMode)}`}>
                <h5 className={`font-medium ${getThemeClass('text-teal-700', isDarkMode)}`}>Meditation</h5>
                <p className={`text-sm ${getThemeClass('text-teal-700', isDarkMode)}`}>Mindfulness improves focus and attention</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}