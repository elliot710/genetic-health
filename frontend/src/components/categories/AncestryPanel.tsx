'use client'
import React, { useMemo } from 'react'
import { Globe, MapPin, Users, Clock, Dna } from 'lucide-react'
import { Badge } from '../ui/badge'
import {
  ComposableMap,
  Geographies,
  Geography,
} from 'react-simple-maps'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  DisclaimerCard,
} from './shared'
import type { CategoryPanelProps } from './types'

const GEO_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json'

interface AncestryRegion {
  region: string
  percentage: number
  confidence?: string
  geographic_origin?: string
  color?: string
}

// Population → hex color
const REGION_COLORS: Record<string, string> = {
  european: '#3b82f6',
  african: '#f59e0b',
  'east asian': '#ef4444',
  'south asian': '#f97316',
  'admixed american': '#22c55e',
}

// ISO 3166-1 numeric → superpopulation mapping
// world-atlas@2 countries-110m.json uses numeric IDs (not ISO-A3)
const COUNTRY_TO_POP: Record<string, string> = {
  // European
  '826': 'european', // GBR
  '250': 'european', // FRA
  '276': 'european', // DEU
  '380': 'european', // ITA
  '724': 'european', // ESP
  '620': 'european', // PRT
  '528': 'european', // NLD
  '056': 'european', // BEL
  '756': 'european', // CHE
  '040': 'european', // AUT
  '616': 'european', // POL
  '203': 'european', // CZE
  '703': 'european', // SVK
  '348': 'european', // HUN
  '642': 'european', // ROU
  '100': 'european', // BGR
  '191': 'european', // HRV
  '688': 'european', // SRB
  '705': 'european', // SVN
  '070': 'european', // BIH
  '807': 'european', // MKD
  '499': 'european', // MNE
  '008': 'european', // ALB
  '300': 'european', // GRC
  '196': 'european', // CYP
  '372': 'european', // IRL
  '352': 'european', // ISL
  '578': 'european', // NOR
  '752': 'european', // SWE
  '246': 'european', // FIN
  '208': 'european', // DNK
  '233': 'european', // EST
  '428': 'european', // LVA
  '440': 'european', // LTU
  '804': 'european', // UKR
  '112': 'european', // BLR
  '498': 'european', // MDA
  '643': 'european', // RUS
  '268': 'european', // GEO
  '051': 'european', // ARM
  '031': 'european', // AZE
  '792': 'european', // TUR
  '470': 'european', // MLT
  '442': 'european', // LUX
  '398': 'european', // KAZ
  '-99': 'european', // Kosovo (used by Natural Earth)
  // African
  '566': 'african', // NGA
  '288': 'african', // GHA
  '404': 'african', // KEN
  '231': 'african', // ETH
  '834': 'african', // TZA
  '710': 'african', // ZAF
  '818': 'african', // EGY
  '504': 'african', // MAR
  '012': 'african', // DZA
  '788': 'african', // TUN
  '120': 'african', // CMR
  '686': 'african', // SEN
  '384': 'african', // CIV
  '180': 'african', // COD
  '178': 'african', // COG
  '024': 'african', // AGO
  '508': 'african', // MOZ
  '450': 'african', // MDG
  '800': 'african', // UGA
  '466': 'african', // MLI
  '854': 'african', // BFA
  '562': 'african', // NER
  '148': 'african', // TCD
  '729': 'african', // SDN
  '728': 'african', // SSD
  '706': 'african', // SOM
  '232': 'african', // ERI
  '262': 'african', // DJI
  '646': 'african', // RWA
  '108': 'african', // BDI
  '454': 'african', // MWI
  '894': 'african', // ZMB
  '716': 'african', // ZWE
  '072': 'african', // BWA
  '516': 'african', // NAM
  '266': 'african', // GAB
  '226': 'african', // GNQ
  '140': 'african', // CAF
  '204': 'african', // BEN
  '768': 'african', // TGO
  '694': 'african', // SLE
  '430': 'african', // LBR
  '324': 'african', // GIN
  '270': 'african', // GMB
  '478': 'african', // MRT
  '434': 'african', // LBY
  '748': 'african', // SWZ
  '426': 'african', // LSO
  // East Asian
  '156': 'east asian', // CHN
  '392': 'east asian', // JPN
  '410': 'east asian', // KOR
  '408': 'east asian', // PRK
  '158': 'east asian', // TWN
  '496': 'east asian', // MNG
  '704': 'east asian', // VNM
  '764': 'east asian', // THA
  '104': 'east asian', // MMR
  '418': 'east asian', // LAO
  '116': 'east asian', // KHM
  '458': 'east asian', // MYS
  '360': 'east asian', // IDN
  '608': 'east asian', // PHL
  '702': 'east asian', // SGP
  '096': 'east asian', // BRN
  '626': 'east asian', // TLS
  '598': 'east asian', // PNG
  // South Asian
  '356': 'south asian', // IND
  '586': 'south asian', // PAK
  '050': 'south asian', // BGD
  '144': 'south asian', // LKA
  '524': 'south asian', // NPL
  '064': 'south asian', // BTN
  '004': 'south asian', // AFG
  '364': 'south asian', // IRN
  '368': 'south asian', // IRQ
  '682': 'south asian', // SAU
  '887': 'south asian', // YEM
  '512': 'south asian', // OMN
  '784': 'south asian', // ARE
  '634': 'south asian', // QAT
  '048': 'south asian', // BHR
  '414': 'south asian', // KWT
  '400': 'south asian', // JOR
  '760': 'south asian', // SYR
  '422': 'south asian', // LBN
  '376': 'south asian', // ISR
  '275': 'south asian', // PSE
  '860': 'south asian', // UZB
  '795': 'south asian', // TKM
  '762': 'south asian', // TJK
  '417': 'south asian', // KGZ
  // Admixed American
  '484': 'admixed american', // MEX
  '076': 'admixed american', // BRA
  '032': 'admixed american', // ARG
  '170': 'admixed american', // COL
  '604': 'admixed american', // PER
  '862': 'admixed american', // VEN
  '152': 'admixed american', // CHL
  '218': 'admixed american', // ECU
  '068': 'admixed american', // BOL
  '600': 'admixed american', // PRY
  '858': 'admixed american', // URY
  '328': 'admixed american', // GUY
  '740': 'admixed american', // SUR
  '320': 'admixed american', // GTM
  '340': 'admixed american', // HND
  '222': 'admixed american', // SLV
  '558': 'admixed american', // NIC
  '188': 'admixed american', // CRI
  '591': 'admixed american', // PAN
  '192': 'admixed american', // CUB
  '214': 'admixed american', // DOM
  '332': 'admixed american', // HTI
  '388': 'admixed american', // JAM
  '780': 'admixed american', // TTO
  '084': 'admixed american', // BLZ
  // USA/Canada/Australia – mostly European-settled but map as neutral
  '840': 'european', // USA (for map display)
  '124': 'european', // CAN
  '036': 'european', // AUS
  '554': 'european', // NZL
}

