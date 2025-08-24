import React from 'react'
import { Globe, MapPin, Users, Clock, Dna } from 'lucide-react'
import { 
  getThemeClass, 
  getGlassBackground, 
  getGlassBorder, 
  getTextPrimary, 
  getTextSecondary, 
  getTagClass, 
  getProgressBarBg 
} from '../../utils/theme'

interface AncestryPanelProps {
  data: any
  isDarkMode?: boolean
}

export default function AncestryPanel({ data, isDarkMode = false }: AncestryPanelProps) {
  const glassBackground = getGlassBackground(isDarkMode);
  const glassBorder = getGlassBorder(isDarkMode);
  const textPrimary = getTextPrimary(isDarkMode);
  const textSecondary = getTextSecondary(isDarkMode);
  const tagClass = getTagClass(isDarkMode);
  const progressBarBg = getProgressBarBg(isDarkMode);

  const ancestryComposition = [
    { region: 'Northern European', percentage: 45.2, color: 'bg-blue-500' },
    { region: 'Southern European', percentage: 23.8, color: 'bg-green-500' },
    { region: 'Eastern European', percentage: 18.5, color: 'bg-purple-500' },
    { region: 'Scandinavian', percentage: 8.7, color: 'bg-yellow-500' },
    { region: 'Broadly European', percentage: 3.8, color: 'bg-gray-500' }
  ]

  const maternalHaplogroup = {
    haplogroup: 'H1a1a',
    origin: 'Western Europe',
    frequency: '6.2% of Europeans',
    age: '~15,000 years ago',
    description: 'Common in Western European populations, particularly in the Atlantic coast regions'
  }

  const paternalHaplogroup = {
    haplogroup: 'R1b-M269',
    origin: 'Western Europe',
    frequency: '60% of Western Europeans',
    age: '~5,000 years ago',
    description: 'The most common paternal lineage in Western Europe, associated with Celtic and Germanic migrations'
  }

  const neanderthalVariants = {
    percentage: 2.1,
    variants: 287,
    moreOrLess: 'more',
    comparison: 'than 68% of users'
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className={`text-2xl font-bold ${textPrimary} mb-2`}>
            Ancestry & Origins
          </h2>
          <p className={textSecondary}>
            Discover your genetic heritage and ancestral journey
          </p>
        </div>
        <div className={`${glassBackground} border ${glassBorder} rounded-xl p-4`}>
          <div className="flex items-center space-x-3">
            <Globe className={`h-8 w-8 ${getThemeClass('text-blue-500', isDarkMode)}`} />
            <div>
              <div className={`text-2xl font-bold ${textPrimary}`}>
                {ancestryComposition.length}
              </div>
              <div className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>
                Regions
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Ancestry Composition */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>
          Ancestry Composition
        </h3>
        <div className="space-y-4">
          {ancestryComposition.map((region, index) => (
            <div key={index} className="space-y-2">
              <div className="flex justify-between items-center">
                <span className={`text-sm font-medium ${textPrimary}`}>
                  {region.region}
                </span>
                <span className={`text-sm font-bold ${textPrimary}`}>
                  {region.percentage}%
                </span>
              </div>
              <div className={`w-full ${progressBarBg} rounded-full h-2`}>
                <div 
                  className={`${region.color} h-2 rounded-full transition-all duration-1000`}
                  style={{ width: `${region.percentage}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Haplogroups */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Maternal Haplogroup */}
        <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
          <div className="flex items-center space-x-3 mb-4">
            <div className="p-2 bg-pink-500/20 rounded-lg">
              <Dna className={`h-5 w-5 ${getThemeClass('text-pink-500', isDarkMode)}`} />
            </div>
            <h3 className={`text-lg font-semibold ${textPrimary}`}>
              Maternal Haplogroup
            </h3>
          </div>
          <div className="space-y-3">
            <div>
              <span className={`text-2xl font-bold ${textPrimary}`}>
                {maternalHaplogroup.haplogroup}
              </span>
            </div>
            <div className="space-y-2">
              <div className="flex items-center space-x-2">
                <MapPin className="h-4 w-4 text-gray-400" />
                <span className={`text-sm ${textSecondary}`}>
                  Origin: {maternalHaplogroup.origin}
                </span>
              </div>
              <div className="flex items-center space-x-2">
                <Users className="h-4 w-4 text-gray-400" />
                <span className={`text-sm ${textSecondary}`}>
                  Frequency: {maternalHaplogroup.frequency}
                </span>
              </div>
              <div className="flex items-center space-x-2">
                <Clock className="h-4 w-4 text-gray-400" />
                <span className={`text-sm ${textSecondary}`}>
                  Age: {maternalHaplogroup.age}
                </span>
              </div>
            </div>
            <p className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)} leading-relaxed`}>
              {maternalHaplogroup.description}
            </p>
          </div>
        </div>

        {/* Paternal Haplogroup */}
        <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
          <div className="flex items-center space-x-3 mb-4">
            <div className="p-2 bg-blue-500/20 rounded-lg">
              <Dna className={`h-5 w-5 ${getThemeClass('text-blue-500', isDarkMode)}`} />
            </div>
            <h3 className={`text-lg font-semibold ${textPrimary}`}>
              Paternal Haplogroup
            </h3>
          </div>
          <div className="space-y-3">
            <div>
              <span className={`text-2xl font-bold ${textPrimary}`}>
                {paternalHaplogroup.haplogroup}
              </span>
            </div>
            <div className="space-y-2">
              <div className="flex items-center space-x-2">
                <MapPin className="h-4 w-4 text-gray-400" />
                <span className={`text-sm ${textSecondary}`}>
                  Origin: {paternalHaplogroup.origin}
                </span>
              </div>
              <div className="flex items-center space-x-2">
                <Users className="h-4 w-4 text-gray-400" />
                <span className={`text-sm ${textSecondary}`}>
                  Frequency: {paternalHaplogroup.frequency}
                </span>
              </div>
              <div className="flex items-center space-x-2">
                <Clock className="h-4 w-4 text-gray-400" />
                <span className={`text-sm ${textSecondary}`}>
                  Age: {paternalHaplogroup.age}
                </span>
              </div>
            </div>
            <p className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)} leading-relaxed`}>
              {paternalHaplogroup.description}
            </p>
          </div>
        </div>
      </div>

      {/* Neanderthal Ancestry */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>
          Neanderthal Ancestry
        </h3>
        <div className="grid md:grid-cols-3 gap-6">
          <div className="text-center">
            <div className={`text-3xl font-bold ${textPrimary} mb-2`}>
              {neanderthalVariants.percentage}%
            </div>
            <div className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>
              Neanderthal DNA
            </div>
          </div>
          <div className="text-center">
            <div className={`text-3xl font-bold ${textPrimary} mb-2`}>
              {neanderthalVariants.variants}
            </div>
            <div className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>
              Variants
            </div>
          </div>
          <div className="text-center">
            <div className={`text-sm ${textSecondary} mb-2`}>
              You have {neanderthalVariants.moreOrLess} Neanderthal DNA
            </div>
            <div className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>
              {neanderthalVariants.comparison}
            </div>
          </div>
        </div>
        <div className={`mt-4 p-4 bg-amber-500/10 border border-amber-500/20 rounded-lg`}>
          <p className={`text-sm ${textSecondary} leading-relaxed`}>
            Neanderthals were ancient human relatives who lived in Europe and Asia. 
            Modern humans of non-African descent typically have 1-4% Neanderthal DNA.
          </p>
        </div>
      </div>
    </div>
  )
}