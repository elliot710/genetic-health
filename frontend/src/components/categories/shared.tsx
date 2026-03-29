'use client'

import React, { useState, useEffect, useMemo } from 'react'
import { LucideIcon, AlertCircle, AlertTriangle, CheckCircle, Flame, Info, ExternalLink, RefreshCw, Search, ChevronRight, ChevronDown, LayoutGrid } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { Badge } from '../ui/badge'
import { Button } from '../ui/button'
import VariantDetailDialog from './VariantDetailDialog'
import {
  getGlassBackground,
  getGlassBorder,
  getTextPrimary,
  getTextSecondary,
  getProgressBarBg,
} from '../../utils/theme'

// ─── Theme Hook ────────────────────────────────────────────────

export function useThemeClasses(isDarkMode: boolean) {
  return {
    glass: getGlassBackground(isDarkMode),
    border: getGlassBorder(isDarkMode),
    textPrimary: getTextPrimary(isDarkMode),
    textSecondary: getTextSecondary(isDarkMode),
    progressBg: getProgressBarBg(isDarkMode),
    isDarkMode,
  }
}

export type ThemeClasses = ReturnType<typeof useThemeClasses>

// ─── Category Header ───────────────────────────────────────────

interface CategoryHeaderProps {
  icon: LucideIcon
  iconColorClass: string
  gradientFrom: string
  gradientTo: string
  borderColor: string
  title: string
  description: string
  count: number
  countLabel: string
  theme: ThemeClasses
}

