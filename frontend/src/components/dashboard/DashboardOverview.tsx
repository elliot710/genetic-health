'use client'

import {
  Heart, AlertTriangle, ChevronRight, Activity, BarChart3,
  Sparkles, Target, Dna, Pill, FlaskConical, Brain, Palette,
  Dumbbell, Apple, Zap, FileText,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { getThemeClass, getTheme } from '@/utils/theme'
import { RiskDistributionChart, FunctionalCategoriesChart, OverviewSummaryPie } from '../categories/GenomicCharts'
import SmartInsights from '../SmartInsights'
import type {
  DashboardData, HealthRisk, DrugResponse, NutritionTrait, SportsPerformance,
  CarrierCondition, MethylationProfile, DetoxProfile, IntelligenceTrait,
  PersonalityTraitData, PhysicalTrait, WellnessTrait, RareMutation, UncommonMutation,
} from '../categories/types'

type Theme = ReturnType<typeof getTheme>

interface DashboardOverviewProps {
  theme: Theme
  isDarkMode: boolean
  data: DashboardData | undefined
  token?: string
  analysisStatus: string
  analysisProgress: number
  isAnalysisRunning: boolean
  variantCategories: { name: string; count: number }[]
  variantCategoryStats: { total: number; annotated: number }
  lastFetchedAt: number | null
  isCached: boolean
  setActiveCategory: (cat: string) => void
  setShowProgress: (show: boolean) => void
  onRefreshData: (force?: boolean) => Promise<void>
}

export default function DashboardOverview({
  theme,
  isDarkMode,
  data,
  token,
  analysisStatus,
  analysisProgress,
  isAnalysisRunning,
  variantCategories,
  variantCategoryStats,
  lastFetchedAt,
  isCached,
  setActiveCategory,
  setShowProgress,
  onRefreshData,
}: DashboardOverviewProps) {
  const healthInsights = generateHealthInsights(data, isDarkMode)
  const quickInsights =
    healthInsights.length > 0
      ? healthInsights
      : [
        {
          category: 'Genetic Analysis',
          insight:
            data?.real_data?.variants && data.real_data.variants.length > 0
              ? `${data.real_data.variants.length} variants uploaded and ready for analysis`
              : 'Upload genetic data to begin analysis',
          icon: Dna,
          color: getThemeClass('text-blue-600', isDarkMode),
          bgColor: getThemeClass('bg-blue-50', isDarkMode),
        },
        {
          category: 'Processing Status',
          insight: 'Background analysis in progress - check back for updated results',
          icon: Activity,
          color: getThemeClass('text-amber-600', isDarkMode),
          bgColor: getThemeClass('bg-amber-50', isDarkMode),
        },
        {
          category: 'Data Quality',
          insight: data?.summary?.analysis_id
            ? `Analysis ID: ${data.summary.analysis_id} - Data successfully stored`
            : 'Ready to process your genetic information',
          icon: Activity,
          color: getThemeClass('text-green-600', isDarkMode),
          bgColor: getThemeClass('bg-green-50', isDarkMode),
        },
      ]

  return (
    <div className="space-y-6">
      {/* Cache indicator + force refresh */}
      {lastFetchedAt && (
        <div className={`flex items-center justify-between ${theme.glass} border ${theme.glassBorder} rounded-xl px-4 py-2`}>
          <span className={`text-xs ${theme.text.muted}`}>
            {isCached ? 'Showing cached data' : 'Data loaded'}{' '}
            {new Date(lastFetchedAt).toLocaleTimeString()}
          </span>
          <button
            onClick={() => onRefreshData(true)}
            className={`text-xs font-medium px-3 py-1 rounded-lg transition-colors ${
              isDarkMode
                ? 'text-teal-400 hover:bg-teal-500/10'
                : 'text-teal-600 hover:bg-teal-50'
            }`}
          >
            Fetch fresh data
          </button>
        </div>
      )}

      {/* Analysis Progress Banner (if running) */}
      {(analysisStatus === 'processing' || isAnalysisRunning) && (
        <div
          className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-5 cursor-pointer hover:shadow-lg transition-all duration-300`}
          onClick={() => setShowProgress(true)}
        >
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-gradient-to-br from-teal-500/20 to-cyan-500/20 rounded-lg border border-teal-500/30">
                <Activity className={`h-5 w-5 ${getThemeClass('text-teal-600', isDarkMode)} animate-pulse`} />
              </div>
              <span className={`font-semibold ${theme.text.primary}`}>Analysis in Progress</span>
            </div>
            <span className={`text-sm font-bold ${theme.text.primary}`}>{analysisProgress}%</span>
          </div>
          <div className={`w-full ${isDarkMode ? 'bg-gray-700' : 'bg-gray-200'} rounded-full h-2`}>
            <div
              className="bg-gradient-to-r from-teal-500 to-cyan-500 h-2 rounded-full transition-all duration-500"
              style={{ width: `${Math.max(0, Math.min(100, analysisProgress))}%` }}
            />
          </div>
        </div>
      )}

      {/* Key Metrics Row */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        {[
          {
            label: 'Total Variants',
            value: (data?.summary?.total_variants || data?.real_data?.variants?.length || 0).toLocaleString(),
            icon: Dna,
            gradient: 'from-blue-500 to-indigo-500',
            navigateTo: 'variant-search',
          },
          {
            label: 'Analyzed',
            value: (data?.summary?.analyzed_variants || 0).toLocaleString(),
            icon: FlaskConical,
            gradient: 'from-violet-500 to-purple-500',
            navigateTo: 'variant-search',
          },
          {
            label: 'Health Risks',
            value: Array.isArray(data?.health_risks) ? data.health_risks.length : 0,
            icon: Heart,
            gradient: 'from-rose-500 to-pink-500',
            navigateTo: 'health',
          },
          {
            label: 'Drug Interactions',
            value: Array.isArray(data?.drug_responses) ? data.drug_responses.length : 0,
            icon: Pill,
            gradient: 'from-amber-500 to-orange-500',
            navigateTo: 'drug-responses',
          },
          {
            label: 'Carrier Conditions',
            value: Array.isArray(data?.carrier_status)
              ? data.carrier_status.filter((c: CarrierCondition) => c.carrier_status === 'carrier').length
              : 0,
            icon: AlertTriangle,
            gradient: 'from-orange-500 to-red-500',
            navigateTo: 'carrier-status',
          },
          {
            label: 'Nutrition Markers',
            value: Array.isArray(data?.nutrition_traits) ? data.nutrition_traits.length : 0,
            icon: Apple,
            gradient: 'from-green-500 to-emerald-500',
            navigateTo: 'food-nutrition',
          },
        ].map((metric) => {
          const Icon = metric.icon
          return (
            <div
              key={metric.label}
              className={`${theme.glass} border ${theme.glassBorder} rounded-xl p-4 cursor-pointer ${theme.glassHover} transition-all duration-300 hover:shadow-md hover:-translate-y-0.5`}
              onClick={() => setActiveCategory(metric.navigateTo)}
            >
              <div className={`p-2 bg-gradient-to-br ${metric.gradient} rounded-lg w-fit mb-3 shadow-lg`}>
                <Icon className="h-4 w-4 text-white" />
              </div>
              <p className={`text-2xl font-bold ${theme.text.primary}`}>{metric.value}</p>
              <p className={`text-xs ${theme.text.muted} mt-0.5`}>{metric.label}</p>
            </div>
          )
        })}
      </div>

      {/* Category Highlights Grid */}
      <CategoryHighlights
        theme={theme}
        isDarkMode={isDarkMode}
        data={data}
        setActiveCategory={setActiveCategory}
      />

      {/* Overview Charts Row */}
      <OverviewCharts theme={theme} isDarkMode={isDarkMode} data={data} />

      {/* Smart AI Insights */}
      <SmartInsights isDarkMode={isDarkMode} token={token} section="overview" title="AI-Powered Analysis" />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Genetic Insights */}
        <div className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-6`}>
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-gradient-to-br from-teal-500/20 to-cyan-500/20 rounded-xl border border-teal-500/30">
                <Sparkles className={`h-5 w-5 ${getThemeClass('text-blue-500', isDarkMode)}`} />
              </div>
              <h3 className={`text-lg font-bold ${theme.text.primary}`}>Key Insights</h3>
            </div>
            <span className={`px-2.5 py-1 ${theme.glass} border ${theme.glassBorder} rounded-full text-xs font-medium ${theme.text.secondary}`}>
              {quickInsights.length} findings
            </span>
          </div>
          <div className="space-y-3">
            {quickInsights.map((insight, index) => {
              const Icon = insight.icon
              const severity =
                index === 0 && Array.isArray(data?.health_risks) && data.health_risks.some((r: HealthRisk) => r.risk_level === 'high')
                  ? 'High'
                  : index === 0
                    ? 'Critical'
                    : index === 1
                      ? 'Moderate'
                      : 'Info'
              const severityColor =
                severity === 'High' || severity === 'Critical'
                  ? isDarkMode
                    ? 'bg-red-500/20 text-red-300 border-red-500/30'
                    : 'bg-red-50 text-red-600 border-red-200'
                  : severity === 'Moderate'
                    ? isDarkMode
                      ? 'bg-amber-500/20 text-amber-300 border-amber-500/30'
                      : 'bg-amber-50 text-amber-600 border-amber-200'
                    : isDarkMode
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                      : 'bg-emerald-50 text-emerald-600 border-emerald-200'
              return (
                <div
                  key={index}
                  className={`flex items-start gap-4 p-4 rounded-xl border ${theme.glassBorder} ${theme.glassHover} transition-all ${(insight as { navigateTo?: string }).navigateTo ? 'cursor-pointer hover:shadow-md' : ''}`}
                  onClick={() => (insight as { navigateTo?: string }).navigateTo && setActiveCategory((insight as { navigateTo?: string }).navigateTo!)}
                >
                  <div className={`p-2.5 ${insight.bgColor} rounded-lg flex-shrink-0`}>
                    <Icon className={`h-5 w-5 ${insight.color}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`font-semibold text-sm ${theme.text.primary}`}>{insight.category}</span>
                      <span className={`px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase border ${severityColor}`}>
                        {severity}
                      </span>
                    </div>
                    <p className={`text-sm ${theme.text.secondary} leading-relaxed`}>{insight.insight}</p>
                  </div>
                  {(insight as { navigateTo?: string }).navigateTo && (
                    <ChevronRight className={`h-4 w-4 ${theme.text.muted} flex-shrink-0 mt-1`} />
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* Variant Categories Breakdown */}
        <div className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-6`}>
          <div className="flex items-center gap-3 mb-5">
            <div className="p-2.5 bg-gradient-to-br from-violet-500/20 to-purple-500/20 rounded-xl border border-violet-500/30">
              <BarChart3 className={`h-5 w-5 ${getThemeClass('text-violet-500', isDarkMode)}`} />
            </div>
            <div>
              <h3 className={`text-lg font-bold ${theme.text.primary}`}>Functional Categories</h3>
              <p className={`text-xs ${theme.text.muted}`}>Variant distribution by consequence type</p>
            </div>
          </div>

          {variantCategories.length > 0 ? (
            <div>
              <FunctionalCategoriesChart data={variantCategories.filter((c) => c.name !== 'Unknown')} isDarkMode={isDarkMode} />
              <div className={`flex justify-between pt-3 mt-2 border-t ${theme.glassBorder}`}>
                <span className={`text-xs font-medium ${theme.text.muted}`}>Total variants</span>
                <span className={`text-xs font-bold ${theme.text.primary}`}>{variantCategoryStats.total.toLocaleString()}</span>
              </div>
              <div className="flex justify-between pt-1">
                <span className={`text-xs font-medium ${theme.text.muted}`}>Annotated</span>
                <span className={`text-xs font-bold ${theme.text.primary}`}>
                  {variantCategoryStats.annotated.toLocaleString()} ({variantCategoryStats.total > 0 ? ((variantCategoryStats.annotated / variantCategoryStats.total) * 100).toFixed(1) : 0}%)
                </span>
              </div>
            </div>
          ) : (
            <div className={`text-center py-8 ${theme.text.muted}`}>
              <BarChart3 className="h-10 w-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">Category data loading...</p>
            </div>
          )}
        </div>
      </div>

      {/* Risk Breakdown & Pharmacogenomic Highlights */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {Array.isArray(data?.health_risks) && data.health_risks.length > 0 && (() => {
          const risks = data.health_risks as HealthRisk[]
          return (
            <div
              className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-6 cursor-pointer hover:shadow-md transition-all`}
              onClick={() => setActiveCategory('health')}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <FileText className={`h-4 w-4 ${getThemeClass('text-blue-500', isDarkMode)}`} />
                  <span className={`text-xs font-semibold uppercase tracking-wider ${theme.text.muted}`}>Risk Breakdown</span>
                </div>
                <ChevronRight className={`h-3.5 w-3.5 ${theme.text.muted}`} />
              </div>
              <RiskDistributionChart data={risks} isDarkMode={isDarkMode} height={160} />
            </div>
          )
        })()}

        {Array.isArray(data?.drug_responses) && data.drug_responses.length > 0 && (
          <div
            className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-6 cursor-pointer hover:shadow-md transition-all`}
            onClick={() => setActiveCategory('drug-responses')}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Pill className={`h-4 w-4 ${getThemeClass('text-purple-500', isDarkMode)}`} />
                <span className={`text-xs font-semibold uppercase tracking-wider ${theme.text.muted}`}>Pharmacogenomic Highlights</span>
              </div>
              <ChevronRight className={`h-3.5 w-3.5 ${theme.text.muted}`} />
            </div>
            <div className="flex flex-wrap gap-2">
              {data.drug_responses.slice(0, 8).map((dr: DrugResponse, i: number) => (
                <span
                  key={i}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium border ${theme.glassBorder} ${isDarkMode ? 'bg-purple-500/10 text-purple-300' : 'bg-purple-50 text-purple-700'}`}
                >
                  {dr.gene}
                  {dr.drug ? ` → ${dr.drug}` : ''}
                </span>
              ))}
              {data.drug_responses.length > 8 && (
                <span className={`px-2.5 py-1 rounded-lg text-xs font-medium ${theme.text.muted}`}>
                  +{data.drug_responses.length - 8} more
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Extracted sub-components ────────────────────────────────────

function CategoryHighlights({
  theme,
  isDarkMode,
  data,
  setActiveCategory,
}: {
  theme: Theme
  isDarkMode: boolean
  data: DashboardData | undefined
  setActiveCategory: (cat: string) => void
}) {
  if (!data) return null

  interface CardItem {
    label: string
    value: string | number
    color?: string
  }

  interface CategoryCard {
    id: string
    title: string
    icon: LucideIcon
    gradient: string
    items: CardItem[]
    summary: string
    hasData: boolean
  }

  const categoryCards: CategoryCard[] = []

  // Health Risks
  if (Array.isArray(data.health_risks) && data.health_risks.length > 0) {
    const high = data.health_risks.filter((r: HealthRisk) => r.risk_level === 'high' || r.risk_level === 'very_high').length
    const moderate = data.health_risks.filter((r: HealthRisk) => r.risk_level === 'moderate').length
    const low = data.health_risks.filter((r: HealthRisk) => r.risk_level === 'low').length
    categoryCards.push({
      id: 'health',
      title: 'Health Risks',
      icon: Heart,
      gradient: 'from-rose-500 to-pink-500',
      items: [
        ...(high > 0 ? [{ label: 'High risk', value: high, color: isDarkMode ? 'text-red-400' : 'text-red-600' }] : []),
        ...(moderate > 0 ? [{ label: 'Moderate', value: moderate, color: isDarkMode ? 'text-amber-400' : 'text-amber-600' }] : []),
        ...(low > 0 ? [{ label: 'Low risk', value: low, color: isDarkMode ? 'text-green-400' : 'text-green-600' }] : []),
      ],
      summary: `${data.health_risks.length} conditions analyzed`,
      hasData: true,
    })
  }

  // Drug Responses
  if (Array.isArray(data.drug_responses) && data.drug_responses.length > 0) {
    const poor = data.drug_responses.filter((r: DrugResponse) => r.response_type === 'poor' || r.response_type === 'poor_metabolizer').length
    const rapid = data.drug_responses.filter((r: DrugResponse) => r.response_type === 'rapid' || r.response_type === 'ultrarapid_metabolizer').length
    const normal = data.drug_responses.length - poor - rapid
    categoryCards.push({
      id: 'drug-responses',
      title: 'Drug Responses',
      icon: Pill,
      gradient: 'from-amber-500 to-orange-500',
      items: [
        { label: 'Total', value: data.drug_responses.length },
        ...(poor > 0 ? [{ label: 'Poor metab.', value: poor, color: isDarkMode ? 'text-red-400' : 'text-red-600' }] : []),
        ...(rapid > 0 ? [{ label: 'Rapid metab.', value: rapid, color: isDarkMode ? 'text-amber-400' : 'text-amber-600' }] : []),
        ...(poor === 0 && rapid === 0 && normal > 0 ? [{ label: 'Normal metab.', value: normal, color: isDarkMode ? 'text-green-400' : 'text-green-600' }] : []),
      ],
      summary: `${data.drug_responses.length} drug-gene interactions`,
      hasData: true,
    })
  }

  // Nutrition
  if (Array.isArray(data.nutrition_traits) && data.nutrition_traits.length > 0) {
    const slow = data.nutrition_traits.filter((n: NutritionTrait) => n.metabolism_type === 'slow').length
    const deficient = data.nutrition_traits.filter((n: NutritionTrait) => n.metabolism_type === 'deficient').length
    const normal = data.nutrition_traits.length - slow - deficient
    categoryCards.push({
      id: 'food-nutrition',
      title: 'Nutrition',
      icon: Apple,
      gradient: 'from-green-500 to-emerald-500',
      items: [
        { label: 'Total', value: data.nutrition_traits.length },
        ...(slow > 0 ? [{ label: 'Slow metab.', value: slow, color: isDarkMode ? 'text-amber-400' : 'text-amber-600' }] : []),
        ...(deficient > 0 ? [{ label: 'Deficient', value: deficient, color: isDarkMode ? 'text-red-400' : 'text-red-600' }] : []),
        ...(slow === 0 && deficient === 0 && normal > 0 ? [{ label: 'Normal', value: normal, color: isDarkMode ? 'text-green-400' : 'text-green-600' }] : []),
      ],
      summary: `${data.nutrition_traits.length} nutritional markers`,
      hasData: true,
    })
  }

  // Sports Performance
  if (Array.isArray(data.sports_performance) && data.sports_performance.length > 0) {
    const highAdv = data.sports_performance.filter((s: SportsPerformance) => s.genetic_advantage === 'high').length
    const modAdv = data.sports_performance.filter((s: SportsPerformance) => s.genetic_advantage === 'moderate').length
    categoryCards.push({
      id: 'sports',
      title: 'Sports Performance',
      icon: Dumbbell,
      gradient: 'from-blue-500 to-cyan-500',
      items: [
        { label: 'Total', value: data.sports_performance.length },
        ...(highAdv > 0 ? [{ label: 'High advantage', value: highAdv, color: isDarkMode ? 'text-green-400' : 'text-green-600' }] : []),
        ...(modAdv > 0 ? [{ label: 'Moderate', value: modAdv, color: isDarkMode ? 'text-blue-400' : 'text-blue-600' }] : []),
      ],
      summary: `${data.sports_performance.length} performance metrics`,
      hasData: true,
    })
  }

  // Ancestry
  if (Array.isArray(data.ancestry_results) && data.ancestry_results.length > 0) {
    categoryCards.push({
      id: 'ancestry',
      title: 'Ancestry & Origins',
      icon: Target,
      gradient: 'from-indigo-500 to-blue-500',
      items: data.ancestry_results.slice(0, 3).map((a) => ({
        label: a.population,
        value: typeof a.percentage === 'number' ? `${a.percentage}%` : a.percentage,
      })),
      summary: `${data.ancestry_results.length} populations identified`,
      hasData: true,
    })
  }

  // Carrier Status
  if (Array.isArray(data.carrier_status) && data.carrier_status.length > 0) {
    const carriers = data.carrier_status.filter((c: CarrierCondition) => c.carrier_status === 'carrier').length
    const counseling = data.carrier_status.filter((c: CarrierCondition) => c.genetic_counseling_recommended).length
    categoryCards.push({
      id: 'carrier-status',
      title: 'Carrier Status',
      icon: AlertTriangle,
      gradient: 'from-orange-500 to-red-500',
      items: [
        { label: 'Carriers', value: carriers, color: isDarkMode ? 'text-orange-400' : 'text-orange-600' },
        ...(counseling > 0 ? [{ label: 'Counsel. rec.', value: counseling, color: isDarkMode ? 'text-red-400' : 'text-red-600' }] : []),
      ],
      summary: `${data.carrier_status.length} conditions screened`,
      hasData: true,
    })
  }

  // Methylation
  if (Array.isArray(data.methylation_profiles) && data.methylation_profiles.length > 0) {
    const impaired = data.methylation_profiles.filter((m: MethylationProfile) => m.methylation_capacity === 'impaired').length
    const reduced = data.methylation_profiles.filter((m: MethylationProfile) => m.methylation_capacity === 'reduced').length
    const normal = data.methylation_profiles.filter((m: MethylationProfile) => m.methylation_capacity === 'normal').length
    categoryCards.push({
      id: 'methylation',
      title: 'Methylation',
      icon: Dna,
      gradient: 'from-cyan-500 to-teal-500',
      items: [
        ...(impaired > 0 ? [{ label: 'Impaired', value: impaired, color: isDarkMode ? 'text-red-400' : 'text-red-600' }] : []),
        ...(reduced > 0 ? [{ label: 'Reduced', value: reduced, color: isDarkMode ? 'text-amber-400' : 'text-amber-600' }] : []),
        ...(normal > 0 ? [{ label: 'Normal', value: normal, color: isDarkMode ? 'text-green-400' : 'text-green-600' }] : []),
        ...(impaired === 0 && reduced === 0 && normal === 0 ? [{ label: 'Total', value: data.methylation_profiles.length }] : []),
      ],
      summary: `${data.methylation_profiles.length} genes profiled`,
      hasData: true,
    })
  }

  // Detoxification
  if (Array.isArray(data.detoxification_profiles) && data.detoxification_profiles.length > 0) {
    const impaired = data.detoxification_profiles.filter((d: DetoxProfile) => d.detox_capacity === 'impaired' || d.detox_capacity === 'slow').length
    const normal = data.detoxification_profiles.filter((d: DetoxProfile) => d.detox_capacity === 'normal').length
    const other = data.detoxification_profiles.length - impaired - normal
    categoryCards.push({
      id: 'detox',
      title: 'Detoxification',
      icon: Zap,
      gradient: 'from-lime-500 to-green-500',
      items: [
        { label: 'Pathways', value: data.detoxification_profiles.length },
        ...(impaired > 0 ? [{ label: 'Impaired/Slow', value: impaired, color: isDarkMode ? 'text-red-400' : 'text-red-600' }] : []),
        ...(normal > 0 ? [{ label: 'Normal', value: normal, color: isDarkMode ? 'text-green-400' : 'text-green-600' }] : []),
        ...(other > 0 && impaired === 0 && normal === 0 ? [{ label: 'Other', value: other }] : []),
      ],
      summary: `${data.detoxification_profiles.length} pathways analyzed`,
      hasData: true,
    })
  }

  // Intelligence
  if (Array.isArray(data.intelligence) && data.intelligence.length > 0) {
    const topPercentile = data.intelligence.reduce(
      (max: IntelligenceTrait | null, c: IntelligenceTrait) => (c.percentile > (max?.percentile || 0) ? c : max),
      null,
    )
    categoryCards.push({
      id: 'intelligence',
      title: 'Intelligence',
      icon: Brain,
      gradient: 'from-purple-500 to-violet-500',
      items: data.intelligence.slice(0, 3).map((c: IntelligenceTrait) => ({
        label: c.cognitive_ability || c.trait_name,
        value: c.percentile ? `${c.percentile}th` : c.genetic_advantage || '—',
      })),
      summary: topPercentile
        ? `Top: ${topPercentile.cognitive_ability || topPercentile.trait_name} (${topPercentile.percentile}th)`
        : `${data.intelligence.length} domains`,
      hasData: true,
    })
  }

  // Personality
  if (Array.isArray(data.personality_traits) && data.personality_traits.length > 0) {
    const sorted = [...data.personality_traits].sort((a: PersonalityTraitData, b: PersonalityTraitData) => (b.score || 0) - (a.score || 0))
    categoryCards.push({
      id: 'personality',
      title: 'Personality',
      icon: Palette,
      gradient: 'from-pink-500 to-rose-500',
      items: sorted.slice(0, 3).map((p: PersonalityTraitData) => ({
        label: p.trait || p.name,
        value: p.score ? `${p.score}%` : p.confidence || '—',
      })),
      summary: sorted[0] ? `Strongest: ${sorted[0].trait || sorted[0].name}` : `${data.personality_traits.length} traits`,
      hasData: true,
    })
  }

  // Physical Traits
  if (Array.isArray(data.physical_traits) && data.physical_traits.length > 0) {
    const byCategory: Record<string, number> = {}
    data.physical_traits.forEach((t: PhysicalTrait) => {
      byCategory[t.trait_category || 'other'] = (byCategory[t.trait_category || 'other'] || 0) + 1
    })
    categoryCards.push({
      id: 'physical-traits',
      title: 'Physical Traits',
      icon: Target,
      gradient: 'from-sky-500 to-blue-500',
      items: Object.entries(byCategory)
        .slice(0, 3)
        .map(([cat, count]) => ({
          label: cat.charAt(0).toUpperCase() + cat.slice(1),
          value: count,
        })),
      summary: `${data.physical_traits.length} traits identified`,
      hasData: true,
    })
  }

  // Wellness
  if (Array.isArray(data.wellness_traits) && data.wellness_traits.length > 0) {
    const wellnessVariant = data.wellness_traits.filter((w: WellnessTrait) => w.value === 'variant_detected' || w.value === 'reduced').length
    const wellnessImpaired = data.wellness_traits.filter((w: WellnessTrait) => w.value === 'impaired').length
    const wellnessNormal = data.wellness_traits.filter((w: WellnessTrait) => w.value === 'normal').length
    categoryCards.push({
      id: 'wellness',
      title: 'Wellness Reports',
      icon: Activity,
      gradient: 'from-emerald-500 to-green-500',
      items: [
        ...(wellnessImpaired > 0 ? [{ label: 'Impaired', value: wellnessImpaired, color: isDarkMode ? 'text-red-400' : 'text-red-600' }] : []),
        ...(wellnessVariant > 0 ? [{ label: 'Variant Detected', value: wellnessVariant, color: isDarkMode ? 'text-amber-400' : 'text-amber-600' }] : []),
        ...(wellnessNormal > 0 ? [{ label: 'Normal', value: wellnessNormal, color: isDarkMode ? 'text-green-400' : 'text-green-600' }] : []),
        ...(wellnessImpaired === 0 && wellnessVariant === 0 && wellnessNormal === 0 ? [{ label: 'Total', value: data.wellness_traits.length }] : []),
      ],
      summary: `${data.wellness_traits.length} wellness metrics`,
      hasData: true,
    })
  }

  // Rare Mutations
  if (Array.isArray(data.rare_mutations) && data.rare_mutations.length > 0) {
    const pathogenic = data.rare_mutations.filter((m: RareMutation) => m.mutation_type === 'pathogenic').length
    const likelyPath = data.rare_mutations.filter((m: RareMutation) => m.mutation_type === 'likely_pathogenic').length
    categoryCards.push({
      id: 'rare-mutations',
      title: 'Rare Mutations',
      icon: AlertTriangle,
      gradient: 'from-red-500 to-rose-600',
      items: [
        { label: 'Total', value: data.rare_mutations.length },
        ...(pathogenic > 0 ? [{ label: 'Pathogenic', value: pathogenic, color: isDarkMode ? 'text-red-400' : 'text-red-600' }] : []),
        ...(likelyPath > 0 ? [{ label: 'Likely pathogenic', value: likelyPath, color: isDarkMode ? 'text-orange-400' : 'text-orange-600' }] : []),
      ],
      summary: `${data.rare_mutations.length} rare variants found`,
      hasData: true,
    })
  }

  // Uncommon Mutations
  if (Array.isArray(data.uncommon_mutations) && data.uncommon_mutations.length > 0) {
    const protective = data.uncommon_mutations.filter((m: UncommonMutation) => m.mutation_type === 'protective_rare').length
    const nonProtective = data.uncommon_mutations.length - protective
    categoryCards.push({
      id: 'uncommon-mutations',
      title: 'Uncommon Mutations',
      icon: Dna,
      gradient: 'from-violet-500 to-purple-600',
      items: [
        { label: 'Total', value: data.uncommon_mutations.length },
        ...(protective > 0 ? [{ label: 'Protective', value: protective, color: isDarkMode ? 'text-green-400' : 'text-green-600' }] : []),
        ...(protective === 0 && nonProtective > 0 ? [{ label: 'Variants', value: nonProtective }] : []),
      ],
      summary: protective > 0 ? `${protective} protective variant${protective > 1 ? 's' : ''}` : `${data.uncommon_mutations.length} uncommon variants`,
      hasData: true,
    })
  }

  if (categoryCards.length === 0) return null

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 bg-gradient-to-br from-blue-500/20 to-indigo-500/20 rounded-xl border border-blue-500/30">
          <BarChart3 className={`h-5 w-5 ${getThemeClass('text-blue-500', isDarkMode)}`} />
        </div>
        <div>
          <h3 className={`text-lg font-bold ${theme.text.primary}`}>Category Highlights</h3>
          <p className={`text-xs ${theme.text.muted}`}>Click any card to explore in detail</p>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {categoryCards.map((card) => {
          const Icon = card.icon
          return (
            <div
              key={card.id}
              className={`${theme.glass} border ${theme.glassBorder} rounded-xl p-5 cursor-pointer ${theme.glassHover} transition-all duration-300 group hover:shadow-lg hover:-translate-y-0.5`}
              onClick={() => setActiveCategory(card.id)}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <div className={`p-2 bg-gradient-to-br ${card.gradient} rounded-lg shadow-lg shadow-black/5 group-hover:scale-110 transition-transform`}>
                    <Icon className="h-4 w-4 text-white" />
                  </div>
                  <h4 className={`font-semibold text-sm ${theme.text.primary}`}>{card.title}</h4>
                </div>
                <ChevronRight className={`h-4 w-4 ${theme.text.muted} group-hover:translate-x-0.5 transition-transform`} />
              </div>
              {card.items.length > 0 ? (
                <div className={`grid gap-3 mb-3 ${card.items.length >= 3 ? 'grid-cols-3' : 'grid-cols-2'}`}>
                  {card.items.map((item, idx) => (
                    <div key={idx} className="min-w-0">
                      <p className={`text-lg font-bold leading-tight ${item.color || theme.text.primary}`}>{item.value}</p>
                      <p className={`text-[11px] ${theme.text.muted} truncate leading-tight mt-0.5`}>{item.label}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mb-3" />
              )}
              <p className={`text-xs ${theme.text.secondary}`}>{card.summary}</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function OverviewCharts({
  theme,
  isDarkMode,
  data,
}: {
  theme: Theme
  isDarkMode: boolean
  data: DashboardData | undefined
}) {
  if (!data) return null

  const pieCounts: { label: string; count: number; color: string }[] = []
  if (Array.isArray(data.health_risks) && data.health_risks.length > 0) pieCounts.push({ label: 'Health Risks', count: data.health_risks.length, color: '#ef4444' })
  if (Array.isArray(data.drug_responses) && data.drug_responses.length > 0) pieCounts.push({ label: 'Drug Responses', count: data.drug_responses.length, color: '#f59e0b' })
  if (Array.isArray(data.carrier_status) && data.carrier_status.length > 0) pieCounts.push({ label: 'Carrier Status', count: data.carrier_status.length, color: '#f97316' })
  if (Array.isArray(data.nutrition_traits) && data.nutrition_traits.length > 0) pieCounts.push({ label: 'Nutrition', count: data.nutrition_traits.length, color: '#22c55e' })
  if (Array.isArray(data.sports_performance) && data.sports_performance.length > 0) pieCounts.push({ label: 'Sports', count: data.sports_performance.length, color: '#14b8a6' })
  if (Array.isArray(data.personality_traits) && data.personality_traits.length > 0) pieCounts.push({ label: 'Personality', count: data.personality_traits.length, color: '#ec4899' })
  if (Array.isArray(data.intelligence) && data.intelligence.length > 0) pieCounts.push({ label: 'Intelligence', count: data.intelligence.length, color: '#8b5cf6' })
  if (Array.isArray(data.rare_mutations) && data.rare_mutations.length > 0) pieCounts.push({ label: 'Rare Mutations', count: data.rare_mutations.length, color: '#dc2626' })
  if (Array.isArray(data.wellness_traits) && data.wellness_traits.length > 0) pieCounts.push({ label: 'Wellness', count: data.wellness_traits.length, color: '#10b981' })
  if (Array.isArray(data.methylation_profiles) && data.methylation_profiles.length > 0) pieCounts.push({ label: 'Methylation', count: data.methylation_profiles.length, color: '#06b6d4' })
  if (Array.isArray(data.detoxification_profiles) && data.detoxification_profiles.length > 0) pieCounts.push({ label: 'Detox', count: data.detoxification_profiles.length, color: '#84cc16' })

  if (pieCounts.length < 2) return null

  return (
    <div className={`${theme.glass} border ${theme.glassBorder} rounded-2xl p-6`}>
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2.5 bg-gradient-to-br from-indigo-500/20 to-purple-500/20 rounded-xl border border-indigo-500/30">
          <Activity className={`h-5 w-5 ${getThemeClass('text-indigo-500', isDarkMode)}`} />
        </div>
        <div>
          <h3 className={`text-lg font-bold ${theme.text.primary}`}>Analysis Distribution</h3>
          <p className={`text-xs ${theme.text.muted}`}>Results breakdown across all categories</p>
        </div>
      </div>
      <OverviewSummaryPie counts={pieCounts} isDarkMode={isDarkMode} height={260} />
    </div>
  )
}

// ── Utility: generate health insights ───────────────────────────

interface HealthInsight {
  category: string
  insight: string
  icon: LucideIcon
  color: string
  bgColor: string
  navigateTo?: string
}

function generateHealthInsights(data: DashboardData | undefined, isDarkMode: boolean): HealthInsight[] {
  const insights: HealthInsight[] = []
  if (!data) return insights

  if (Array.isArray(data.health_risks) && data.health_risks.length > 0) {
    const highRisk = data.health_risks.filter((r: HealthRisk) => r.risk_level === 'high' || r.risk_level === 'very_high').length
    const moderateRisk = data.health_risks.filter((r: HealthRisk) => r.risk_level === 'moderate').length

    if (highRisk > 0) {
      insights.push({
        category: 'High Risk Variants',
        insight: `${highRisk} high-risk genetic variants identified requiring attention`,
        icon: AlertTriangle,
        color: getThemeClass('text-red-600', isDarkMode),
        bgColor: getThemeClass('bg-red-50', isDarkMode),
        navigateTo: 'health',
      })
    }
    if (moderateRisk > 0) {
      insights.push({
        category: 'Moderate Risk',
        insight: `${moderateRisk} variants show moderate risk associations`,
        icon: AlertTriangle,
        color: getThemeClass('text-amber-600', isDarkMode),
        bgColor: getThemeClass('bg-amber-50', isDarkMode),
        navigateTo: 'health',
      })
    }
  }

  if (Array.isArray(data.drug_responses) && data.drug_responses.length > 0) {
    const poor = data.drug_responses.filter((r: DrugResponse) => r.response_type === 'poor').length
    const rapid = data.drug_responses.filter((r: DrugResponse) => r.response_type === 'rapid').length
    const detail =
      poor > 0 || rapid > 0
        ? ` — ${poor > 0 ? `${poor} poor metabolizer` : ''}${poor > 0 && rapid > 0 ? ', ' : ''}${rapid > 0 ? `${rapid} rapid metabolizer` : ''}`
        : ''
    insights.push({
      category: 'Drug Metabolism',
      insight: `${data.drug_responses.length} drug-gene interactions identified${detail}`,
      icon: Pill,
      color: getThemeClass('text-purple-600', isDarkMode),
      bgColor: getThemeClass('bg-purple-50', isDarkMode),
      navigateTo: 'drug-responses',
    })
  }

  if (Array.isArray(data.rare_mutations) && data.rare_mutations.length > 0) {
    const pathogenic = data.rare_mutations.filter((m: RareMutation) => m.mutation_type === 'pathogenic' || m.clinical_significance === 'very_high').length
    insights.push({
      category: 'Rare Mutations',
      insight: `${data.rare_mutations.length} rare mutation${data.rare_mutations.length > 1 ? 's' : ''} detected${pathogenic > 0 ? ` — ${pathogenic} pathogenic` : ''}`,
      icon: AlertTriangle,
      color: getThemeClass('text-red-600', isDarkMode),
      bgColor: getThemeClass('bg-red-50', isDarkMode),
      navigateTo: 'rare-mutations',
    })
  }

  if (Array.isArray(data.carrier_status) && data.carrier_status.length > 0) {
    const carriers = data.carrier_status.filter((c: CarrierCondition) => c.carrier_status === 'carrier').length
    const counseling = data.carrier_status.filter((c: CarrierCondition) => c.genetic_counseling_recommended).length
    if (carriers > 0) {
      insights.push({
        category: 'Carrier Status',
        insight: `Carrier for ${carriers} condition${carriers > 1 ? 's' : ''}${counseling > 0 ? ` — counseling recommended for ${counseling}` : ''}`,
        icon: AlertTriangle,
        color: getThemeClass('text-orange-600', isDarkMode),
        bgColor: getThemeClass('bg-orange-50', isDarkMode),
        navigateTo: 'carrier-status',
      })
    }
  }

  if (Array.isArray(data.nutrition_traits) && data.nutrition_traits.length > 0) {
    const sensitivities = data.nutrition_traits.filter((n: NutritionTrait) => n.metabolism_type === 'slow' || n.metabolism_type === 'deficient').length
    if (sensitivities > 0) {
      insights.push({
        category: 'Nutrition',
        insight: `${sensitivities} nutrient metabolism concern${sensitivities > 1 ? 's' : ''} detected`,
        icon: Apple,
        color: getThemeClass('text-orange-600', isDarkMode),
        bgColor: getThemeClass('bg-orange-50', isDarkMode),
        navigateTo: 'food-nutrition',
      })
    }
  }

  if (Array.isArray(data.methylation_profiles) && data.methylation_profiles.length > 0) {
    const impaired = data.methylation_profiles.filter((m: MethylationProfile) => m.methylation_capacity === 'impaired' || m.methylation_capacity === 'reduced').length
    if (impaired > 0) {
      insights.push({
        category: 'Methylation',
        insight: `${impaired} gene${impaired > 1 ? 's' : ''} with reduced methylation capacity`,
        icon: Dna,
        color: getThemeClass('text-teal-600', isDarkMode),
        bgColor: getThemeClass('bg-teal-50', isDarkMode),
        navigateTo: 'methylation',
      })
    }
  }

  if (Array.isArray(data.sports_performance) && data.sports_performance.length > 0) {
    const highAdvantage = data.sports_performance.filter((s: SportsPerformance) => s.genetic_advantage === 'high').length
    if (highAdvantage > 0) {
      insights.push({
        category: 'Athletic Potential',
        insight: `High genetic advantage in ${highAdvantage} performance categor${highAdvantage > 1 ? 'ies' : 'y'}`,
        icon: Dumbbell,
        color: getThemeClass('text-green-600', isDarkMode),
        bgColor: getThemeClass('bg-green-50', isDarkMode),
        navigateTo: 'sports',
      })
    }
  }

  if (data.real_data?.variants && data.real_data.variants.length > 0) {
    const variants = data.real_data.variants
    const withRsId = variants.filter((v) => v.rsid && v.rsid !== '-' && v.rsid !== 'nan').length
    const coverage = Math.round((withRsId / variants.length) * 100)
    insights.push({
      category: 'Analysis Coverage',
      insight: `${coverage}% of variants have reference IDs for clinical analysis`,
      icon: Target,
      color: getThemeClass('text-green-600', isDarkMode),
      bgColor: getThemeClass('bg-green-50', isDarkMode),
      navigateTo: 'variant-search',
    })
  }

  return insights
}
