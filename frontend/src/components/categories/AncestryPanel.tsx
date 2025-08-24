import React from 'react'
import { Globe, MapPin, Users, Clock, Dna } from 'lucide-react'

interface AncestryPanelProps {
  data: any
  isDarkMode?: boolean
}

export default function AncestryPanel({ data, isDarkMode = false }: AncestryPanelProps) {
  const theme = {
    glass: isDarkMode 
      ? 'bg-black/20 backdrop-blur-xl border-white/10' 
      : 'bg-white/30 backdrop-blur-xl border-white/30',
    text: {
      primary: isDarkMode ? 'text-white' : 'text-gray-900',
      secondary: isDarkMode ? 'text-gray-300' : 'text-gray-700',
      muted: isDarkMode ? 'text-gray-400' : 'text-gray-500',
    }
  }

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
          <h2 className={`text-2xl font-bold ${theme.text.primary} mb-2`}>
            Ancestry & Origins
          </h2>
          <p className={theme.text.secondary}>
            Discover your genetic heritage and ancestral journey
          </p>
        </div>
        <div className={`${theme.glass} rounded-xl p-4`}>
          <div className="flex items-center space-x-3">
            <Globe className="h-8 w-8 text-blue-500" />
            <div>
              <div className={`text-2xl font-bold ${theme.text.primary}`}>
                {ancestryComposition.length}
              </div>
              <div className={`text-sm ${theme.text.muted}`}>
                Regions
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Ancestry Composition */}
      <div className={`${theme.glass} rounded-xl p-6 border border-white/10`}>
        <h3 className={`text-lg font-semibold ${theme.text.primary} mb-4`}>
          Ancestry Composition
        </h3>
        <div className="space-y-4">
          {ancestryComposition.map((region, index) => (
            <div key={index} className="space-y-2">
              <div className="flex justify-between items-center">
                <span className={`text-sm font-medium ${theme.text.primary}`}>
                  {region.region}
                </span>
                <span className={`text-sm font-bold ${theme.text.primary}`}>
                  {region.percentage}%
                </span>
              </div>
              <div className="w-full bg-gray-700/30 rounded-full h-2">
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
        <div className={`${theme.glass} rounded-xl p-6 border border-white/10`}>
          <div className="flex items-center space-x-3 mb-4">
            <div className="p-2 bg-pink-500/20 rounded-lg">
              <Dna className="h-5 w-5 text-pink-500" />
            </div>
            <h3 className={`text-lg font-semibold ${theme.text.primary}`}>
              Maternal Haplogroup
            </h3>
          </div>
          <div className="space-y-3">
            <div>
              <span className={`text-2xl font-bold ${theme.text.primary}`}>
                {maternalHaplogroup.haplogroup}
              </span>
            </div>
            <div className="space-y-2">
              <div className="flex items-center space-x-2">
                <MapPin className="h-4 w-4 text-gray-400" />
                <span className={`text-sm ${theme.text.secondary}`}>
                  Origin: {maternalHaplogroup.origin}
                </span>
              </div>
              <div className="flex items-center space-x-2">
                <Users className="h-4 w-4 text-gray-400" />
                <span className={`text-sm ${theme.text.secondary}`}>
                  Frequency: {maternalHaplogroup.frequency}
                </span>
              </div>
              <div className="flex items-center space-x-2">
                <Clock className="h-4 w-4 text-gray-400" />
                <span className={`text-sm ${theme.text.secondary}`}>
                  Age: {maternalHaplogroup.age}
                </span>
              </div>
            </div>
            <p className={`text-sm ${theme.text.muted} leading-relaxed`}>
              {maternalHaplogroup.description}
            </p>
          </div>
        </div>

        {/* Paternal Haplogroup */}
        <div className={`${theme.glass} rounded-xl p-6 border border-white/10`}>
          <div className="flex items-center space-x-3 mb-4">
            <div className="p-2 bg-blue-500/20 rounded-lg">
              <Dna className="h-5 w-5 text-blue-500" />
            </div>
            <h3 className={`text-lg font-semibold ${theme.text.primary}`}>
              Paternal Haplogroup
            </h3>
          </div>
          <div className="space-y-3">
            <div>
              <span className={`text-2xl font-bold ${theme.text.primary}`}>
                {paternalHaplogroup.haplogroup}
              </span>
            </div>
            <div className="space-y-2">
              <div className="flex items-center space-x-2">
                <MapPin className="h-4 w-4 text-gray-400" />
                <span className={`text-sm ${theme.text.secondary}`}>
                  Origin: {paternalHaplogroup.origin}
                </span>
              </div>
              <div className="flex items-center space-x-2">
                <Users className="h-4 w-4 text-gray-400" />
                <span className={`text-sm ${theme.text.secondary}`}>
                  Frequency: {paternalHaplogroup.frequency}
                </span>
              </div>
              <div className="flex items-center space-x-2">
                <Clock className="h-4 w-4 text-gray-400" />
                <span className={`text-sm ${theme.text.secondary}`}>
                  Age: {paternalHaplogroup.age}
                </span>
              </div>
            </div>
            <p className={`text-sm ${theme.text.muted} leading-relaxed`}>
              {paternalHaplogroup.description}
            </p>
          </div>
        </div>
      </div>

      {/* Neanderthal Ancestry */}
      <div className={`${theme.glass} rounded-xl p-6 border border-white/10`}>
        <h3 className={`text-lg font-semibold ${theme.text.primary} mb-4`}>
          Neanderthal Ancestry
        </h3>
        <div className="grid md:grid-cols-3 gap-6">
          <div className="text-center">
            <div className={`text-3xl font-bold ${theme.text.primary} mb-2`}>
              {neanderthalVariants.percentage}%
            </div>
            <div className={`text-sm ${theme.text.muted}`}>
              Neanderthal DNA
            </div>
          </div>
          <div className="text-center">
            <div className={`text-3xl font-bold ${theme.text.primary} mb-2`}>
              {neanderthalVariants.variants}
            </div>
            <div className={`text-sm ${theme.text.muted}`}>
              Variants
            </div>
          </div>
          <div className="text-center">
            <div className={`text-sm ${theme.text.secondary} mb-2`}>
              You have {neanderthalVariants.moreOrLess} Neanderthal DNA
            </div>
            <div className={`text-sm ${theme.text.muted}`}>
              {neanderthalVariants.comparison}
            </div>
          </div>
        </div>
        <div className={`mt-4 p-4 bg-amber-500/10 border border-amber-500/20 rounded-lg`}>
          <p className={`text-sm ${theme.text.secondary} leading-relaxed`}>
            Neanderthals were ancient human relatives who lived in Europe and Asia. 
            Modern humans of non-African descent typically have 1-4% Neanderthal DNA.
          </p>
        </div>
      </div>
    </div>
  )
}