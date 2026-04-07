'use client'

import React, { useState, useEffect, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { ExternalLink, Dna, FlaskConical, BookOpen, Activity, X, ChevronDown, ChevronUp, AlertTriangle, Pill, Shield, Atom, RefreshCw, Bookmark } from 'lucide-react'
import { Badge } from '../ui/badge'
import { apiUrl } from '@/lib/api'
import SmartInsights from '../SmartInsights'

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
  user_genotype?: string
  cache_hit?: boolean
  gwas_catalog?: {
    found: boolean
    associations?: Array<{
      rsid?: string
      trait?: string
      mapped_trait?: string
      p_value?: number
      or_beta?: number
      risk_allele_frequency?: number
    }>
    top_trait?: string
    top_p_value?: number
    genome_wide_significant?: boolean
  }
  clingen?: {
    found: boolean
    gene_symbol?: string
    strongest_classification?: string
    is_definitive?: boolean
    is_disputed?: boolean
    disease_count?: number
    curations?: Array<{
      disease_label?: string
      moi?: string
      classification?: string
      report_url?: string
    }>
  }
  open_targets?: {
    found: boolean
    gene_symbol?: string
    associations?: Array<{ disease_name: string; score: number; genetic_association_score?: number }>
    top_disease?: string
    max_score?: number
    has_strong_genetic_evidence?: boolean
  }
  gnomad_tx?: {
    found: boolean
    gene?: string
    consequence?: string
    lof?: string
    mean_expression?: number
    transcript_count?: number
    top_tissues?: Record<string, number>
    transcripts?: Array<{
      ensg?: string
      symbol?: string
      csq?: string
      lof?: string
      mean_expression?: number
      top_tissues?: Record<string, number>
    }>
  }
  gene_constraint?: {
    pli?: number
    loeuf?: number
    mis_z?: number
    syn_z?: number
  }
  clinvar_gene_stats?: {
    total_submissions?: number
    pathogenic_count?: number
    uncertain_count?: number
    conflict_count?: number
  }
  clinvar_local?: {
    found: boolean
    genes?: string[]
    clinical_significances?: string[]
    gene_conditions?: Array<{ gene?: string; conditions?: string[] }>
    review_statuses?: string[]
    has_conflicting_interpretations?: boolean
    molecular_consequences?: string[]
    allele_frequencies?: Record<string, number>
  }
}

// ─── Props ──────────────────────────────────────────────────────

