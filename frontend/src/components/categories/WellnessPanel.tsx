import React, { useState, useEffect } from 'react'
import { Activity, Heart, Moon, Droplets, Thermometer, Zap, Shield } from 'lucide-react'
import { 
  getThemeClass, 
  getGlassBackground, 
  getGlassBorder, 
  getTextPrimary, 
  getTextSecondary, 
  getTagClass, 
  getProgressBarBg 
} from '../../utils/theme'

interface WellnessTrait {
  name: string;
  value: string;
  gene: string;
  confidence: string;
}

interface WellnessCategory {
  category: string;
  icon: any;
  color: string;
  bgColor: string;
  traits: WellnessTrait[];
}

interface WellnessPanelProps {
  data: any
  isDarkMode?: boolean
  token?: string
}

export default function WellnessPanel({ data, isDarkMode = false, token }: WellnessPanelProps) {
  const [wellnessData, setWellnessData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchWellnessData = async () => {
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
          setWellnessData(dashboardData);
        }
      } catch (error) {
        console.error('Error fetching wellness data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchWellnessData();
  }, [token]);

  const glassBackground = getGlassBackground(isDarkMode);
  const glassBorder = getGlassBorder(isDarkMode);
  const textPrimary = getTextPrimary(isDarkMode);
  const textSecondary = getTextSecondary(isDarkMode);
  const tagClass = getTagClass(isDarkMode);
  const progressBarBg = getProgressBarBg(isDarkMode);

  const getWellnessTraits = (): WellnessCategory[] => {
    // Try to get real data first
    if (wellnessData?.wellness_traits && wellnessData.wellness_traits.length > 0) {
      // Group wellness traits by category
      const grouped = wellnessData.wellness_traits.reduce((acc: any, trait: any) => {
        const category = trait.category || 'General Wellness';
        if (!acc[category]) {
          acc[category] = [];
        }
        acc[category].push({
          name: trait.trait || trait.name || 'Unknown Trait',
          value: trait.value || trait.result || 'Normal',
          gene: trait.gene || trait.marker || 'Multiple genes',
          confidence: trait.confidence || 'Medium'
        });
        return acc;
      }, {});

      // Convert to expected format
      return Object.keys(grouped).map(categoryName => ({
        category: categoryName,
        icon: getCategoryIcon(categoryName),
        color: getCategoryColor(categoryName),
        bgColor: getCategoryBgColor(categoryName),
        traits: grouped[categoryName]
      }));
    }

    // Fallback data if no real data available
    return [
      {
        category: 'Sleep & Circadian Rhythm',
        icon: Moon,
        color: 'text-purple-500',
        bgColor: 'bg-purple-500/10',
        traits: [
          { name: 'Deep Sleep', value: 'Typical', gene: 'DEC2', confidence: 'High' },
          { name: 'Morning Person', value: 'Yes', gene: 'PER2', confidence: 'High' },
          { name: 'Sleep Duration Need', value: '7-8 hours', gene: 'CLOCK', confidence: 'Medium' }
        ]
      },
      {
        category: 'Cardiovascular Health',
        icon: Heart,
        color: 'text-red-500',
        bgColor: 'bg-red-500/10',
        traits: [
          { name: 'HDL Cholesterol Response', value: 'Good Response', gene: 'CETP', confidence: 'High' },
          { name: 'Blood Pressure', value: 'Normal Tendency', gene: 'ACE', confidence: 'Medium' },
          { name: 'Heart Rate Recovery', value: 'Fast', gene: 'ADRB1', confidence: 'High' }
        ]
      },
      {
        category: 'Inflammation & Immunity',
        icon: Shield,
        color: 'text-green-500',
        bgColor: 'bg-green-500/10',
        traits: [
          { name: 'C-Reactive Protein', value: 'Low Levels', gene: 'CRP', confidence: 'High' },
          { name: 'Immune Response', value: 'Strong', gene: 'HLA-B', confidence: 'Medium' },
          { name: 'Inflammatory Response', value: 'Moderate', gene: 'TNF-α', confidence: 'High' }
        ]
      },
      {
        category: 'Metabolic Health',
        icon: Zap,
        color: 'text-yellow-500',
        bgColor: 'bg-yellow-500/10',
        traits: [
          { name: 'Insulin Sensitivity', value: 'High', gene: 'TCF7L2', confidence: 'High' },
          { name: 'Metabolic Rate', value: 'Fast', gene: 'UCP1', confidence: 'Medium' },
          { name: 'Blood Sugar Response', value: 'Normal', gene: 'PPARG', confidence: 'High' }
        ]
      },
      {
        category: 'Hydration & Electrolytes',
        icon: Droplets,
        color: 'text-blue-500',
        bgColor: 'bg-blue-500/10',
        traits: [
          { name: 'Sodium Sensitivity', value: 'Low', gene: 'ACE', confidence: 'Medium' },
          { name: 'Hydration Needs', value: 'Standard', gene: 'AQP2', confidence: 'Low' },
          { name: 'Electrolyte Balance', value: 'Good', gene: 'SCNN1A', confidence: 'Medium' }
        ]
      },
      {
        category: 'Stress Response',
        icon: Activity,
        color: 'text-orange-500',
        bgColor: 'bg-orange-500/10',
        traits: [
          { name: 'Cortisol Response', value: 'Normal', gene: 'FKBP5', confidence: 'High' },
          { name: 'Stress Resilience', value: 'High', gene: 'COMT', confidence: 'High' },
          { name: 'Recovery Time', value: 'Fast', gene: 'BDNF', confidence: 'Medium' }
        ]
      }
    ];
  };

  const getCategoryIcon = (categoryName: string) => {
    const name = categoryName.toLowerCase();
    if (name.includes('sleep') || name.includes('circadian')) return Moon;
    if (name.includes('cardio') || name.includes('heart')) return Heart;
    if (name.includes('inflam') || name.includes('immun')) return Shield;
    if (name.includes('metabol') || name.includes('energy')) return Zap;
    if (name.includes('hydrat') || name.includes('electrolyte')) return Droplets;
    if (name.includes('stress') || name.includes('recovery')) return Activity;
    if (name.includes('temperature') || name.includes('thermal')) return Thermometer;
    return Activity;
  };

  const getCategoryColor = (categoryName: string) => {
    const name = categoryName.toLowerCase();
    if (name.includes('sleep') || name.includes('circadian')) return 'text-purple-500';
    if (name.includes('cardio') || name.includes('heart')) return 'text-red-500';
    if (name.includes('inflam') || name.includes('immun')) return 'text-green-500';
    if (name.includes('metabol') || name.includes('energy')) return 'text-yellow-500';
    if (name.includes('hydrat') || name.includes('electrolyte')) return 'text-blue-500';
    if (name.includes('stress') || name.includes('recovery')) return 'text-orange-500';
    return 'text-gray-500';
  };

  const getCategoryBgColor = (categoryName: string) => {
    const name = categoryName.toLowerCase();
    if (name.includes('sleep') || name.includes('circadian')) return 'bg-purple-500/10';
    if (name.includes('cardio') || name.includes('heart')) return 'bg-red-500/10';
    if (name.includes('inflam') || name.includes('immun')) return 'bg-green-500/10';
    if (name.includes('metabol') || name.includes('energy')) return 'bg-yellow-500/10';
    if (name.includes('hydrat') || name.includes('electrolyte')) return 'bg-blue-500/10';
    if (name.includes('stress') || name.includes('recovery')) return 'bg-orange-500/10';
    return 'bg-gray-500/10';
  };

  const wellnessTraits = getWellnessTraits();

  const overallScore = 78
  const improvementAreas = [
    'Consider magnesium supplementation for better sleep quality',
    'Omega-3 fatty acids may help optimize inflammation response',
    'Regular exercise timing can enhance your natural circadian rhythm'
  ]

  const getConfidenceColor = (confidence: string) => {
    switch (confidence.toLowerCase()) {
      case 'high': return 'text-green-500 bg-green-500/10 border-green-500/20'
      case 'medium': return 'text-yellow-500 bg-yellow-500/10 border-yellow-500/20'
      case 'low': return 'text-gray-500 bg-gray-500/10 border-gray-500/20'
      default: return 'text-gray-500 bg-gray-500/10 border-gray-500/20'
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className={`text-2xl font-bold ${textPrimary} mb-2`}>
            Wellness Reports
          </h2>
          <p className={textSecondary}>
            Personalized insights for optimal health and wellbeing
          </p>
        </div>
        <div className={`${glassBackground} border ${glassBorder} rounded-xl p-4`}>
          <div className="flex items-center space-x-3">
            <Activity className={`h-8 w-8 ${getThemeClass('text-green-500', isDarkMode)}`} />
            <div>
              <div className={`text-2xl font-bold ${textPrimary}`}>
                {overallScore}
              </div>
              <div className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>
                Wellness Score
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Overall Wellness Score */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>
          Overall Wellness Assessment
        </h3>
        <div className="flex items-center space-x-4 mb-4">
          <div className="flex-1">
            <div className="flex justify-between items-center mb-2">
              <span className={`text-sm ${textSecondary}`}>Wellness Score</span>
              <span className={`text-lg font-bold ${textPrimary}`}>{overallScore}/100</span>
            </div>
            <div className="w-full bg-gray-700/30 rounded-full h-3">
              <div 
                className="bg-gradient-to-r from-green-500 to-blue-500 h-3 rounded-full transition-all duration-1000"
                style={{ width: `${overallScore}%` }}
              />
            </div>
          </div>
        </div>
        <div className="grid md:grid-cols-3 gap-4">
          <div className="text-center">
            <div className={`text-xl font-bold ${getThemeClass('text-green-500', isDarkMode)} mb-1`}>
              12
            </div>
            <div className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>
              Optimal Traits
            </div>
          </div>
          <div className="text-center">
            <div className={`text-xl font-bold ${getThemeClass('text-yellow-500', isDarkMode)} mb-1`}>
              6
            </div>
            <div className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>
              Moderate Traits
            </div>
          </div>
          <div className="text-center">
            <div className={`text-xl font-bold ${getThemeClass('text-red-500', isDarkMode)} mb-1`}>
              0
            </div>
            <div className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>
              Risk Traits
            </div>
          </div>
        </div>
      </div>

      {/* Wellness Categories */}
      <div className="grid gap-6">
        {wellnessTraits.map((category: WellnessCategory, categoryIndex: number) => {
          const Icon = category.icon
          return (
            <div key={categoryIndex} className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
              <div className="flex items-center space-x-3 mb-4">
                <div className={`p-2 ${category.bgColor} rounded-lg`}>
                  <Icon className={`h-5 w-5 ${category.color}`} />
                </div>
                <h3 className={`text-lg font-semibold ${textPrimary}`}>
                  {category.category}
                </h3>
              </div>
              
              <div className="grid gap-3">
                {category.traits.map((trait: WellnessTrait, traitIndex: number) => (
                  <div key={traitIndex} className="flex items-center justify-between p-3 bg-black/10 rounded-lg">
                    <div>
                      <h4 className={`text-sm font-medium ${textPrimary} mb-1`}>
                        {trait.name}
                      </h4>
                      <p className={`text-xs ${getThemeClass("text-gray-500", isDarkMode)}`}>
                        Gene: {trait.gene}
                      </p>
                    </div>
                    <div className="text-right">
                      <div className={`text-sm font-semibold ${textPrimary} mb-1`}>
                        {trait.value}
                      </div>
                      <div className={`px-2 py-1 rounded-full text-xs border ${getConfidenceColor(trait.confidence)}`}>
                        {trait.confidence}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>

      {/* Personalized Recommendations */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6 border border-green-500/20 bg-green-500/5`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>
          Personalized Recommendations
        </h3>
        <div className="space-y-3">
          {improvementAreas.map((recommendation: string, index: number) => (
            <div key={index} className="flex items-start space-x-3">
              <div className="w-2 h-2 bg-green-500 rounded-full mt-2 flex-shrink-0" />
              <p className={`text-sm ${textSecondary}`}>
                {recommendation}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}