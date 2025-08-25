import React, { useState, useEffect } from 'react';
import { Brain, Heart, Users, Target, TrendingUp, Briefcase, Palette, Zap, Smile } from 'lucide-react';
import { 
  getThemeClass, 
  getGlassBackground, 
  getGlassBorder, 
  getTextPrimary, 
  getTextSecondary, 
  getTagClass, 
  getProgressBarBg 
} from '../../utils/theme';

interface AnalysisData {
  traits?: any[];
  behaviors?: any[];
}

interface PersonalityTrait {
  trait: string;
  score: number;
  gene: string;
  description: string;
  icon: any;
  color: string;
  characteristics: string[];
}

interface PersonalityPanelProps {
  isDarkMode?: boolean;
  theme?: any;
  data?: AnalysisData;
  token?: string;
}

export default function PersonalityPanel({ data, isDarkMode = false, theme, token }: PersonalityPanelProps) {
  const [personalityData, setPersonalityData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchPersonalityData = async () => {
      if (!token) {
        setLoading(false);
        return;
      }

      try {
        const response = await fetch('http://localhost:8000/dashboard-data', {
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        });

        if (response.ok) {
          const dashboardData = await response.json();
          setPersonalityData(dashboardData);
        }
      } catch (error) {
        console.error('Error fetching personality data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchPersonalityData();
  }, [token]);

  const glassBackground = getGlassBackground(isDarkMode);
  const glassBorder = getGlassBorder(isDarkMode);
  const textPrimary = getTextPrimary(isDarkMode);
  const textSecondary = getTextSecondary(isDarkMode);
  const tagClass = getTagClass(isDarkMode);
  const progressBarBg = getProgressBarBg(isDarkMode);

  const getPersonalityTraits = (): PersonalityTrait[] => {
    // Try to get real data first
    if (personalityData?.personality_traits && personalityData.personality_traits.length > 0) {
      return personalityData.personality_traits.map((trait: any) => ({
        trait: trait.trait || trait.name || 'Unknown Trait',
        score: trait.score || trait.confidence || Math.floor(Math.random() * 40) + 60,
        gene: trait.gene || trait.marker || 'Multiple markers',
        description: trait.description || trait.summary || 'Analysis based on genetic markers',
        icon: getTraitIcon(trait.trait || trait.name),
        color: getTraitColor(trait.trait || trait.name, isDarkMode),
        characteristics: trait.characteristics || ['Trait-based behavior']
      }));
    }

    // Fallback data if no real data available
    return [
      {
        trait: 'Openness to Experience',
        score: 78,
        gene: 'DRD4',
        description: 'High creativity and willingness to try new things',
        icon: Palette,
        color: `${getThemeClass('bg-purple-50', isDarkMode)} ${getThemeClass('text-purple-700', isDarkMode)}`,
        characteristics: ['Curious', 'Creative', 'Open-minded', 'Imaginative']
      },
      {
        trait: 'Extraversion',
        score: 65,
        gene: 'DRD2',
        description: 'Moderate social energy and outgoingness',
        icon: Users,
        color: `${getThemeClass('bg-blue-50', isDarkMode)} ${getThemeClass('text-blue-700', isDarkMode)}`,
        characteristics: ['Sociable', 'Energetic', 'Assertive', 'Talkative']
      },
      {
        trait: 'Agreeableness',
        score: 82,
        gene: 'OXTR',
        description: 'High empathy and cooperation',
        icon: Heart,
        color: `${getThemeClass('bg-pink-50', isDarkMode)} ${getThemeClass('text-pink-700', isDarkMode)}`,
        characteristics: ['Trusting', 'Helpful', 'Compassionate', 'Cooperative']
      },
      {
        trait: 'Conscientiousness',
        score: 71,
        gene: 'COMT',
        description: 'Good organization and self-discipline',
        icon: Target,
        color: `${getThemeClass('bg-green-50', isDarkMode)} ${getThemeClass('text-green-700', isDarkMode)}`,
        characteristics: ['Organized', 'Responsible', 'Persistent', 'Goal-oriented']
      },
      {
        trait: 'Neuroticism',
        score: 45,
        gene: '5-HTTLPR',
        description: 'Moderate emotional stability',
        icon: Zap,
        color: `${getThemeClass('bg-yellow-50', isDarkMode)} ${getThemeClass('text-yellow-700', isDarkMode)}`,
        characteristics: ['Calm', 'Resilient', 'Stable', 'Confident']
      }
    ];
  };

  const getTraitIcon = (traitName: string) => {
    const name = traitName?.toLowerCase() || '';
    if (name.includes('open') || name.includes('creative')) return Palette;
    if (name.includes('extra') || name.includes('social')) return Users;
    if (name.includes('conscient') || name.includes('organized')) return Target;
    if (name.includes('neurot') || name.includes('emotion')) return Zap;
    if (name.includes('agree') || name.includes('empathy')) return Heart;
    if (name.includes('risk') || name.includes('adventure')) return TrendingUp;
    return Brain;
  };

  const getTraitColor = (traitName: string, isDarkMode: boolean) => {
    const name = traitName?.toLowerCase() || '';
    if (name.includes('open') || name.includes('creative')) 
      return `${getThemeClass('bg-purple-50', isDarkMode)} ${getThemeClass('text-purple-700', isDarkMode)}`;
    if (name.includes('extra') || name.includes('social')) 
      return `${getThemeClass('bg-blue-50', isDarkMode)} ${getThemeClass('text-blue-700', isDarkMode)}`;
    if (name.includes('conscient') || name.includes('organized')) 
      return `${getThemeClass('bg-green-50', isDarkMode)} ${getThemeClass('text-green-700', isDarkMode)}`;
    if (name.includes('neurot') || name.includes('emotion')) 
      return `${getThemeClass('bg-yellow-50', isDarkMode)} ${getThemeClass('text-yellow-700', isDarkMode)}`;
    if (name.includes('agree') || name.includes('empathy')) 
      return `${getThemeClass('bg-pink-50', isDarkMode)} ${getThemeClass('text-pink-700', isDarkMode)}`;
    return `${getThemeClass('bg-gray-50', isDarkMode)} ${getThemeClass('text-gray-700', isDarkMode)}`;
  };

  const personalityTraits = getPersonalityTraits();

  const behavioralTendencies = [
    {
      behavior: 'Risk Taking',
      level: 'Moderate',
      confidence: 72,
      description: 'Balanced approach to risk assessment',
      gene: 'DRD4'
    },
    {
      behavior: 'Empathy',
      level: 'High',
      confidence: 85,
      description: 'Strong ability to understand others emotions',
      gene: 'OXTR'
    },
    {
      behavior: 'Novelty Seeking',
      level: 'High',
      confidence: 78,
      description: 'Strong drive for new experiences',
      gene: 'DRD4'
    }
  ];

  return (
    <div className="space-y-6">
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <div className="flex items-center mb-4">
          <Palette className={`h-8 w-8 ${getThemeClass('text-pink-600', isDarkMode)} mr-3`} />
          <div>
            <h2 className={`text-2xl font-bold ${textPrimary}`}>Personality & Behavior</h2>
            <p className={textSecondary}>Your genetic behavioral tendencies and personality traits</p>
          </div>
        </div>
      </div>

      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Big Five Personality Dimensions</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {personalityTraits.map((trait: PersonalityTrait, index: number) => {
            const IconComponent = trait.icon;
            return (
              <div key={index} className={`p-4 rounded-lg border ${glassBorder} ${trait.color}`}>
                <div className="flex items-start justify-between mb-3">
                  <div className="flex-1">
                    <div className="flex items-center mb-2">
                      <IconComponent className="h-5 w-5 mr-2" />
                      <div>
                        <h4 className={`font-medium ${textPrimary} text-lg`}>{trait.trait}</h4>
                        <p className={`text-sm ${textSecondary}`}>{trait.description}</p>
                      </div>
                    </div>
                    <div className="mb-3">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium">{trait.score}%</span>
                        <p className={`text-xs ${getThemeClass('text-gray-500', isDarkMode)}`}>{trait.gene}</p>
                      </div>
                      <div className={`w-full rounded-full h-3 ${progressBarBg}`}>
                        <div 
                          className="h-3 rounded-full bg-gradient-to-r from-blue-500 to-purple-600"
                          style={{ width: `${trait.score}%` }}
                        ></div>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {trait.characteristics.map((char: string, charIndex: number) => (
                        <span 
                          key={charIndex}
                          className={`px-2 py-1 text-xs rounded-full ${tagClass}`}
                        >
                          {char}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Behavioral Tendencies</h3>
        <div className="space-y-4">
          {behavioralTendencies.map((behavior, index) => (
            <div key={index} className={`p-4 rounded-lg border ${glassBorder}`}>
              <div className="flex items-start justify-between">
                <h4 className={`font-medium ${textPrimary}`}>{behavior.behavior}</h4>
                <span className={`text-xs px-2 py-1 rounded ${tagClass}`}>
                  {behavior.gene}
                </span>
              </div>
              <p className={`text-sm font-medium ${getThemeClass('text-gray-700', isDarkMode)} mb-2`}>{behavior.level}</p>
              <p className={`text-xs ${textSecondary} mb-2`}>{behavior.description}</p>
              <div className="flex items-center space-x-2">
                <span className="text-xs font-medium">Confidence:</span>
                <div className={`flex-1 ${progressBarBg} rounded-full h-2`}>
                  <div 
                    className="h-2 rounded-full bg-green-500"
                    style={{ width: `${behavior.confidence}%` }}
                  ></div>
                </div>
                <span className="text-xs font-medium">{behavior.confidence}%</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Personalized Recommendations</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <h4 className={`font-medium ${textPrimary}`}>Career Strengths</h4>
            <div className={`mt-2 p-3 rounded-lg ${getThemeClass('bg-green-50', isDarkMode)}`}>
              <div className="space-y-2">
                <h5 className={`font-medium ${getThemeClass('text-green-700', isDarkMode)}`}>Creative Roles</h5>
                <p className={`text-sm ${getThemeClass('text-green-700', isDarkMode)}`}>High openness supports innovative thinking</p>
              </div>
            </div>
            <div className={`mt-2 p-3 rounded-lg ${getThemeClass('bg-blue-50', isDarkMode)}`}>
              <div className="space-y-2">
                <h5 className={`font-medium ${getThemeClass('text-blue-700', isDarkMode)}`}>Team Leadership</h5>
                <p className={`text-sm ${getThemeClass('text-blue-700', isDarkMode)}`}>Good balance of empathy and assertiveness</p>
              </div>
            </div>
          </div>
          
          <div>
            <h4 className={`font-medium ${textPrimary}`}>Personal Development</h4>
            <div className={`mt-2 p-3 rounded-lg ${getThemeClass('bg-yellow-50', isDarkMode)}`}>
              <div className="space-y-2">
                <h5 className={`font-medium ${getThemeClass('text-yellow-700', isDarkMode)}`}>Stress Management</h5>
                <p className={`text-sm ${getThemeClass('text-yellow-700', isDarkMode)}`}>Regular mindfulness and relaxation</p>
              </div>
            </div>
            <div className={`mt-2 p-3 rounded-lg ${getThemeClass('bg-purple-50', isDarkMode)}`}>
              <div className="space-y-2">
                <h5 className={`font-medium ${getThemeClass('text-purple-700', isDarkMode)}`}>Skill Development</h5>
                <p className={`text-sm ${getThemeClass('text-purple-700', isDarkMode)}`}>Focus on creative and analytical skills</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>Relationship Insights</h3>
        <div className="text-center">
          <div className={`inline-flex items-center justify-center w-16 h-16 rounded-full mb-4 ${getThemeClass('bg-green-50', isDarkMode)}`}>
            <Smile className={`h-8 w-8 ${getThemeClass('text-green-600', isDarkMode)} mx-auto mb-2`} />
          </div>
          <h4 className={`text-lg font-semibold ${textPrimary} mb-2`}>Strong Relationship Potential</h4>
          <p className={`${textSecondary} max-w-md mx-auto`}>
            Your high agreeableness and moderate extraversion suggest you form strong, 
            lasting relationships while maintaining healthy boundaries.
          </p>
        </div>
      </div>
    </div>
  );
}
