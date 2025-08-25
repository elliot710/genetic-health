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

  // Check if ancestry data is available from the database
  const hasRealData = data?.ancestry_results && data.ancestry_results.length > 0
  const ancestryData = hasRealData ? data.ancestry_results[0] : null

  // If no real data is available, show message
  if (!hasRealData) {
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
                  0
                </div>
                <div className={`text-sm ${getThemeClass("text-gray-500", isDarkMode)}`}>
                  Regions
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* No Data Available */}
        <div className={`${glassBackground} border ${glassBorder} rounded-xl p-8 text-center`}>
          <div className="flex flex-col items-center space-y-4">
            <div className="p-4 bg-gradient-to-br from-blue-500/20 to-purple-500/20 backdrop-blur-xl rounded-xl border border-blue-500/30">
              <Globe className="h-8 w-8 text-blue-400" />
            </div>
            <div>
              <h3 className={`text-xl font-bold ${textPrimary} mb-2`}>
                Ancestry Analysis in Progress
              </h3>
              <p className={`${textSecondary} max-w-md mx-auto`}>
                Ancestry composition analysis is not yet available for your genetic data. 
                This analysis requires specific ancestry-informative markers that may be added in future updates.
              </p>
            </div>
          </div>
        </div>

        {/* Information Panel */}
        <div className={`${glassBackground} border ${glassBorder} rounded-xl p-8`}>
          <h3 className={`text-xl font-bold ${textPrimary} mb-6`}>
            About Ancestry Analysis
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 className={`text-lg font-semibold ${textPrimary} mb-4`}>Ancestry Composition</h4>
              <p className={`${textSecondary} leading-relaxed`}>
                Ancestry composition analysis compares your DNA to reference populations 
                from around the world to estimate your genetic heritage from different 
                geographic regions and ethnic groups.
              </p>
            </div>
            <div>
              <h4 className={`text-lg font-semibold ${textPrimary} mb-4`}>Haplogroups</h4>
              <p className={`${textSecondary} leading-relaxed`}>
                Maternal and paternal haplogroups trace your direct maternal and paternal 
                lineages back thousands of years, revealing ancient migration patterns 
                and ancestral origins.
              </p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Use real ancestry data when available
  const ancestryComposition = ancestryData?.composition || []
  const maternalHaplogroup = ancestryData?.maternal_haplogroup || null
  const paternalHaplogroup = ancestryData?.paternal_haplogroup || null
  const neanderthalVariants = ancestryData?.neanderthal_variants || null

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
          {ancestryComposition.map((region: any, index: number) => (
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
                {maternalHaplogroup?.haplogroup || 'Not Available'}
              </span>
            </div>
            {maternalHaplogroup && (
              <>
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
              </>
            )}
            {!maternalHaplogroup && (
              <p className={`text-sm ${textSecondary}`}>
                Maternal haplogroup analysis not yet available
              </p>
            )}
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
                {paternalHaplogroup?.haplogroup || 'Not Available'}
              </span>
            </div>
            {paternalHaplogroup && (
              <>
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
              </>
            )}
            {!paternalHaplogroup && (
              <p className={`text-sm ${textSecondary}`}>
                Paternal haplogroup analysis not yet available
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Neanderthal Ancestry */}
      <div className={`${glassBackground} border ${glassBorder} rounded-xl p-6`}>
        <h3 className={`text-lg font-semibold ${textPrimary} mb-4`}>
          Neanderthal Ancestry
        </h3>
        {neanderthalVariants ? (
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
        ) : (
          <div className="text-center py-8">
            <p className={`${textSecondary}`}>
              Neanderthal ancestry analysis not yet available
            </p>
          </div>
        )}
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