// Projection config per dominant population for auto-zoom
const REGION_PROJECTIONS: Record<string, { center: [number, number]; scale: number }> = {
  european:           { center: [15, 52],  scale: 500 },
  african:            { center: [20, 0],   scale: 350 },
  'east asian':       { center: [110, 30], scale: 400 },
  'south asian':      { center: [70, 25],  scale: 450 },
  'admixed american': { center: [-65, -5], scale: 350 },
}

function getRegionKey(region: string): string {
  const r = region.toLowerCase()
  if (r.includes('europe')) return 'european'
  if (r.includes('africa')) return 'african'
  if (r.includes('east asia')) return 'east asian'
  if (r.includes('south asia')) return 'south asian'
  if (r.includes('america')) return 'admixed american'
  return r
}

function getRegionIcon(region: string) {
  const name = region.toLowerCase()
  if (name.includes('europe')) return '🌍'
  if (name.includes('africa')) return '🌍'
  if (name.includes('asia') || name.includes('east')) return '🌏'
  if (name.includes('america')) return '🌎'
  return '🧬'
}

function getRegionColor(region: string) {
  const name = region.toLowerCase()
  if (name.includes('europe')) return { bg: 'bg-blue-500/20', bar: 'bg-gradient-to-r from-blue-500 to-blue-400', hex: '#3b82f6' }
  if (name.includes('africa')) return { bg: 'bg-amber-500/20', bar: 'bg-gradient-to-r from-amber-500 to-amber-400', hex: '#f59e0b' }
  if (name.includes('east asia')) return { bg: 'bg-red-500/20', bar: 'bg-gradient-to-r from-red-500 to-red-400', hex: '#ef4444' }
  if (name.includes('south asia')) return { bg: 'bg-orange-500/20', bar: 'bg-gradient-to-r from-orange-500 to-orange-400', hex: '#f97316' }
  if (name.includes('america')) return { bg: 'bg-green-500/20', bar: 'bg-gradient-to-r from-green-500 to-green-400', hex: '#22c55e' }
  return { bg: 'bg-teal-500/20', bar: 'bg-gradient-to-r from-teal-500 to-teal-400', hex: '#14b8a6' }
}

