'use client'

import React, { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { ExternalLink, Dna, FlaskConical, BookOpen, Activity, X, ChevronDown, ChevronUp, AlertTriangle, Pill, Shield, Atom, RefreshCw } from 'lucide-react'
import { Badge } from '../ui/badge'
import { apiUrl } from '@/lib/api'

// ─── Types ──────────────────────────────────────────────────────

interface TranscriptConsequence {
  gene_symbol?: string
  gene_id?: string
  transcript_id?: string
  consequence_terms?: string[]
  impact?: string
  amino_acids?: string
  codons?: string
  sift_prediction?: string
  sift_score?: number | null
  polyphen_prediction?: string
  polyphen_score?: number | null
  protein_position?: string
}

interface PopulationFrequency {
  allele: string
  frequency: number
}

interface Publication {
  pmid?: string
  title?: string
  journal?: string
  year?: string | number
}

interface VariantDetails {
  found: boolean
  rsid: string
  description?: string
  most_severe_consequence?: string
  allele_string?: string
  chromosome?: string
  position?: number
  transcripts?: TranscriptConsequence[]
  total_transcripts?: number
  clinical_significance?: string[]
  clinvar_ids?: string[]
  population_frequencies?: Record<string, PopulationFrequency>
  clinvar?: {
    found: boolean
    count: number
    ids: string[]
    entries?: Array<{
      uid: string
      title: string
      accession: string
      clinical_significance: string[]
      conditions: string[]
      variation_type: string
    }>
  }
  pharmacogenomics?: { found: boolean; data?: Record<string, unknown> }
  snpedia?: { found: boolean; title?: string; summary?: string }
  publications?: { count: number; items: Publication[] }
  alpha_missense?: {
    found: boolean
    am_pathogenicity?: number
    am_class?: string
    protein_variant?: string
    uniprot_id?: string
    transcript_id?: string
    gene_mean_pathogenicity?: number
    isoform_count?: number
    isoforms?: Array<{
      transcript_id: string
      protein_variant: string
      am_pathogenicity: number
      am_class: string
    }>
    disclaimer?: string
  }
  gnomad?: {
    found: boolean
    source?: string
    variant_id?: string
    variant_type?: string
    af?: number | null
    ac?: number | null
    an?: number | null
    nhomalt?: number | null
    filter_status?: string
    gene?: string
    consequence?: string
    impact?: string
    hgvsc?: string
    hgvsp?: string
    population_frequencies?: Record<string, { name: string; af: number }>
    cadd?: {
      raw?: number | null
      phred?: number | null
      interpretation?: string
    }
    predictions?: {
      sift?: { category?: string; score?: number | null }
      polyphen?: { category?: string; score?: number | null }
    }
    conservation?: {
      primate?: number | null
      mammal?: number | null
      vertebrate?: number | null
    }
    splice_ai?: {
      acceptor_gain?: number | null
      acceptor_loss?: number | null
      donor_gain?: number | null
      donor_loss?: number | null
      max_score?: number | null
    }
  }
  thousand_genomes?: {
    found: boolean
    source?: string
    variant_type?: string
    minor_allele?: string
    maf?: number | null
    mac?: number | null
    ancestral_allele?: string
    population_frequencies?: Record<string, { name: string; af: number }>
  }
  pathogenicity_score?: {
    composite_score: number
    confidence: string
    evidence_count: number
    classification: string
    sources: Record<string, { score: number; weight: number; label: string; raw_value: unknown }>
    conflicts: string[]
    total_weight: number
  }
  chembl?: {
    gene?: string
    found: boolean
    source?: string
    targets?: Array<{ tid: number; target_name: string; uniprot_id?: string }>
    drugs?: Array<{
      drug_name?: string
      chembl_id?: string
      max_phase?: number
      first_approval?: number
      mechanism_of_action?: string
      action_type?: string
      target_name?: string
      uniprot_id?: string
    }>
    warnings?: Array<{
      drug_name?: string
      warning_type?: string
      warning_class?: string
      warning_description?: string
      warning_year?: number
    }>
  }
  fda_drug?: {
    found: boolean
    items?: Array<{
      drug?: string
      found: boolean
      generic_name?: string
      brand_name?: string
      pharm_class?: string
      route?: string
      cyp_enzymes_mentioned?: string[]
      drug_interactions?: string
      indications?: string
      pharmacokinetics?: string
    }>
  }
  alphafold?: {
    gene?: string
    found: boolean
    source?: string
    entry_id?: string
    uniprot_id?: string
    protein_name?: string
    global_confidence?: number
    plddt_very_high?: number
    plddt_confident?: number
    plddt_low?: number
    plddt_very_low?: number
    model_date?: string
    all_isoforms?: Array<{ entry_id?: string; uniprot_id?: string; confidence?: number }>
  }
}

// ─── Props ──────────────────────────────────────────────────────

interface VariantDetailDialogProps {
  rsid: string
  gene?: string
  token?: string
  isDarkMode?: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
}

// ─── Impact badge color ─────────────────────────────────────────

function impactColor(impact?: string): string {
  switch (impact?.toUpperCase()) {
    case 'HIGH': return 'bg-red-500/15 text-red-400 border-red-500/30'
    case 'MODERATE': return 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30'
    case 'LOW': return 'bg-green-500/15 text-green-400 border-green-500/30'
    default: return 'bg-gray-500/15 text-gray-400 border-gray-500/30'
  }
}

function clinSigColor(sig: string): string {
  const s = sig.toLowerCase()
  if (s.includes('pathogenic') && !s.includes('benign')) return 'bg-red-500/15 text-red-400 border-red-500/30'
  if (s.includes('likely_pathogenic')) return 'bg-orange-500/15 text-orange-400 border-orange-500/30'
  if (s.includes('uncertain')) return 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30'
  if (s.includes('benign')) return 'bg-green-500/15 text-green-400 border-green-500/30'
  return 'bg-gray-500/15 text-gray-400 border-gray-500/30'
}

function formatFrequency(freq: number): string {
  if (freq === 0) return '0%'
  if (freq < 0.0001) return `${(freq * 100).toExponential(1)}%`
  return `${(freq * 100).toFixed(3)}%`
}

function formatPopName(name: string): string {
  return name
    .replace('gnomAD exomes: ', '')
    .replace('gnomAD genomes: ', '')
    .replace('gnomAD exomes (global)', 'Global (Exomes)')
    .replace('gnomAD genomes (global)', 'Global (Genomes)')
    .replace('1000 Genomes (global)', '1000G Global')
    .replace('afr', 'African')
    .replace('amr', 'American')
    .replace('asj', 'Ashkenazi Jewish')
    .replace('eas', 'East Asian')
    .replace('fin', 'Finnish')
    .replace('mid', 'Middle Eastern')
    .replace('nfe', 'Non-Finnish European')
    .replace('sas', 'South Asian')
    .replace('remaining', 'Other')
    .replace('ami', 'Amish')
    .replace('eur', 'European')
    .replace('sas', 'South Asian')
}

function classificationColor(cls: string): string {
  switch (cls) {
    case 'pathogenic': return 'text-red-400'
    case 'likely_pathogenic': return 'text-orange-400'
    case 'uncertain': return 'text-yellow-400'
    case 'likely_benign': return 'text-blue-400'
    case 'benign': return 'text-green-400'
    default: return 'text-gray-400'
  }
}

function classificationBg(cls: string): string {
  switch (cls) {
    case 'pathogenic': return 'bg-red-500/15 border-red-500/30'
    case 'likely_pathogenic': return 'bg-orange-500/15 border-orange-500/30'
    case 'uncertain': return 'bg-yellow-500/15 border-yellow-500/30'
    case 'likely_benign': return 'bg-blue-500/15 border-blue-500/30'
    case 'benign': return 'bg-green-500/15 border-green-500/30'
    default: return 'bg-gray-500/15 border-gray-500/30'
  }
}

function scoreBarColor(score: number): string {
  if (score >= 0.8) return 'bg-red-500'
  if (score >= 0.6) return 'bg-orange-500'
  if (score >= 0.3) return 'bg-yellow-500'
  if (score >= 0.15) return 'bg-blue-500'
  return 'bg-green-500'
}

function confidenceBadge(conf: string): string {
  switch (conf) {
    case 'high': return 'bg-green-500/15 text-green-400 border-green-500/30'
    case 'moderate': return 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30'
    case 'low': return 'bg-orange-500/15 text-orange-400 border-orange-500/30'
    default: return 'bg-gray-500/15 text-gray-400 border-gray-500/30'
  }
}

// ─── Component ──────────────────────────────────────────────────

export default function VariantDetailDialog({
  rsid,
  gene,
  token,
  isDarkMode = false,
  open,
  onOpenChange,
}: VariantDetailDialogProps) {
  const [details, setDetails] = useState<VariantDetails | null>(null)
  const [loading, setLoading] = useState(false)
  const [showPubs, setShowPubs] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  const fetchDetails = (forceRefresh = false) => {
    if (!rsid || !token) return
    if (forceRefresh) {
      setRefreshing(true)
    } else {
      setDetails(null)
      setLoading(true)
    }
    setShowPubs(false)

    const url = apiUrl(`/api/annotations/variant-details/${rsid}${forceRefresh ? '?refresh=true' : ''}`)
    fetch(url, {
      credentials: 'include',
    })
      .then((res) => res.json())
      .then((data) => setDetails(data))
      .catch(() => setDetails({ found: false, rsid }))
      .finally(() => {
        setLoading(false)
        setRefreshing(false)
      })
  }

  useEffect(() => {
    if (!open || !rsid || !token) return
    fetchDetails(false)
  }, [open, rsid, token])

  const bg = isDarkMode ? 'bg-gray-900/95' : 'bg-white'
  const border = isDarkMode ? 'border-white/10' : 'border-gray-200'
  const textPrimary = isDarkMode ? 'text-gray-100' : 'text-gray-900'
  const textSecondary = isDarkMode ? 'text-gray-400' : 'text-gray-500'
  const cardBg = isDarkMode ? 'bg-white/5' : 'bg-gray-50'

  if (!open) return null

  const modal = (
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions
    <div onClick={(e) => e.stopPropagation()} onMouseDown={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()}>
      {/* Backdrop */}
      <div className="fixed inset-0 z-50 bg-black/60" aria-hidden="true" />
      {/* Scrollable wrapper */}
      <div
        role="dialog"
        aria-modal="true"
        className="fixed inset-0 z-50 overflow-y-auto overscroll-contain"
      >
        <div className="flex min-h-full items-center justify-center py-8 px-4">
          <div
            className={`relative w-full max-w-6xl flex flex-col gap-6 p-6 ${bg} ${border} border rounded-2xl`}
          >
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-gradient-to-br from-blue-500/20 to-purple-500/20 border border-blue-500/30">
                <Dna className="h-5 w-5 text-blue-400" />
              </div>
              <div>
                <h2 className={`text-lg font-bold ${textPrimary}`}>
                  {rsid}
                  {gene && gene !== 'Unknown' && !gene.startsWith('rs') && (
                    <span className={`ml-2 text-sm font-normal ${textSecondary}`}>({gene})</span>
                  )}
                </h2>
                <p className={textSecondary}>
                  {loading ? 'Loading annotation data…' : details?.most_severe_consequence || 'Variant annotation details'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => fetchDetails(true)}
                disabled={refreshing || loading}
                title="Refresh from external APIs"
                className={`p-1.5 rounded-lg ${isDarkMode ? 'hover:bg-white/10' : 'hover:bg-gray-100'} transition-colors disabled:opacity-40`}
              >
                <RefreshCw className={`h-4 w-4 ${textSecondary} ${refreshing ? 'animate-spin' : ''}`} />
              </button>
              <button
                onClick={() => onOpenChange(false)}
                className={`p-1.5 rounded-lg ${isDarkMode ? 'hover:bg-white/10' : 'hover:bg-gray-100'} transition-colors`}
              >
                <X className={`h-4 w-4 ${textSecondary}`} />
              </button>
            </div>
          </div>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-blue-500 border-t-transparent" />
          </div>
        )}

        {!loading && details && !details.found && (
          <p className={`text-center py-8 ${textSecondary}`}>No annotation data found for {rsid}</p>
        )}

        {!loading && details?.found && (
          <div className="space-y-4">

            {/* ── Location & Alleles ── */}
            {(details.chromosome || details.allele_string) && (
              <div className={`${cardBg} rounded-xl p-4 border ${border}`}>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                  {details.chromosome && (
                    <div>
                      <span className={`text-xs font-medium ${textSecondary} block`}>Chromosome</span>
                      <span className={`font-mono ${textPrimary}`}>{details.chromosome}</span>
                    </div>
                  )}
                  {details.position && (
                    <div>
                      <span className={`text-xs font-medium ${textSecondary} block`}>Position</span>
                      <span className={`font-mono ${textPrimary}`}>{details.position.toLocaleString()}</span>
                    </div>
                  )}
                  {details.allele_string && (
                    <div>
                      <span className={`text-xs font-medium ${textSecondary} block`}>Alleles</span>
                      <span className={`font-mono ${textPrimary}`}>{details.allele_string}</span>
                    </div>
                  )}
                  {details.most_severe_consequence && (
                    <div>
                      <span className={`text-xs font-medium ${textSecondary} block`}>Most Severe</span>
                      <span className={textPrimary}>{details.most_severe_consequence}</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── Variant Description ── */}
            {details.description && (
              <div className={`${cardBg} rounded-xl p-4 border ${border}`}>
                <p className={`text-sm leading-relaxed ${textSecondary}`}>{details.description}</p>
              </div>
            )}

            {/* ── Composite Pathogenicity Score ── */}
            {details.pathogenicity_score && details.pathogenicity_score.evidence_count > 0 && (() => {
              const ps = details.pathogenicity_score
              const pct = Math.round(ps.composite_score * 100)
              const clsLabel = ps.classification.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
              const sourceEntries = Object.entries(ps.sources).sort(([,a], [,b]) => b.weight - a.weight)
              return (
                <div className={`${cardBg} rounded-xl p-4 border ${border}`}>
                  <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-3 flex items-center gap-1.5`}>
                    <Activity className="h-3.5 w-3.5" /> Composite Pathogenicity Score
                    <Badge variant="outline" className={`${confidenceBadge(ps.confidence)} text-[10px] ml-1`}>
                      {ps.confidence} confidence
                    </Badge>
                    <Badge variant="outline" className="bg-gray-500/10 text-gray-400 border-gray-500/20 text-[10px]">
                      {ps.evidence_count} sources
                    </Badge>
                  </h4>

                  {/* Score bar + classification */}
                  <div className="flex items-center gap-3 mb-3">
                    <div className="flex-1">
                      <div className="h-3 rounded-full bg-gray-700/50 overflow-hidden relative">
                        <div
                          className={`h-full rounded-full ${scoreBarColor(ps.composite_score)} transition-all duration-500`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                    <span className={`text-lg font-bold font-mono ${classificationColor(ps.classification)}`}>
                      {pct}%
                    </span>
                  </div>

                  <div className={`inline-block rounded-lg px-3 py-1 border text-sm font-medium mb-3 ${classificationBg(ps.classification)} ${classificationColor(ps.classification)}`}>
                    {clsLabel}
                  </div>

                  {/* Per-source breakdown */}
                  <div className="space-y-1.5 mt-2">
                    {sourceEntries.map(([src, info]) => (
                      <div key={src} className="flex items-center gap-2 text-xs">
                        <span className={`w-28 truncate ${textSecondary}`}>{src.replace(/_/g, ' ')}</span>
                        <div className="flex-1 h-1.5 rounded-full bg-gray-700/40 overflow-hidden">
                          <div
                            className={`h-full rounded-full ${scoreBarColor(info.score)}`}
                            style={{ width: `${Math.round(info.score * 100)}%` }}
                          />
                        </div>
                        <span className={`w-10 text-right font-mono ${textSecondary}`}>
                          {(info.score * 100).toFixed(0)}%
                        </span>
                        <span className={`w-8 text-right font-mono text-[10px] ${textSecondary}`}>
                          ×{info.weight}
                        </span>
                      </div>
                    ))}
                  </div>

                  {/* Conflicts */}
                  {ps.conflicts.length > 0 && (
                    <div className="mt-3 space-y-1">
                      {ps.conflicts.map((c, i) => (
                        <div key={i} className="flex items-start gap-1.5 text-xs text-amber-400">
                          <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" />
                          <span>{c}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })()}

            {/* ── Clinical Significance ── */}
            {details.clinical_significance && details.clinical_significance.length > 0 && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex items-center gap-1.5`}>
                  <Activity className="h-3.5 w-3.5" /> Clinical Significance
                  {details.clinvar?.count ? (
                    <Badge variant="outline" className="bg-orange-500/10 text-orange-400 border-orange-500/20 text-[10px] ml-1">
                      {details.clinvar.count} ClinVar {details.clinvar.count === 1 ? 'report' : 'reports'}
                    </Badge>
                  ) : null}
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {details.clinical_significance.map((sig) => (
                    <Badge key={sig} variant="outline" className={`${clinSigColor(sig)} text-xs`}>
                      {sig.replace(/_/g, ' ')}
                    </Badge>
                  ))}
                </div>

                {/* ClinVar entries with conditions and links */}
                {details.clinvar?.entries && details.clinvar.entries.length > 0 && (
                  <div className={`mt-3 space-y-2 rounded-lg border ${isDarkMode ? 'border-orange-500/20 bg-orange-500/5' : 'border-orange-200 bg-orange-50/50'} p-3`}>
                    <span className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider`}>ClinVar Reports</span>
                    {details.clinvar.entries.map((entry, idx) => (
                      <div key={`${entry.uid}-${idx}`} className={`flex items-start justify-between gap-2 text-xs ${isDarkMode ? 'border-b border-white/5 pb-1.5' : 'border-b border-gray-200/50 pb-1.5'} last:border-0`}>
                        <div className="flex-1 min-w-0">
                          <div className="flex flex-wrap gap-1 mb-0.5">
                            {entry.clinical_significance.map((sig) => (
                              <Badge key={sig} variant="outline" className={`${clinSigColor(sig)} text-[10px]`}>
                                {sig.replace(/_/g, ' ')}
                              </Badge>
                            ))}
                          </div>
                          {entry.conditions.length > 0 && (
                            <span className={textSecondary}>{entry.conditions.join('; ')}</span>
                          )}
                        </div>
                        <a
                          href={`https://www.ncbi.nlm.nih.gov/clinvar/variation/${entry.uid}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-orange-400 hover:text-orange-300 shrink-0 transition-colors"
                        >
                          {entry.accession || entry.uid} <ExternalLink className="h-3 w-3" />
                        </a>
                      </div>
                    ))}
                  </div>
                )}

                {/* Fallback: Legacy VCV/ID links when no entries */}
                {(!details.clinvar?.entries || details.clinvar.entries.length === 0) && (
                  <>
                    {details.clinvar_ids && details.clinvar_ids.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {details.clinvar_ids.filter(id => id.startsWith('VCV')).slice(0, 3).map((id) => (
                          <a
                            key={id}
                            href={`https://www.ncbi.nlm.nih.gov/clinvar/variation/${id.replace('VCV', '')}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-orange-400 hover:text-orange-300 transition-colors"
                          >
                            ClinVar {id} <ExternalLink className="h-3 w-3" />
                          </a>
                        ))}
                      </div>
                    )}
                    {details.clinvar?.ids && details.clinvar.ids.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {details.clinvar.ids.map((id) => (
                          <a
                            key={`cv-${id}`}
                            href={`https://www.ncbi.nlm.nih.gov/clinvar/variation/${id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-orange-400 hover:text-orange-300 transition-colors"
                          >
                            ClinVar:{id} <ExternalLink className="h-3 w-3" />
                          </a>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            {/* ── Transcript Consequences ── */}
            {details.transcripts && details.transcripts.length > 0 && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex items-center gap-1.5`}>
                  <Dna className="h-3.5 w-3.5" /> Transcript Consequences
                  <span className={`text-xs font-normal ${textSecondary}`}>
                    ({details.transcripts.length}{details.total_transcripts && details.total_transcripts > details.transcripts.length ? ` of ${details.total_transcripts}` : ''})
                  </span>
                </h4>
                <div className="overflow-x-auto rounded-xl border border-white/5">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className={`${cardBg} border-b ${border}`}>
                        <th className={`text-left px-3 py-2 font-medium ${textSecondary}`}>Gene</th>
                        <th className={`text-left px-3 py-2 font-medium ${textSecondary}`}>Consequence</th>
                        <th className={`text-left px-3 py-2 font-medium ${textSecondary}`}>Impact</th>
                        <th className={`text-left px-3 py-2 font-medium ${textSecondary}`}>AA</th>
                        <th className={`text-left px-3 py-2 font-medium ${textSecondary}`}>SIFT</th>
                        <th className={`text-left px-3 py-2 font-medium ${textSecondary}`}>PolyPhen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {details.transcripts.map((tc, i) => (
                        <tr key={i} className={`border-b ${border} last:border-b-0`}>
                          <td className={`px-3 py-2 ${textPrimary} font-medium`}>
                            {tc.gene_symbol || '—'}
                            {tc.transcript_id && (
                              <div className={`text-[10px] ${textSecondary} font-mono`}>{tc.transcript_id}</div>
                            )}
                          </td>
                          <td className={`px-3 py-2 ${textPrimary}`}>
                            {tc.consequence_terms?.join(', ') || '—'}
                          </td>
                          <td className="px-3 py-2">
                            <Badge variant="outline" className={`${impactColor(tc.impact)} text-[10px] px-1.5 py-0`}>
                              {tc.impact || '—'}
                            </Badge>
                          </td>
                          <td className={`px-3 py-2 font-mono ${textPrimary}`}>
                            {tc.amino_acids || '—'}
                            {tc.protein_position && <span className={`text-[10px] ${textSecondary} ml-1`}>p.{tc.protein_position}</span>}
                          </td>
                          <td className={`px-3 py-2 ${textPrimary}`}>
                            {tc.sift_prediction ? (
                              <span className={tc.sift_prediction.includes('deleterious') ? 'text-red-400' : 'text-green-400'}>
                                {tc.sift_prediction.replace(/_/g, ' ')}
                                {tc.sift_score != null && <span className={`text-[10px] ${textSecondary} ml-1`}>({tc.sift_score.toFixed(3)})</span>}
                              </span>
                            ) : '—'}
                          </td>
                          <td className={`px-3 py-2 ${textPrimary}`}>
                            {tc.polyphen_prediction ? (
                              <span className={tc.polyphen_prediction.includes('damaging') ? 'text-red-400' : 'text-green-400'}>
                                {tc.polyphen_prediction.replace(/_/g, ' ')}
                                {tc.polyphen_score != null && <span className={`text-[10px] ${textSecondary} ml-1`}>({tc.polyphen_score.toFixed(3)})</span>}
                              </span>
                            ) : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}



            {/* ── Pharmacogenomics ── */}
            {details.pharmacogenomics?.found && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex items-center gap-1.5`}>
                  <FlaskConical className="h-3.5 w-3.5" /> Pharmacogenomics
                </h4>
                <div className={`${cardBg} rounded-xl p-3 border ${border}`}>
                  <p className={`text-xs ${textPrimary}`}>ClinPGx pharmacogenomic data available for this variant.</p>
                  <a
                    href={`https://www.clinpgx.org/variant/${rsid}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-purple-400 hover:text-purple-300 mt-1 transition-colors"
                  >
                    View on ClinPGx <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              </div>
            )}

            {/* ── AlphaMissense AI Prediction ── */}
            {details.alpha_missense?.found && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex items-center gap-1.5`}>
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-400" /> AlphaMissense AI Prediction
                  <Badge variant="outline" className="bg-amber-500/15 text-amber-400 border-amber-500/30 text-[10px] px-1.5 py-0 ml-1">
                    AI
                  </Badge>
                </h4>
                <div className={`${cardBg} rounded-xl p-3 border ${border} space-y-2.5`}>
                  {/* Pathogenicity score bar */}
                  {details.alpha_missense.am_pathogenicity != null && (
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className={`text-xs ${textSecondary}`}>Pathogenicity Score</span>
                        <span className={`text-sm font-mono font-bold ${
                          details.alpha_missense.am_pathogenicity > 0.564 ? 'text-red-400' :
                          details.alpha_missense.am_pathogenicity < 0.34 ? 'text-green-400' : 'text-amber-400'
                        }`}>
                          {details.alpha_missense.am_pathogenicity.toFixed(4)}
                        </span>
                      </div>
                      <div className="relative h-2 rounded-full bg-gradient-to-r from-green-500 via-amber-500 to-red-500 overflow-hidden">
                        <div
                          className="absolute top-0 h-full w-1 bg-white rounded-full shadow-md"
                          style={{ left: `${Math.min(details.alpha_missense.am_pathogenicity * 100, 100)}%` }}
                        />
                      </div>
                      <div className="flex justify-between mt-0.5">
                        <span className={`text-[10px] ${textSecondary}`}>Benign (0)</span>
                        <span className={`text-[10px] ${textSecondary}`}>Pathogenic (1)</span>
                      </div>
                    </div>
                  )}
                  {/* Classification badge */}
                  {details.alpha_missense.am_class && (
                    <div className="flex items-center gap-2">
                      <span className={`text-xs ${textSecondary}`}>Classification:</span>
                      <Badge variant="outline" className={`text-xs ${
                        details.alpha_missense.am_class === 'likely_pathogenic' ? 'bg-red-500/15 text-red-400 border-red-500/30' :
                        details.alpha_missense.am_class === 'likely_benign' ? 'bg-green-500/15 text-green-400 border-green-500/30' :
                        'bg-amber-500/15 text-amber-400 border-amber-500/30'
                      }`}>
                        {details.alpha_missense.am_class.replace(/_/g, ' ')}
                      </Badge>
                    </div>
                  )}
                  {/* Protein variant */}
                  {details.alpha_missense.protein_variant && (
                    <div className="flex items-center gap-2">
                      <span className={`text-xs ${textSecondary}`}>Protein change:</span>
                      <span className={`text-xs font-mono ${textPrimary}`}>{details.alpha_missense.protein_variant}</span>
                    </div>
                  )}
                  {/* Gene-level mean pathogenicity */}
                  {details.alpha_missense.gene_mean_pathogenicity != null && (
                    <div className="flex items-center gap-2">
                      <span className={`text-xs ${textSecondary}`}>Gene avg pathogenicity:</span>
                      <span className={`text-xs font-mono ${
                        details.alpha_missense.gene_mean_pathogenicity > 0.564 ? 'text-red-400' :
                        details.alpha_missense.gene_mean_pathogenicity < 0.34 ? 'text-green-400' : 'text-amber-400'
                      }`}>
                        {details.alpha_missense.gene_mean_pathogenicity.toFixed(4)}
                      </span>
                    </div>
                  )}
                  {/* Isoform predictions */}
                  {details.alpha_missense.isoforms && details.alpha_missense.isoforms.length > 1 && (
                    <div>
                      <span className={`text-xs ${textSecondary}`}>Isoform predictions ({details.alpha_missense.isoform_count}):</span>
                      <div className="mt-1 space-y-1">
                        {details.alpha_missense.isoforms.slice(0, 5).map((iso, i) => (
                          <div key={i} className={`flex items-center gap-2 text-[11px] ${cardBg} rounded px-2 py-1`}>
                            <span className={`font-mono ${textSecondary} truncate max-w-[140px]`} title={iso.transcript_id}>{iso.transcript_id}</span>
                            <span className={`font-mono ${textSecondary}`}>{iso.protein_variant}</span>
                            <span className={`font-mono ${
                              iso.am_pathogenicity > 0.564 ? 'text-red-400' :
                              iso.am_pathogenicity < 0.34 ? 'text-green-400' : 'text-amber-400'
                            }`}>
                              {iso.am_pathogenicity.toFixed(4)}
                            </span>
                            <Badge variant="outline" className={`text-[9px] px-1 py-0 ${
                              iso.am_class === 'likely_pathogenic' ? 'bg-red-500/15 text-red-400 border-red-500/30' :
                              iso.am_class === 'likely_benign' ? 'bg-green-500/15 text-green-400 border-green-500/30' :
                              'bg-amber-500/15 text-amber-400 border-amber-500/30'
                            }`}>
                              {iso.am_class.replace(/_/g, ' ')}
                            </Badge>
                          </div>
                        ))}
                        {details.alpha_missense.isoforms.length > 5 && (
                          <span className={`text-[10px] ${textSecondary}`}>+ {details.alpha_missense.isoforms.length - 5} more isoforms</span>
                        )}
                      </div>
                    </div>
                  )}
                  {/* Disclaimer */}
                  <div className={`flex items-start gap-1.5 pt-1.5 border-t ${border}`}>
                    <AlertTriangle className="h-3 w-3 text-amber-400 mt-0.5 flex-shrink-0" />
                    <p className={`text-[10px] ${textSecondary} leading-relaxed`}>
                      {details.alpha_missense.disclaimer || 'AlphaMissense predictions are AI-generated (DeepMind) and have NOT been clinically validated. Do not use for clinical decision-making.'}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* ── gnomAD Population Frequencies ── */}
            {details.gnomad?.found && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex items-center gap-1.5`}>
                  <Activity className="h-3.5 w-3.5" /> gnomAD
                  {details.gnomad.source && (
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                      {details.gnomad.source.replace('gnomad_', '').replace('gnomad', 'local')}
                    </Badge>
                  )}
                </h4>
                <div className={`${cardBg} rounded-xl p-3 border ${border} space-y-2`}>
                  {/* Global AF summary */}
                  <div className="flex items-center justify-between">
                    <span className={`text-xs ${textSecondary}`}>Global Allele Frequency</span>
                    <span className={`text-sm font-mono font-semibold ${
                      details.gnomad.af != null && details.gnomad.af < 0.001 ? 'text-red-400' :
                      details.gnomad.af != null && details.gnomad.af < 0.01 ? 'text-amber-400' :
                      'text-green-400'
                    }`}>
                      {details.gnomad.af != null ? formatFrequency(details.gnomad.af) : 'N/A'}
                    </span>
                  </div>

                  {/* AC / AN / nhomalt */}
                  <div className="grid grid-cols-3 gap-2">
                    {details.gnomad.ac != null && (
                      <div className={`text-center p-1.5 rounded-lg ${isDarkMode ? 'bg-white/5' : 'bg-gray-100'}`}>
                        <div className={`text-[10px] ${textSecondary}`}>Allele Count</div>
                        <div className={`text-xs font-mono ${textPrimary}`}>{details.gnomad.ac.toLocaleString()}</div>
                      </div>
                    )}
                    {details.gnomad.an != null && (
                      <div className={`text-center p-1.5 rounded-lg ${isDarkMode ? 'bg-white/5' : 'bg-gray-100'}`}>
                        <div className={`text-[10px] ${textSecondary}`}>Allele Number</div>
                        <div className={`text-xs font-mono ${textPrimary}`}>{details.gnomad.an.toLocaleString()}</div>
                      </div>
                    )}
                    {details.gnomad.nhomalt != null && (
                      <div className={`text-center p-1.5 rounded-lg ${isDarkMode ? 'bg-white/5' : 'bg-gray-100'}`}>
                        <div className={`text-[10px] ${textSecondary}`}>Homozygotes</div>
                        <div className={`text-xs font-mono ${textPrimary}`}>{details.gnomad.nhomalt.toLocaleString()}</div>
                      </div>
                    )}
                  </div>

                  {/* Filter status */}
                  {details.gnomad.filter_status && (
                    <div className="flex items-center gap-1.5">
                      <span className={`text-[10px] ${textSecondary}`}>Filter:</span>
                      <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${
                        details.gnomad.filter_status === 'PASS' ? 'bg-green-500/15 text-green-400 border-green-500/30' :
                        'bg-amber-500/15 text-amber-400 border-amber-500/30'
                      }`}>
                        {details.gnomad.filter_status}
                      </Badge>
                    </div>
                  )}

                  {/* CADD Pathogenicity Score */}
                  {details.gnomad.cadd && details.gnomad.cadd.phred != null && (
                    <div className={`pt-2 border-t ${border}`}>
                      <div className={`text-[10px] font-semibold ${textSecondary} uppercase tracking-wider mb-1.5`}>
                        CADD Pathogenicity
                      </div>
                      <div className="flex items-center gap-3">
                        <div className={`flex items-center justify-center w-12 h-12 rounded-full border-2 ${
                          details.gnomad.cadd.phred >= 30 ? 'border-red-500 text-red-400' :
                          details.gnomad.cadd.phred >= 20 ? 'border-orange-500 text-orange-400' :
                          details.gnomad.cadd.phred >= 15 ? 'border-amber-500 text-amber-400' :
                          details.gnomad.cadd.phred >= 10 ? 'border-yellow-500 text-yellow-400' :
                          'border-green-500 text-green-400'
                        }`}>
                          <span className="text-sm font-bold">{details.gnomad.cadd.phred.toFixed(1)}</span>
                        </div>
                        <div className="flex-1">
                          <div className={`text-xs font-medium ${textPrimary}`}>PHRED Score</div>
                          {details.gnomad.cadd.interpretation && (
                            <div className={`text-[10px] ${textSecondary}`}>{details.gnomad.cadd.interpretation}</div>
                          )}
                          {details.gnomad.cadd.raw != null && (
                            <div className={`text-[10px] ${textSecondary}`}>Raw: {details.gnomad.cadd.raw.toFixed(4)}</div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Functional Predictions (SIFT + PolyPhen) */}
                  {details.gnomad.predictions && (
                    <div className={`pt-2 border-t ${border}`}>
                      <div className={`text-[10px] font-semibold ${textSecondary} uppercase tracking-wider mb-1.5`}>
                        Functional Predictions
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        {details.gnomad.predictions.sift && (
                          <div className={`p-1.5 rounded-lg ${isDarkMode ? 'bg-white/5' : 'bg-gray-100'}`}>
                            <div className={`text-[10px] ${textSecondary}`}>SIFT</div>
                            <Badge variant="outline" className={`text-[10px] px-1.5 py-0 mt-0.5 ${
                              details.gnomad.predictions.sift.category?.toLowerCase() === 'deleterious' ? 'bg-red-500/15 text-red-400 border-red-500/30' :
                              'bg-green-500/15 text-green-400 border-green-500/30'
                            }`}>
                              {details.gnomad.predictions.sift.category || 'N/A'}
                            </Badge>
                            {details.gnomad.predictions.sift.score != null && (
                              <div className={`text-[10px] font-mono ${textSecondary} mt-0.5`}>{details.gnomad.predictions.sift.score.toFixed(3)}</div>
                            )}
                          </div>
                        )}
                        {details.gnomad.predictions.polyphen && (
                          <div className={`p-1.5 rounded-lg ${isDarkMode ? 'bg-white/5' : 'bg-gray-100'}`}>
                            <div className={`text-[10px] ${textSecondary}`}>PolyPhen</div>
                            <Badge variant="outline" className={`text-[10px] px-1.5 py-0 mt-0.5 ${
                              details.gnomad.predictions.polyphen.category?.toLowerCase().includes('damaging') ? 'bg-red-500/15 text-red-400 border-red-500/30' :
                              details.gnomad.predictions.polyphen.category?.toLowerCase() === 'possibly_damaging' ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' :
                              'bg-green-500/15 text-green-400 border-green-500/30'
                            }`}>
                              {details.gnomad.predictions.polyphen.category?.replace(/_/g, ' ') || 'N/A'}
                            </Badge>
                            {details.gnomad.predictions.polyphen.score != null && (
                              <div className={`text-[10px] font-mono ${textSecondary} mt-0.5`}>{details.gnomad.predictions.polyphen.score.toFixed(3)}</div>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Conservation Scores (PhyloP) */}
                  {details.gnomad.conservation && (
                    <div className={`pt-2 border-t ${border}`}>
                      <div className={`text-[10px] font-semibold ${textSecondary} uppercase tracking-wider mb-1.5`}>
                        Conservation (PhyloP)
                      </div>
                      <div className="grid grid-cols-3 gap-2">
                        {details.gnomad.conservation.primate != null && (
                          <div className={`text-center p-1.5 rounded-lg ${isDarkMode ? 'bg-white/5' : 'bg-gray-100'}`}>
                            <div className={`text-[10px] ${textSecondary}`}>Primate</div>
                            <div className={`text-xs font-mono font-medium ${
                              details.gnomad.conservation.primate > 0 ? 'text-green-400' : 'text-gray-400'
                            }`}>{details.gnomad.conservation.primate.toFixed(2)}</div>
                          </div>
                        )}
                        {details.gnomad.conservation.mammal != null && (
                          <div className={`text-center p-1.5 rounded-lg ${isDarkMode ? 'bg-white/5' : 'bg-gray-100'}`}>
                            <div className={`text-[10px] ${textSecondary}`}>Mammal</div>
                            <div className={`text-xs font-mono font-medium ${
                              details.gnomad.conservation.mammal > 0 ? 'text-green-400' : 'text-gray-400'
                            }`}>{details.gnomad.conservation.mammal.toFixed(2)}</div>
                          </div>
                        )}
                        {details.gnomad.conservation.vertebrate != null && (
                          <div className={`text-center p-1.5 rounded-lg ${isDarkMode ? 'bg-white/5' : 'bg-gray-100'}`}>
                            <div className={`text-[10px] ${textSecondary}`}>Vertebrate</div>
                            <div className={`text-xs font-mono font-medium ${
                              details.gnomad.conservation.vertebrate > 0 ? 'text-green-400' : 'text-gray-400'
                            }`}>{details.gnomad.conservation.vertebrate.toFixed(2)}</div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* SpliceAI Scores */}
                  {details.gnomad.splice_ai && details.gnomad.splice_ai.max_score != null && details.gnomad.splice_ai.max_score > 0 && (
                    <div className={`pt-2 border-t ${border}`}>
                      <div className={`text-[10px] font-semibold ${textSecondary} uppercase tracking-wider mb-1.5`}>
                        SpliceAI
                        {details.gnomad.splice_ai.max_score >= 0.8 && (
                          <Badge variant="outline" className="ml-1.5 text-[10px] px-1.5 py-0 bg-red-500/15 text-red-400 border-red-500/30">
                            High Impact
                          </Badge>
                        )}
                        {details.gnomad.splice_ai.max_score >= 0.5 && details.gnomad.splice_ai.max_score < 0.8 && (
                          <Badge variant="outline" className="ml-1.5 text-[10px] px-1.5 py-0 bg-amber-500/15 text-amber-400 border-amber-500/30">
                            Moderate Impact
                          </Badge>
                        )}
                      </div>
                      <div className="space-y-1">
                        {[
                          { label: 'Acceptor Gain', value: details.gnomad.splice_ai.acceptor_gain },
                          { label: 'Acceptor Loss', value: details.gnomad.splice_ai.acceptor_loss },
                          { label: 'Donor Gain', value: details.gnomad.splice_ai.donor_gain },
                          { label: 'Donor Loss', value: details.gnomad.splice_ai.donor_loss },
                        ].filter(s => s.value != null && s.value > 0).map(s => (
                          <div key={s.label} className="flex items-center gap-2">
                            <span className={`text-[10px] ${textSecondary} w-24 text-right`}>{s.label}</span>
                            <div className={`flex-1 h-3 rounded-full overflow-hidden ${isDarkMode ? 'bg-white/5' : 'bg-gray-200'}`}>
                              <div
                                className={`h-full rounded-full ${
                                  s.value! >= 0.8 ? 'bg-linear-to-r from-red-500 to-red-400' :
                                  s.value! >= 0.5 ? 'bg-linear-to-r from-amber-500 to-amber-400' :
                                  'bg-linear-to-r from-blue-500 to-cyan-400'
                                }`}
                                style={{ width: `${Math.min(s.value! * 100, 100)}%` }}
                              />
                            </div>
                            <span className={`text-[10px] font-mono ${textPrimary} w-10 text-right`}>
                              {s.value!.toFixed(2)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Population frequency bars */}
                  {details.gnomad.population_frequencies && Object.keys(details.gnomad.population_frequencies).length > 0 && (
                    <div className={`pt-2 border-t ${border}`}>
                      <div className={`text-[10px] font-semibold ${textSecondary} uppercase tracking-wider mb-1.5`}>
                        Population Frequencies
                      </div>
                      <div className="space-y-1">
                        {Object.entries(details.gnomad.population_frequencies)
                          .sort(([, a], [, b]) => (b.af || 0) - (a.af || 0))
                          .map(([code, pop]) => {
                            const maxAf = Math.max(
                              ...Object.values(details.gnomad!.population_frequencies!).map(p => p.af || 0),
                              0.001
                            )
                            const barWidth = maxAf > 0 ? Math.max((pop.af / maxAf) * 100, 1) : 1
                            return (
                              <div key={code} className="flex items-center gap-2">
                                <span className={`text-[10px] ${textSecondary} w-28 truncate text-right`}>
                                  {pop.name}
                                </span>
                                <div className={`flex-1 h-3 rounded-full overflow-hidden ${isDarkMode ? 'bg-white/5' : 'bg-gray-200'}`}>
                                  <div
                                    className="h-full rounded-full bg-linear-to-r from-blue-500 to-cyan-400"
                                    style={{ width: `${barWidth}%` }}
                                  />
                                </div>
                                <span className={`text-[10px] font-mono ${textPrimary} w-16 text-right`}>
                                  {formatFrequency(pop.af)}
                                </span>
                              </div>
                            )
                          })}
                      </div>
                    </div>
                  )}

                  {/* Consequence info from gnomAD */}
                  {(details.gnomad.consequence || details.gnomad.gene) && (
                    <div className={`flex flex-wrap gap-1.5 pt-1.5 border-t ${border}`}>
                      {details.gnomad.gene && (
                        <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${isDarkMode ? 'border-white/20' : ''}`}>
                          {details.gnomad.gene}
                        </Badge>
                      )}
                      {details.gnomad.consequence && (
                        <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${
                          details.gnomad.impact === 'HIGH' ? 'bg-red-500/15 text-red-400 border-red-500/30' :
                          details.gnomad.impact === 'MODERATE' ? 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30' :
                          'bg-gray-500/15 text-gray-400 border-gray-500/30'
                        }`}>
                          {details.gnomad.consequence.replace(/_/g, ' ')}
                        </Badge>
                      )}
                    </div>
                  )}

                  {/* Link to gnomAD browser */}
                  <a
                    href={`https://gnomad.broadinstitute.org/variant/${details.gnomad.variant_id || rsid}?dataset=gnomad_r4`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors"
                  >
                    View on gnomAD Browser <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              </div>
            )}

            {/* ── 1000 Genomes Phase 3 Population Frequencies ── */}
            {details.thousand_genomes?.found && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex items-center gap-1.5`}>
                  <Activity className="h-3.5 w-3.5" /> 1000 Genomes
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                    Phase 3
                  </Badge>
                </h4>
                <div className={`${cardBg} rounded-xl p-3 border ${border} space-y-2`}>
                  {/* MAF summary */}
                  {details.thousand_genomes.maf != null && (
                    <div className="flex items-center justify-between">
                      <span className={`text-xs ${textSecondary}`}>Minor Allele Frequency</span>
                      <span className={`text-sm font-mono font-semibold ${
                        details.thousand_genomes.maf < 0.001 ? 'text-red-400' :
                        details.thousand_genomes.maf < 0.01 ? 'text-amber-400' :
                        'text-green-400'
                      }`}>
                        {formatFrequency(details.thousand_genomes.maf)}
                      </span>
                    </div>
                  )}

                  {/* Minor allele / Ancestral allele / MAC */}
                  <div className="grid grid-cols-3 gap-2">
                    {details.thousand_genomes.minor_allele && (
                      <div className={`text-center p-1.5 rounded-lg ${isDarkMode ? 'bg-white/5' : 'bg-gray-100'}`}>
                        <div className={`text-[10px] ${textSecondary}`}>Minor Allele</div>
                        <div className={`text-xs font-mono ${textPrimary}`}>{details.thousand_genomes.minor_allele}</div>
                      </div>
                    )}
                    {details.thousand_genomes.ancestral_allele && (
                      <div className={`text-center p-1.5 rounded-lg ${isDarkMode ? 'bg-white/5' : 'bg-gray-100'}`}>
                        <div className={`text-[10px] ${textSecondary}`}>Ancestral Allele</div>
                        <div className={`text-xs font-mono ${textPrimary}`}>{details.thousand_genomes.ancestral_allele}</div>
                      </div>
                    )}
                    {details.thousand_genomes.mac != null && (
                      <div className={`text-center p-1.5 rounded-lg ${isDarkMode ? 'bg-white/5' : 'bg-gray-100'}`}>
                        <div className={`text-[10px] ${textSecondary}`}>Minor Allele Count</div>
                        <div className={`text-xs font-mono ${textPrimary}`}>{details.thousand_genomes.mac.toLocaleString()}</div>
                      </div>
                    )}
                  </div>

                  {/* Variant type */}
                  {details.thousand_genomes.variant_type && (
                    <div className="flex items-center gap-1.5">
                      <span className={`text-[10px] ${textSecondary}`}>Type:</span>
                      <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                        {details.thousand_genomes.variant_type}
                      </Badge>
                    </div>
                  )}

                  {/* Population frequency bars */}
                  {details.thousand_genomes.population_frequencies && Object.keys(details.thousand_genomes.population_frequencies).length > 0 && (
                    <div className={`pt-2 border-t ${border}`}>
                      <div className={`text-[10px] font-semibold ${textSecondary} uppercase tracking-wider mb-1.5`}>
                        Super-Population Frequencies
                      </div>
                      <div className="space-y-1">
                        {Object.entries(details.thousand_genomes.population_frequencies)
                          .sort(([, a], [, b]) => (b.af || 0) - (a.af || 0))
                          .map(([code, pop]) => {
                            const maxAf = Math.max(
                              ...Object.values(details.thousand_genomes!.population_frequencies!).map(p => p.af || 0),
                              0.001
                            )
                            const barWidth = maxAf > 0 ? Math.max((pop.af / maxAf) * 100, 1) : 1
                            return (
                              <div key={code} className="flex items-center gap-2">
                                <span className={`text-[10px] ${textSecondary} w-28 truncate text-right`}>
                                  {pop.name}
                                </span>
                                <div className={`flex-1 h-3 rounded-full overflow-hidden ${isDarkMode ? 'bg-white/5' : 'bg-gray-200'}`}>
                                  <div
                                    className="h-full rounded-full bg-linear-to-r from-emerald-500 to-teal-400"
                                    style={{ width: `${barWidth}%` }}
                                  />
                                </div>
                                <span className={`text-[10px] font-mono ${textPrimary} w-16 text-right`}>
                                  {formatFrequency(pop.af)}
                                </span>
                              </div>
                            )
                          })}
                      </div>
                    </div>
                  )}

                  {/* Link to Ensembl browser */}
                  <a
                    href={`https://www.ensembl.org/Homo_sapiens/Variation/Population?v=${rsid}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors"
                  >
                    View on Ensembl <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              </div>
            )}

            {/* ── ChEMBL Drug Mechanisms ── */}
            {details.chembl?.found && details.chembl.drugs && details.chembl.drugs.length > 0 && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex items-center gap-1.5`}>
                  <Pill className="h-3.5 w-3.5" /> Drug Mechanisms
                  <Badge variant="outline" className="bg-indigo-500/10 text-indigo-400 border-indigo-500/20 text-[10px] ml-1">
                    ChEMBL
                  </Badge>
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                    {details.chembl.drugs.length} drug{details.chembl.drugs.length !== 1 ? 's' : ''}
                  </Badge>
                </h4>
                <div className={`${cardBg} rounded-xl p-3 border ${border} space-y-2`}>
                  {details.chembl.drugs.slice(0, 8).map((drug, i) => (
                    <div key={i} className={`flex items-start justify-between gap-2 text-xs ${i > 0 ? `border-t ${border} pt-2` : ''}`}>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className={`font-medium ${textPrimary}`}>{drug.drug_name || 'Unknown'}</span>
                          {drug.max_phase != null && drug.max_phase >= 4 && (
                            <Badge variant="outline" className="bg-green-500/15 text-green-400 border-green-500/30 text-[10px] px-1 py-0">
                              Approved
                            </Badge>
                          )}
                          {drug.max_phase != null && drug.max_phase > 0 && drug.max_phase < 4 && (
                            <Badge variant="outline" className="bg-blue-500/15 text-blue-400 border-blue-500/30 text-[10px] px-1 py-0">
                              Phase {drug.max_phase}
                            </Badge>
                          )}
                          {drug.first_approval && (
                            <span className={`text-[10px] ${textSecondary}`}>({drug.first_approval})</span>
                          )}
                        </div>
                        {drug.mechanism_of_action && (
                          <div className={`text-[10px] ${textSecondary} mt-0.5`}>{drug.mechanism_of_action}</div>
                        )}
                        {drug.target_name && (
                          <div className={`text-[10px] ${textSecondary}`}>Target: {drug.target_name}</div>
                        )}
                      </div>
                      {drug.chembl_id && (
                        <a
                          href={`https://www.ebi.ac.uk/chembl/compound_report_card/${drug.chembl_id}/`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-indigo-400 hover:text-indigo-300 shrink-0 text-[10px] transition-colors"
                        >
                          {drug.chembl_id} <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </div>
                  ))}
                  {details.chembl.drugs.length > 8 && (
                    <span className={`text-[10px] ${textSecondary}`}>+ {details.chembl.drugs.length - 8} more drugs</span>
                  )}

                  {/* Drug warnings */}
                  {details.chembl.warnings && details.chembl.warnings.length > 0 && (
                    <div className={`pt-2 border-t ${border}`}>
                      <div className={`text-[10px] font-semibold ${textSecondary} uppercase tracking-wider mb-1.5 flex items-center gap-1`}>
                        <AlertTriangle className="h-3 w-3 text-amber-400" /> Drug Warnings
                      </div>
                      {details.chembl.warnings.map((w, i) => (
                        <div key={i} className="flex items-start gap-1.5 text-[10px] mb-1">
                          <AlertTriangle className="h-3 w-3 text-amber-400 mt-0.5 shrink-0" />
                          <div>
                            <span className={`font-medium ${textPrimary}`}>{w.drug_name}</span>
                            {w.warning_year && <span className={`${textSecondary} ml-1`}>({w.warning_year})</span>}
                            {w.warning_description && <span className={`${textSecondary} ml-1`}>— {w.warning_description}</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── FDA Drug Interactions ── */}
            {details.fda_drug?.found && details.fda_drug.items && details.fda_drug.items.length > 0 && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex items-center gap-1.5`}>
                  <Shield className="h-3.5 w-3.5" /> FDA Drug Interactions
                  <Badge variant="outline" className="bg-rose-500/10 text-rose-400 border-rose-500/20 text-[10px] ml-1">
                    FDA
                  </Badge>
                </h4>
                <div className={`${cardBg} rounded-xl p-3 border ${border} space-y-3`}>
                  {details.fda_drug.items.slice(0, 5).map((item, i) => (
                    <div key={i} className={`${i > 0 ? `border-t ${border} pt-2` : ''}`}>
                      <div className="flex items-center gap-1.5 flex-wrap mb-1">
                        <span className={`text-xs font-medium ${textPrimary}`}>
                          {item.generic_name || item.drug || 'Unknown'}
                        </span>
                        {item.brand_name && (
                          <span className={`text-[10px] ${textSecondary}`}>({item.brand_name})</span>
                        )}
                        {item.route && (
                          <Badge variant="outline" className={`text-[10px] px-1 py-0 ${isDarkMode ? 'border-white/20' : ''}`}>
                            {item.route}
                          </Badge>
                        )}
                      </div>
                      {item.cyp_enzymes_mentioned && item.cyp_enzymes_mentioned.length > 0 && (
                        <div className="flex flex-wrap gap-1 mb-1">
                          {item.cyp_enzymes_mentioned.map((cyp) => (
                            <Badge key={cyp} variant="outline" className="bg-rose-500/15 text-rose-400 border-rose-500/30 text-[10px] px-1.5 py-0">
                              {cyp}
                            </Badge>
                          ))}
                        </div>
                      )}
                      {item.drug_interactions && (
                        <p className={`text-[10px] ${textSecondary} leading-relaxed line-clamp-3`}>
                          {item.drug_interactions}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ── AlphaFold Protein Structure ── */}
            {details.alphafold?.found && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex items-center gap-1.5`}>
                  <Atom className="h-3.5 w-3.5" /> Protein Structure Confidence
                  <Badge variant="outline" className="bg-teal-500/10 text-teal-400 border-teal-500/20 text-[10px] ml-1">
                    AlphaFold
                  </Badge>
                </h4>
                <div className={`${cardBg} rounded-xl p-3 border ${border} space-y-2`}>
                  {details.alphafold.protein_name && (
                    <div>
                      <span className={`text-xs ${textPrimary} font-medium`}>{details.alphafold.protein_name}</span>
                    </div>
                  )}

                  {/* Global confidence score */}
                  {details.alphafold.global_confidence != null && (
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className={`text-xs ${textSecondary}`}>Global Confidence (pLDDT)</span>
                        <span className={`text-sm font-mono font-bold ${
                          details.alphafold.global_confidence >= 90 ? 'text-blue-400' :
                          details.alphafold.global_confidence >= 70 ? 'text-cyan-400' :
                          details.alphafold.global_confidence >= 50 ? 'text-yellow-400' : 'text-orange-400'
                        }`}>
                          {details.alphafold.global_confidence.toFixed(1)}
                        </span>
                      </div>
                      <div className="h-2 rounded-full bg-gray-700/50 overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            details.alphafold.global_confidence >= 90 ? 'bg-blue-500' :
                            details.alphafold.global_confidence >= 70 ? 'bg-cyan-500' :
                            details.alphafold.global_confidence >= 50 ? 'bg-yellow-500' : 'bg-orange-500'
                          }`}
                          style={{ width: `${Math.min(details.alphafold.global_confidence, 100)}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* pLDDT breakdown */}
                  {(details.alphafold.plddt_very_high != null || details.alphafold.plddt_confident != null) && (
                    <div className="grid grid-cols-4 gap-1.5 mt-1">
                      {[
                        { label: 'Very High', value: details.alphafold.plddt_very_high, color: 'text-blue-400' },
                        { label: 'Confident', value: details.alphafold.plddt_confident, color: 'text-cyan-400' },
                        { label: 'Low', value: details.alphafold.plddt_low, color: 'text-yellow-400' },
                        { label: 'Very Low', value: details.alphafold.plddt_very_low, color: 'text-orange-400' },
                      ].map(({ label, value, color }) => value != null && (
                        <div key={label} className={`text-center p-1.5 rounded-lg ${isDarkMode ? 'bg-white/5' : 'bg-gray-100'}`}>
                          <div className={`text-[10px] ${textSecondary}`}>{label}</div>
                          <div className={`text-xs font-mono font-medium ${color}`}>
                            {(value * 100).toFixed(1)}%
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* UniProt + external links */}
                  <div className="flex flex-wrap gap-2 pt-1.5">
                    {details.alphafold.entry_id && (
                      <a
                        href={`https://alphafold.ebi.ac.uk/entry/${details.alphafold.entry_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-teal-400 hover:text-teal-300 transition-colors"
                      >
                        AlphaFold DB <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                    {details.alphafold.uniprot_id && (
                      <a
                        href={`https://www.uniprot.org/uniprot/${details.alphafold.uniprot_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-xs text-teal-400 hover:text-teal-300 transition-colors"
                      >
                        UniProt <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>

                  <div className={`flex items-start gap-1.5 pt-1.5 border-t ${border}`}>
                    <AlertTriangle className="h-3 w-3 text-amber-400 mt-0.5 shrink-0" />
                    <p className={`text-[10px] ${textSecondary} leading-relaxed`}>
                      AlphaFold predictions are AI-generated (DeepMind). Confidence scores reflect model certainty, not clinical validation.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* ── SNPedia ── */}
            {details.snpedia?.found && details.snpedia.summary && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex items-center gap-1.5`}>
                  <BookOpen className="h-3.5 w-3.5" /> SNPedia
                </h4>
                <div className={`${cardBg} rounded-xl p-3 border ${border}`}>
                  <p className={`text-xs ${textSecondary} leading-relaxed`}>{details.snpedia.summary}</p>
                  <a
                    href={`https://www.snpedia.com/index.php/${rsid}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-green-400 hover:text-green-300 mt-1 transition-colors"
                  >
                    View on SNPedia <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              </div>
            )}

            {/* ── Publications ── */}
            {details.publications && details.publications.count > 0 && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex items-center gap-1.5`}>
                  <BookOpen className="h-3.5 w-3.5" /> Publications
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                    {details.publications.count}
                  </Badge>
                </h4>
                {!showPubs ? (
                  <button
                    type="button"
                    onClick={() => setShowPubs(true)}
                    className={`${cardBg} rounded-xl p-3 border ${border} w-full text-left hover:border-blue-500/30 transition-colors`}
                  >
                    <span className={`text-xs ${textPrimary}`}>
                      {details.publications.count} publication{details.publications.count !== 1 ? 's' : ''} found
                    </span>
                    <span className={`text-xs ${textSecondary} ml-2`}>Click to view</span>
                  </button>
                ) : (
                  <div className={`${cardBg} rounded-xl p-3 border ${border} space-y-2 max-h-60 overflow-y-auto`}>
                    {details.publications.items.map((pub, i) => (
                      <div key={i} className={`text-xs border-b ${border} last:border-b-0 pb-2 last:pb-0`}>
                        {pub.pmid ? (
                          <a
                            href={`https://pubmed.ncbi.nlm.nih.gov/${pub.pmid}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-400 hover:text-blue-300 transition-colors leading-relaxed"
                          >
                            {pub.title || `PMID: ${pub.pmid}`}
                            <ExternalLink className="h-3 w-3 inline ml-1" />
                          </a>
                        ) : (
                          <span className={textPrimary}>{pub.title}</span>
                        )}
                        {(pub.journal || pub.year) && (
                          <div className={`${textSecondary} mt-0.5`}>
                            {pub.journal}{pub.journal && pub.year ? ' · ' : ''}{pub.year}
                          </div>
                        )}
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={() => setShowPubs(false)}
                      className={`text-xs ${isDarkMode ? 'text-blue-400 hover:text-blue-300' : 'text-blue-600 hover:text-blue-500'} transition-colors`}
                    >
                      Collapse
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* ── External Links ── */}
            <div className={`flex flex-wrap gap-2 pt-2 border-t ${border}`}>
              <a href={`https://www.ncbi.nlm.nih.gov/snp/${rsid}`} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors">
                dbSNP <ExternalLink className="h-3 w-3" />
              </a>
              <a href={`https://www.ncbi.nlm.nih.gov/clinvar/?term=${rsid}`} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-orange-400 hover:text-orange-300 transition-colors">
                ClinVar <ExternalLink className="h-3 w-3" />
              </a>
              <a href={`https://www.ensembl.org/Homo_sapiens/Variation/Explore?v=${rsid}`} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-purple-400 hover:text-purple-300 transition-colors">
                Ensembl <ExternalLink className="h-3 w-3" />
              </a>
              <a href={`https://pubmed.ncbi.nlm.nih.gov/?term=${rsid}`} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-yellow-400 hover:text-yellow-300 transition-colors">
                PubMed <ExternalLink className="h-3 w-3" />
              </a>
              <a href={`https://www.snpedia.com/index.php/${rsid}`} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-green-400 hover:text-green-300 transition-colors">
                SNPedia <ExternalLink className="h-3 w-3" />
              </a>
              {gene && gene !== 'Unknown' && !gene.startsWith('rs') && (
                <>
                  <a href={`https://www.genecards.org/cgi-bin/carddisp.pl?gene=${gene}`} target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 transition-colors">
                    GeneCards <ExternalLink className="h-3 w-3" />
                  </a>
                  <a href={`https://omim.org/search?search=${gene}`} target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-pink-400 hover:text-pink-300 transition-colors">
                    OMIM <ExternalLink className="h-3 w-3" />
                  </a>
                </>
              )}
            </div>
          </div>
        )}
      </div>
      </div>
      </div>
    </div>
  )

  return typeof document !== 'undefined' ? createPortal(modal, document.body) : null
}