export function CategoryHeader({
  icon: Icon,
  iconColorClass,
  gradientFrom,
  gradientTo,
  borderColor,
  title,
  description,
  count,
  countLabel,
  theme,
}: CategoryHeaderProps) {
  return (
    <Card className={`${theme.glass} border ${theme.border} ring-0`}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-3 rounded-xl bg-linear-to-br ${gradientFrom} ${gradientTo} border ${borderColor}`}>
              <Icon className={`h-6 w-6 ${iconColorClass}`} />
            </div>
            <div>
              <CardTitle className={`text-2xl font-bold ${theme.textPrimary}`}>{title}</CardTitle>
              <CardDescription className={theme.textSecondary}>{description}</CardDescription>
            </div>
          </div>
          <Badge variant="outline" className="text-sm px-3 py-1.5">
            {count} {countLabel}
          </Badge>
        </div>
      </CardHeader>
    </Card>
  )
}

// ─── Empty State ───────────────────────────────────────────────

interface EmptyStateProps {
  icon: LucideIcon
  iconColorClass: string
  gradientFrom: string
  gradientTo: string
  borderColor: string
  title: string
  description: string
  theme: ThemeClasses
}

export function EmptyState({
  icon: Icon,
  iconColorClass,
  gradientFrom,
  gradientTo,
  borderColor,
  title,
  description,
  theme,
}: EmptyStateProps) {
  return (
    <Card className={`${theme.glass} border ${theme.border} ring-0`}>
      <CardContent className="py-12">
        <div className="flex flex-col items-center gap-4 text-center">
          <div className={`p-4 rounded-xl bg-linear-to-br ${gradientFrom} ${gradientTo} border ${borderColor}`}>
            <Icon className={`h-8 w-8 ${iconColorClass}`} />
          </div>
          <div>
            <h3 className={`text-xl font-bold ${theme.textPrimary} mb-2`}>{title}</h3>
            <p className={`${theme.textSecondary} max-w-md`}>{description}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ─── Error State ──────────────────────────────────────────────

interface ErrorStateProps {
  message?: string
  onRetry?: () => void
  theme: ThemeClasses
}

export function ErrorState({ message = 'Failed to load data.', onRetry, theme }: ErrorStateProps) {
  return (
    <Card className={`${theme.glass} border ${theme.border} ring-0`}>
      <CardContent className="py-12">
        <div className="flex flex-col items-center gap-4 text-center">
          <div className="p-4 rounded-xl bg-linear-to-br from-red-500/20 to-red-600/10 border border-red-500/30">
            <AlertCircle className="h-8 w-8 text-red-400" />
          </div>
          <div>
            <h3 className={`text-xl font-bold ${theme.textPrimary} mb-2`}>Something went wrong</h3>
            <p className={`${theme.textSecondary} max-w-md`}>{message}</p>
          </div>
          {onRetry && (
            <Button variant="outline" size="sm" onClick={onRetry} className="mt-2 gap-2">
              <RefreshCw className="h-4 w-4" />
              Retry
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// ─── Section Card ──────────────────────────────────────────────

interface SectionCardProps {
  title: string
  description?: string
  theme: ThemeClasses
  children: React.ReactNode
}

export function SectionCard({ title, description, theme, children }: SectionCardProps) {
  return (
    <Card className={`${theme.glass} border ${theme.border} ring-0`}>
      <CardHeader>
        <CardTitle className={`text-lg font-semibold ${theme.textPrimary}`}>{title}</CardTitle>
        {description && <CardDescription className={theme.textSecondary}>{description}</CardDescription>}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

// ─── Status Badge (risk/capacity/significance) ────────────────

/**
 * Semantic: "bad" values (high risk, impaired, pathogenic) → red
 *           "moderate" values → yellow
 *           "good" values (low risk, normal, benign) → green
 */
type Severity = 'danger' | 'warning' | 'success' | 'info' | 'neutral'

const SEVERITY_STYLES: Record<Severity, string> = {
  danger: 'bg-red-500/10 text-red-500 border-red-500/20',
  warning: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
  success: 'bg-green-500/10 text-green-500 border-green-500/20',
  info: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  neutral: 'bg-gray-500/10 text-gray-500 border-gray-500/20',
}

const SEVERITY_ICONS: Record<Severity, LucideIcon> = {
  danger: AlertTriangle,
  warning: Flame,
  success: CheckCircle,
  info: Info,
  neutral: Info,
}

interface StatusBadgeProps {
  label: string
  severity: Severity
  showIcon?: boolean
  className?: string
}

export function StatusBadge({ label, severity, showIcon = true, className = '' }: StatusBadgeProps) {
  const Icon = SEVERITY_ICONS[severity]
  return (
    <Badge variant="outline" className={`${SEVERITY_STYLES[severity]} ${className}`}>
      {showIcon && <Icon className="h-3 w-3 mr-1" />}
      {label}
    </Badge>
  )
}

// ─── Severity helpers ──────────────────────────────────────────

/** Map risk levels (high=bad) to severity */
export function riskToSeverity(risk: string): Severity {
  switch (risk?.toLowerCase()) {
    case 'high':
    case 'very_high':
      return 'danger'
    case 'moderate':
    case 'medium':
    case 'intermediate':
      return 'warning'
    case 'low':
      return 'success'
    case 'pending':
    case 'processing':
      return 'info'
    default:
      return 'neutral'
  }
}

/** Map detox/methylation capacity to severity */
export function capacityToSeverity(capacity: string): Severity {
  switch (capacity?.toLowerCase()) {
    case 'impaired':
      return 'danger'
    case 'variant_detected':
    case 'reduced':
      return 'warning'
    case 'normal':
      return 'success'
    default:
      return 'neutral'
  }
}

/** Map genetic advantage / confidence to severity */
export function advantageToSeverity(value: string): Severity {
  const v = value?.toLowerCase() || ''
  if (v.includes('high') || v.includes('strong') || v.includes('enhanced'))
    return 'success'
  if (v.includes('moderate') || v.includes('variant'))
    return 'warning'
  if (v.includes('low') || v.includes('none'))
    return 'neutral'
  return 'info'
}

/**
 * Toxin/pathway sensitivity: Low function = BAD, High function = GOOD.
 * In genetic detox context, "sensitivity: low" means the pathway 
 * has reduced function → bad → red.
 */
export function sensitivityToSeverity(sensitivity: string): Severity {
  switch (sensitivity?.toLowerCase()) {
    case 'high':
      return 'success'
    case 'moderate':
      return 'warning'
    case 'low':
      return 'danger'
    default:
      return 'neutral'
  }
}

/** Clinical significance to severity */
export function clinicalSignificanceToSeverity(significance: string): Severity {
  const s = significance?.toLowerCase() || ''
  if (s.includes('pathogenic') && !s.includes('likely')) return 'danger'
  if (s.includes('likely') && s.includes('pathogenic')) return 'danger'
  if (s.includes('vus') || s.includes('uncertain') || s === 'moderate' || s === 'high') return 'warning'
  if (s.includes('benign') || s === 'low') return 'success'
  return 'neutral'
}

/** Carrier status to severity */
export function carrierStatusToSeverity(status: string): Severity {
  switch (status?.toLowerCase()) {
    case 'affected':
      return 'danger'
    case 'carrier':
      return 'warning'
    case 'non-carrier':
    case 'not a carrier':
      return 'success'
    default:
      return 'neutral'
  }
}

// ─── Score Bar ─────────────────────────────────────────────────

interface ScoreBarProps {
  label: string
  value: number
  maxValue?: number
  colorClass?: string
  theme: ThemeClasses
  showPercent?: boolean
  suffix?: string
}

export function ScoreBar({
  label,
  value,
  maxValue = 100,
  colorClass,
  theme,
  showPercent = true,
  suffix = '%',
}: ScoreBarProps) {
  const pct = Math.min((value / maxValue) * 100, 100)
  const barColor = colorClass || getScoreBarColor(value)
  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-1">
        <span className={`text-xs ${theme.textSecondary}`}>{label}</span>
        <span className={`text-xs font-medium ${theme.textPrimary}`}>
          {showPercent ? `${Math.round(value)}${suffix}` : `${Math.round(value)}/${maxValue}`}
        </span>
      </div>
      <div className={`w-full h-2 rounded-full ${theme.progressBg}`}>
        <div
          className={`h-2 rounded-full ${barColor} transition-all duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function getScoreBarColor(score: number): string {
  if (score >= 70) return 'bg-gradient-to-r from-green-500 to-emerald-500'
  if (score >= 40) return 'bg-gradient-to-r from-yellow-500 to-amber-500'
  return 'bg-gradient-to-r from-red-500 to-orange-500'
}

/** Risk bar: higher score = worse → red */
export function getRiskBarColor(score: number): string {
  if (score >= 50) return 'bg-gradient-to-r from-red-500 to-red-400'
  if (score >= 25) return 'bg-gradient-to-r from-yellow-500 to-yellow-400'
  return 'bg-gradient-to-r from-green-500 to-green-400'
}

// ─── Pathogenicity Score Bar ───────────────────────────────────

function getPathogenicityColor(score: number): string {
  if (score >= 80) return 'bg-gradient-to-r from-red-600 to-red-400'
  if (score >= 60) return 'bg-gradient-to-r from-orange-500 to-red-400'
  if (score >= 30) return 'bg-gradient-to-r from-yellow-500 to-amber-400'
  if (score >= 15) return 'bg-gradient-to-r from-green-400 to-emerald-400'
  return 'bg-gradient-to-r from-green-500 to-emerald-500'
}

interface PathogenicityBarProps {
  rsid: string
  pathogenicityMap?: Record<string, { score: number; classification: string; confidence: string; evidence_count: number }>
  theme: ThemeClasses
}

/**
 * Compact pathogenicity score bar. Renders nothing if no data for the given rsid.
 * Uses the same ScoringEngine output as VariantDetailDialog for consistency.
 */
export function PathogenicityBar({ rsid, pathogenicityMap, theme }: PathogenicityBarProps) {
  const [override, setOverride] = useState<{ score: number; classification: string } | null>(null)

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail
      if (detail?.rsid === rsid) {
        setOverride({ score: detail.score, classification: detail.classification })
      }
    }
    window.addEventListener('pathogenicity-update', handler)
    return () => window.removeEventListener('pathogenicity-update', handler)
  }, [rsid])

  const entry = override || pathogenicityMap?.[rsid]
  if (!entry) return null

  return (
    <ScoreBar
      label={`Pathogenicity Score (${entry.classification.replace(/_/g, ' ')})`}
      value={entry.score}
      colorClass={getPathogenicityColor(entry.score)}
      theme={theme}
    />
  )
}