function AncestryMap({ composition, isDarkMode }: { composition: AncestryRegion[]; isDarkMode: boolean }) {
  // Build {popKey → percentage} lookup
  const popPct = useMemo(() => {
    const m: Record<string, number> = {}
    for (const r of composition) {
      m[getRegionKey(r.region)] = r.percentage
    }
    return m
  }, [composition])

  // Dominant population for auto-zoom
  const dominantPop = useMemo(() => {
    let best = ''
    let bestPct = 0
    for (const [pop, pct] of Object.entries(popPct)) {
      if (pct > bestPct) { bestPct = pct; best = pop }
    }
    return best
  }, [popPct])

  const projection = REGION_PROJECTIONS[dominantPop] || { center: [15, 10] as [number, number], scale: 160 }

  // Build {numericId → fill color with opacity scaled by percentage}
  // Normalize to 3-digit zero-padded keys for consistent lookup
  const countryFills = useMemo(() => {
    const fills: Record<string, string> = {}
    for (const [numId, pop] of Object.entries(COUNTRY_TO_POP)) {
      const pct = popPct[pop] ?? 0
      if (pct < 0.5) continue
      const baseColor = REGION_COLORS[pop] || '#6b7280'
      const opacity = Math.round((0.3 + (pct / 100) * 0.6) * 100) / 100
      const color = hexToRgba(baseColor, opacity)
      // Store both padded and unpadded forms
      fills[numId] = color
      fills[numId.replace(/^0+/, '') || '0'] = color
      fills[numId.padStart(3, '0')] = color
    }
    return fills
  }, [popPct])

  const defaultFill = isDarkMode ? '#1e293b' : '#e2e8f0'
  const strokeColor = isDarkMode ? '#334155' : '#cbd5e1'

  return (
    <div className="w-full" style={{ aspectRatio: '2/1' }}>
      <ComposableMap
        projection="geoMercator"
        projectionConfig={{ scale: projection.scale, center: projection.center }}
        style={{ width: '100%', height: '100%' }}
      >
        <Geographies geography={GEO_URL}>
          {({ geographies }) =>
            geographies.map((geo) => {
              const numId = geo.id || ''
              const fill = countryFills[numId] || defaultFill
              return (
                <Geography
                  key={geo.rsmKey}
                  geography={geo}
                  fill={fill}
                  stroke={strokeColor}
                  strokeWidth={0.5}
                  style={{
                    default: { outline: 'none' },
                    hover: { outline: 'none', opacity: 0.85 },
                    pressed: { outline: 'none' },
                  }}
                />
              )
            })
          }
        </Geographies>
      </ComposableMap>
    </div>
  )
}

