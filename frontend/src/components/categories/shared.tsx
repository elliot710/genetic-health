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
            <div className={`p-3 rounded-xl bg-gradient-to-br ${gradientFrom} ${gradientTo} border ${borderColor}`}>
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
          <div className={`p-4 rounded-xl bg-gradient-to-br ${gradientFrom} ${gradientTo} border ${borderColor}`}>
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
      {isHomo ? 'Homozygous' : 'Heterozygous'}
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
  let cleaned = raw.replace(/[_]+/g, ' ').trim()
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
      next.has(key) ? next.delete(key) : next.add(key)
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
