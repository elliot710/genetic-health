'use client'

import { useState, useEffect, useCallback } from 'react'
import { Search, Loader2, AlertCircle, CheckCircle, Info, ExternalLink, AlertTriangle, ChevronLeft, ChevronRight, Database, Globe, X, BarChart3, RefreshCw, Clock, Bookmark, Shield, Activity, FlaskConical } from 'lucide-react'
import type { getTheme } from '@/utils/theme'
import { apiFetch } from '@/lib/api'

type Theme = ReturnType<typeof getTheme>

interface VariantSearchProps {
  token?: string
  isDarkMode?: boolean
  theme?: Theme
}

interface VariantResult {
  rsid: string
  chromosome: string
  position: number
  ref_allele: string
  alt_allele: string
  genotype: string | null
  has_annotation: boolean
  category: string
  annotation: {
    sources: string[]
    gene: string | null
    consequence: string | null
    clinical_significance: string[]
    clinvar_count?: number
    alpha_missense?: { score?: number; classification?: string } | null
  } | null
}

interface CategoryInfo {
  name: string
  count: number
}

interface SearchResponse {
  variants: VariantResult[]
  total: number
  page: number
  per_page: number
  pages: number
}

interface LookupBasicInfo {
  gene_symbol?: string
  most_severe_consequence?: string
  allele_string?: string
  chromosome?: string
  start?: number
  strand?: number
  clinvar_count?: number
}

interface LookupAnnotationSource {
  found?: boolean
  [key: string]: unknown
}

interface ClinvarLocalAnnotation extends LookupAnnotationSource {
  conditions?: string[]
  genes?: string[]
  clinical_significance?: string
}

interface GnomadLocalAnnotation extends LookupAnnotationSource {
  af?: number
  ac?: number
  an?: number
  hom?: number
}

interface GnomadConstraintAnnotation extends LookupAnnotationSource {
  gene?: string
  pli?: number
  loeuf?: number
  interpretation?: string
}

interface EnsemblLocalAnnotation extends LookupAnnotationSource {
  gene_symbol?: string
  gene_id?: string
  biotype?: string
  transcript_count?: number
  chromosome?: string
  start?: number
  end?: number
  strand?: number
  description?: string
}

interface ChemblDrug {
  drug_name?: string
  max_phase?: number
  mechanism?: string
}

interface ChemblAnnotation extends LookupAnnotationSource {
  drugs?: ChemblDrug[]
}

interface AlphaFoldAnnotation extends LookupAnnotationSource {
  uniprot_id?: string
  avg_plddt?: number
}

interface PopulationEntry {
  allele: string
  frequency: number
}

interface AlphaMissenseIsoform {
  transcript_id: string
  protein_variant: string
  am_pathogenicity: number
  am_class: string
}

interface GwasAssociation {
  rsid?: string
  trait?: string
  mapped_trait?: string
  p_value?: number
  odds_ratio?: number
  pubmed_id?: string
  study_accession?: string
}

interface GwasAnnotation extends LookupAnnotationSource {
  associations?: GwasAssociation[]
  top_trait?: string
  top_p_value?: number
  genome_wide_significant?: boolean
}

interface ClinGenCuration {
  disease_label?: string
  classification?: string
  moi?: string
  gcep?: string
}

interface ClinGenAnnotation extends LookupAnnotationSource {
  gene_symbol?: string
  strongest_classification?: string
  is_definitive?: boolean
  is_disputed?: boolean
  disease_count?: number
  curations?: ClinGenCuration[]
}

interface OpenTargetsAssociation {
  disease_label?: string
  overall_score?: number
  genetic_association?: number
  literature_mining?: number
}

interface OpenTargetsAnnotation extends LookupAnnotationSource {
  gene_symbol?: string
  ensembl_id?: string
  top_disease?: string
  max_score?: number
  has_strong_genetic_evidence?: boolean
  associations?: OpenTargetsAssociation[]
}

interface TranscriptConsequence {
  transcript_id?: string
  gene_symbol?: string
  gene_id?: string
  biotype?: string
  consequence_terms?: string[]
  impact?: string
  sift_score?: number
  sift_prediction?: string
  polyphen_score?: number
  polyphen_prediction?: string
  hgvsc?: string
  hgvsp?: string
  canonical?: number
  protein_start?: number
  protein_end?: number
}

interface LookupResult {
  variant_id: string
  found: boolean
  description?: string
  cached?: boolean
  cached_at?: string
  basic_info: LookupBasicInfo
  clinical_significance?: string[]
  population_data?: {
    minor_allele?: string
    populations?: Record<string, PopulationEntry>
  }
  annotations?: {
    ensembl?: LookupAnnotationSource
    clinvar?: LookupAnnotationSource
    clinvar_local?: ClinvarLocalAnnotation
    gnomad_local?: GnomadLocalAnnotation
    gnomad_constraint?: GnomadConstraintAnnotation
    ensembl_local?: EnsemblLocalAnnotation
    bq_chembl?: ChemblAnnotation
    bq_alphafold?: AlphaFoldAnnotation
    gwas_catalog?: GwasAnnotation
    clingen?: ClinGenAnnotation
    open_targets?: OpenTargetsAnnotation
    transcript_consequences?: TranscriptConsequence[]
    [key: string]: LookupAnnotationSource | undefined
  }
  literature?: {
    snpedia_found?: boolean
    title?: string
    wiki_text?: string
  }
  pharmacogenomics?: {
    found?: boolean
    data?: Record<string, unknown>
  }
  alpha_missense?: {
    found?: boolean
    am_pathogenicity?: number
    am_class?: string
    protein_variant?: string
    gene_mean_pathogenicity?: number
    isoforms?: AlphaMissenseIsoform[]
    isoform_count?: number
    disclaimer?: string
  }
  external_links?: Record<string, string>
}

