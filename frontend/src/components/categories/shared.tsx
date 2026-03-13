'use client'

import React, { useState } from 'react'
import { LucideIcon, AlertTriangle, CheckCircle, Flame, Info, ExternalLink, Search } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'
import { Badge } from '../ui/badge'
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
}

/**
 * Compact research database links with optional "View Details" dialog.
 * When token is provided, shows a button to open the annotation dialog.
 */
export function VariantLinks({ rsid, gene, token, isDarkMode = false }: VariantLinksProps) {
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
  title: string
  text: string
  borderColorClass?: string
  bgTintClass?: string
  theme: ThemeClasses
}

export function DisclaimerCard({
  icon: Icon = Info,
  title,
  text,
  borderColorClass = 'border-blue-500/20',
  bgTintClass = 'bg-blue-500/5',
  theme,
}: DisclaimerCardProps) {
  return (
    <Card className={`${theme.glass} border ${theme.border} ring-0 ${borderColorClass} ${bgTintClass}`}>
      <CardContent className="pt-6">
        <div className="flex items-start space-x-3">
          <Icon className="h-5 w-5 text-blue-500 mt-0.5" />
          <div>
            <h3 className={`font-semibold ${theme.textPrimary} mb-2`}>{title}</h3>
            <p className={`text-sm ${theme.textSecondary} leading-relaxed`}>{text}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
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