function hexToRgba(hex: string, opacity: number): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${opacity})`
}

export default function AncestryPanel({ isDarkMode = false, data }: CategoryPanelProps) {
  const theme = useThemeClasses(isDarkMode)

  const getAncestryData = () => {
    const results = data?.ancestry_results
    const hasRealData = !!results && results.length > 0
    if (!hasRealData) {
      return {
        hasRealData: false,
        ancestryComposition: [] as AncestryRegion[],
        maternalHaplogroup: null,
        paternalHaplogroup: null,
        neanderthalVariants: null,
      }
    }

    const first = results[0]
    let composition: AncestryRegion[] = first?.composition || []
    if (composition.length === 0) {
      composition = results
        .filter((r: Record<string, unknown>) => r.population)
        .map((r: Record<string, unknown>) => ({
          region: String(r.population),
          percentage: parseFloat(String(r.percentage)) || 0,
        }))
    }

    return {
      hasRealData: true,
      ancestryComposition: composition,
      maternalHaplogroup: first?.maternal_haplogroup || null,
      paternalHaplogroup: first?.paternal_haplogroup || null,
      neanderthalVariants: first?.neanderthal_variants || null,
    }
  }

  const { hasRealData, ancestryComposition, maternalHaplogroup, paternalHaplogroup, neanderthalVariants } = getAncestryData()
  const hasHaplogroupData = maternalHaplogroup || paternalHaplogroup

  const headerProps = {
    icon: Globe,
    iconColorClass: 'text-blue-400',
    gradientFrom: 'from-blue-500/20',
    gradientTo: 'to-cyan-500/20',
    borderColor: 'border-blue-500/30',
    title: 'Ancestry & Heritage',
    description: 'Explore your genetic ancestry composition',
    count: ancestryComposition.length,
    countLabel: ancestryComposition.length === 1 ? 'Region' : 'Regions',
    theme,
  }

  if (!hasRealData) {
    return (
      <div className="space-y-6">
        <CategoryHeader {...headerProps} />
        <EmptyState
          icon={Globe}
          iconColorClass="text-blue-400"
          gradientFrom="from-blue-500/20"
          gradientTo="to-cyan-500/20"
          borderColor="border-blue-500/30"
          title="No Ancestry Data Available"
          description="Ancestry composition analysis is not yet available for your genetic data. Upload genetic data to see your ancestry results."
          theme={theme}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <CategoryHeader {...headerProps} />

      {/* Map + Legend side-by-side layout like MyHeritage */}
      <SectionCard title="Ancestry Composition" theme={theme}>
        <div className="flex flex-col lg:flex-row gap-6">
          {/* Left: Legend / Breakdown */}
          <div className="w-full lg:w-80 flex-shrink-0 space-y-3">
            {ancestryComposition.map((region: AncestryRegion, index: number) => {
              const rc = getRegionColor(region.region)
              return (
                <div key={index} className={`${theme.glass} border ${theme.border} rounded-xl p-3`}>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: rc.hex }} />
                      <span className={`font-semibold text-sm ${theme.textPrimary}`}>{region.region}</span>
                    </div>
                    <span className={`font-bold text-sm ${theme.textPrimary}`}>{region.percentage}%</span>
                  </div>
                  <div className={`w-full ${theme.progressBg} rounded-full h-1.5`}>
                    <div
                      className="h-1.5 rounded-full transition-all duration-1000"
                      style={{ width: `${region.percentage}%`, backgroundColor: rc.hex }}
                    />
                  </div>
                </div>
              )
            })}
          </div>

          {/* Right: World Map */}
          <div className="flex-1 min-w-0">
            <AncestryMap composition={ancestryComposition} isDarkMode={isDarkMode} />
          </div>
        </div>
      </SectionCard>

      {hasHaplogroupData && (
        <SectionCard title="Genetic Lineage" description="Notable ancestry markers and lineage information" theme={theme}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Maternal Haplogroup */}
            <div className={`${theme.glass} border ${theme.border} rounded-xl p-5`}>
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-pink-500/20 rounded-lg">
                  <Dna className="h-5 w-5 text-pink-500" />
                </div>
                <h4 className={`text-lg font-semibold ${theme.textPrimary}`}>Maternal Lineage</h4>
              </div>
              <div className="space-y-3">
                <span className={`text-2xl font-bold ${theme.textPrimary}`}>
                  {maternalHaplogroup?.haplogroup || 'Not Available'}
                </span>
                {maternalHaplogroup ? (
                  <>
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <MapPin className="h-4 w-4 text-gray-400" />
                        <span className={`text-sm ${theme.textSecondary}`}>Origin: {maternalHaplogroup.origin}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Users className="h-4 w-4 text-gray-400" />
                        <span className={`text-sm ${theme.textSecondary}`}>Frequency: {maternalHaplogroup.frequency}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Clock className="h-4 w-4 text-gray-400" />
                        <span className={`text-sm ${theme.textSecondary}`}>Age: {maternalHaplogroup.age}</span>
                      </div>
                    </div>
                    <p className={`text-sm ${theme.textSecondary} leading-relaxed`}>{maternalHaplogroup.description}</p>
                  </>
                ) : (
                  <p className={`text-sm ${theme.textSecondary}`}>Maternal haplogroup analysis not yet available</p>
                )}
              </div>
            </div>

            {/* Paternal Haplogroup */}
            <div className={`${theme.glass} border ${theme.border} rounded-xl p-5`}>
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-blue-500/20 rounded-lg">
                  <Dna className="h-5 w-5 text-blue-500" />
                </div>
                <h4 className={`text-lg font-semibold ${theme.textPrimary}`}>Paternal Lineage</h4>
              </div>
              <div className="space-y-3">
                <span className={`text-2xl font-bold ${theme.textPrimary}`}>
                  {paternalHaplogroup?.haplogroup || 'Not Available'}
                </span>
                {paternalHaplogroup ? (
                  <>
                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <MapPin className="h-4 w-4 text-gray-400" />
                        <span className={`text-sm ${theme.textSecondary}`}>Origin: {paternalHaplogroup.origin}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Users className="h-4 w-4 text-gray-400" />
                        <span className={`text-sm ${theme.textSecondary}`}>Frequency: {paternalHaplogroup.frequency}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Clock className="h-4 w-4 text-gray-400" />
                        <span className={`text-sm ${theme.textSecondary}`}>Age: {paternalHaplogroup.age}</span>
                      </div>
                    </div>
                    <p className={`text-sm ${theme.textSecondary} leading-relaxed`}>{paternalHaplogroup.description}</p>
                  </>
                ) : (
                  <p className={`text-sm ${theme.textSecondary}`}>Paternal haplogroup analysis not yet available</p>
                )}
              </div>
            </div>
          </div>
        </SectionCard>
      )}

      <SectionCard title="Neanderthal Ancestry" theme={theme}>
        {neanderthalVariants ? (
          <div className="grid md:grid-cols-3 gap-6">
            <div className="text-center">
              <div className={`text-3xl font-bold ${theme.textPrimary} mb-2`}>{neanderthalVariants.percentage}%</div>
              <div className={`text-sm ${theme.textSecondary}`}>Neanderthal DNA</div>
            </div>
            <div className="text-center">
              <div className={`text-3xl font-bold ${theme.textPrimary} mb-2`}>{neanderthalVariants.variants}</div>
              <div className={`text-sm ${theme.textSecondary}`}>Variants</div>
            </div>
            <div className="text-center">
              <div className={`text-sm ${theme.textSecondary} mb-2`}>You have {neanderthalVariants.moreOrLess} Neanderthal DNA</div>
              <div className={`text-sm ${theme.textSecondary}`}>{neanderthalVariants.comparison}</div>
            </div>
          </div>
        ) : (
          <div className="text-center py-8">
            <p className={theme.textSecondary}>Neanderthal ancestry analysis not yet available</p>
          </div>
        )}
        <div className="mt-4 p-4 bg-amber-500/10 border border-amber-500/20 rounded-lg">
          <p className={`text-sm ${theme.textSecondary} leading-relaxed`}>
            Neanderthals were ancient human relatives who lived in Europe and Asia.
            Modern humans of non-African descent typically have 1-4% Neanderthal DNA.
          </p>
        </div>
      </SectionCard>

      <DisclaimerCard theme={theme} />
    </div>
  )
}
