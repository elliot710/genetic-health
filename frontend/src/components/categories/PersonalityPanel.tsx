import React from 'react'
import { Palette, Users, Smile, Zap, Heart } from 'lucide-react'

interface AnalysisData {
  summary?: any
  health_risks?: any
  drug_interactions?: any
  recommendations?: string[]
}

interface PersonalityPanelProps {
  data: AnalysisData
}

export default function PersonalityPanel({ data }: PersonalityPanelProps) {
  const personalityTraits = [
    {
      trait: 'Openness to Experience',
      score: 78,
      gene: 'DRD4',
      description: 'High creativity and willingness to try new things',
      icon: Palette,
      color: 'bg-purple-50 text-purple-700',
      characteristics: ['Curious', 'Creative', 'Open-minded', 'Imaginative']
    },
    {
      trait: 'Extraversion',
      score: 65,
      gene: 'DRD2',
      description: 'Moderate social energy and outward focus',
      icon: Users,
      color: 'bg-blue-50 text-blue-700',
      characteristics: ['Sociable', 'Assertive', 'Energetic', 'Talkative']
    },
    {
      trait: 'Agreeableness',
      score: 82,
      gene: 'OXTR',
      description: 'High tendency to be cooperative and trusting',
      icon: Heart,
      color: 'bg-pink-50 text-pink-700',
      characteristics: ['Compassionate', 'Cooperative', 'Trusting', 'Helpful']
    },
    {
      trait: 'Conscientiousness',
      score: 70,
      gene: 'KATNAL2',
      description: 'Good self-discipline and organization',
      icon: Zap,
      color: 'bg-green-50 text-green-700',
      characteristics: ['Organized', 'Disciplined', 'Goal-oriented', 'Reliable']
    },
    {
      trait: 'Emotional Stability',
      score: 60,
      gene: '5-HTTLPR',
      description: 'Moderate resilience to stress',
      icon: Smile,
      color: 'bg-yellow-50 text-yellow-700',
      characteristics: ['Calm', 'Resilient', 'Confident', 'Relaxed']
    }
  ]

  const behavioralTendencies = [
    {
      behavior: 'Risk Taking',
      level: 'Moderate',
      gene: 'DRD4',
      description: 'Balanced approach to risk assessment',
      implications: 'Good at calculated risks, not impulsive'
    },
    {
      behavior: 'Stress Response',
      level: 'Sensitive',
      gene: 'COMT',
      description: 'Higher sensitivity to stressful situations',
      implications: 'Benefits from stress management techniques'
    },
    {
      behavior: 'Social Bonding',
      level: 'High',
      gene: 'OXTR',
      description: 'Strong capacity for forming social bonds',
      implications: 'Thrives in collaborative environments'
    },
    {
      behavior: 'Novelty Seeking',
      level: 'High',
      gene: 'DRD4',
      description: 'Strong drive to seek new experiences',
      implications: 'Enjoys variety and new challenges'
    }
  ]

  const getScoreColor = (score: number) => {
    if (score >= 75) return 'text-green-600'
    if (score >= 50) return 'text-yellow-600'
    return 'text-red-600'
  }

  const getScoreBg = (score: number) => {
    if (score >= 75) return 'bg-green-500'
    if (score >= 50) return 'bg-yellow-500'
    return 'bg-red-500'
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <div className="flex items-center mb-4">
          <Palette className="h-8 w-8 text-pink-600 mr-3" />
          <div>
            <h2 className="text-2xl font-bold text-gray-900">Personality & Behavior</h2>
            <p className="text-gray-600">Your genetic behavioral tendencies and personality traits</p>
          </div>
        </div>
      </div>

      {/* Big Five Personality Traits */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Big Five Personality Dimensions</h3>
        <div className="space-y-6">
          {personalityTraits.map((trait, index) => {
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
                        <p className="text-sm text-gray-600">{trait.description}</p>
                      </div>
                      <div className="text-right">
                        <span className={`text-2xl font-bold ${getScoreColor(trait.score)}`}>
                          {trait.score}
                        </span>
                        <p className="text-xs text-gray-500">{trait.gene}</p>
                      </div>
                    </div>
                    <div className="mb-3">
                      <div className="w-full bg-gray-200 rounded-full h-3">
                        <div 
                          className={`h-3 rounded-full ${getScoreBg(trait.score)}`}
                          style={{ width: `${trait.score}%` }}
                        ></div>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {trait.characteristics.map((char, charIndex) => (
                        <span 
                          key={charIndex}
                          className="px-2 py-1 bg-gray-100 text-gray-700 text-xs rounded-full"
                        >
                          {char}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Behavioral Tendencies */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Behavioral Tendencies</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {behavioralTendencies.map((behavior, index) => (
            <div key={index} className="border rounded-lg p-4">
              <div className="flex justify-between items-start mb-2">
                <h4 className="font-medium text-gray-900">{behavior.behavior}</h4>
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded">
                  {behavior.gene}
                </span>
              </div>
              <p className="text-sm font-medium text-gray-700 mb-2">{behavior.level}</p>
              <p className="text-xs text-gray-600 mb-2">{behavior.description}</p>
              <div className="bg-blue-50 p-2 rounded text-xs text-blue-700">
                💡 {behavior.implications}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Personality-Based Recommendations */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Personalized Recommendations</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <h4 className="font-medium text-gray-900">Career Strengths</h4>
            <div className="space-y-3">
              <div className="p-3 bg-green-50 rounded-lg">
                <h5 className="font-medium text-green-900">Creative Roles</h5>
                <p className="text-sm text-green-700">High openness supports innovative thinking</p>
              </div>
              <div className="p-3 bg-blue-50 rounded-lg">
                <h5 className="font-medium text-blue-900">Team Collaboration</h5>
                <p className="text-sm text-blue-700">Strong agreeableness enhances teamwork</p>
              </div>
              <div className="p-3 bg-purple-50 rounded-lg">
                <h5 className="font-medium text-purple-900">Project Management</h5>
                <p className="text-sm text-purple-700">Good conscientiousness for organization</p>
              </div>
            </div>
          </div>
          
          <div className="space-y-4">
            <h4 className="font-medium text-gray-900">Personal Development</h4>
            <div className="space-y-3">
              <div className="p-3 bg-yellow-50 rounded-lg">
                <h5 className="font-medium text-yellow-900">Stress Management</h5>
                <p className="text-sm text-yellow-700">Regular mindfulness and relaxation</p>
              </div>
              <div className="p-3 bg-pink-50 rounded-lg">
                <h5 className="font-medium text-pink-900">Social Activities</h5>
                <p className="text-sm text-pink-700">Engage in group activities and networking</p>
              </div>
              <div className="p-3 bg-orange-50 rounded-lg">
                <h5 className="font-medium text-orange-900">Learning Style</h5>
                <p className="text-sm text-orange-700">Interactive and experiential learning</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Relationship Insights */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Relationship Insights</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-4 bg-pink-50 rounded-lg text-center">
            <Heart className="h-8 w-8 text-pink-600 mx-auto mb-2" />
            <h4 className="font-medium text-pink-900 mb-1">Communication Style</h4>
            <p className="text-sm text-pink-700">Empathetic and cooperative</p>
          </div>
          <div className="p-4 bg-blue-50 rounded-lg text-center">
            <Users className="h-8 w-8 text-blue-600 mx-auto mb-2" />
            <h4 className="font-medium text-blue-900 mb-1">Social Preference</h4>
            <p className="text-sm text-blue-700">Enjoys both groups and one-on-one</p>
          </div>
          <div className="p-4 bg-green-50 rounded-lg text-center">
            <Smile className="h-8 w-8 text-green-600 mx-auto mb-2" />
            <h4 className="font-medium text-green-900 mb-1">Conflict Resolution</h4>
            <p className="text-sm text-green-700">Seeks harmony and compromise</p>
          </div>
        </div>
      </div>
    </div>
  )
}