export default function VariantSearch({ token, isDarkMode = false, theme }: VariantSearchProps) {
  const defaultTheme = {
    glass: isDarkMode ? 'bg-slate-800/40 backdrop-blur-xl' : 'bg-white/40 backdrop-blur-xl',
    glassBorder: isDarkMode ? 'border-slate-700/50' : 'border-gray-200/30',
    text: {
      primary: isDarkMode ? 'text-white' : 'text-slate-900',
      secondary: isDarkMode ? 'text-slate-300' : 'text-slate-600',
      tertiary: isDarkMode ? 'text-gray-400' : 'text-gray-600',
      muted: isDarkMode ? 'text-slate-400' : 'text-slate-500'
    }
  }
  const t = theme || defaultTheme

  const [activeTab, setActiveTab] = useState<'my-variants' | 'lookup'>('my-variants')

  // My Variants state
  const [query, setQuery] = useState('')
  const [chromosome, setChromosome] = useState('')
  const [annotatedFilter, setAnnotatedFilter] = useState<string>('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [categories, setCategories] = useState<CategoryInfo[]>([])
  const [page, setPage] = useState(1)
  const [perPage] = useState(25)
  const [searchData, setSearchData] = useState<SearchResponse | null>(null)
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState('')

  // External lookup state
  const [lookupTerm, setLookupTerm] = useState('')
  const [lookupLoading, setLookupLoading] = useState(false)
  const [lookupResults, setLookupResults] = useState<LookupResult | null>(null)
  const [lookupError, setLookupError] = useState('')

  // Saved variants state
  const [savedRsids, setSavedRsids] = useState<Set<string>>(new Set())
  const [savedFilter, setSavedFilter] = useState(false)

  const fetchSavedRsids = useCallback(async () => {
    if (!token) return
    try {
      const res = await apiFetch('/auth/saved-variants')
      const data = await res.json()
      setSavedRsids(new Set(data.map((v: { rsid: string }) => v.rsid)))
    } catch { /* ignore */ }
  }, [token])

  useEffect(() => { fetchSavedRsids() }, [fetchSavedRsids])

  const toggleSave = async (rsid: string, gene?: string | null, consequence?: string | null, clinSig?: string | null) => {
    if (!token) return
    const wasSaved = savedRsids.has(rsid)
    try {
      if (wasSaved) {
        await apiFetch(`/auth/saved-variants/${rsid}`, { method: 'DELETE' })
        setSavedRsids(prev => { const next = new Set(prev); next.delete(rsid); return next })
      } else {
        await apiFetch('/auth/saved-variants', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ rsid, gene: gene || null, most_severe_consequence: consequence || null, clinical_significance: clinSig || null }),
        })
        setSavedRsids(prev => new Set(prev).add(rsid))
      }
    } catch { /* ignore */ }
  }

  useEffect(() => {
    if (!token) return
    apiFetch('/api/variants/categories')
      .then(r => r.json())
      .then(d => { if (d?.categories) setCategories(d.categories) })
      .catch(() => {})
  }, [token])

  const fetchVariants = useCallback(async () => {
    if (!token) return
    setSearchLoading(true)
    setSearchError('')
    try {
      const params = new URLSearchParams()
      if (query) params.set('q', query)
      if (chromosome) params.set('chromosome', chromosome)
      if (annotatedFilter === 'true') params.set('annotated', 'true')
      if (annotatedFilter === 'false') params.set('annotated', 'false')
      if (categoryFilter) params.set('category', categoryFilter)
      if (savedFilter) params.set('saved', 'true')
      params.set('page', String(page))
      params.set('per_page', String(perPage))

      const res = await apiFetch(`/api/variants/search?${params}`)
      const data: SearchResponse = await res.json()
      setSearchData(data)
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Search failed')
    } finally {
      setSearchLoading(false)
    }
  }, [token, query, chromosome, annotatedFilter, categoryFilter, savedFilter, page, perPage])

  useEffect(() => {
    if (activeTab === 'my-variants') {
      fetchVariants()
    }
  }, [activeTab, fetchVariants])

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setPage(1)
    fetchVariants()
  }

  const clearFilters = () => {
    setQuery('')
    setChromosome('')
    setAnnotatedFilter('')
    setCategoryFilter('')
    setSavedFilter(false)
    setPage(1)
  }

  const doLookup = async (rsid?: string, forceRefresh = false) => {
    const term = rsid || lookupTerm.trim()
    if (!term) {
      setLookupError('Please enter a variant ID')
      return
    }
    setLookupLoading(true)
    setLookupError('')
    if (!forceRefresh) setLookupResults(null)
    if (rsid) {
      setLookupTerm(rsid)
      setActiveTab('lookup')
    }
    try {
      const res = await apiFetch('/api/variants/lookup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ variant_id: term, include_literature: true, include_clinpgx: true, force_refresh: forceRefresh })
      })
      setLookupResults(await res.json())
    } catch (err) {
      setLookupError(err instanceof Error ? err.message : 'Lookup failed')
    } finally {
      setLookupLoading(false)
    }
  }

  const consequenceBadge = (consequence: string | null) => {
    if (!consequence) return null
    const label = consequence.replace(/_/g, ' ')
    const color = consequence.includes('missense') || consequence.includes('frameshift') || consequence.includes('stop')
      ? isDarkMode ? 'bg-red-500/20 text-red-300' : 'bg-red-100 text-red-700'
      : consequence.includes('synonymous')
        ? isDarkMode ? 'bg-green-500/20 text-green-300' : 'bg-green-100 text-green-700'
        : isDarkMode ? 'bg-slate-500/20 text-slate-300' : 'bg-gray-100 text-gray-700'
    return <span className={`px-2 py-0.5 rounded text-xs font-medium ${color}`}>{label}</span>
  }

  const sourceBadge = (source: string, label?: string) => {
    const colors: Record<string, string> = {
      ensembl: isDarkMode ? 'bg-green-500/20 text-green-300' : 'bg-green-100 text-green-700',
      clinvar: isDarkMode ? 'bg-red-500/20 text-red-300' : 'bg-red-100 text-red-700',
      clinpgx: isDarkMode ? 'bg-purple-500/20 text-purple-300' : 'bg-purple-100 text-purple-700',
      snpedia: isDarkMode ? 'bg-orange-500/20 text-orange-300' : 'bg-orange-100 text-orange-700',
      litvar: isDarkMode ? 'bg-blue-500/20 text-blue-300' : 'bg-blue-100 text-blue-700',
      clinvar_local: isDarkMode ? 'bg-rose-500/20 text-rose-300' : 'bg-rose-100 text-rose-700',
      gnomad_local: isDarkMode ? 'bg-teal-500/20 text-teal-300' : 'bg-teal-100 text-teal-700',
      gnomad_constraint: isDarkMode ? 'bg-teal-500/20 text-teal-300' : 'bg-teal-100 text-teal-700',
      ensembl_local: isDarkMode ? 'bg-emerald-500/20 text-emerald-300' : 'bg-emerald-100 text-emerald-700',
      bq_chembl: isDarkMode ? 'bg-indigo-500/20 text-indigo-300' : 'bg-indigo-100 text-indigo-700',
      bq_alphafold: isDarkMode ? 'bg-cyan-500/20 text-cyan-300' : 'bg-cyan-100 text-cyan-700',
      bq_fda_drug: isDarkMode ? 'bg-pink-500/20 text-pink-300' : 'bg-pink-100 text-pink-700',
      gwas_catalog: isDarkMode ? 'bg-violet-500/20 text-violet-300' : 'bg-violet-100 text-violet-700',
      clingen: isDarkMode ? 'bg-emerald-500/20 text-emerald-300' : 'bg-emerald-100 text-emerald-700',
      open_targets: isDarkMode ? 'bg-amber-500/20 text-amber-300' : 'bg-amber-100 text-amber-700',
    }
    return (
      <span key={source} className={`px-2 py-0.5 rounded text-xs font-medium ${colors[source] || (isDarkMode ? 'bg-slate-500/20 text-slate-300' : 'bg-gray-100 text-gray-600')}`}>
        {label || source}
      </span>
    )
  }

  return (
    <div className="space-y-6">
      {/* Tab Selector */}
      <div className={`${t.glass} border ${t.glassBorder} rounded-2xl p-2 flex gap-2`}>
        <button
          onClick={() => setActiveTab('my-variants')}
          className={`flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-medium transition-all ${
            activeTab === 'my-variants'
              ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-lg'
              : `${t.text.secondary} ${isDarkMode ? 'hover:bg-slate-700/40' : 'hover:bg-gray-200/40'}`
          }`}
        >
          <Database className="h-4 w-4" />
          My Variants
        </button>
        <button
          onClick={() => setActiveTab('lookup')}
          className={`flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-medium transition-all ${
            activeTab === 'lookup'
              ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-lg'
              : `${t.text.secondary} ${isDarkMode ? 'hover:bg-slate-700/40' : 'hover:bg-gray-200/40'}`
          }`}
        >
          <Globe className="h-4 w-4" />
          External Lookup
        </button>
      </div>

      {/* MY VARIANTS TAB */}
      {activeTab === 'my-variants' && (
        <div className={`${t.glass} border ${t.glassBorder} rounded-2xl shadow-xl p-6`}>
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-gradient-to-r from-indigo-500 to-purple-500 rounded-xl">
              <Database className="h-5 w-5 text-white" />
            </div>
            <div>
              <h3 className={`text-xl font-bold ${t.text.primary}`}>My Variants</h3>
              <p className={`text-sm ${t.text.muted}`}>Search and filter your uploaded genetic variants</p>
            </div>
          </div>

          {/* Search & Filters */}
          <form onSubmit={handleSearchSubmit} className="flex flex-col sm:flex-row gap-3 mb-6">
            <div className="flex-1 relative">
              <Search className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${t.text.muted}`} />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search by rsid (e.g., rs429358)"
                className={`w-full pl-10 pr-4 py-2.5 rounded-xl border ${t.glassBorder} ${t.glass} ${t.text.primary} focus:outline-none focus:ring-2 focus:ring-indigo-500/50 text-sm`}
              />
            </div>
            <select
              value={chromosome}
              onChange={(e) => { setChromosome(e.target.value); setPage(1) }}
              className={`px-3 py-2.5 rounded-xl border ${t.glassBorder} ${t.glass} ${t.text.primary} text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50`}
            >
              <option value="">All Chromosomes</option>
              {[...Array(22)].map((_, i) => (
                <option key={i + 1} value={String(i + 1)}>Chr {i + 1}</option>
              ))}
              <option value="X">Chr X</option>
              <option value="Y">Chr Y</option>
              <option value="MT">Chr MT</option>
            </select>
            <select
              value={annotatedFilter}
              onChange={(e) => { setAnnotatedFilter(e.target.value); setPage(1) }}
              className={`px-3 py-2.5 rounded-xl border ${t.glassBorder} ${t.glass} ${t.text.primary} text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50`}
            >
              <option value="">All Variants</option>
              <option value="true">Annotated Only</option>
              <option value="false">Unannotated Only</option>
            </select>
            <select
              value={categoryFilter}
              onChange={(e) => { setCategoryFilter(e.target.value); setPage(1) }}
              className={`px-3 py-2.5 rounded-xl border ${t.glassBorder} ${t.glass} ${t.text.primary} text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50`}
            >
              <option value="">All Categories</option>
              {categories.map(c => (
                <option key={c.name} value={c.name}>{c.name} ({c.count})</option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => { setSavedFilter(f => !f); setPage(1) }}
              className={`flex items-center gap-1.5 px-3 py-2.5 rounded-xl border text-sm font-medium transition-all ${
                savedFilter
                  ? 'bg-blue-500/20 text-blue-400 border-blue-500/30'
                  : `${t.glassBorder} ${t.text.muted} ${isDarkMode ? 'hover:bg-slate-700/40' : 'hover:bg-gray-200/40'}`
              }`}
              title="Show saved variants only"
            >
              <Bookmark className={`h-3.5 w-3.5 ${savedFilter ? 'fill-blue-400' : ''}`} />
              Saved
            </button>
            <button type="submit" className="px-5 py-2.5 bg-gradient-to-r from-indigo-500/80 to-purple-600/80 text-white rounded-xl hover:from-purple-600/80 hover:to-indigo-500/80 transition-all text-sm font-medium border border-white/20 shadow-lg">
              Search
            </button>
            {(query || chromosome || annotatedFilter || categoryFilter || savedFilter) && (
              <button type="button" onClick={clearFilters} className={`px-3 py-2.5 rounded-xl border ${t.glassBorder} ${t.text.muted} transition-all text-sm`}>
                <X className="h-4 w-4" />
              </button>
            )}
          </form>

          {/* Summary bar */}
          {searchData && (
            <div className={`flex items-center justify-between mb-4 text-sm ${t.text.muted}`}>
              <span>{searchData.total.toLocaleString()} variants found</span>
              <span>Page {searchData.page} of {searchData.pages}</span>
            </div>
          )}

          {/* Error */}
          {searchError && (
            <div className={`mb-4 p-3 ${isDarkMode ? 'bg-red-500/20 border-red-500/30' : 'bg-red-50 border-red-200'} border rounded-xl flex items-center gap-2`}>
              <AlertCircle className="h-4 w-4 text-red-500" />
              <span className={`text-sm ${isDarkMode ? 'text-red-200' : 'text-red-700'}`}>{searchError}</span>
            </div>
          )}

          {/* Loading */}
          {searchLoading && (
            <div className="flex justify-center py-12">
              <Loader2 className={`h-8 w-8 animate-spin ${t.text.muted}`} />
            </div>
          )}

          {/* Results table */}
          {!searchLoading && searchData && searchData.variants.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className={`border-b ${t.glassBorder}`}>
                    <th className={`text-left py-3 px-3 ${t.text.secondary} font-semibold`}>RS ID</th>
                    <th className={`text-left py-3 px-3 ${t.text.secondary} font-semibold`}>Chr</th>
                    <th className={`text-left py-3 px-3 ${t.text.secondary} font-semibold`}>Position</th>
                    <th className={`text-left py-3 px-3 ${t.text.secondary} font-semibold`}>Ref/Alt</th>
                    <th className={`text-left py-3 px-3 ${t.text.secondary} font-semibold`}>Gene</th>
                    <th className={`text-left py-3 px-3 ${t.text.secondary} font-semibold`}>Consequence</th>
                    <th className={`text-left py-3 px-3 ${t.text.secondary} font-semibold`}>Category</th>
                    <th className={`text-left py-3 px-3 ${t.text.secondary} font-semibold`}>Sources</th>
                    <th className={`text-left py-3 px-3 ${t.text.secondary} font-semibold`}>AM</th>
                    <th className={`text-left py-3 px-3 ${t.text.secondary} font-semibold`}>CV</th>
                    <th className={`text-left py-3 px-3 ${t.text.secondary} font-semibold`}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {searchData.variants.map((v) => (
                    <tr
                      key={v.rsid}
                      className={`border-b ${t.glassBorder} transition-all ${isDarkMode ? 'hover:bg-slate-700/30' : 'hover:bg-gray-200/30'}`}
                    >
                      <td className={`py-3 px-3 font-mono font-semibold ${t.text.primary}`}>{v.rsid}</td>
                      <td className={`py-3 px-3 font-mono ${t.text.secondary}`}>{v.chromosome}</td>
                      <td className={`py-3 px-3 font-mono ${t.text.secondary}`}>{v.position.toLocaleString()}</td>
                      <td className={`py-3 px-3 font-mono ${t.text.secondary}`}>{v.ref_allele}/{v.alt_allele}</td>
                      <td className={`py-3 px-3 ${t.text.primary}`}>{v.annotation?.gene || '-'}</td>
                      <td className="py-3 px-3">{v.annotation ? consequenceBadge(v.annotation.consequence) : <span className={t.text.muted}>-</span>}</td>
                      <td className={`py-3 px-3 text-xs font-medium ${t.text.secondary}`}>{v.category || '-'}</td>
                      <td className="py-3 px-3">
                        <div className="flex flex-wrap gap-1">
                          {v.annotation?.sources.map(s => sourceBadge(s)) || <span className={t.text.muted}>-</span>}
                        </div>
                      </td>
                      <td className="py-3 px-3">
                        {v.annotation?.alpha_missense?.score != null ? (
                          <span
                            className={`inline-flex items-center text-xs font-semibold rounded px-1.5 py-0.5 border ${
                              v.annotation.alpha_missense.classification === 'likely_pathogenic'
                                ? 'text-red-400 bg-red-500/10 border-red-500/20'
                                : v.annotation.alpha_missense.classification === 'ambiguous'
                                  ? 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20'
                                  : 'text-green-400 bg-green-500/10 border-green-500/20'
                            }`}
                            title={`AlphaMissense: ${v.annotation.alpha_missense.score.toFixed(3)} — ${(v.annotation.alpha_missense.classification || '').replace(/_/g, ' ')}`}
                          >
                            {v.annotation.alpha_missense.score.toFixed(2)}
                          </span>
                        ) : <span className={t.text.muted}>-</span>}
                      </td>
                      <td className="py-3 px-3">
                        {v.annotation?.clinvar_count ? (
                          <span
                            className="inline-flex items-center text-xs font-semibold rounded px-1.5 py-0.5 border text-orange-400 bg-orange-500/10 border-orange-500/20"
                            title={`${v.annotation.clinvar_count} ClinVar ${v.annotation.clinvar_count === 1 ? 'report' : 'reports'}`}
                          >
                            {v.annotation.clinvar_count}
                          </span>
                        ) : <span className={t.text.muted}>-</span>}
                      </td>
                      <td className="py-3 px-3">
                        <div className="flex items-center gap-1.5">
                          <button
                            onClick={() => toggleSave(v.rsid, v.annotation?.gene, v.annotation?.consequence, v.annotation?.clinical_significance?.join(', '))}
                            className={`p-1 rounded-lg transition-all ${isDarkMode ? 'hover:bg-slate-700/40' : 'hover:bg-gray-200/40'}`}
                            title={savedRsids.has(v.rsid) ? 'Remove from saved' : 'Save variant'}
                          >
                            <Bookmark className={`h-3.5 w-3.5 ${savedRsids.has(v.rsid) ? 'fill-blue-400 text-blue-400' : t.text.muted}`} />
                          </button>
                          <button
                            onClick={() => doLookup(v.rsid)}
                            className={`px-2 py-1 rounded-lg text-xs font-medium transition-all ${isDarkMode ? 'bg-indigo-500/20 text-indigo-300 hover:bg-indigo-500/30' : 'bg-indigo-100 text-indigo-700 hover:bg-indigo-200'}`}
                            title="Full external lookup"
                          >
                            <Globe className="h-3 w-3 inline mr-1" />
                            Lookup
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Empty state */}
          {!searchLoading && searchData && searchData.variants.length === 0 && (
            <div className="text-center py-12">
              <Search className={`h-12 w-12 mx-auto mb-4 ${t.text.muted} opacity-50`} />
              <h3 className={`text-lg font-medium ${t.text.primary} mb-2`}>No variants found</h3>
              <p className={t.text.secondary}>Try adjusting your search or filters</p>
            </div>
          )}

          {/* Pagination */}
          {searchData && searchData.pages > 1 && (
            <div className="flex items-center justify-center gap-2 mt-6">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                className={`p-2 rounded-lg border ${t.glassBorder} ${page <= 1 ? 'opacity-40 cursor-not-allowed' : `${t.text.primary} ${isDarkMode ? 'hover:bg-slate-700/40' : 'hover:bg-gray-200/40'}`} transition-all`}
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              {(() => {
                const pages: number[] = []
                const start = Math.max(1, page - 2)
                const end = Math.min(searchData.pages, page + 2)
                if (start > 1) pages.push(1)
                if (start > 2) pages.push(-1)
                for (let i = start; i <= end; i++) pages.push(i)
                if (end < searchData.pages - 1) pages.push(-2)
                if (end < searchData.pages) pages.push(searchData.pages)
                return pages.map((p, i) =>
                  p < 0 ? (
                    <span key={`e${i}`} className={t.text.muted}>...</span>
                  ) : (
                    <button
                      key={p}
                      onClick={() => setPage(p)}
                      className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                        p === page
                          ? 'bg-gradient-to-r from-indigo-500 to-purple-500 text-white shadow-md'
                          : `${t.text.secondary} border ${t.glassBorder} ${isDarkMode ? 'hover:bg-slate-700/40' : 'hover:bg-gray-200/40'}`
                      }`}
                    >
                      {p}
                    </button>
                  )
                )
              })()}
              <button
                onClick={() => setPage(p => Math.min(searchData.pages, p + 1))}
                disabled={page >= searchData.pages}
                className={`p-2 rounded-lg border ${t.glassBorder} ${page >= searchData.pages ? 'opacity-40 cursor-not-allowed' : `${t.text.primary} ${isDarkMode ? 'hover:bg-slate-700/40' : 'hover:bg-gray-200/40'}`} transition-all`}
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          )}
        </div>
      )}

      {/* EXTERNAL LOOKUP TAB */}
      {activeTab === 'lookup' && (
        <div className={`${t.glass} border ${t.glassBorder} rounded-2xl shadow-xl p-6`}>
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-gradient-to-r from-indigo-500 to-purple-500 rounded-xl">
              <Globe className="h-5 w-5 text-white" />
            </div>
            <div>
              <h3 className={`text-xl font-bold ${t.text.primary}`}>External Variant Lookup</h3>
              <p className={`text-sm ${t.text.muted}`}>Query multiple databases for detailed variant information</p>
            </div>
          </div>

          {/* Search Input */}
          <div className="flex gap-3 mb-6">
            <div className="flex-1">
              <input
                type="text"
                value={lookupTerm}
                onChange={(e) => setLookupTerm(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && doLookup()}
                placeholder="Enter variant ID (e.g., rs53576, rs429358)"
                className={`w-full px-4 py-3 rounded-xl border ${t.glassBorder} ${t.glass} ${t.text.primary} placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/50`}
              />
            </div>
            <button
              onClick={() => doLookup()}
              disabled={lookupLoading}
              className="px-6 py-3 bg-gradient-to-r from-indigo-500/80 to-purple-600/80 text-white rounded-xl hover:from-purple-600/80 hover:to-indigo-500/80 transition-all disabled:opacity-50 flex items-center gap-2 border border-white/20 shadow-lg"
            >
              {lookupLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              <span>{lookupLoading ? 'Searching...' : 'Search'}</span>
            </button>
          </div>

          {/* Error */}
          {lookupError && (
            <div className={`mb-6 p-4 ${isDarkMode ? 'bg-red-500/20 border-red-500/30' : 'bg-red-50 border-red-200'} border rounded-xl flex items-center gap-3`}>
              <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0" />
              <div className={`${isDarkMode ? 'text-red-200' : 'text-red-700'} text-sm`}>{lookupError}</div>
            </div>
          )}

          {/* Results */}
          {lookupResults && lookupResults.found && (
            <div className="space-y-4">
              {/* Cache indicator */}
              {lookupResults.cached && (
                <div className={`flex items-center justify-between p-3 rounded-xl border ${isDarkMode ? 'bg-amber-500/10 border-amber-500/20' : 'bg-amber-50 border-amber-200'}`}>
                  <div className="flex items-center gap-2">
                    <Clock className={`h-4 w-4 ${isDarkMode ? 'text-amber-400' : 'text-amber-600'}`} />
                    <span className={`text-sm ${isDarkMode ? 'text-amber-300' : 'text-amber-700'}`}>
                      Loaded from cache
                      {lookupResults.cached_at && (
                        <span className={`ml-1 ${isDarkMode ? 'text-amber-400/70' : 'text-amber-600/70'}`}>
                          &middot; Last fetched {(() => {
                            const diff = Date.now() - new Date(lookupResults.cached_at).getTime()
                            const mins = Math.floor(diff / 60000)
                            if (mins < 1) return 'just now'
                            if (mins < 60) return `${mins}m ago`
                            const hours = Math.floor(mins / 60)
                            if (hours < 24) return `${hours}h ago`
                            const days = Math.floor(hours / 24)
                            return `${days}d ago`
                          })()}
                        </span>
                      )}
                    </span>
                  </div>
                  <button
                    onClick={() => doLookup(undefined, true)}
                    disabled={lookupLoading}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                      isDarkMode
                        ? 'bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 border border-amber-500/30'
                        : 'bg-amber-100 text-amber-700 hover:bg-amber-200 border border-amber-200'
                    } ${lookupLoading ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    <RefreshCw className={`h-3 w-3 ${lookupLoading ? 'animate-spin' : ''}`} />
                    Refresh from sources
                  </button>
                </div>
              )}
              {/* Summary Header */}
              <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <div className="flex items-center gap-3 mb-1">
                      <h4 className={`text-2xl font-bold font-mono ${t.text.primary}`}>{lookupResults.variant_id}</h4>
                      {lookupResults.basic_info?.gene_symbol && (
                        <span className={`px-3 py-1 rounded-lg text-sm font-bold ${isDarkMode ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30' : 'bg-indigo-100 text-indigo-700 border border-indigo-200'}`}>
                          {lookupResults.basic_info.gene_symbol}
                        </span>
                      )}
                      {lookupResults.basic_info?.most_severe_consequence && consequenceBadge(lookupResults.basic_info.most_severe_consequence)}
                    </div>
                    <div className={`flex flex-wrap items-center gap-4 text-sm ${t.text.secondary} mt-2`}>
                      {lookupResults.basic_info?.allele_string && (
                        <span>Alleles: <span className={`font-mono font-medium ${t.text.primary}`}>{lookupResults.basic_info.allele_string}</span></span>
                      )}
                      {lookupResults.basic_info?.chromosome && (
                        <span>Chr <span className={`font-mono font-medium ${t.text.primary}`}>{lookupResults.basic_info.chromosome}</span>
                          {lookupResults.basic_info.start && (
                            <span className="font-mono">:{lookupResults.basic_info.start.toLocaleString()}</span>
                          )}
                        </span>
                      )}
                      {lookupResults.basic_info?.strand != null && (
                        <span>Strand: <span className={`font-medium ${t.text.primary}`}>{lookupResults.basic_info.strand === 1 ? '+' : '-'}</span></span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      onClick={() => toggleSave(
                        lookupResults.variant_id,
                        lookupResults.basic_info?.gene_symbol,
                        lookupResults.basic_info?.most_severe_consequence,
                        lookupResults.clinical_significance?.join(', ')
                      )}
                      className={`p-1.5 rounded-lg transition-all ${isDarkMode ? 'hover:bg-slate-700/40' : 'hover:bg-gray-200/40'}`}
                      title={savedRsids.has(lookupResults.variant_id) ? 'Remove from saved' : 'Save variant'}
                    >
                      <Bookmark className={`h-5 w-5 ${savedRsids.has(lookupResults.variant_id) ? 'fill-blue-400 text-blue-400' : t.text.muted}`} />
                    </button>
                    <CheckCircle className="h-6 w-6 text-green-500" />
                  </div>
                </div>

                {/* Source badges */}
                <div className="flex flex-wrap gap-2 mt-3">
                  {lookupResults.annotations?.ensembl?.found && sourceBadge('ensembl')}
                  {lookupResults.annotations?.clinvar?.found && sourceBadge('clinvar')}
                  {lookupResults.annotations?.snpedia?.found && sourceBadge('snpedia')}
                  {lookupResults.annotations?.clinpgx?.found && sourceBadge('clinpgx')}
                  {lookupResults.alpha_missense?.found && (
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${isDarkMode ? 'bg-amber-500/20 text-amber-300' : 'bg-amber-100 text-amber-700'}`}>
                      AlphaMissense
                    </span>
                  )}
                  {lookupResults.annotations?.clinvar_local && sourceBadge('clinvar_local', 'ClinVar DB')}
                  {lookupResults.annotations?.gnomad_local?.found && sourceBadge('gnomad_local', 'gnomAD')}
                  {lookupResults.annotations?.gnomad_constraint && sourceBadge('gnomad_constraint', 'Gene Constraint')}
                  {lookupResults.annotations?.ensembl_local?.found && sourceBadge('ensembl_local', 'Ensembl DB')}
                  {lookupResults.annotations?.bq_chembl?.found && sourceBadge('bq_chembl', 'ChEMBL')}
                  {lookupResults.annotations?.bq_alphafold?.found && sourceBadge('bq_alphafold', 'AlphaFold')}
                  {lookupResults.annotations?.bq_fda_drug?.found && sourceBadge('bq_fda_drug', 'FDA Drug')}
                  {lookupResults.annotations?.gwas_catalog?.found && sourceBadge('gwas_catalog', 'GWAS Catalog')}
                  {lookupResults.annotations?.clingen?.found && sourceBadge('clingen', 'ClinGen')}
                  {lookupResults.annotations?.open_targets?.found && sourceBadge('open_targets', 'Open Targets')}
                  {(lookupResults.annotations?.transcript_consequences?.length ?? 0) > 0 && sourceBadge('ensembl_local', 'VEP Transcripts')}
                </div>
              </div>

              {/* Variant Description */}
              {lookupResults.description && (
                <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                  <p className={`text-sm leading-relaxed ${t.text.secondary}`}>{lookupResults.description}</p>
                </div>
              )}

              {/* Clinical Significance */}
              {(lookupResults.clinical_significance?.length ?? 0) > 0 && (
                <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                  <h4 className={`font-bold ${t.text.primary} mb-3 flex items-center gap-2`}>
                    <AlertTriangle className="h-4 w-4 text-amber-500" />
                    Clinical Significance
                    {(lookupResults.basic_info?.clinvar_count ?? 0) > 0 && (
                      <span className={`text-xs font-normal ${t.text.muted}`}>({lookupResults.basic_info!.clinvar_count} ClinVar entries)</span>
                    )}
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {lookupResults.clinical_significance!.map((sig: string, i: number) => {
                      const lower = sig.toLowerCase()
                      const color = lower.includes('pathogenic')
                        ? isDarkMode ? 'bg-red-500/20 text-red-300 border-red-500/30' : 'bg-red-50 text-red-700 border-red-200'
                        : lower.includes('benign')
                          ? isDarkMode ? 'bg-green-500/20 text-green-300 border-green-500/30' : 'bg-green-50 text-green-700 border-green-200'
                          : lower.includes('risk') || lower.includes('drug_response')
                            ? isDarkMode ? 'bg-amber-500/20 text-amber-300 border-amber-500/30' : 'bg-amber-50 text-amber-700 border-amber-200'
                            : lower.includes('protective')
                              ? isDarkMode ? 'bg-blue-500/20 text-blue-300 border-blue-500/30' : 'bg-blue-50 text-blue-700 border-blue-200'
                              : isDarkMode ? 'bg-slate-500/20 text-slate-300 border-slate-500/30' : 'bg-gray-50 text-gray-600 border-gray-200'
                      return (
                        <span key={i} className={`px-3 py-1.5 rounded-lg text-xs font-medium border ${color}`}>
                          {sig.replace(/_/g, ' ')}
                        </span>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Population Frequencies */}
              {Object.keys(lookupResults.population_data?.populations || {}).length > 0 && (
                <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                  <h4 className={`font-bold ${t.text.primary} mb-1 flex items-center gap-2`}>
                    <BarChart3 className="h-4 w-4 text-cyan-500" />
                    Population Frequencies
                  </h4>
                  <p className={`text-xs ${t.text.muted} mb-4`}>
                    Allele frequency across global populations
                    {lookupResults.population_data?.minor_allele && (
                      <> &middot; Minor allele: <span className="font-mono font-medium">{lookupResults.population_data.minor_allele}</span></>
                    )}
                  </p>
                  <div className="space-y-2">
                    {(() => {
                      const pops = lookupResults.population_data!.populations as Record<string, PopulationEntry>
                      const sorted = Object.entries(pops)
                        .sort(([, a], [, b]) => b.frequency - a.frequency)
                        .slice(0, 6)
                      const maxFreq = sorted.length > 0 ? sorted[0][1].frequency : 1

                      const popLabels: Record<string, string> = {
                        eur: 'European', afr: 'African', eas: 'East Asian', sas: 'South Asian',
                        amr: 'American', gnomade_afr: 'gnomAD African', gnomade_eas: 'gnomAD East Asian',
                        gnomade_amr: 'gnomAD American', gnomade_sas: 'gnomAD South Asian',
                        gnomade_nfe: 'gnomAD Non-Finnish Eur.', gnomade_fin: 'gnomAD Finnish',
                        gnomade_asj: 'gnomAD Ashkenazi Jewish', gnomade_remaining: 'gnomAD Other',
                        gnomade_mid: 'gnomAD Middle Eastern',
                      }
                      return sorted.map(([name, data]) => (
                        <div key={name} className="flex items-center gap-3">
                          <span className={`text-xs ${t.text.secondary} w-40 truncate text-right`} title={name}>
                            {popLabels[name] || name}
                          </span>
                          <div className={`flex-1 h-5 rounded-full overflow-hidden ${isDarkMode ? 'bg-slate-700/50' : 'bg-gray-200/60'}`}>
                            <div
                              className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-blue-500 transition-all"
                              style={{ width: `${Math.max((data.frequency / maxFreq) * 100, 2)}%` }}
                            />
                          </div>
                          <span className={`text-xs font-mono font-medium ${t.text.primary} w-16 text-right`}>
                            {(data.frequency * 100).toFixed(1)}%
                          </span>
                        </div>
                      ))
                    })()}
                  </div>
                  {Object.keys(lookupResults.population_data?.populations || {}).length > 12 && (
                    <p className={`text-xs ${t.text.muted} mt-3`}>
                      Showing top 6 of {Object.keys(lookupResults.population_data?.populations || {}).length} populations
                    </p>
                  )}
                </div>
              )}

              {/* SNPedia */}
              {lookupResults.literature?.snpedia_found && (
                <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                  <h4 className={`font-bold ${t.text.primary} mb-3 flex items-center gap-2`}>
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${isDarkMode ? 'bg-orange-500/20 text-orange-300' : 'bg-orange-100 text-orange-700'}`}>SNPedia</span>
                    {lookupResults.literature.title}
                  </h4>
                  {(() => {
                    const wikiText = lookupResults.literature.wiki_text || ''
                    // Parse wiki template fields
                    const fields: Record<string, string> = {}
                    const fieldRegex = /\|(\w+)=([^\n|]*)/g
                    let match
                    while ((match = fieldRegex.exec(wikiText)) !== null) {
                      fields[match[1]] = match[2].trim()
                    }
                    
                    // Parse genotype entries
                    const genotypeRegex = /\{\{Genotype\s*\|[^}]*gene=([^|]*)\|[^}]*rsid=\d+\|[^}]*allele1=([^|]*)\|[^}]*allele2=([^|]*)\|[^}]*magnitude=([^|]*)\|[^}]*repute=([^|]*)\|[^}]*summary=([^}]*)\}\}/g
                    const genotypes: { allele1: string; allele2: string; magnitude: string; repute: string; summary: string }[] = []
                    let gMatch
                    while ((gMatch = genotypeRegex.exec(wikiText)) !== null) {
                      genotypes.push({
                        allele1: gMatch[2]?.trim() || '',
                        allele2: gMatch[3]?.trim() || '',
                        magnitude: gMatch[4]?.trim() || '',
                        repute: gMatch[5]?.trim() || '',
                        summary: gMatch[6]?.trim() || ''
                      })
                    }

                    return (
                      <div className="space-y-3">
                        {/* Key fields */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                          {fields.Gene && (
                            <div className={`p-2 rounded-lg ${isDarkMode ? 'bg-slate-700/30' : 'bg-gray-100/60'}`}>
                              <div className={`text-xs ${t.text.muted}`}>Gene</div>
                              <div className={`font-medium ${t.text.primary}`}>{fields.Gene}</div>
                            </div>
                          )}
                          {fields.Chromosome && (
                            <div className={`p-2 rounded-lg ${isDarkMode ? 'bg-slate-700/30' : 'bg-gray-100/60'}`}>
                              <div className={`text-xs ${t.text.muted}`}>Chromosome</div>
                              <div className={`font-medium font-mono ${t.text.primary}`}>{fields.Chromosome}</div>
                            </div>
                          )}
                          {fields.position && (
                            <div className={`p-2 rounded-lg ${isDarkMode ? 'bg-slate-700/30' : 'bg-gray-100/60'}`}>
                              <div className={`text-xs ${t.text.muted}`}>Position</div>
                              <div className={`font-medium font-mono ${t.text.primary}`}>{Number(fields.position).toLocaleString()}</div>
                            </div>
                          )}
                          {fields.GMAF && (
                            <div className={`p-2 rounded-lg ${isDarkMode ? 'bg-slate-700/30' : 'bg-gray-100/60'}`}>
                              <div className={`text-xs ${t.text.muted}`}>Global MAF</div>
                              <div className={`font-medium font-mono ${t.text.primary}`}>{(Number(fields.GMAF) * 100).toFixed(1)}%</div>
                            </div>
                          )}
                        </div>

                        {/* Genotype table */}
                        {genotypes.length > 0 && (
                          <div>
                            <h5 className={`text-sm font-semibold ${t.text.secondary} mb-2`}>Genotypes</h5>
                            <div className="overflow-x-auto">
                              <table className="w-full text-sm">
                                <thead>
                                  <tr className={`border-b ${t.glassBorder}`}>
                                    <th className={`text-left py-2 px-3 ${t.text.muted} text-xs font-medium`}>Genotype</th>
                                    <th className={`text-left py-2 px-3 ${t.text.muted} text-xs font-medium`}>Magnitude</th>
                                    <th className={`text-left py-2 px-3 ${t.text.muted} text-xs font-medium`}>Repute</th>
                                    <th className={`text-left py-2 px-3 ${t.text.muted} text-xs font-medium`}>Summary</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {genotypes.map((g, i) => (
                                    <tr key={i} className={`border-b ${t.glassBorder} ${isDarkMode ? 'hover:bg-slate-700/20' : 'hover:bg-gray-100/40'}`}>
                                      <td className={`py-2 px-3 font-mono font-medium ${t.text.primary}`}>({g.allele1};{g.allele2})</td>
                                      <td className={`py-2 px-3 ${t.text.secondary}`}>{g.magnitude}</td>
                                      <td className="py-2 px-3">
                                        {g.repute && (
                                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                                            g.repute.toLowerCase() === 'bad'
                                              ? isDarkMode ? 'bg-red-500/20 text-red-300' : 'bg-red-100 text-red-700'
                                              : g.repute.toLowerCase() === 'good'
                                                ? isDarkMode ? 'bg-green-500/20 text-green-300' : 'bg-green-100 text-green-700'
                                                : isDarkMode ? 'bg-slate-500/20 text-slate-300' : 'bg-gray-100 text-gray-600'
                                          }`}>
                                            {g.repute}
                                          </span>
                                        )}
                                      </td>
                                      <td className={`py-2 px-3 text-xs ${t.text.secondary}`}>{g.summary}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}
                      </div>
                    )
                  })()}
                </div>
              )}

              {/* Pharmacogenomics */}
              {lookupResults.pharmacogenomics?.found && (() => {
                const pgxData = lookupResults.pharmacogenomics.data;
                const variants = Array.isArray(pgxData) ? pgxData : [pgxData];
                return (
                  <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                    <h4 className={`font-bold ${t.text.primary} mb-3 flex items-center gap-2`}>
                      <Info className="h-4 w-4 text-purple-500" />
                      Pharmacogenomic Data
                      <span className={`text-xs font-normal ${t.text.tertiary}`}>ClinPGx</span>
                    </h4>
                    {variants.filter(Boolean).map((v: Record<string, unknown>, vi: number) => {
                      const genes = (v.relatedGenes as Array<{ symbol?: string; name?: string }>) || [];
                      const locations = (v.locations as Array<{ assembly?: string; begin?: number; end?: number; variantAlleles?: string[]; sequence?: { name?: string } }>) || [];
                      const genomicLocs = locations.filter(l => l.assembly);
                      return (
                        <div key={vi} className={`${vi > 0 ? 'mt-4 pt-4 border-t ' + t.glassBorder : ''}`}>
                          <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
                            <div>
                              <span className={`${t.text.tertiary} text-xs`}>Variant</span>
                              <p className={`${t.text.primary} font-medium`}>{(v.symbol as string) || (v.name as string) || '—'}</p>
                            </div>
                            <div>
                              <span className={`${t.text.tertiary} text-xs`}>Type</span>
                              <p className={`${t.text.primary}`}>{(v.type as string) || '—'} · {(v.changeClassification as string) || '—'}</p>
                            </div>
                            {v.clinicalSignificance && (
                              <div>
                                <span className={`${t.text.tertiary} text-xs`}>Clinical Significance</span>
                                <p className={`font-medium ${(v.clinicalSignificance as string) === 'drug-response' ? 'text-purple-500' : t.text.primary}`}>{(v.clinicalSignificance as string)}</p>
                              </div>
                            )}
                            {genes.length > 0 && (
                              <div>
                                <span className={`${t.text.tertiary} text-xs`}>Related Genes</span>
                                <div className="flex flex-wrap gap-1 mt-0.5">
                                  {genes.map((g, gi) => (
                                    <span key={gi} className={`px-2 py-0.5 rounded text-xs font-medium ${isDarkMode ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30' : 'bg-purple-100 text-purple-700 border border-purple-200'}`}>
                                      {g.symbol}{g.name ? ` — ${g.name}` : ''}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                            <div>
                              <span className={`${t.text.tertiary} text-xs`}>Rarity</span>
                              <p className={`${t.text.primary}`}>{v.rare ? 'Rare' : 'Common'}{v.raritySource ? ` (${v.raritySource as string})` : ''}</p>
                            </div>
                          </div>
                          {genomicLocs.length > 0 && (
                            <div className="mt-3">
                              <span className={`${t.text.tertiary} text-xs`}>Genomic Locations</span>
                              <div className={`mt-1 rounded-lg overflow-hidden border ${t.glassBorder}`}>
                                <table className="w-full text-xs">
                                  <thead>
                                    <tr className={isDarkMode ? 'bg-slate-700/30' : 'bg-gray-100/60'}>
                                      <th className={`py-1.5 px-3 text-left ${t.text.tertiary}`}>Assembly</th>
                                      <th className={`py-1.5 px-3 text-left ${t.text.tertiary}`}>Position</th>
                                      <th className={`py-1.5 px-3 text-left ${t.text.tertiary}`}>Alt Alleles</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {genomicLocs.map((loc, li) => (
                                      <tr key={li} className={li % 2 === 0 ? '' : (isDarkMode ? 'bg-slate-700/10' : 'bg-gray-50/40')}>
                                        <td className={`py-1.5 px-3 ${t.text.primary}`}>{loc.assembly}</td>
                                        <td className={`py-1.5 px-3 font-mono ${t.text.secondary}`}>{loc.sequence?.name?.replace(/\[.*?\]/, '')}:{loc.begin?.toLocaleString()}</td>
                                        <td className={`py-1.5 px-3 font-mono ${t.text.secondary}`}>{loc.variantAlleles?.join(', ') || '—'}</td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                );
              })()}

              {/* AlphaMissense AI Prediction */}
              {lookupResults.alpha_missense?.found && (
                <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                  <h4 className={`font-bold ${t.text.primary} mb-3 flex items-center gap-2`}>
                    <AlertTriangle className="h-4 w-4 text-amber-500" />
                    AlphaMissense AI Prediction
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${isDarkMode ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30' : 'bg-amber-100 text-amber-700 border border-amber-200'}`}>
                      AI
                    </span>
                  </h4>
                  <div className="space-y-3">
                    {/* Score and classification */}
                    {lookupResults.alpha_missense.am_pathogenicity != null && (
                      <div>
                        <div className="flex items-center justify-between mb-1.5">
                          <span className={`text-sm ${t.text.secondary}`}>Pathogenicity Score</span>
                          <span className={`text-lg font-mono font-bold ${
                            lookupResults.alpha_missense.am_pathogenicity > 0.564 ? 'text-red-400' :
                            lookupResults.alpha_missense.am_pathogenicity < 0.34 ? 'text-green-400' : 'text-amber-400'
                          }`}>
                            {lookupResults.alpha_missense.am_pathogenicity.toFixed(4)}
                          </span>
                        </div>
                        <div className="relative h-3 rounded-full bg-gradient-to-r from-green-500 via-amber-500 to-red-500 overflow-hidden">
                          <div
                            className="absolute top-0 h-full w-1.5 bg-white rounded-full shadow-lg"
                            style={{ left: `${Math.min(lookupResults.alpha_missense.am_pathogenicity * 100, 100)}%` }}
                          />
                        </div>
                        <div className="flex justify-between mt-1">
                          <span className={`text-xs ${t.text.muted}`}>Benign (0)</span>
                          <span className={`text-xs ${t.text.muted}`}>Pathogenic (1)</span>
                        </div>
                      </div>
                    )}
                    {/* Classification + protein */}
                    <div className="grid grid-cols-2 gap-3">
                      {lookupResults.alpha_missense.am_class && (
                        <div className={`p-2.5 rounded-lg ${isDarkMode ? 'bg-slate-700/30' : 'bg-gray-100/60'}`}>
                          <div className={`text-xs ${t.text.muted} mb-1`}>Classification</div>
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                            lookupResults.alpha_missense.am_class === 'likely_pathogenic'
                              ? isDarkMode ? 'bg-red-500/20 text-red-300' : 'bg-red-100 text-red-700'
                              : lookupResults.alpha_missense.am_class === 'likely_benign'
                                ? isDarkMode ? 'bg-green-500/20 text-green-300' : 'bg-green-100 text-green-700'
                                : isDarkMode ? 'bg-amber-500/20 text-amber-300' : 'bg-amber-100 text-amber-700'
                          }`}>
                            {lookupResults.alpha_missense.am_class.replace(/_/g, ' ')}
                          </span>
                        </div>
                      )}
                      {lookupResults.alpha_missense.protein_variant && (
                        <div className={`p-2.5 rounded-lg ${isDarkMode ? 'bg-slate-700/30' : 'bg-gray-100/60'}`}>
                          <div className={`text-xs ${t.text.muted} mb-1`}>Protein Change</div>
                          <span className={`text-sm font-mono font-medium ${t.text.primary}`}>
                            {lookupResults.alpha_missense.protein_variant}
                          </span>
                        </div>
                      )}
                    </div>
                    {/* Gene-level mean pathogenicity */}
                    {lookupResults.alpha_missense.gene_mean_pathogenicity != null && (
                      <div className={`p-2.5 rounded-lg ${isDarkMode ? 'bg-slate-700/30' : 'bg-gray-100/60'}`}>
                        <div className={`text-xs ${t.text.muted} mb-1`}>Gene Average Pathogenicity</div>
                        <span className={`text-sm font-mono font-medium ${
                          lookupResults.alpha_missense.gene_mean_pathogenicity > 0.564 ? 'text-red-400' :
                          lookupResults.alpha_missense.gene_mean_pathogenicity < 0.34 ? 'text-green-400' : 'text-amber-400'
                        }`}>
                          {lookupResults.alpha_missense.gene_mean_pathogenicity.toFixed(4)}
                        </span>
                        <span className={`text-xs ${t.text.muted} ml-2`}>(mean across all missense variants in this gene)</span>
                      </div>
                    )}
                    {/* Isoform predictions */}
                    {lookupResults.alpha_missense.isoforms && lookupResults.alpha_missense.isoforms.length > 1 && (
                      <div>
                        <div className={`text-xs ${t.text.muted} mb-1.5`}>Isoform Predictions ({lookupResults.alpha_missense.isoform_count})</div>
                        <div className="space-y-1">
                          {lookupResults.alpha_missense.isoforms.slice(0, 6).map((iso: AlphaMissenseIsoform, i: number) => (
                            <div key={i} className={`flex items-center gap-3 text-xs p-2 rounded-lg ${isDarkMode ? 'bg-slate-700/20' : 'bg-gray-50'}`}>
                              <span className={`font-mono ${t.text.secondary} truncate max-w-[160px]`} title={iso.transcript_id}>{iso.transcript_id}</span>
                              <span className={`font-mono ${t.text.primary}`}>{iso.protein_variant}</span>
                              <span className={`font-mono font-medium ${
                                iso.am_pathogenicity > 0.564 ? 'text-red-400' :
                                iso.am_pathogenicity < 0.34 ? 'text-green-400' : 'text-amber-400'
                              }`}>
                                {iso.am_pathogenicity.toFixed(4)}
                              </span>
                              <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                                iso.am_class === 'likely_pathogenic'
                                  ? isDarkMode ? 'bg-red-500/20 text-red-300' : 'bg-red-100 text-red-700'
                                  : iso.am_class === 'likely_benign'
                                    ? isDarkMode ? 'bg-green-500/20 text-green-300' : 'bg-green-100 text-green-700'
                                    : isDarkMode ? 'bg-amber-500/20 text-amber-300' : 'bg-amber-100 text-amber-700'
                              }`}>
                                {iso.am_class.replace(/_/g, ' ')}
                              </span>
                            </div>
                          ))}
                          {lookupResults.alpha_missense.isoforms.length > 6 && (
                            <span className={`text-xs ${t.text.muted}`}>+ {lookupResults.alpha_missense.isoforms.length - 6} more isoforms</span>
                          )}
                        </div>
                      </div>
                    )}
                    {/* Disclaimer */}
                    <div className={`flex items-start gap-2 p-2.5 rounded-lg ${isDarkMode ? 'bg-amber-500/10 border border-amber-500/20' : 'bg-amber-50 border border-amber-200'}`}>
                      <AlertTriangle className={`h-3.5 w-3.5 mt-0.5 flex-shrink-0 ${isDarkMode ? 'text-amber-400' : 'text-amber-600'}`} />
                      <p className={`text-xs ${isDarkMode ? 'text-amber-300/80' : 'text-amber-700'} leading-relaxed`}>
                        {lookupResults.alpha_missense.disclaimer || 'AlphaMissense predictions are AI-generated (DeepMind) and have NOT been clinically validated. Do not use for clinical decision-making.'}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* ── ClinVar Local Conditions ── */}
              {lookupResults.annotations?.clinvar_local && (() => {
                const cv = lookupResults.annotations.clinvar_local
                const rawConditions = cv.conditions || []
                const genes = cv.genes || []
                const clinsig = cv.clinical_significance
                // Split pipe-delimited conditions, filter "not provided", deduplicate
                const conditions = [...new Set(
                  rawConditions.flatMap((c: string) => c.split('|').map((s: string) => s.trim()))
                    .filter((s: string) => s && s.toLowerCase() !== 'not provided')
                )]
                if (!conditions.length && !genes.length) return null
                return (
                  <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                    <h4 className={`font-bold ${t.text.primary} mb-3 flex items-center gap-2`}>
                      <Database className="h-4 w-4 text-rose-500" />
                      ClinVar Local Database
                    </h4>
                    {clinsig && (
                      <div className={`text-sm mb-2 ${t.text.secondary}`}>
                        Significance: <span className={`font-medium ${
                          clinsig.toLowerCase().includes('pathogenic') ? 'text-red-400' :
                          clinsig.toLowerCase().includes('benign') ? 'text-green-400' : t.text.primary
                        }`}>{clinsig}</span>
                      </div>
                    )}
                    {genes.length > 0 && (
                      <div className={`text-sm mb-2 ${t.text.secondary}`}>
                        Genes: <span className={`font-mono font-medium ${t.text.primary}`}>{genes.join(', ')}</span>
                      </div>
                    )}
                    {conditions.length > 0 && (
                      <div>
                        <div className={`text-sm mb-1.5 ${t.text.secondary}`}>Associated conditions:</div>
                        <div className="flex flex-wrap gap-1.5">
                          {conditions.slice(0, 8).map((c: string) => (
                            <span key={c} className={`px-2 py-0.5 rounded text-xs ${isDarkMode ? 'bg-rose-500/15 text-rose-300' : 'bg-rose-100 text-rose-700'}`}>
                              {c}
                            </span>
                          ))}
                          {conditions.length > 8 && (
                            <span className={`text-xs ${t.text.muted}`}>+ {conditions.length - 8} more</span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )
              })()}

              {/* ── gnomAD Local Frequencies ── */}
              {/* gated on actual frequency fields, not just `found` — CADD-only
                  hits carry conservation/pathogenicity data with no af/ac/an/hom */}
              {lookupResults.annotations?.gnomad_local?.found &&
               (lookupResults.annotations.gnomad_local.af != null ||
                lookupResults.annotations.gnomad_local.ac != null ||
                lookupResults.annotations.gnomad_local.an != null ||
                lookupResults.annotations.gnomad_local.hom != null) && (() => {
                const gn = lookupResults.annotations.gnomad_local
                const af = gn.af
                const ac = gn.ac
                const an = gn.an
                const hom = gn.hom
                return (
                  <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                    <h4 className={`font-bold ${t.text.primary} mb-3 flex items-center gap-2`}>
                      <BarChart3 className="h-4 w-4 text-teal-500" />
                      gnomAD Frequencies
                    </h4>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                      {af != null && (
                        <div>
                          <div className={`text-xs ${t.text.muted}`}>Allele Freq</div>
                          <div className={`text-sm font-mono font-medium ${
                            af < 0.001 ? 'text-red-400' : af < 0.01 ? 'text-amber-400' : t.text.primary
                          }`}>{af < 0.001 ? af.toExponential(2) : af.toFixed(4)}</div>
                        </div>
                      )}
                      {ac != null && (
                        <div>
                          <div className={`text-xs ${t.text.muted}`}>Allele Count</div>
                          <div className={`text-sm font-mono ${t.text.primary}`}>{ac.toLocaleString()}</div>
                        </div>
                      )}
                      {an != null && (
                        <div>
                          <div className={`text-xs ${t.text.muted}`}>Allele Number</div>
                          <div className={`text-sm font-mono ${t.text.primary}`}>{an.toLocaleString()}</div>
                        </div>
                      )}
                      {hom != null && (
                        <div>
                          <div className={`text-xs ${t.text.muted}`}>Homozygotes</div>
                          <div className={`text-sm font-mono ${t.text.primary}`}>{hom.toLocaleString()}</div>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })()}

              {/* ── Gene Constraint (gnomAD) ── */}
              {lookupResults.annotations?.gnomad_constraint && (() => {
                const gc = lookupResults.annotations.gnomad_constraint
                const pli = gc.pli
                const loeuf = gc.loeuf
                const interp = gc.interpretation
                return (
                  <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                    <h4 className={`font-bold ${t.text.primary} mb-3 flex items-center gap-2`}>
                      <BarChart3 className="h-4 w-4 text-teal-500" />
                      Gene Constraint — {gc.gene}
                    </h4>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                      {pli != null && (
                        <div>
                          <div className={`text-xs ${t.text.muted}`}>pLI</div>
                          <div className={`text-sm font-mono font-medium ${
                            pli > 0.9 ? 'text-red-400' : pli > 0.5 ? 'text-amber-400' : 'text-green-400'
                          }`}>{pli.toFixed(3)}</div>
                        </div>
                      )}
                      {loeuf != null && (
                        <div>
                          <div className={`text-xs ${t.text.muted}`}>LOEUF</div>
                          <div className={`text-sm font-mono font-medium ${
                            loeuf < 0.35 ? 'text-red-400' : loeuf < 0.6 ? 'text-amber-400' : 'text-green-400'
                          }`}>{loeuf.toFixed(3)}</div>
                        </div>
                      )}
                      {interp && (
                        <div>
                          <div className={`text-xs ${t.text.muted}`}>Interpretation</div>
                          <div className={`text-sm font-medium ${t.text.primary}`}>{interp}</div>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })()}

              {/* ── Ensembl Local Gene Info ── */}
              {lookupResults.annotations?.ensembl_local?.found && (() => {
                const eg = lookupResults.annotations.ensembl_local
                return (
                  <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                    <h4 className={`font-bold ${t.text.primary} mb-3 flex items-center gap-2`}>
                      <Database className="h-4 w-4 text-emerald-500" />
                      Ensembl Gene — {eg.gene_symbol}
                    </h4>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
                      <div>
                        <div className={`text-xs ${t.text.muted}`}>Gene ID</div>
                        <div className={`font-mono ${t.text.primary}`}>{eg.gene_id}</div>
                      </div>
                      <div>
                        <div className={`text-xs ${t.text.muted}`}>Biotype</div>
                        <div className={t.text.primary}>{(eg.biotype || '').replace(/_/g, ' ')}</div>
                      </div>
                      {eg.transcript_count && (
                        <div>
                          <div className={`text-xs ${t.text.muted}`}>Transcripts</div>
                          <div className={t.text.primary}>{eg.transcript_count}</div>
                        </div>
                      )}
                      {eg.chromosome && (
                        <div className="col-span-2 sm:col-span-3">
                          <div className={`text-xs ${t.text.muted}`}>Location</div>
                          <div className={`font-mono ${t.text.primary}`}>
                            chr{eg.chromosome}:{eg.start?.toLocaleString()}-{eg.end?.toLocaleString()} ({eg.strand === 1 ? '+' : '-'})
                          </div>
                        </div>
                      )}
                      {eg.description && (
                        <div className="col-span-2 sm:col-span-3">
                          <div className={`text-xs ${t.text.muted}`}>Description</div>
                          <div className={`${t.text.secondary} text-xs`}>{eg.description}</div>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })()}

              {/* ── ChEMBL Drug Data ── */}
              {lookupResults.annotations?.bq_chembl?.found && (() => {
                const ch = lookupResults.annotations.bq_chembl
                const drugs = ch.drugs || []
                if (!drugs.length) return null
                return (
                  <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                    <h4 className={`font-bold ${t.text.primary} mb-3 flex items-center gap-2`}>
                      <Database className="h-4 w-4 text-indigo-500" />
                      ChEMBL Drug Targets ({drugs.length})
                    </h4>
                    <div className="space-y-2">
                      {drugs.slice(0, 6).map((d, i) => (
                        <div key={i} className={`flex items-center justify-between gap-3 px-3 py-2 rounded-lg ${isDarkMode ? 'bg-slate-800/40' : 'bg-gray-50'}`}>
                          <div>
                            <span className={`text-sm font-medium ${t.text.primary}`}>{d.drug_name}</span>
                            {d.max_phase != null && (
                              <span className={`ml-2 text-xs ${t.text.muted}`}>Phase {d.max_phase}</span>
                            )}
                          </div>
                          {d.mechanism && (
                            <span className={`text-xs ${t.text.secondary} truncate max-w-[200px]`}>{d.mechanism}</span>
                          )}
                        </div>
                      ))}
                      {drugs.length > 6 && (
                        <span className={`text-xs ${t.text.muted}`}>+ {drugs.length - 6} more drugs</span>
                      )}
                    </div>
                  </div>
                )
              })()}

              {/* ── AlphaFold Structure ── */}
              {lookupResults.annotations?.bq_alphafold?.found && (() => {
                const af = lookupResults.annotations.bq_alphafold
                return (
                  <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                    <h4 className={`font-bold ${t.text.primary} mb-3 flex items-center gap-2`}>
                      <Database className="h-4 w-4 text-cyan-500" />
                      AlphaFold Structure
                    </h4>
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      {af.uniprot_id && (
                        <div>
                          <div className={`text-xs ${t.text.muted}`}>UniProt ID</div>
                          <div className={`font-mono ${t.text.primary}`}>{af.uniprot_id}</div>
                        </div>
                      )}
                      {af.avg_plddt != null && (
                        <div>
                          <div className={`text-xs ${t.text.muted}`}>Avg. pLDDT</div>
                          <div className={`font-mono font-medium ${
                            af.avg_plddt > 90 ? 'text-green-400' :
                            af.avg_plddt > 70 ? 'text-amber-400' : 'text-red-400'
                          }`}>{af.avg_plddt.toFixed(1)}</div>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })()}

              {/* ── Transcript Consequences (VEP) ── */}
              {(lookupResults.annotations?.transcript_consequences?.length ?? 0) > 0 && (() => {
                const tcs = lookupResults.annotations!.transcript_consequences!
                const canonical = tcs.find(t => t.canonical === 1) || tcs[0]
                const worstSift = tcs.reduce<TranscriptConsequence | null>((w, t) =>
                  t.sift_score != null && (w == null || t.sift_score < (w.sift_score ?? 1)) ? t : w, null)
                const worstPP = tcs.reduce<TranscriptConsequence | null>((w, t) =>
                  t.polyphen_score != null && (w == null || t.polyphen_score > (w.polyphen_score ?? 0)) ? t : w, null)
                return (
                  <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                    <h4 className={`font-bold ${t.text.primary} mb-1 flex items-center gap-2`}>
                      <FlaskConical className="h-4 w-4 text-blue-500" />
                      Transcript Consequences
                      <span className={`text-xs font-normal ${t.text.muted}`}>{tcs.length} transcript{tcs.length !== 1 ? 's' : ''} · Ensembl VEP</span>
                    </h4>
                    {/* Key scores row */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                      {worstSift && worstSift.sift_score != null && (
                        <div className={`p-2.5 rounded-lg ${isDarkMode ? 'bg-slate-700/30' : 'bg-gray-100/60'}`}>
                          <div className={`text-xs ${t.text.muted} mb-1`}>SIFT (lowest)</div>
                          <div className={`text-sm font-mono font-medium ${worstSift.sift_score < 0.05 ? 'text-red-400' : 'text-green-400'}`}>
                            {worstSift.sift_score.toFixed(3)}
                          </div>
                          {worstSift.sift_prediction && (
                            <div className={`text-xs mt-0.5 ${t.text.muted}`}>{worstSift.sift_prediction.replace(/_/g, ' ')}</div>
                          )}
                        </div>
                      )}
                      {worstPP && worstPP.polyphen_score != null && (
                        <div className={`p-2.5 rounded-lg ${isDarkMode ? 'bg-slate-700/30' : 'bg-gray-100/60'}`}>
                          <div className={`text-xs ${t.text.muted} mb-1`}>PolyPhen-2 (highest)</div>
                          <div className={`text-sm font-mono font-medium ${worstPP.polyphen_score > 0.85 ? 'text-red-400' : worstPP.polyphen_score > 0.446 ? 'text-amber-400' : 'text-green-400'}`}>
                            {worstPP.polyphen_score.toFixed(3)}
                          </div>
                          {worstPP.polyphen_prediction && (
                            <div className={`text-xs mt-0.5 ${t.text.muted}`}>{worstPP.polyphen_prediction.replace(/_/g, ' ')}</div>
                          )}
                        </div>
                      )}
                      {canonical?.hgvsc && (
                        <div className={`p-2.5 rounded-lg ${isDarkMode ? 'bg-slate-700/30' : 'bg-gray-100/60'} col-span-2`}>
                          <div className={`text-xs ${t.text.muted} mb-1`}>HGVS (canonical)</div>
                          <div className={`text-xs font-mono ${t.text.primary} break-all`}>{canonical.hgvsc}</div>
                          {canonical.hgvsp && <div className={`text-xs font-mono ${t.text.secondary} break-all`}>{canonical.hgvsp}</div>}
                        </div>
                      )}
                    </div>
                    {/* Transcript table */}
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className={`border-b ${t.glassBorder}`}>
                            <th className={`text-left py-2 px-2 ${t.text.muted} font-medium`}>Transcript</th>
                            <th className={`text-left py-2 px-2 ${t.text.muted} font-medium`}>Consequence</th>
                            <th className={`text-left py-2 px-2 ${t.text.muted} font-medium`}>Impact</th>
                            <th className={`text-left py-2 px-2 ${t.text.muted} font-medium`}>SIFT</th>
                            <th className={`text-left py-2 px-2 ${t.text.muted} font-medium`}>PolyPhen</th>
                          </tr>
                        </thead>
                        <tbody>
                          {tcs.slice(0, 8).map((tc, i) => (
                            <tr key={i} className={`border-b ${t.glassBorder} ${isDarkMode ? 'hover:bg-slate-700/20' : 'hover:bg-gray-100/40'}`}>
                              <td className={`py-2 px-2 font-mono ${tc.canonical ? t.text.primary : t.text.secondary}`}>
                                {tc.transcript_id || '—'}
                                {tc.canonical === 1 && <span className={`ml-1 text-[10px] ${isDarkMode ? 'text-indigo-400' : 'text-indigo-600'}`}>canonical</span>}
                              </td>
                              <td className="py-2 px-2">
                                {tc.consequence_terms?.[0] && (
                                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                                    (tc.consequence_terms[0] || '').includes('missense') || (tc.consequence_terms[0] || '').includes('stop') || (tc.consequence_terms[0] || '').includes('frameshift')
                                      ? isDarkMode ? 'bg-red-500/20 text-red-300' : 'bg-red-100 text-red-700'
                                      : (tc.consequence_terms[0] || '').includes('synonymous')
                                        ? isDarkMode ? 'bg-green-500/20 text-green-300' : 'bg-green-100 text-green-700'
                                        : isDarkMode ? 'bg-slate-600/30 text-slate-300' : 'bg-gray-100 text-gray-600'
                                  }`}>
                                    {tc.consequence_terms[0].replace(/_/g, ' ')}
                                  </span>
                                )}
                              </td>
                              <td className={`py-2 px-2 font-medium ${
                                tc.impact === 'HIGH' ? 'text-red-400' :
                                tc.impact === 'MODERATE' ? 'text-amber-400' :
                                tc.impact === 'LOW' ? 'text-green-400' : t.text.muted
                              }`}>{tc.impact || '—'}</td>
                              <td className={`py-2 px-2 font-mono ${tc.sift_score != null && tc.sift_score < 0.05 ? 'text-red-400' : 'text-green-400'}`}>
                                {tc.sift_score != null ? tc.sift_score.toFixed(3) : '—'}
                              </td>
                              <td className={`py-2 px-2 font-mono ${tc.polyphen_score != null && tc.polyphen_score > 0.85 ? 'text-red-400' : tc.polyphen_score != null && tc.polyphen_score > 0.446 ? 'text-amber-400' : 'text-green-400'}`}>
                                {tc.polyphen_score != null ? tc.polyphen_score.toFixed(3) : '—'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {tcs.length > 8 && (
                      <p className={`text-xs ${t.text.muted} mt-2`}>Showing 8 of {tcs.length} transcripts</p>
                    )}
                  </div>
                )
              })()}

              {/* ── GWAS Catalog ── */}
              {lookupResults.annotations?.gwas_catalog?.found && (() => {
                const gw = lookupResults.annotations.gwas_catalog!
                return (
                  <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                    <h4 className={`font-bold ${t.text.primary} mb-1 flex items-center gap-2`}>
                      <Activity className="h-4 w-4 text-purple-500" />
                      GWAS Catalog
                      {gw.genome_wide_significant && (
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${isDarkMode ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30' : 'bg-purple-100 text-purple-700 border border-purple-200'}`}>
                          Genome-Wide Significant
                        </span>
                      )}
                    </h4>
                    <p className={`text-xs ${t.text.secondary} mb-3 leading-relaxed`}>
                      Large population studies link this variant to the traits below. A lower p‑value means a stronger, more replicated association.
                      {gw.genome_wide_significant
                        ? ' All associations shown meet the p ≤ 5×10⁻⁸ genome-wide significance threshold.'
                        : ' These are statistical associations, not direct causes.'}
                    </p>
                    <div className={`space-y-2`}>
                      {gw.top_trait && (
                        <div className={`flex items-center justify-between rounded-lg p-2.5 border ${t.glassBorder} ${isDarkMode ? 'bg-purple-500/8' : 'bg-purple-50'}`}>
                          <span className={`text-sm font-semibold ${t.text.primary}`}>{gw.top_trait}</span>
                          {gw.top_p_value != null && (
                            <span className="text-xs font-mono text-purple-400">p = {gw.top_p_value.toExponential(2)}</span>
                          )}
                        </div>
                      )}
                      {(gw.associations?.length ?? 0) > 1 && gw.associations!.slice(1, 7).map((a, i) => {
                        const pval = a.p_value
                        const strength = pval == null ? '' : pval <= 1e-30 ? 'Very strong' : pval <= 1e-15 ? 'Strong' : pval <= 5e-8 ? 'Significant' : 'Suggestive'
                        const sc = strength === 'Very strong' ? 'text-purple-400' : strength === 'Strong' ? 'text-blue-400' : strength === 'Significant' ? 'text-green-400' : t.text.muted
                        return (
                          <div key={i} className={`flex items-center justify-between text-xs border-t ${t.glassBorder} pt-1.5`}>
                            <span className={`truncate max-w-[55%] ${t.text.secondary}`}>{a.mapped_trait ?? a.trait ?? '—'}</span>
                            <div className="flex items-center gap-2 shrink-0">
                              {strength && <span className={sc}>{strength}</span>}
                              <span className={`font-mono ${t.text.muted}`}>{pval != null ? `p=${pval.toExponential(1)}` : '—'}</span>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                    <div className={`text-xs ${t.text.muted} border-t ${t.glassBorder} pt-2 mt-3 grid grid-cols-2 gap-x-4`}>
                      <span className="text-purple-400">p ≤ 10⁻³⁰ · Very strong</span>
                      <span className="text-blue-400">p ≤ 10⁻¹⁵ · Strong</span>
                      <span className="text-green-400">p ≤ 5×10⁻⁸ · Significant (GWS)</span>
                      <span className={t.text.muted}>p &gt; 5×10⁻⁸ · Suggestive</span>
                    </div>
                    <a href={`https://www.ebi.ac.uk/gwas/search?query=${lookupResults.variant_id}`} target="_blank" rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-purple-400 hover:text-purple-300 transition-colors mt-2">
                      View in GWAS Catalog <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                )
              })()}

              {/* ── ClinGen Gene Validity ── */}
              {lookupResults.annotations?.clingen?.found && (() => {
                const cg = lookupResults.annotations.clingen!
                const clsColor = cg.strongest_classification === 'Definitive' ? 'bg-green-500/15 text-green-400 border-green-500/30'
                  : cg.strongest_classification === 'Strong' ? 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30'
                  : cg.strongest_classification === 'Moderate' ? 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30'
                  : cg.strongest_classification === 'Limited' ? 'bg-orange-500/15 text-orange-400 border-orange-500/30'
                  : 'bg-red-500/15 text-red-400 border-red-500/30'
                return (
                  <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                    <h4 className={`font-bold ${t.text.primary} mb-1 flex items-center gap-2`}>
                      <Shield className="h-4 w-4 text-green-500" />
                      ClinGen Gene Validity
                      {cg.strongest_classification && (
                        <span className={`px-2 py-0.5 rounded text-xs font-medium border ${clsColor}`}>{cg.strongest_classification}</span>
                      )}
                    </h4>
                    <p className={`text-xs ${t.text.secondary} mb-3`}>
                      Expert-curated evidence for <span className="font-semibold">{cg.gene_symbol}</span> gene-disease relationships.
                      {cg.disease_count ? ` ${cg.disease_count} disease association${cg.disease_count > 1 ? 's' : ''}.` : ''}
                      {cg.is_definitive && ' Definitive evidence — highest confidence classification.'}
                      {cg.is_disputed && ' This gene-disease relationship is disputed.'}
                    </p>
                    {(cg.curations?.length ?? 0) > 0 && (
                      <div className="space-y-1">
                        {cg.curations!.slice(0, 5).map((c, i) => {
                          const cc = c.classification === 'Definitive' ? 'bg-green-500/15 text-green-400' : c.classification === 'Strong' ? 'bg-cyan-500/15 text-cyan-400' : c.classification === 'Moderate' ? 'bg-yellow-500/15 text-yellow-400' : c.classification === 'Limited' ? 'bg-orange-500/15 text-orange-400' : 'bg-red-500/15 text-red-400'
                          return (
                            <div key={i} className={`flex items-center justify-between text-xs p-2 rounded-lg ${isDarkMode ? 'bg-slate-700/20' : 'bg-gray-50'}`}>
                              <div>
                                <span className={`font-medium ${t.text.primary}`}>{c.disease_label || '—'}</span>
                                {c.moi && <span className={`ml-2 ${t.text.muted}`}>· {c.moi}</span>}
                              </div>
                              {c.classification && (
                                <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${cc}`}>{c.classification}</span>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )}
                    <a href={`https://search.clinicalgenome.org/kb/gene-validity?gene=${cg.gene_symbol ?? ''}`} target="_blank" rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-green-400 hover:text-green-300 transition-colors mt-2">
                      View ClinGen curations <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                )
              })()}

              {/* ── Open Targets ── */}
              {lookupResults.annotations?.open_targets?.found && (() => {
                const ot = lookupResults.annotations.open_targets!
                return (
                  <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                    <h4 className={`font-bold ${t.text.primary} mb-1 flex items-center gap-2`}>
                      <BarChart3 className="h-4 w-4 text-orange-500" />
                      Open Targets
                      {ot.has_strong_genetic_evidence && (
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${isDarkMode ? 'bg-orange-500/20 text-orange-300 border border-orange-500/30' : 'bg-orange-100 text-orange-700 border border-orange-200'}`}>
                          Strong genetic evidence
                        </span>
                      )}
                    </h4>
                    <p className={`text-xs ${t.text.secondary} mb-3`}>
                      Gene–disease association scores from Open Targets Platform for <span className="font-semibold">{ot.gene_symbol ?? lookupResults.basic_info?.gene_symbol}</span>.
                      Scores combine genetic, literature, somatic and other evidence (0–1 scale).
                    </p>
                    {ot.max_score != null && (
                      <div className="mb-4">
                        <div className="flex items-center justify-between mb-1">
                          <span className={`text-xs ${t.text.secondary}`}>Highest association score</span>
                          <span className={`text-sm font-mono font-bold ${ot.max_score > 0.7 ? 'text-red-400' : ot.max_score > 0.4 ? 'text-amber-400' : 'text-green-400'}`}>
                            {ot.max_score.toFixed(2)}
                          </span>
                        </div>
                        <div className={`h-2 rounded-full overflow-hidden ${isDarkMode ? 'bg-slate-700/50' : 'bg-gray-200'}`}>
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-orange-500 to-red-500 transition-all"
                            style={{ width: `${Math.round(ot.max_score * 100)}%` }}
                          />
                        </div>
                      </div>
                    )}
                    {(ot.associations?.length ?? 0) > 0 && (
                      <div className="space-y-1">
                        {ot.associations!.slice(0, 5).map((a, i) => (
                          <div key={i} className={`flex items-center justify-between text-xs p-2 rounded-lg ${isDarkMode ? 'bg-slate-700/20' : 'bg-gray-50'}`}>
                            <span className={`font-medium ${t.text.primary} truncate max-w-[60%]`}>{a.disease_label || '—'}</span>
                            <div className="flex items-center gap-2 shrink-0">
                              {a.genetic_association != null && (
                                <span className={`${t.text.muted}`} title="Genetic association">G:{a.genetic_association.toFixed(2)}</span>
                              )}
                              {a.overall_score != null && (
                                <span className={`font-mono font-medium ${a.overall_score > 0.7 ? 'text-red-400' : a.overall_score > 0.4 ? 'text-amber-400' : 'text-green-400'}`}>
                                  {a.overall_score.toFixed(2)}
                                </span>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    <a href={`https://platform.opentargets.org/target/${ot.ensembl_id ?? ''}`} target="_blank" rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-orange-400 hover:text-orange-300 transition-colors mt-2">
                      View on Open Targets Platform <ExternalLink className="h-3 w-3" />
                    </a>
                  </div>
                )
              })()}

              {/* External Links */}
              <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                <h4 className={`font-bold ${t.text.primary} mb-3 flex items-center gap-2`}>
                  <ExternalLink className="h-4 w-4 text-purple-500" />
                  External Resources
                </h4>
                <div className="flex flex-wrap gap-2">
                  {[
                    { label: 'dbSNP', url: `https://www.ncbi.nlm.nih.gov/snp/${lookupResults.variant_id}`, color: isDarkMode ? 'bg-blue-500/20 hover:bg-blue-500/30 text-blue-300' : 'bg-blue-100 hover:bg-blue-200 text-blue-800', show: true },
                    { label: 'Ensembl', url: `https://www.ensembl.org/Homo_sapiens/Variation/Summary?v=${lookupResults.variant_id}`, color: isDarkMode ? 'bg-green-500/20 hover:bg-green-500/30 text-green-300' : 'bg-green-100 hover:bg-green-200 text-green-800', show: !!lookupResults.annotations?.ensembl?.found },
                    { label: 'ClinVar', url: `https://www.ncbi.nlm.nih.gov/clinvar/?term=${lookupResults.variant_id}`, color: isDarkMode ? 'bg-red-500/20 hover:bg-red-500/30 text-red-300' : 'bg-red-100 hover:bg-red-200 text-red-800', show: !!lookupResults.annotations?.clinvar?.found },
                    { label: 'ClinPGx', url: `https://www.clinpgx.org/variant/${lookupResults.variant_id}`, color: isDarkMode ? 'bg-purple-500/20 hover:bg-purple-500/30 text-purple-300' : 'bg-purple-100 hover:bg-purple-200 text-purple-800', show: !!lookupResults.pharmacogenomics?.found },
                    { label: 'SNPedia', url: `https://www.snpedia.com/index.php/${lookupResults.variant_id}`, color: isDarkMode ? 'bg-orange-500/20 hover:bg-orange-500/30 text-orange-300' : 'bg-orange-100 hover:bg-orange-200 text-orange-800', show: !!lookupResults.literature?.snpedia_found },
                    { label: 'GWAS Catalog', url: `https://www.ebi.ac.uk/gwas/search?query=${lookupResults.variant_id}`, color: isDarkMode ? 'bg-violet-500/20 hover:bg-violet-500/30 text-violet-300' : 'bg-violet-100 hover:bg-violet-200 text-violet-800', show: !!lookupResults.annotations?.gwas_catalog?.found },
                    { label: 'ClinGen', url: `https://search.clinicalgenome.org/kb/gene-validity?gene=${lookupResults.annotations?.clingen?.gene_symbol ?? lookupResults.basic_info?.gene_symbol ?? ''}`, color: isDarkMode ? 'bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300' : 'bg-emerald-100 hover:bg-emerald-200 text-emerald-800', show: !!lookupResults.annotations?.clingen?.found },
                    { label: 'Open Targets', url: `https://platform.opentargets.org/target/${lookupResults.annotations?.open_targets?.ensembl_id ?? ''}`, color: isDarkMode ? 'bg-amber-500/20 hover:bg-amber-500/30 text-amber-300' : 'bg-amber-100 hover:bg-amber-200 text-amber-800', show: !!lookupResults.annotations?.open_targets?.found },
                    { label: 'PubMed', url: `https://pubmed.ncbi.nlm.nih.gov/?term=${lookupResults.variant_id}`, color: isDarkMode ? 'bg-teal-500/20 hover:bg-teal-500/30 text-teal-300' : 'bg-teal-100 hover:bg-teal-200 text-teal-800', show: true },
                  ].filter(link => link.show).map(link => (
                    <a key={link.label} href={link.url} target="_blank" rel="noopener noreferrer"
                      className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors flex items-center gap-1.5 ${link.color}`}>
                      <ExternalLink className="h-3 w-3" />
                      {link.label}
                    </a>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Not Found */}
          {lookupResults && !lookupResults.found && (
            <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-6 text-center`}>
              <AlertCircle className={`h-12 w-12 mx-auto mb-4 ${t.text.secondary} opacity-50`} />
              <h3 className={`text-lg font-semibold ${t.text.primary} mb-2`}>Variant Not Found</h3>
              <p className={t.text.secondary}>
                No information found for <span className="font-mono">{lookupResults.variant_id}</span>.
              </p>
            </div>
          )}

          {/* Initial State */}
          {!lookupResults && !lookupLoading && !lookupError && (
            <div className="text-center py-8">
              <Globe className={`h-12 w-12 mx-auto mb-4 ${t.text.secondary} opacity-50`} />
              <h3 className={`text-lg font-semibold ${t.text.primary} mb-2`}>Search External Databases</h3>
              <p className={t.text.secondary}>Query Ensembl, ClinVar, ClinPGx, SNPedia, gnomAD, ChEMBL, and local databases</p>
              <div className={`text-sm mt-4 ${t.text.secondary}`}>
                <p className="mb-2">Examples:</p>
                <div className="flex flex-wrap gap-2 justify-center">
                  {['rs53576', 'rs1695', 'rs429358', 'rs12202969'].map(ex => (
                    <button
                      key={ex}
                      onClick={() => { setLookupTerm(ex); doLookup(ex) }}
                      className={`px-2 py-1 ${t.glass} border ${t.glassBorder} rounded text-xs font-mono hover:ring-2 hover:ring-indigo-500/50 transition-all`}
                    >
                      {ex}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