interface VariantDetailDialogProps {
  rsid: string
  gene?: string
  genotype?: string
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
  if (s.includes('conflicting')) return 'bg-amber-500/15 text-amber-400 border-amber-500/30'
  // Check likely_pathogenic BEFORE pathogenic — "likely_pathogenic" contains "pathogenic"
  if (s.includes('likely_pathogenic') || s.includes('likely pathogenic')) return 'bg-orange-500/15 text-orange-400 border-orange-500/30'
  if (s.includes('pathogenic') && !s.includes('benign')) return 'bg-red-500/15 text-red-400 border-red-500/30'
  if (s.includes('uncertain')) return 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30'
  if (s.includes('benign')) return 'bg-green-500/15 text-green-400 border-green-500/30'
  if (s.includes('drug') && s.includes('response')) return 'bg-purple-500/15 text-purple-400 border-purple-500/30'
  if (s.includes('risk factor')) return 'bg-orange-500/15 text-orange-400 border-orange-500/30'
  if (s.includes('protective')) return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
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
  genotype: genotypeProp,
  token,
  isDarkMode = false,
  open,
  onOpenChange,
}: VariantDetailDialogProps) {
  const [details, setDetails] = useState<VariantDetails | null>(null)
  const [loading, setLoading] = useState(false)
  const [showPubs, setShowPubs] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [isSaved, setIsSaved] = useState(false)
  const [saveBusy, setSaveBusy] = useState(false)

  // Keep a ref so fetchDetails always reads the latest details without stale closure issues
  const detailsRef = useRef<VariantDetails | null>(null)
  useEffect(() => { detailsRef.current = details }, [details])

  // Check if this variant is already saved when the dialog opens
  useEffect(() => {
    if (!open || !rsid) return
    fetch(apiUrl('/auth/saved-variants'), { credentials: 'include' })
      .then(r => r.ok ? r.json() : [])
      .then((list: { rsid: string }[]) => setIsSaved(list.some(v => v.rsid === rsid)))
      .catch(() => {})
  }, [open, rsid])

  const toggleSave = async () => {
    if (saveBusy) return
    setSaveBusy(true)
    try {
      if (isSaved) {
        const res = await fetch(apiUrl(`/auth/saved-variants/${rsid}`), {
          method: 'DELETE',
          credentials: 'include',
        })
        if (res.ok) setIsSaved(false)
      } else {
        const res = await fetch(apiUrl('/auth/saved-variants'), {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            rsid,
            gene: gene || details?.transcripts?.[0]?.gene_symbol || null,
            genotype: genotypeProp || details?.user_genotype || null,
            most_severe_consequence: details?.most_severe_consequence || null,
            clinical_significance: details?.clinical_significance?.[0] || null,
          }),
        })
        if (res.ok || res.status === 409) setIsSaved(true)
      }
    } catch { /* ignore */ }
    finally { setSaveBusy(false) }
  }

  const fetchDetails = useCallback((forceRefresh = false) => {
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
      .then((data) => {
        // Use detailsRef (not details state) so we always read the latest value,
        // even when this callback is called from a setTimeout (stale closure fix).
        if (forceRefresh && !data?.user_genotype && detailsRef.current?.user_genotype) {
          data = { ...data, user_genotype: detailsRef.current.user_genotype }
        }
        setDetails(data)
        // Broadcast updated pathogenicity score so panel cards can sync
        if (forceRefresh && data?.pathogenicity_score) {
          const ps = data.pathogenicity_score
          window.dispatchEvent(new CustomEvent('pathogenicity-update', {
            detail: {
              rsid,
              score: Math.round(ps.composite_score * 100),
              classification: ps.classification || 'unknown',
              confidence: ps.confidence || 'none',
              evidence_count: ps.evidence_count || 0,
            },
          }))
        }
      })
      .catch(() => setDetails({ found: false, rsid }))
      .finally(() => {
        setLoading(false)
        setRefreshing(false)
      })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rsid, token])

  useEffect(() => {
    if (!open || !rsid || !token) return
    fetchDetails(false)
  }, [open, rsid, token, fetchDetails])

  // Close on Escape key
  useEffect(() => {
    if (!open) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onOpenChange(false)
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, onOpenChange])

  const bg = isDarkMode ? 'bg-gray-900/95' : 'bg-white'
  const border = isDarkMode ? 'border-white/10' : 'border-gray-200'
  const textPrimary = isDarkMode ? 'text-gray-100' : 'text-gray-900'
  const textSecondary = isDarkMode ? 'text-gray-400' : 'text-gray-500'
  const cardBg = isDarkMode ? 'bg-white/5' : 'bg-gray-50'

  // Use the prop genotype if provided, otherwise fall back to the user_genotype
  // returned by the backend (looked up from their analysis variants).
  const genotype = genotypeProp || details?.user_genotype

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
        <div className="flex min-h-full items-center justify-center py-4 sm:py-8 px-2 sm:px-4" onClick={() => onOpenChange(false)}>
          <div
            className={`relative w-full max-w-6xl flex flex-col gap-4 sm:gap-6 p-4 sm:p-6 ${bg} ${border} border rounded-2xl`}
            onClick={(e) => e.stopPropagation()}
          >
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-linear-to-br from-blue-500/20 to-purple-500/20 border border-blue-500/30">
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
                onClick={toggleSave}
                disabled={saveBusy || loading}
                title={isSaved ? 'Remove from saved variants' : 'Save variant'}
                className={`p-1.5 rounded-lg ${isDarkMode ? 'hover:bg-white/10' : 'hover:bg-gray-100'} transition-colors disabled:opacity-40`}
              >
                <Bookmark className={`h-4 w-4 ${isSaved ? 'fill-blue-400 text-blue-400' : textSecondary}`} />
              </button>
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

        {/* Subtle banner shown during background auto-refresh (data still visible) */}
        {refreshing && !loading && (
          <div className={`flex items-center gap-2 text-[11px] ${textSecondary} px-1`}>
            <div className="h-3 w-3 rounded-full border border-blue-400 border-t-transparent animate-spin shrink-0" />
            Refreshing from external APIs…
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
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-sm">
                  {details.chromosome && (
                    <div className="min-w-0">
                      <span className={`text-xs font-medium ${textSecondary} block`}>Chromosome</span>
                      <span className={`font-mono ${textPrimary}`}>{details.chromosome}</span>
                    </div>
                  )}
                  {details.position && (
                    <div className="min-w-0">
                      <span className={`text-xs font-medium ${textSecondary} block`}>Position</span>
                      <span className={`font-mono ${textPrimary}`}>{details.position.toLocaleString()}</span>
                    </div>
                  )}
                  {details.allele_string && (
                    <div className="min-w-0">
                      <span className={`text-xs font-medium ${textSecondary} block`}>Alleles (Ref/Alt)</span>
                      <span
                        className={`font-mono ${textPrimary} block truncate`}
                        title={details.allele_string}
                      >{details.allele_string}</span>
                    </div>
                  )}
                  {details.most_severe_consequence && (
                    <div className="min-w-0">
                      <span className={`text-xs font-medium ${textSecondary} block`}>Most Severe</span>
                      <span className={`${textPrimary} block truncate`} title={details.most_severe_consequence}>{details.most_severe_consequence}</span>
                    </div>
                  )}
                  {genotype && (() => {
                    const parts = details.allele_string?.split('/') ?? []
                    const ref = parts[0]?.toUpperCase()
                    // Handle multi-alt: A/G,T → alts = ['G', 'T']
                    const alts = parts.slice(1).flatMap(p => p.split(',').map(a => a.trim().toUpperCase())).filter(Boolean)
                    const gt = genotype.toUpperCase()
                    // Detect consumer indel codes: DD, DI, ID, II (diploid) or D, I (hemizygous X/Y)
                    const isIndel = /^[DI]{1,2}$/.test(gt)
                    // Split into individual allele tokens, handling slash-separated formats too
                    const rawAlleles = gt.includes('/') ? gt.split('/') : gt.split('')
                    const alleles = rawAlleles.filter(a => a && a !== '/')
                    const isHemizygous = isIndel && alleles.length === 1
                    // For indels: D=deletion allele, I=insertion allele
                    // ref shorter → deletion (D) is ref; alt shorter → insertion (I) is ref
                    const refLen = ref === '-' || ref === '.' ? 0 : (ref?.length ?? 0)
                    const altLen = alts[0] === '-' || alts[0] === '.' ? 0 : (alts[0]?.length ?? 0)
                    const dIsRef = isIndel ? refLen <= altLen : false
                    return (
                      <div>
                        <span className={`text-xs font-medium ${textSecondary} block`}>Your Genotype</span>
                        <div className="flex items-center gap-1 font-mono mt-0.5">
                          {alleles.map((a, i) => {
                            let isRef: boolean
                            let isAlt: boolean
                            if (isIndel) {
                              isRef = dIsRef ? a === 'D' : a === 'I'
                              isAlt = dIsRef ? a === 'I' : a === 'D'
                            } else {
                              isRef = !!(ref && a === ref)
                              isAlt = alts.length > 0 && alts.includes(a)
                            }
                            return (
                              <span
                                key={i}
                                title={isRef ? 'Reference allele' : isAlt ? 'Alternate allele' : 'Unknown allele'}
                                className={`inline-flex items-center justify-center w-6 h-6 rounded text-xs font-bold border ${
                                  isAlt
                                    ? 'bg-orange-500/20 text-orange-300 border-orange-500/40'
                                    : isRef
                                      ? 'bg-green-500/15 text-green-400 border-green-500/30'
                                      : 'bg-gray-500/15 text-gray-400 border-gray-500/30'
                                }`}
                              >
                                {a}
                              </span>
                            )
                          })}
                          {isHemizygous && (
                            <span className={`text-xs ${textSecondary} ml-1`} title="Hemizygous — only one allele (X/Y chromosome)">hemi</span>
                          )}
                        </div>
                      </div>
                    )
                  })()}
                </div>
                {/* Genotype interpretation row */}
                {genotype && details.allele_string && (() => {
                  const parts = details.allele_string.split('/')
                  const ref = parts[0]?.toUpperCase()
                  const alts = parts.slice(1).flatMap(p => p.split(',').map(a => a.trim().toUpperCase())).filter(Boolean)
                  const gt = genotype.toUpperCase()
                  const isIndel = /^[DI]{1,2}$/.test(gt)
                  const alleles = gt.includes('/') ? gt.split('/').filter(a => a && a !== '/') : gt.split('')

                  let altCount: number
                  let refCount: number
                  let altLabel: string

                  if (isIndel) {
                    // D=shorter, I=longer; determine mapping from ref/alt lengths
                    const refLen = ref === '-' || ref === '.' ? 0 : (ref?.length ?? 0)
                    const altLens = alts.map(a => a === '-' || a === '.' ? 0 : a.length)
                    const hasShorter = altLens.some(l => l < refLen)
                    const hasLonger = altLens.some(l => l > refLen)
                    if (hasShorter && hasLonger) {
                      // Mixed-direction multi-allelic: both D and I are alts
                      refCount = 0
                      altCount = alleles.length
                      altLabel = alts.join('/')
                    } else {
                      const dIsRef = refLen <= (altLens[0] ?? 0)
                      refCount = alleles.filter(a => dIsRef ? a === 'D' : a === 'I').length
                      altCount = alleles.filter(a => dIsRef ? a === 'I' : a === 'D').length
                      altLabel = alts[0] || (dIsRef ? 'I' : 'D')
                    }
                  } else {
                    altCount = alleles.filter(a => alts.includes(a)).length
                    refCount = alleles.filter(a => a === ref).length
                    const carriedAlts = [...new Set(alleles.filter(a => alts.includes(a)))]
                    altLabel = carriedAlts.join('/') || alts[0] || ''
                  }

                  const hasAlt = altCount > 0
                  const isXLinked = details.chromosome?.toUpperCase() === 'X'
                  const isSingleAllele = alleles.length === 1
                  const zygosity =
                    refCount === alleles.length ? 'homozygous reference' :
                    altCount === alleles.length
                      ? (isXLinked || isSingleAllele ? 'hemizygous' : 'homozygous alternate') :
                    refCount > 0 && hasAlt ? 'heterozygous' : null
                  const refDisplay = isIndel ? `${ref} (reference)` : ref
                  const altDisplay = isIndel ? `${alts[0] || 'alternate'} (alternate)` : altLabel
                  const implication =
                    zygosity === 'homozygous reference'
                      ? `Your genotype (${genotype}) matches the reference allele (${refDisplay}) on both chromosomes — this is the common variant with no change from the reference genome.`
                      : zygosity === 'hemizygous'
                        ? `Your genotype (${genotype}) carries the alternate allele (${altDisplay}) on the X chromosome — as a hemizygous variant, you have a single copy with no second allele to compensate.`
                        : zygosity === 'homozygous alternate'
                          ? `Your genotype (${genotype}) carries the alternate allele (${altDisplay}) on both chromosomes — you have two copies of the variant. The reference allele (${refDisplay}) is absent. This is the highest-dosage form of this variant.`
                          : zygosity === 'heterozygous'
                            ? `Your genotype (${genotype}) is one copy of the reference (${refDisplay}) and one copy of the alternate (${altDisplay}) — you carry one variant allele. This is the heterozygous state.`
                            : null
                  if (!implication) return null
                  return (
                    <div className={`mt-3 pt-3 border-t ${border} flex items-start gap-2`}>
                      <span className={`text-xs leading-relaxed ${textSecondary}`}>
                        <span className={`font-semibold ${
                          zygosity === 'homozygous alternate' || zygosity === 'hemizygous' ? 'text-orange-400' :
                          zygosity === 'heterozygous' ? 'text-yellow-400' : 'text-green-400'
                        }`}>
                          {zygosity?.replace(/\b\w/g, c => c.toUpperCase())}
                        </span>
                        {' — '}
                        {implication}
                      </span>
                    </div>
                  )
                })()}
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
                  <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-3 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
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
                        <span className={`w-20 sm:w-28 shrink-0 truncate ${textSecondary}`}>{src.replace(/_/g, ' ')}</span>
                        <div className="flex-1 h-1.5 rounded-full bg-gray-700/40 overflow-hidden">
                          <div
                            className={`h-full rounded-full ${scoreBarColor(info.score)}`}
                            style={{ width: `${Math.round(info.score * 100)}%` }}
                          />
                        </div>
                        <span className={`w-8 sm:w-10 text-right font-mono ${textSecondary}`}>
                          {(info.score * 100).toFixed(0)}%
                        </span>
                        <span className={`w-7 sm:w-8 text-right font-mono text-[10px] ${textSecondary}`}>
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

                  {/* Interpretation guidance when conflicting */}
                  {ps.conflicts.length > 0 && (
                    <div className={`mt-2 text-[10px] ${textSecondary} leading-relaxed border-t ${border} pt-2`}>
                      <Shield className="h-3 w-3 inline mr-1 text-amber-400" />
                      Conflicting evidence means different sources disagree on this variant&apos;s clinical impact.
                      The composite score may not accurately reflect actual risk. Consult a genetic counselor for clinical interpretation.
                    </div>
                  )}
                </div>
              )
            })()}

            {/* ── Data Source Availability ── */}
            {(() => {
              const psKeys = Object.keys(details.pathogenicity_score?.sources ?? {})
              const sources = [
                { key: 'clinvar', label: 'ClinVar', available: !!(details.clinvar?.found || (details.clinical_significance && details.clinical_significance.length > 0) || psKeys.includes('clinvar')) },
                { key: 'ensembl', label: 'Ensembl VEP', available: !!(details.transcripts && details.transcripts.length > 0) || psKeys.includes('ensembl_vep') },
                { key: 'gnomad', label: 'gnomAD', available: !!details.gnomad?.found || psKeys.includes('gnomad') },
                { key: 'alpha_missense', label: 'AlphaMissense', available: !!details.alpha_missense?.found || psKeys.includes('alpha_missense') },
                { key: 'snpedia', label: 'SNPedia', available: !!details.snpedia?.found },
                { key: 'publications', label: 'Literature', available: !!(details.publications && details.publications.count > 0) },
                { key: 'gnomad_tx', label: 'gnomAD-tx', available: !!details.gnomad_tx?.found },
                { key: 'gene_constraint', label: 'Gene Constraint', available: !!(details.gene_constraint?.pli != null || details.gene_constraint?.loeuf != null) },
                { key: 'gwas', label: 'GWAS', available: !!details.gwas_catalog?.found },
                { key: 'clingen', label: 'ClinGen', available: !!details.clingen?.found },
                { key: 'open_targets', label: 'Open Targets', available: !!details.open_targets?.found },
              ]
              const available = sources.filter(s => s.available)
              const unavailable = sources.filter(s => !s.available)
              return unavailable.length > 0 ? (
                <div className={`flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] ${textSecondary}`}>
                  <span className="font-medium">Sources:</span>
                  {available.map(s => (
                    <span key={s.key} className="text-green-400/70">✓ {s.label}</span>
                  ))}
                  {unavailable.map(s => (
                    <span key={s.key} className="text-gray-500">✗ {s.label}</span>
                  ))}
                </div>
              ) : null
            })()}

            {/* ── Clinical Significance ── */}
            {details.clinical_significance && details.clinical_significance.length > 0 && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
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

                    {/* Mixed-evidence warning when ClinVar entries contain BOTH pathogenic and benign reports */}
                    {(() => {
                      const allSigs = details.clinvar!.entries!.flatMap(e => e.clinical_significance.map(s => s.toLowerCase()))
                      const hasPathogenic = allSigs.some(s => s.includes('pathogenic') && !s.includes('conflicting') && !s.includes('benign'))
                      const hasBenign = allSigs.some(s => s.includes('benign'))
                      if (hasPathogenic && hasBenign) {
                        return (
                          <div className={`flex items-start gap-1.5 text-[10px] ${textSecondary} leading-relaxed mt-2 pt-2 border-t ${border}`}>
                            <AlertTriangle className="h-3 w-3 text-amber-400 mt-0.5 shrink-0" />
                            <span>
                              This variant has <span className="text-red-400 font-medium">pathogenic</span> and <span className="text-green-400 font-medium">benign</span> reports
                              from different submitters. The clinical significance depends on the specific condition and the submitting laboratory&apos;s evidence.
                              Verify with your healthcare provider.
                            </span>
                          </div>
                        )
                      }
                      return null
                    })()}
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

            {/* ── Ensembl VEP Summary ── */}
            {details.transcripts && details.transcripts.length > 0 && (() => {
              const tcs = details.transcripts
              const uniqueGenes = [...new Set(tcs.map(t => t.gene_symbol).filter(Boolean))]
              const impacts: Record<string, number> = {}
              tcs.forEach(t => { if (t.impact) impacts[t.impact] = (impacts[t.impact] || 0) + 1 })
              const worstSift = tcs.reduce<TranscriptConsequence | null>((worst, t) => {
                if (t.sift_score == null) return worst
                if (!worst || worst.sift_score == null || t.sift_score < worst.sift_score) return t
                return worst
              }, null)
              const worstPP = tcs.reduce<TranscriptConsequence | null>((worst, t) => {
                if (t.polyphen_score == null) return worst
                if (!worst || worst.polyphen_score == null || t.polyphen_score > worst.polyphen_score) return t
                return worst
              }, null)
              const uniqueConsequences = [...new Set(tcs.flatMap(t => t.consequence_terms || []))]
              return (
                <div>
                  <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
                    <Dna className="h-3.5 w-3.5" /> Ensembl VEP
                    <Badge variant="outline" className="bg-blue-500/10 text-blue-400 border-blue-500/20 text-[10px] ml-1">
                      {details.total_transcripts || tcs.length} transcripts
                    </Badge>
                  </h4>
                  <div className={`${cardBg} rounded-xl p-3 border ${border} space-y-2.5`}>
                    {/* Consequence types */}
                    <div>
                      <span className={`text-[10px] font-semibold ${textSecondary} uppercase tracking-wider`}>Consequence Types</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {uniqueConsequences.map(c => (
                          <Badge key={c} variant="outline" className={`text-[10px] px-1.5 py-0 ${
                            c.includes('stop') || c.includes('frameshift') || c.includes('splice_donor') || c.includes('splice_acceptor')
                              ? 'bg-red-500/15 text-red-400 border-red-500/30'
                              : c.includes('missense') || c.includes('inframe')
                                ? 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30'
                                : c.includes('synonymous') || c.includes('coding_sequence')
                                  ? 'bg-green-500/15 text-green-400 border-green-500/30'
                                  : 'bg-gray-500/15 text-gray-400 border-gray-500/30'
                          }`}>
                            {c}
                          </Badge>
                        ))}
                      </div>
                    </div>

                    {/* Affected genes & impact distribution */}
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <span className={`text-[10px] font-semibold ${textSecondary} uppercase tracking-wider`}>Affected Genes</span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {uniqueGenes.slice(0, 6).map(g => (
                            <Badge key={g} variant="outline" className="bg-blue-500/10 text-blue-400 border-blue-500/20 text-[10px] px-1.5 py-0">
                              {g}
                            </Badge>
                          ))}
                          {uniqueGenes.length > 6 && (
                            <span className={`text-[10px] ${textSecondary}`}>+{uniqueGenes.length - 6} more</span>
                          )}
                        </div>
                      </div>
                      <div>
                        <span className={`text-[10px] font-semibold ${textSecondary} uppercase tracking-wider`}>Impact Distribution</span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {['HIGH', 'MODERATE', 'LOW', 'MODIFIER'].filter(imp => impacts[imp]).map(imp => (
                            <Badge key={imp} variant="outline" className={`${impactColor(imp)} text-[10px] px-1.5 py-0`}>
                              {imp} ({impacts[imp]})
                            </Badge>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* Functional predictions summary */}
                    {(worstSift || worstPP) && (
                      <div className={`pt-2 border-t ${border}`}>
                        <span className={`text-[10px] font-semibold ${textSecondary} uppercase tracking-wider`}>Functional Predictions</span>
                        <div className="grid grid-cols-2 gap-2 mt-1">
                          {worstSift && (
                            <div className={`p-1.5 rounded-lg ${isDarkMode ? 'bg-white/5' : 'bg-gray-100'}`}>
                              <div className={`text-[10px] ${textSecondary}`}>SIFT (worst)</div>
                              <Badge variant="outline" className={`text-[10px] px-1.5 py-0 mt-0.5 ${
                                worstSift.sift_prediction?.includes('deleterious') ? 'bg-red-500/15 text-red-400 border-red-500/30' :
                                'bg-green-500/15 text-green-400 border-green-500/30'
                              }`}>
                                {worstSift.sift_prediction?.replace(/_/g, ' ') || 'N/A'}
                              </Badge>
                              {worstSift.sift_score != null && (
                                <div className={`text-[10px] font-mono ${textSecondary} mt-0.5`}>{worstSift.sift_score.toFixed(3)} — {worstSift.gene_symbol}</div>
                              )}
                            </div>
                          )}
                          {worstPP && (
                            <div className={`p-1.5 rounded-lg ${isDarkMode ? 'bg-white/5' : 'bg-gray-100'}`}>
                              <div className={`text-[10px] ${textSecondary}`}>PolyPhen (worst)</div>
                              <Badge variant="outline" className={`text-[10px] px-1.5 py-0 mt-0.5 ${
                                worstPP.polyphen_prediction?.includes('damaging') ? 'bg-red-500/15 text-red-400 border-red-500/30' :
                                worstPP.polyphen_prediction === 'possibly_damaging' ? 'bg-amber-500/15 text-amber-400 border-amber-500/30' :
                                'bg-green-500/15 text-green-400 border-green-500/30'
                              }`}>
                                {worstPP.polyphen_prediction?.replace(/_/g, ' ') || 'N/A'}
                              </Badge>
                              {worstPP.polyphen_score != null && (
                                <div className={`text-[10px] font-mono ${textSecondary} mt-0.5`}>{worstPP.polyphen_score.toFixed(3)} — {worstPP.gene_symbol}</div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Ensembl link */}
                    <div className={`pt-2 border-t ${border} flex items-center justify-between`}>
                      <span className={`text-[10px] ${textSecondary}`}>
                        VEP annotated {details.total_transcripts || tcs.length} transcript{(details.total_transcripts || tcs.length) !== 1 ? 's' : ''} across {uniqueGenes.length} gene{uniqueGenes.length !== 1 ? 's' : ''}
                      </span>
                      <a
                        href={`https://www.ensembl.org/Homo_sapiens/Variation/Explore?v=${rsid}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-[10px] text-blue-400 hover:text-blue-300 transition-colors"
                      >
                        View on Ensembl <ExternalLink className="h-3 w-3" />
                      </a>
                    </div>
                  </div>
                </div>
              )
            })()}

            {/* ── Transcript Consequences ── */}
            {details.transcripts && details.transcripts.length > 0 && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
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
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
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
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
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
                      <div className="relative h-2 rounded-full bg-linear-to-r from-green-500 via-amber-500 to-red-500 overflow-hidden">
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
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
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
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className={`text-xs ${textSecondary}`}>Protein change:</span>
                      <span className={`text-xs font-mono ${textPrimary}`}>{details.alpha_missense.protein_variant}</span>
                    </div>
                  )}
                  {/* Gene-level mean pathogenicity */}
                  {details.alpha_missense.gene_mean_pathogenicity != null && (
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
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
                            <span className={`font-mono ${textSecondary} truncate max-w-35`} title={iso.transcript_id}>{iso.transcript_id}</span>
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
                    <AlertTriangle className="h-3 w-3 text-amber-400 mt-0.5 shrink-0" />
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
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
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
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
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
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
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
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
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
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
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

            {/* ── gnomAD Transcript Expression ── */}
            {details.gnomad_tx?.found && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
                  <Dna className="h-3.5 w-3.5" /> Transcript Expression
                  <Badge variant="outline" className="bg-teal-500/10 text-teal-400 border-teal-500/20 text-[10px] ml-1">gnomAD-tx</Badge>
                  {details.gnomad_tx.lof && (
                    <Badge className={`text-[10px] ${details.gnomad_tx.lof === 'HC' ? 'bg-red-500/15 text-red-400 border-red-500/30' : 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30'}`}>
                      {details.gnomad_tx.lof} LoF
                    </Badge>
                  )}
                </h4>
                <div className={`${cardBg} rounded-xl p-3 border ${border} space-y-2`}>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {details.gnomad_tx.gene && (
                      <div><span className={textSecondary}>Gene:</span> <span className={textPrimary}>{details.gnomad_tx.gene}</span></div>
                    )}
                    {details.gnomad_tx.consequence && (
                      <div><span className={textSecondary}>Consequence:</span> <span className={textPrimary}>{details.gnomad_tx.consequence.replace(/_/g, ' ')}</span></div>
                    )}
                    {details.gnomad_tx.transcript_count != null && (
                      <div><span className={textSecondary}>Transcripts:</span> <span className={textPrimary}>{details.gnomad_tx.transcript_count}</span></div>
                    )}
                    {details.gnomad_tx.mean_expression != null && (
                      <div><span className={textSecondary}>Mean expression:</span> <span className={textPrimary}>{(details.gnomad_tx.mean_expression * 100).toFixed(1)}%</span></div>
                    )}
                  </div>
                  {details.gnomad_tx.top_tissues && Object.keys(details.gnomad_tx.top_tissues).length > 0 && (
                    <div>
                      <p className={`text-[10px] ${textSecondary} mb-1`}>Top tissues (GTEx):</p>
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(details.gnomad_tx.top_tissues)
                          .sort(([, a], [, b]) => b - a)
                          .slice(0, 6)
                          .map(([tissue, expr]) => (
                            <Badge key={tissue} variant="outline" className="text-[10px] px-1.5 py-0">
                              {tissue.replace(/_/g, ' ')}: {(expr * 100).toFixed(0)}%
                            </Badge>
                          ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── Gene Constraint ── */}
            {details.gene_constraint && (details.gene_constraint.pli != null || details.gene_constraint.loeuf != null) && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
                  <Shield className="h-3.5 w-3.5" /> Gene Constraint
                  <Badge variant="outline" className="bg-violet-500/10 text-violet-400 border-violet-500/20 text-[10px] ml-1">gnomAD</Badge>
                </h4>
                <div className={`${cardBg} rounded-xl p-3 border ${border}`}>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {details.gene_constraint.pli != null && (
                      <div>
                        <span className={textSecondary}>pLI: </span>
                        <span className={`font-medium ${details.gene_constraint.pli > 0.9 ? 'text-red-400' : details.gene_constraint.pli > 0.5 ? 'text-yellow-400' : 'text-green-400'}`}>
                          {details.gene_constraint.pli.toFixed(4)}
                        </span>
                        <span className={`text-[10px] ${textSecondary} ml-1`}>
                          {details.gene_constraint.pli > 0.9 ? '(LoF intolerant)' : details.gene_constraint.pli > 0.5 ? '(intermediate)' : '(LoF tolerant)'}
                        </span>
                      </div>
                    )}
                    {details.gene_constraint.loeuf != null && (
                      <div>
                        <span className={textSecondary}>LOEUF: </span>
                        <span className={`font-medium ${details.gene_constraint.loeuf < 0.35 ? 'text-red-400' : details.gene_constraint.loeuf < 0.6 ? 'text-yellow-400' : 'text-green-400'}`}>
                          {details.gene_constraint.loeuf.toFixed(3)}
                        </span>
                        <span className={`text-[10px] ${textSecondary} ml-1`}>
                          {details.gene_constraint.loeuf < 0.35 ? '(highly constrained)' : details.gene_constraint.loeuf < 0.6 ? '(constrained)' : '(tolerant)'}
                        </span>
                      </div>
                    )}
                    {details.gene_constraint.mis_z != null && (
                      <div><span className={textSecondary}>Missense Z: </span><span className={textPrimary}>{details.gene_constraint.mis_z.toFixed(2)}</span></div>
                    )}
                    {details.gene_constraint.syn_z != null && (
                      <div><span className={textSecondary}>Synonymous Z: </span><span className={textPrimary}>{details.gene_constraint.syn_z.toFixed(2)}</span></div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* ── ClinVar Gene Stats ── */}
            {details.clinvar_gene_stats && details.clinvar_gene_stats.total_submissions != null && details.clinvar_gene_stats.total_submissions > 0 && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
                  <Activity className="h-3.5 w-3.5" /> Gene-Level ClinVar
                </h4>
                <div className={`${cardBg} rounded-xl p-3 border ${border}`}>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div><span className={textSecondary}>Total submissions: </span><span className={textPrimary}>{details.clinvar_gene_stats.total_submissions}</span></div>
                    {details.clinvar_gene_stats.pathogenic_count != null && (
                      <div><span className={textSecondary}>Pathogenic/LP: </span><span className="text-red-400 font-medium">{details.clinvar_gene_stats.pathogenic_count}</span></div>
                    )}
                    {details.clinvar_gene_stats.uncertain_count != null && (
                      <div><span className={textSecondary}>VUS: </span><span className="text-yellow-400">{details.clinvar_gene_stats.uncertain_count}</span></div>
                    )}
                    {details.clinvar_gene_stats.conflict_count != null && details.clinvar_gene_stats.conflict_count > 0 && (
                      <div><span className={textSecondary}>Conflicting: </span><span className="text-amber-400">{details.clinvar_gene_stats.conflict_count}</span></div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* ── ClinVar Local ── */}
            {details.clinvar_local?.found && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
                  <Activity className="h-3.5 w-3.5" /> ClinVar Local
                  <Badge variant="outline" className="bg-orange-500/10 text-orange-400 border-orange-500/20 text-[10px] ml-1">Local DB</Badge>
                  {details.clinvar_local.has_conflicting_interpretations && (
                    <Badge className="text-[10px] bg-amber-500/15 text-amber-400 border-amber-500/30">Conflicting</Badge>
                  )}
                </h4>
                <div className={`${cardBg} rounded-xl p-3 border ${border} space-y-2`}>
                  {details.clinvar_local.clinical_significances && details.clinvar_local.clinical_significances.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {details.clinvar_local.clinical_significances.map((sig, i) => (
                        <Badge key={i} className={`text-[10px] ${clinSigColor(sig)}`}>{sig.replace(/_/g, ' ')}</Badge>
                      ))}
                    </div>
                  )}
                  {details.clinvar_local.gene_conditions && details.clinvar_local.gene_conditions.length > 0 && (
                    <div className="text-xs space-y-1">
                      {details.clinvar_local.gene_conditions.slice(0, 5).map((gc, i) => (
                        <div key={i}>
                          {gc.gene && <span className="text-blue-400 font-medium">{gc.gene}: </span>}
                          <span className={textSecondary}>{gc.conditions?.join(', ')}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  {details.clinvar_local.review_statuses && details.clinvar_local.review_statuses.length > 0 && (
                    <div className={`text-[10px] ${textSecondary}`}>
                      Review: {details.clinvar_local.review_statuses.join(', ').replace(/_/g, ' ')}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── SNPedia ── */}
            {details.snpedia?.found && details.snpedia.summary && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
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
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
                  <BookOpen className="h-3.5 w-3.5" /> Publications
                  <Badge variant="outline" className="bg-blue-500/10 text-blue-400 border-blue-500/20 text-[10px] ml-1">LitVar</Badge>
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

            {/* ── GWAS Catalog ── */}
            {details.gwas_catalog?.found && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
                  <Activity className="h-3.5 w-3.5" /> GWAS Catalog
                  {details.gwas_catalog.genome_wide_significant && (
                    <Badge className="text-xs bg-purple-500/15 text-purple-400 border-purple-500/30 ml-1">Genome-Wide Significant</Badge>
                  )}
                </h4>
                <div className={`${cardBg} rounded-xl p-3 border ${border} space-y-3`}>
                  {/* Explanation banner */}
                  <p className={`text-xs ${textSecondary} leading-relaxed`}>
                    This variant has been found in large population studies to be statistically associated with the traits below.
                    A lower p-value means a stronger, more reliable association.
                    {details.gwas_catalog.genome_wide_significant
                      ? ' All associations shown are genome-wide significant (p ≤ 5×10⁻⁸) — the gold standard threshold for genetic association studies.'
                      : ' This is a statistical association, not a direct cause of disease.'}
                  </p>
                  {/* Top association */}
                  {details.gwas_catalog.top_trait && (
                    <div className={`rounded-lg p-2 border ${border} ${isDarkMode ? 'bg-purple-500/8' : 'bg-purple-50'}`}>
                      <div className="flex items-center justify-between gap-2">
                        <span className={`text-xs font-semibold ${textPrimary}`}>{details.gwas_catalog.top_trait}</span>
                        {details.gwas_catalog.top_p_value != null && (
                          <span className="text-xs font-mono text-purple-400 shrink-0">
                            p = {details.gwas_catalog.top_p_value.toExponential(2)}
                          </span>
                        )}
                      </div>
                      <p className={`text-xs ${textSecondary} mt-0.5`}>Strongest association in this dataset</p>
                    </div>
                  )}
                  {/* Additional associations */}
                  {(details.gwas_catalog.associations?.length ?? 0) > 1 && (
                    <div className="space-y-0">
                      <p className={`text-xs font-medium ${textSecondary} mb-1`}>Other trait associations:</p>
                      {details.gwas_catalog.associations!.slice(0, 6).map((a, i) => {
                        const pval = a.p_value
                        const strength = pval == null ? null : pval <= 1e-30 ? 'Very strong' : pval <= 1e-15 ? 'Strong' : pval <= 1e-8 ? 'Significant' : 'Suggestive'
                        const strengthColor = strength === 'Very strong' ? 'text-purple-400' : strength === 'Strong' ? 'text-blue-400' : strength === 'Significant' ? 'text-green-400' : textSecondary
                        return (
                          <div key={i} className={`flex items-center justify-between text-xs border-t ${border} pt-1.5`}>
                            <span className={`truncate max-w-[55%] ${textSecondary}`}>{a.mapped_trait ?? a.trait ?? '—'}</span>
                            <div className="flex items-center gap-2 shrink-0">
                              {strength && <span className={`text-xs ${strengthColor}`}>{strength}</span>}
                              <span className={`font-mono ${textSecondary}`}>{pval != null ? `p=${pval.toExponential(1)}` : '—'}</span>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                  {/* P-value legend */}
                  <div className={`text-xs ${textSecondary} border-t ${border} pt-2 space-y-0.5`}>
                    <p className="font-medium mb-1">How to read p-values:</p>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
                      <span className="text-purple-400">p ≤ 10⁻³⁰ · Very strong</span>
                      <span className="text-blue-400">p ≤ 10⁻¹⁵ · Strong</span>
                      <span className="text-green-400">p ≤ 5×10⁻⁸ · Significant (GWS)</span>
                      <span className={textSecondary}>p &gt; 5×10⁻⁸ · Suggestive only</span>
                    </div>
                  </div>
                  <a href={`https://www.ebi.ac.uk/gwas/search?query=${rsid}`} target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-purple-400 hover:text-purple-300 transition-colors">
                    View full record in GWAS Catalog <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              </div>
            )}

            {/* ── ClinGen ── */}
            {details.clingen?.found && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
                  <Shield className="h-3.5 w-3.5" /> ClinGen Gene Validity
                  {details.clingen.strongest_classification && (() => {
                    const cls = details.clingen!.strongest_classification!
                    const color = cls === 'Definitive' ? 'bg-green-500/15 text-green-400 border-green-500/30'
                      : cls === 'Strong' ? 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30'
                      : cls === 'Moderate' ? 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30'
                      : cls === 'Limited' ? 'bg-orange-500/15 text-orange-400 border-orange-500/30'
                      : 'bg-red-500/15 text-red-400 border-red-500/30'
                    return <Badge className={`text-xs ${color} ml-1`}>{cls}</Badge>
                  })()}
                </h4>
                <div className={`${cardBg} rounded-xl p-3 border ${border} space-y-2`}>
                  <p className={`text-xs ${textSecondary}`}>Gene-level evidence — {details.clingen.gene_symbol ?? 'unknown gene'}
                    {details.clingen.disease_count ? ` · ${details.clingen.disease_count} disease association${details.clingen.disease_count > 1 ? 's' : ''}` : ''}
                  </p>
                  {details.clingen.curations?.slice(0, 4).map((c, i) => (
                    <div key={i} className={`flex items-start justify-between text-xs border-t ${border} pt-1 gap-2`}>
                      <div className="flex-1 min-w-0">
                        <span className={`font-medium ${textPrimary} block truncate`}>{c.disease_label ?? '—'}</span>
                        {c.moi && <span className={`${textSecondary}`}>{c.moi}</span>}
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        {c.classification && <Badge className="text-xs bg-gray-500/15 text-gray-400 border-gray-500/30">{c.classification}</Badge>}
                        {c.report_url && (
                          <a href={c.report_url} target="_blank" rel="noopener noreferrer"
                            className="text-cyan-400 hover:text-cyan-300"><ExternalLink className="h-3 w-3" /></a>
                        )}
                      </div>
                    </div>
                  ))}
                  <a href={`https://search.clinicalgenome.org/kb/genes?search=${details.clingen.gene_symbol ?? ''}`}
                    target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 mt-1 transition-colors">
                    View in ClinGen <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              </div>
            )}

            {/* ── Open Targets ── */}
            {details.open_targets?.found && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-1`}>
                  <Atom className="h-3.5 w-3.5" /> Open Targets
                  {details.open_targets.has_strong_genetic_evidence && (
                    <Badge className="text-xs bg-blue-500/15 text-blue-400 border-blue-500/30 ml-1">Strong Genetic Evidence</Badge>
                  )}
                </h4>
                <div className={`${cardBg} rounded-xl p-3 border ${border} space-y-2`}>
                  {details.open_targets.max_score != null && (
                    <div className="flex items-center gap-2">
                      <span className={`text-xs ${textSecondary} w-24`}>Max score</span>
                      <div className="flex-1 bg-gray-700/40 rounded-full h-1.5">
                        <div
                          className="bg-blue-500 h-1.5 rounded-full"
                          style={{ width: `${Math.round(details.open_targets.max_score * 100)}%` }}
                        />
                      </div>
                      <span className={`text-xs font-mono ${textPrimary}`}>{details.open_targets.max_score.toFixed(2)}</span>
                    </div>
                  )}
                  {details.open_targets.associations?.slice(0, 5).map((a, i) => (
                    <div key={i} className={`flex items-center justify-between text-xs border-t ${border} pt-1`}>
                      <span className={`truncate max-w-[65%] ${textSecondary}`}>{a.disease_name}</span>
                      <div className="flex items-center gap-2 shrink-0">
                        {a.genetic_association_score != null && (
                          <span className="font-mono text-blue-400">{a.genetic_association_score.toFixed(2)}</span>
                        )}
                        <span className={`font-mono ${textSecondary}`}>{a.score.toFixed(2)}</span>
                      </div>
                    </div>
                  ))}
                  <a href={`https://platform.opentargets.org/target/${details.open_targets.gene_symbol ?? ''}`}
                    target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 mt-1 transition-colors">
                    View in Open Targets <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              </div>
            )}

            {/* ── AI-Powered Analysis ── */}
            <SmartInsights
              isDarkMode={isDarkMode}
              token={token}
              rsid={rsid}
              variantData={details as Record<string, unknown>}
              compact
              title="AI Variant Analysis"
            />

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
              <a href={`https://www.ebi.ac.uk/gwas/search?query=${rsid}`} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-purple-400 hover:text-purple-300 transition-colors">
                GWAS Catalog <ExternalLink className="h-3 w-3" />
              </a>
              {gene && gene !== 'Unknown' && !gene.startsWith('rs') && (
                <a href={`https://platform.opentargets.org/target/${gene}`} target="_blank" rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors">
                  Open Targets <ExternalLink className="h-3 w-3" />
                </a>
              )}
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
