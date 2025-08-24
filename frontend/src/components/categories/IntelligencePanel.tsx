import React from 'react'
import { Brain, BookOpen, Lightbulb, Target, Puzzle } from 'lucide-react'

interface AnalysisData {
  summary?: any
  health_risks?: any
  drug_interactions?: any
  recommendations?: string[]
}

interface IntelligencePanelProps {
  data: AnalysisData
}

export default function IntelligencePanel({ data }: IntelligencePanelProps) {
  const cognitiveTraits = [
    {
      trait: 'Working Memory',
      gene: 'COMT',
      score: 82,
      description: 'Strong ability to hold and manipulate information',
      icon: Brain,
      color: 'bg-purple-50 text-purple-700'
    },
    {
      trait: 'Processing Speed',
      gene: 'SNAP25',
      score: 75,
      description: 'Good mental processing efficiency',
      icon: Lightbulb,
      color: 'bg-yellow-50 text-yellow-700'
    },
    {
      trait: 'Learning Ability',
      gene: 'BDNF',
      score: 88,
      description: 'Enhanced capacity for acquiring new skills',
      icon: BookOpen,
      color: 'bg-blue-50 text-blue-700'
    },
    {
      trait: 'Focus & Attention',
      gene: 'DRD4',
      score: 70,
      description: 'Moderate sustained attention capacity',
      icon: Target,
      color: 'bg-green-50 text-green-700'
    },
    {
      trait: 'Pattern Recognition',
      gene: 'CACNA1C',
      score: 85,
      description: 'Strong ability to identify patterns and relationships',
      icon: Puzzle,
      color: 'bg-indigo-50 text-indigo-700'
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
          <Brain className="h-8 w-8 text-purple-600 mr-3" />
          <div>
            <h2 className="text-2xl font-bold text-gray-900">Intelligence & Cognition</h2>
            <p className="text-gray-600">Your genetic cognitive profile and learning potential</p>
          </div>
        </div>
      </div>

      {/* Cognitive Traits */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Cognitive Abilities</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {cognitiveTraits.map((trait, index) => {
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
                    <div className="flex items-center space-x-3 mb-2">
                      <div className="w-20 bg-gray-200 rounded-full h-2">
                        <div 
                          className={`h-2 rounded-full ${getScoreBg(trait.score)}`}
                          style={{ width: `${trait.score}%` }}
                        ></div>
                      </div>
                      <span className={`text-sm font-medium ${getScoreColor(trait.score)}`}>
                        {trait.score}/100
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

      {/* Learning Styles */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Optimal Learning Styles</h3>
        <div className="space-y-4">
          {learningStyles.map((style, index) => (
            <div key={index} className="border rounded-lg p-4">
              <div className="flex justify-between items-center mb-2">
                <h4 className="font-medium text-gray-900">{style.style}</h4>
                <div className="flex items-center space-x-2">
                  <div className="w-24 bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-purple-500 h-2 rounded-full"
                      style={{ width: `${style.effectiveness}%` }}
                    ></div>
                  </div>
                  <span className="text-sm font-medium text-gray-700">{style.effectiveness}%</span>
                </div>
              </div>
              <p className="text-sm text-gray-600 mb-3">{style.description}</p>
              <div className="bg-gray-50 rounded-lg p-3">
                <h5 className="text-sm font-medium text-gray-900 mb-2">Optimization Tips:</h5>
                <ul className="text-sm text-gray-600 space-y-1">
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
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Cognitive Enhancement Strategies</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <h4 className="font-medium text-gray-900">Brain Training</h4>
            <div className="space-y-3">
              <div className="p-3 bg-blue-50 rounded-lg">
                <h5 className="font-medium text-blue-900">Memory Games</h5>
                <p className="text-sm text-blue-700">Enhance working memory with targeted exercises</p>
              </div>
              <div className="p-3 bg-green-50 rounded-lg">
                <h5 className="font-medium text-green-900">Problem Solving</h5>
                <p className="text-sm text-green-700">Regular puzzles and logic games</p>
              </div>
              <div className="p-3 bg-purple-50 rounded-lg">
                <h5 className="font-medium text-purple-900">Reading</h5>
                <p className="text-sm text-purple-700">Diverse reading materials to boost comprehension</p>
              </div>
            </div>
          </div>
          
          <div className="space-y-4">
            <h4 className="font-medium text-gray-900">Lifestyle Factors</h4>
            <div className="space-y-3">
              <div className="p-3 bg-orange-50 rounded-lg">
                <h5 className="font-medium text-orange-900">Sleep Quality</h5>
                <p className="text-sm text-orange-700">7-9 hours for optimal cognitive function</p>
              </div>
              <div className="p-3 bg-red-50 rounded-lg">
                <h5 className="font-medium text-red-900">Physical Exercise</h5>
                <p className="text-sm text-red-700">Regular cardio enhances neuroplasticity</p>
              </div>
              <div className="p-3 bg-teal-50 rounded-lg">
                <h5 className="font-medium text-teal-900">Meditation</h5>
                <p className="text-sm text-teal-700">Mindfulness improves focus and attention</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}