// ─── Variant Info Box (consistent across all panels) ──────────

interface VariantInfoBoxProps {
  rsid?: string
  gene?: string
  token?: string
  isDarkMode?: boolean
  alphaMissense?: { score?: number; classification?: string } | null
  clinvarCount?: number
  genotype?: string
  pathogenicityMap?: Record<string, { score: number; classification: string; confidence: string; evidence_count: number }>
  theme: ThemeClasses
}

/**
 * Compact labeled "Associated Variants" box used in the expanded section
 * of every category panel. Shows pathogenicity score + variant links.
 */
export function VariantInfoBox({
  rsid, gene, token, isDarkMode = false, alphaMissense, clinvarCount, genotype, pathogenicityMap, theme,
}: VariantInfoBoxProps) {
  const validRsid = rsid && rsid.startsWith('rs')
  if (!validRsid) return null
  return (
    <div>
      <h5 className={`text-xs font-semibold ${theme.textSecondary} uppercase tracking-wide mb-1.5`}>Associated Variants</h5>
      <div className={`rounded-lg p-2.5 border ${theme.border} ${theme.isDarkMode ? 'bg-white/3' : 'bg-gray-50/60'} space-y-2`}>
        <PathogenicityBar rsid={rsid!} pathogenicityMap={pathogenicityMap} theme={theme} />
        <VariantLinks
          rsid={rsid}
          gene={gene}
          token={token}
          isDarkMode={isDarkMode}
          alphaMissense={alphaMissense}
          clinvarCount={clinvarCount}
          genotype={genotype}
        />
      </div>
    </div>
  )
}

// ─── Gene Context Box ──────────────────────────────────────────

import type { GeneStats } from './types'

interface GeneContextBoxProps {
  gene: string
  stats: GeneStats
  theme: ThemeClasses
}

// ─── AlphaFold Protein Confidence Badge ────────────────────────

interface AlphaFoldBadgeProps {
  confidence?: number | null
  highPct?: number
  lowPct?: number
}

/**
 * Compact inline badge showing AlphaFold global confidence for the protein.
 * Green ≥ 70%, amber 50–69%, red < 50%.
 */
export function AlphaFoldBadge({ confidence, highPct, lowPct }: AlphaFoldBadgeProps) {
  if (confidence == null) return null
  const pct = Math.round(confidence)
  const color = pct >= 70 ? 'text-green-400 border-green-500/30 bg-green-500/10' :
                pct >= 50 ? 'text-amber-400 border-amber-500/30 bg-amber-500/10' :
                            'text-red-400 border-red-500/30 bg-red-500/10'
  return (
    <span
      title={`AlphaFold protein structure confidence: ${pct}% global${highPct ? ` · ${Math.round(highPct * 100)}% very high confidence residues` : ''}${lowPct ? ` · ${Math.round(lowPct * 100)}% very low confidence (disordered)` : ''}`}
      className={`inline-flex items-center gap-1 text-[10px] font-medium rounded px-1.5 py-0.5 border ${color}`}
    >
      <svg className="h-2.5 w-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
      </svg>
      AF {pct}%
    </span>
  )
}

/**
 * Expanded section: gene-level ClinVar burden + known disease associations.
 * Shows how many pathogenic variants are known for this gene and what diseases
 * are associated, with OMIM links.
 */
export function GeneContextBox({ gene, stats, theme }: GeneContextBoxProps) {
  const [showAll, setShowAll] = React.useState(false)
  if (!stats) return null
  const conditions = stats.conditions || []
  const visible = showAll ? conditions : conditions.slice(0, 4)
  const hasMore = conditions.length > 4

  const burdenColor =
    stats.pathogenic_lp >= 100 ? 'text-red-400' :
    stats.pathogenic_lp >= 20  ? 'text-orange-400' :
    stats.pathogenic_lp > 0    ? 'text-yellow-400' : 'text-gray-400'

  return (
    <div>
      <h5 className={`text-xs font-semibold ${theme.textSecondary} uppercase tracking-wide mb-1.5`}>
        Gene Context
      </h5>
      <div className={`rounded-lg p-2.5 border ${theme.border} ${theme.isDarkMode ? 'bg-white/3' : 'bg-gray-50/60'} space-y-2`}>
        {/* Burden stats row */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
          <span className={`font-semibold ${theme.textPrimary}`}>{gene}</span>
          {stats.pathogenic_lp > 0 && (
            <span className={`font-medium ${burdenColor}`}>
              {stats.pathogenic_lp.toLocaleString()} pathogenic/LP
            </span>
          )}
          {stats.vus > 0 && (
            <span className={`${theme.textSecondary}`}>
              {stats.vus.toLocaleString()} VUS
            </span>
          )}
          {stats.total_submissions > 0 && (
            <span className={`${theme.textSecondary}`}>
              {stats.total_submissions.toLocaleString()} submissions
            </span>
          )}
          {stats.gene_mim && (
            <a
              href={`https://omim.org/entry/${stats.gene_mim}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-400 hover:text-blue-300 transition-colors"
              onClick={e => e.stopPropagation()}
            >
              OMIM:{stats.gene_mim} ↗
            </a>
          )}
        </div>
        {/* Disease associations */}
        {conditions.length > 0 && (
          <div>
            <span className={`text-[10px] font-semibold ${theme.textSecondary} uppercase tracking-wide`}>
              Known associations ({conditions.length})
            </span>
            <div className="flex flex-wrap gap-1 mt-1">
              {visible.map((c, i) => (
                c.disease_mim ? (
                  <a
                    key={i}
                    href={`https://omim.org/entry/${c.disease_mim}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`inline-flex items-center gap-1 text-[10px] rounded px-1.5 py-0.5 border ${theme.border} ${theme.isDarkMode ? 'bg-white/5 hover:bg-white/10' : 'bg-gray-100/80 hover:bg-gray-200/80'} ${theme.textSecondary} hover:text-blue-400 transition-colors`}
                    onClick={e => e.stopPropagation()}
                  >
                    {c.disease_name} ↗
                  </a>
                ) : (
                  <a
                    key={i}
                    href={`https://omim.org/search?search=${encodeURIComponent(c.disease_name)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`inline-flex items-center gap-1 text-[10px] rounded px-1.5 py-0.5 border ${theme.border} ${theme.isDarkMode ? 'bg-white/5 hover:bg-white/10' : 'bg-gray-100/80 hover:bg-gray-200/80'} ${theme.textSecondary} hover:text-blue-400 transition-colors`}
                    onClick={e => e.stopPropagation()}
                  >
                    {c.disease_name}
                  </a>
                )
              ))}
              {hasMore && !showAll && (
                <button
                  className={`text-[10px] ${theme.textSecondary} hover:${theme.textPrimary} underline`}
                  onClick={e => { e.stopPropagation(); setShowAll(true) }}
                >
                  +{conditions.length - 4} more
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * Compact single-line gene burden strip for collapsed cards.
 * Shows "153 pathogenic · 5 diseases" in secondary text under the badges.
 */
export function GeneBurdenStrip({ gene, stats, theme }: GeneContextBoxProps) {
  if (!stats) return null
  const parts: string[] = []
  if (stats.pathogenic_lp > 0) parts.push(`${stats.pathogenic_lp.toLocaleString()} pathogenic`)
  if (stats.conditions.length > 0) parts.push(`${stats.conditions.length} known disease${stats.conditions.length !== 1 ? 's' : ''}`)
  if (parts.length === 0) return null
  return (
    <p className={`text-[10px] ${theme.textSecondary} mt-1`}>
      {gene} · {parts.join(' · ')}
    </p>
  )
}

// ─── AlphaFold Structural Detail Box ───────────────────────────

interface AlphaFoldDetailBoxProps {
  rsid?: string
  alphafoldData?: {
    confidence?: number | null
    high_confidence_pct?: number
    low_confidence_pct?: number
    protein_name?: string
  } | null
  theme: ThemeClasses
}

/**
 * Expanded section: full AlphaFold protein structure confidence breakdown.
 * Shows pLDDT score visually with per-region breakdown and clinical interpretation.
 * High confidence (≥70%) = reliable structure prediction → variant likely disrupts real domain.
 * Low confidence (<50%) = intrinsically disordered region → variant effect harder to predict.
 */
export function AlphaFoldDetailBox({ rsid, alphafoldData, theme }: AlphaFoldDetailBoxProps) {
  if (!alphafoldData || alphafoldData.confidence == null) return null

  const pct = Math.round(alphafoldData.confidence)
  const highPct = Math.round((alphafoldData.high_confidence_pct ?? 0) * 100)
  const lowPct = Math.round((alphafoldData.low_confidence_pct ?? 0) * 100)
  const rawProteinName = alphafoldData.protein_name
  const proteinName = Array.isArray(rawProteinName)
    ? rawProteinName[0] || null
    : rawProteinName || null

  const confidenceColor =
    pct >= 70 ? 'text-green-400' : pct >= 50 ? 'text-amber-400' : 'text-red-400'
  const barColor =
    pct >= 70 ? 'bg-green-500' : pct >= 50 ? 'bg-amber-500' : 'bg-red-500'

  const interpretation =
    pct >= 90 ? 'Very high confidence — structure is highly reliable. Variant likely disrupts a well-defined structural domain.' :
    pct >= 70 ? 'Confident structure. Variant falls in a region with reliable 3D prediction — functional impact is assessable.' :
    pct >= 50 ? 'Low confidence — this region may be partially disordered. Structural impact harder to predict.' :
                'Very low confidence — intrinsically disordered region. AlphaFold structure not reliable here.'

  return (
    <div>
      <h5 className={`text-xs font-semibold ${theme.textSecondary} uppercase tracking-wide mb-1.5`}>
        AlphaFold Protein Structure
      </h5>
      <div className={`rounded-lg p-2.5 border ${theme.border} ${theme.isDarkMode ? 'bg-white/3' : 'bg-gray-50/60'} space-y-2`}>
        {/* Protein name */}
        {proteinName && (
          <p className={`text-xs font-medium ${theme.textPrimary} truncate`} title={proteinName}>
            {proteinName}
          </p>
        )}
        {/* Global confidence bar */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className={`text-xs ${theme.textSecondary}`}>Global model confidence (pLDDT)</span>
            <span className={`text-sm font-bold font-mono ${confidenceColor}`}>{pct}%</span>
          </div>
          <div className={`h-2 rounded-full ${theme.isDarkMode ? 'bg-white/10' : 'bg-gray-200'} overflow-hidden`}>
            <div className={`h-full rounded-full ${barColor} transition-all`} style={{ width: `${pct}%` }} />
          </div>
        </div>
        {/* pLDDT region breakdown */}
        {(highPct > 0 || lowPct > 0) && (
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className={`rounded px-1.5 py-1 ${theme.isDarkMode ? 'bg-green-500/10' : 'bg-green-50'}`}>
              <div className="text-[10px] text-green-400 font-semibold">{highPct}%</div>
              <div className={`text-[9px] ${theme.textSecondary}`}>Very high</div>
              <div className={`text-[9px] ${theme.textSecondary}`}>(pLDDT ≥90)</div>
            </div>
            <div className={`rounded px-1.5 py-1 ${theme.isDarkMode ? 'bg-amber-500/10' : 'bg-amber-50'}`}>
              <div className="text-[10px] text-amber-400 font-semibold">{Math.max(0, 100 - highPct - lowPct)}%</div>
              <div className={`text-[9px] ${theme.textSecondary}`}>Confident</div>
              <div className={`text-[9px] ${theme.textSecondary}`}>(50–89)</div>
            </div>
            <div className={`rounded px-1.5 py-1 ${theme.isDarkMode ? 'bg-red-500/10' : 'bg-red-50'}`}>
              <div className="text-[10px] text-red-400 font-semibold">{lowPct}%</div>
              <div className={`text-[9px] ${theme.textSecondary}`}>Disordered</div>
              <div className={`text-[9px] ${theme.textSecondary}`}>(pLDDT &lt;50)</div>
            </div>
          </div>
        )}
        {/* Clinical interpretation */}
        <p className={`text-[10px] ${theme.textSecondary} leading-relaxed`}>
          {interpretation}
        </p>
        {/* Link to AlphaFold DB */}
        {rsid && (
          <a
            href={`https://alphafold.ebi.ac.uk/search/text/${rsid}`}
            target="_blank"
            rel="noopener noreferrer"
            onClick={e => e.stopPropagation()}
            className="inline-flex items-center gap-1 text-[10px] text-blue-400 hover:text-blue-300 transition-colors"
          >
            View in AlphaFold DB ↗
          </a>
        )}
      </div>
    </div>
  )
}

// ─── Research Links (inline compact) ───────────────────────────


const DB_LINKS: Record<string, (rsid: string) => string> = {
  dbSNP: (rsid) => `https://www.ncbi.nlm.nih.gov/snp/${rsid}`,
  ClinVar: (rsid) => `https://www.ncbi.nlm.nih.gov/clinvar/?term=${rsid}`,
  SNPedia: (rsid) => `https://www.snpedia.com/index.php/${rsid}`,
  Ensembl: (rsid) => `https://www.ensembl.org/Homo_sapiens/Variation/Explore?v=${rsid}`,
  PubMed: (rsid) => `https://pubmed.ncbi.nlm.nih.gov/?term=${rsid}`,
}

const GENE_LINKS: Record<string, (gene: string) => string> = {
  GeneCards: (gene) => `https://www.genecards.org/cgi-bin/carddisp.pl?gene=${gene}`,
  OMIM: (gene) => `https://omim.org/search?search=${gene}`,
  UniProt: (gene) => `https://www.uniprot.org/uniprotkb?query=${gene}+AND+organism_id:9606`,
}

const LINK_COLORS: Record<string, string> = {
  dbSNP: 'text-blue-400 hover:text-blue-300',
  ClinVar: 'text-orange-400 hover:text-orange-300',
  SNPedia: 'text-green-400 hover:text-green-300',
  Ensembl: 'text-purple-400 hover:text-purple-300',
  PubMed: 'text-yellow-400 hover:text-yellow-300',
  GeneCards: 'text-cyan-400 hover:text-cyan-300',
  OMIM: 'text-pink-400 hover:text-pink-300',
  UniProt: 'text-teal-400 hover:text-teal-300',
}

interface VariantLinksProps {
  rsid?: string
  gene?: string
  token?: string
  isDarkMode?: boolean
  alphaMissense?: { score?: number; classification?: string } | null
  clinvarCount?: number
  genotype?: string
}

/**
 * Compact research database links with optional "View Details" dialog.
 * When token is provided, shows a button to open the annotation dialog.
 */
export function VariantLinks({ rsid, gene, token, isDarkMode = false, alphaMissense, clinvarCount, genotype }: VariantLinksProps) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const validRsid = rsid && rsid !== 'Unknown' && rsid !== 'Multiple' && rsid.startsWith('rs')
  const validGene =
    gene &&
    gene !== 'Unknown' &&
    gene !== 'Multiple' &&
    gene !== 'Multiple genes' &&
    gene !== 'Multiple markers' &&
    !gene.startsWith('rs')

  const links: { name: string; url: string }[] = []

  if (validRsid) {
    for (const [name, fn] of Object.entries(DB_LINKS)) {
      links.push({ name, url: fn(rsid!) })
    }
  }

  if (validGene) {
    for (const [name, fn] of Object.entries(GENE_LINKS)) {
      links.push({ name, url: fn(gene!) })
    }
  }

  if (links.length === 0 && !validRsid) return null

  return (
    <>
      <div className="flex flex-wrap gap-2 pt-2 items-center">
        {validRsid && token && (
          <button
            onClick={(e) => { e.stopPropagation(); setDialogOpen(true) }}
            className="inline-flex items-center gap-1 text-xs font-semibold text-blue-400 hover:text-blue-300 bg-blue-500/10 hover:bg-blue-500/20 border border-blue-500/20 rounded-md px-2 py-0.5 transition-colors"
          >
            <Search className="h-3 w-3" />
            Details
          </button>
        )}
        {alphaMissense && alphaMissense.score != null && (
          <span
            className={`inline-flex items-center gap-1 text-xs font-semibold rounded-md px-2 py-0.5 border ${
              alphaMissense.classification === 'likely_pathogenic'
                ? 'text-red-400 bg-red-500/10 border-red-500/20'
                : alphaMissense.classification === 'ambiguous'
                  ? 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20'
                  : 'text-green-400 bg-green-500/10 border-green-500/20'
            }`}
            title={`AlphaMissense: ${alphaMissense.score.toFixed(3)} — ${(alphaMissense.classification || '').replace(/_/g, ' ')}`}
          >
            AM {alphaMissense.score.toFixed(2)}
          </span>
        )}
        {clinvarCount != null && clinvarCount > 0 && (
          <span
            className="inline-flex items-center gap-1 text-xs font-semibold rounded-md px-2 py-0.5 border text-orange-400 bg-orange-500/10 border-orange-500/20"
            title={`${clinvarCount} ClinVar ${clinvarCount === 1 ? 'report' : 'reports'}`}
          >
            CV {clinvarCount}
          </span>
        )}
        {links.map(({ name, url }) => (
          <a
            key={name}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className={`inline-flex items-center gap-1 text-xs font-medium ${LINK_COLORS[name] || 'text-blue-400 hover:text-blue-300'} transition-colors`}
          >
            {name}
            <ExternalLink className="h-3 w-3" />
          </a>
        ))}
      </div>
      {validRsid && token && (
        <VariantDetailDialog
          rsid={rsid!}
          gene={validGene ? gene : undefined}
          genotype={genotype}
          token={token}
          isDarkMode={isDarkMode}
          open={dialogOpen}
          onOpenChange={setDialogOpen}
        />
      )}
    </>
  )
}

// ─── Clickable Rsid Badge ──────────────────────────────────────

// ─── Zygosity Badge ────────────────────────────────────────────

/** Determine if genotype is homozygous (both alleles identical) or heterozygous */
export function getZygosity(genotype?: string): 'homo' | 'het' | null {
  if (!genotype || genotype.length !== 2) return null
  return genotype[0] === genotype[1] ? 'homo' : 'het'
}

export function ZygosityBadge({ genotype }: { genotype?: string }) {
  const zyg = getZygosity(genotype)
  if (!zyg) return null
  const isHomo = zyg === 'homo'
  return (
    <Badge
      variant="outline"
      className={`text-xs ${isHomo ? 'bg-red-500/10 text-red-500 border-red-500/20' : 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20'}`}
    >
      {isHomo ? 'Homo' : 'Het'}
    </Badge>
  )
}

// ─── Evidence Badge (ClinVar review status) ───────────────────

/**
 * Shows a confidence indicator for auto-discovered vs curated mappings.
 * review_status comes from ClinVar's review_status field on auto-categorized
 * variants. Manual curated mappings won't have it and show a green "Curated" badge.
 */
export function EvidenceBadge({ reviewStatus }: { reviewStatus?: string | null }) {
  if (!reviewStatus) {
    // Manually curated mapping — highest confidence
    return (
      <Badge variant="outline" className="text-xs bg-emerald-500/10 text-emerald-600 border-emerald-500/20 dark:text-emerald-400">
        ✓ Curated
      </Badge>
    )
  }

  const rs = reviewStatus.toLowerCase()
  let stars = 0
  let label = ''
  if (rs.includes('practice guideline')) { stars = 4; label = '4★ Guidelines' }
  else if (rs.includes('expert panel')) { stars = 3; label = '3★ Expert Panel' }
  else if (rs.includes('multiple submitters') || rs.includes('no conflicts')) { stars = 2; label = '2★ Multi-Submitters' }
  else if (rs.includes('single submitter') || rs.includes('criteria provided')) { stars = 1; label = '1★ Single Submitter' }
  else { label = 'Auto-discovered' }

  const colorClass = stars >= 3
    ? 'bg-blue-500/10 text-blue-600 border-blue-500/20 dark:text-blue-400'
    : stars === 2
      ? 'bg-yellow-500/10 text-yellow-600 border-yellow-500/20 dark:text-yellow-400'
      : 'bg-gray-500/10 text-gray-500 border-gray-500/20'

  return (
    <Badge variant="outline" className={`text-xs ${colorClass}`}>
      {label}
    </Badge>
  )
}

/** Returns the star count (0–4) from a ClinVar review_status string. */
export function reviewStatusStars(reviewStatus?: string | null): number {
  if (!reviewStatus) return 5  // curated = best
  const rs = reviewStatus.toLowerCase()
  if (rs.includes('practice guideline')) return 4
  if (rs.includes('expert panel')) return 3
  if (rs.includes('multiple submitters') || rs.includes('no conflicts')) return 2
  if (rs.includes('single submitter') || rs.includes('criteria provided')) return 1
  return 0
}

// ─── Clickable Rsid Badge (with zygosity) ──────────────────────

interface ClickableRsidBadgeProps {
  rsid: string
  gene?: string
  genotype?: string
  token?: string
  isDarkMode?: boolean
}

/**
 * A mono-font rsid badge that opens the VariantDetailDialog on click.
 * Reusable across any panel that displays rsids.
 */
export function ClickableRsidBadge({ rsid, gene, genotype, token, isDarkMode = false }: ClickableRsidBadgeProps) {
  const [dialogOpen, setDialogOpen] = useState(false)
  const validRsid = rsid && rsid !== 'Unknown' && rsid.startsWith('rs')

  return (
    <>
      <Badge
        variant="outline"
        className={`text-xs font-mono ${validRsid && token ? 'cursor-pointer hover:bg-blue-500/10 hover:border-blue-500/40 transition-colors' : ''}`}
        onClick={validRsid && token ? (e: React.MouseEvent) => { e.stopPropagation(); setDialogOpen(true) } : undefined}
      >
        {rsid}{genotype ? ` ${genotype}` : ''}
      </Badge>
      <ZygosityBadge genotype={genotype} />
      {validRsid && token && (
        <VariantDetailDialog
          rsid={rsid}
          gene={gene}
          genotype={genotype}
          token={token}
          isDarkMode={isDarkMode}
          open={dialogOpen}
          onOpenChange={setDialogOpen}
        />
      )}
    </>
  )
}

// ─── Recommendation Block ──────────────────────────────────────

interface RecommendationBlockProps {
  title: string
  text: string
  theme: ThemeClasses
}

export function RecommendationBlock({ title, text, theme }: RecommendationBlockProps) {
  return (
    <div className={`p-3 ${theme.isDarkMode ? 'bg-blue-500/10' : 'bg-blue-50/50'} rounded-lg border-l-4 border-blue-400`}>
      <h5 className={`text-sm font-semibold ${theme.textPrimary} mb-1`}>{title}</h5>
      <p className={`text-sm ${theme.textSecondary}`}>{text}</p>
    </div>
  )
}

// ─── Disclaimer Card ───────────────────────────────────────────

interface DisclaimerCardProps {
  icon?: LucideIcon
  title?: string
  text?: string
  borderColorClass?: string
  bgTintClass?: string
  theme: ThemeClasses
}

export function DisclaimerCard({
  icon: Icon = Info,
  title = 'Important Disclaimer',
  text = 'This information is for educational purposes only and should not be used as a substitute for professional medical advice, diagnosis, or treatment. Always consult a qualified healthcare provider.',
  borderColorClass = 'border-blue-500/20',
  bgTintClass = 'bg-blue-500/5',
  theme,
}: DisclaimerCardProps) {
  return (
    <div className={`${theme.glass} border ${theme.border} rounded-xl ${borderColorClass} ${bgTintClass} px-3 py-2`}>
      <div className="flex items-center space-x-2">
        <Icon className="h-4 w-4 text-blue-500 shrink-0" />
        <div>
          <h3 className={`text-sm font-semibold ${theme.textPrimary}`}>{title}</h3>
          <p className={`text-xs ${theme.textSecondary} leading-relaxed`}>{text}</p>
        </div>
      </div>
    </div>
  )
}

// ─── Condition / trait name cleaner ─────────────────────────────
/**
 * Clean raw ClinVar pipe/semicolon-delimited condition strings.
 * Extracts the first meaningful name and title-cases all-uppercase entries.
 */
const SKIP_CONDITIONS = new Set([
  'not provided', 'not specified', 'see cases', 'not applicable',
])

export function cleanCondition(raw?: string | null): string {
  if (!raw) return 'Unknown'
  // Convert snake_case to spaced words first
  const cleaned = raw.replace(/[_]+/g, ' ').trim()
  if (!cleaned.includes('|') && !cleaned.includes(';')) {
    // Title-case if it looks like a slug (all lowercase, no capitals)
    if (cleaned === cleaned.toLowerCase()) {
      return toTitleCase(cleaned)
    }
    // Title-case if the string is entirely uppercase (e.g. ClinVar condition names)
    if (cleaned === cleaned.toUpperCase() && cleaned.length > 3) {
      return toTitleCase(cleaned)
    }
    return cleaned
  }
  const parts = cleaned.replace(/;/g, '|').split('|')
  for (const part of parts) {
    const trimmed = part.trim()
    if (trimmed && !SKIP_CONDITIONS.has(trimmed.toLowerCase())) {
      return trimmed === trimmed.toUpperCase() ? toTitleCase(trimmed) : trimmed
    }
  }
  return parts[0]?.trim() ? toTitleCase(parts[0].trim()) : raw
}

function toTitleCase(s: string): string {
  return s
    .toLowerCase()
    .replace(/\b\w/g, c => c.toUpperCase())
}

// ─── Format helpers ────────────────────────────────────────────

export function formatLabel(value: string): string {
  return (
    value
      ?.replace(/[_]+/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase()) || 'Unknown'
  )
}

/**
 * Extract the first valid rsid from a list of variant strings.
 */
export function firstRsid(variants?: string[]): string | undefined {
  return variants?.find((v) => v && v.startsWith('rs'))
}

// ─── Masonry Layout ─────────────────────────────────────────────

export function MasonryLayout({ children }: { children: React.ReactNode }) {
  const items = React.Children.toArray(children)
  const col1 = items.filter((_, i) => i % 2 === 0)
  const col2 = items.filter((_, i) => i % 2 !== 0)

  return (
    <div className="flex flex-col md:flex-row gap-4">
      <div className="flex-1 space-y-4">{col1}</div>
      <div className="flex-1 space-y-4">{col2}</div>
    </div>
  )
}

// ─── Grouping Utilities ─────────────────────────────────────────

interface GroupItem<T> { key: string; label: string; items: T[] }

export function useGrouping<T>(
  items: T[],
  groupBy: string,
  getGroupKey: (item: T) => string,
  allLabel = 'All Items'
) {
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())

  const groups: GroupItem<T>[] = useMemo(() => {
    if (groupBy === 'none') return [{ key: 'all', label: allLabel, items }]
    const map = new Map<string, T[]>()
    for (const item of items) {
      const key = getGroupKey(item)
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(item)
    }
    return Array.from(map.entries())
      .map(([key, groupItems]) => ({
        key,
        label: key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
        items: groupItems,
      }))
      .sort((a, b) => b.items.length - a.items.length)
  }, [items, groupBy, getGroupKey, allLabel])

  const toggleGroup = (key: string) => {
    setCollapsedGroups(prev => {
      const next = new Set(prev)
      if (next.has(key)) { next.delete(key) } else { next.add(key) }
      return next
    })
  }

  const resetCollapsed = () => setCollapsedGroups(new Set())

  return { groups, collapsedGroups, toggleGroup, resetCollapsed }
}

export function GroupHeader({
  groupKey,
  label,
  count,
  isCollapsed,
  onToggle,
  theme,
}: {
  groupKey: string
  label: string
  count: number
  isCollapsed: boolean
  onToggle: (key: string) => void
  theme: ThemeClasses
}) {
  return (
    <button
      className={`w-full flex items-center justify-between py-2.5 px-4 rounded-lg ${theme.glass} border ${theme.border} mb-3 hover:opacity-80 transition-opacity cursor-pointer`}
      onClick={() => onToggle(groupKey)}
    >
      <div className="flex items-center gap-2">
        {isCollapsed
          ? <ChevronRight className={`h-4 w-4 ${theme.textSecondary}`} />
          : <ChevronDown className={`h-4 w-4 ${theme.textSecondary}`} />}
        <span className={`font-semibold text-sm ${theme.textPrimary}`}>{label}</span>
      </div>
      <span className={`text-sm font-medium ${theme.textSecondary}`}>{count}</span>
    </button>
  )
}

export function GroupBySelect({
  value,
  onChange,
  options,
  theme,
}: {
  value: string
  onChange: (value: string) => void
  options: Record<string, string>
  theme: ThemeClasses
}) {
  return (
    <div className="relative min-w-40">
      <LayoutGrid className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} focus:outline-none text-sm appearance-none cursor-pointer`}
      >
        {Object.entries(options).map(([key, label]) => (
          <option key={key} value={key}>{label}</option>
        ))}
      </select>
    </div>
  )
}

/**
 * Extract the gene name (non-rsid) from a string.
 */
export function isValidGene(gene?: string): boolean {
  if (!gene) return false
  return (
    gene !== 'Unknown' &&
    gene !== 'Multiple' &&
    gene !== 'Multiple genes' &&
    gene !== 'Multiple markers' &&
    !gene.startsWith('rs')
  )
}
