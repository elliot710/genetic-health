'use client'

import { useState, useEffect, useCallback } from 'react'
import { Search, Loader2, AlertCircle, CheckCircle, Info, ExternalLink, AlertTriangle, ChevronLeft, ChevronRight, Database, Globe, X, BarChart3, RefreshCw, Clock } from 'lucide-react'

interface VariantSearchProps {
  token?: string
  isDarkMode?: boolean
  theme?: any
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

export default function VariantSearch({ token, isDarkMode = false, theme }: VariantSearchProps) {
  const defaultTheme = {
    glass: isDarkMode ? 'bg-slate-800/40 backdrop-blur-xl' : 'bg-white/40 backdrop-blur-xl',
    glassBorder: isDarkMode ? 'border-slate-700/50' : 'border-gray-200/30',
    text: {
      primary: isDarkMode ? 'text-white' : 'text-slate-900',
      secondary: isDarkMode ? 'text-slate-300' : 'text-slate-600',
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
  const [lookupResults, setLookupResults] = useState<any>(null)
  const [lookupError, setLookupError] = useState('')

  useEffect(() => {
    if (!token) return
    fetch('http://localhost:8000/api/variants/categories', {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(r => r.ok ? r.json() : null)
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
      params.set('page', String(page))
      params.set('per_page', String(perPage))

      const res = await fetch(`http://localhost:8000/api/variants/search?${params}`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (!res.ok) throw new Error('Failed to search variants')
      const data: SearchResponse = await res.json()
      setSearchData(data)
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Search failed')
    } finally {
      setSearchLoading(false)
    }
  }, [token, query, chromosome, annotatedFilter, categoryFilter, page, perPage])

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
      const res = await fetch('http://localhost:8000/api/variants/lookup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token && { Authorization: `Bearer ${token}` })
        },
        body: JSON.stringify({ variant_id: term, include_literature: true, include_clinpgx: true, force_refresh: forceRefresh })
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Lookup failed')
      }
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

  const sourceBadge = (source: string) => {
    const colors: Record<string, string> = {
      ensembl: isDarkMode ? 'bg-green-500/20 text-green-300' : 'bg-green-100 text-green-700',
      clinvar: isDarkMode ? 'bg-red-500/20 text-red-300' : 'bg-red-100 text-red-700',
      clinpgx: isDarkMode ? 'bg-purple-500/20 text-purple-300' : 'bg-purple-100 text-purple-700',
      snpedia: isDarkMode ? 'bg-orange-500/20 text-orange-300' : 'bg-orange-100 text-orange-700',
      litvar: isDarkMode ? 'bg-blue-500/20 text-blue-300' : 'bg-blue-100 text-blue-700',
    }
    return (
      <span key={source} className={`px-2 py-0.5 rounded text-xs font-medium ${colors[source] || (isDarkMode ? 'bg-slate-500/20 text-slate-300' : 'bg-gray-100 text-gray-600')}`}>
        {source}
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
            <button type="submit" className="px-5 py-2.5 bg-gradient-to-r from-indigo-500/80 to-purple-600/80 text-white rounded-xl hover:from-purple-600/80 hover:to-indigo-500/80 transition-all text-sm font-medium border border-white/20 shadow-lg">
              Search
            </button>
            {(query || chromosome || annotatedFilter || categoryFilter) && (
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
                        <button
                          onClick={() => doLookup(v.rsid)}
                          className={`px-2 py-1 rounded-lg text-xs font-medium transition-all ${isDarkMode ? 'bg-indigo-500/20 text-indigo-300 hover:bg-indigo-500/30' : 'bg-indigo-100 text-indigo-700 hover:bg-indigo-200'}`}
                          title="Full external lookup"
                        >
                          <Globe className="h-3 w-3 inline mr-1" />
                          Lookup
                        </button>
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
                  <CheckCircle className="h-6 w-6 text-green-500 flex-shrink-0" />
                </div>

                {/* Source badges */}
                <div className="flex flex-wrap gap-2 mt-3">
                  {lookupResults.annotations?.ensembl?.found && sourceBadge('ensembl')}
                  {lookupResults.annotations?.clinvar?.found && sourceBadge('clinvar')}
                  {lookupResults.annotations?.snpedia?.found && sourceBadge('snpedia')}
                  {lookupResults.annotations?.clinpgx?.found && sourceBadge('clinpgx')}
                </div>
              </div>

              {/* Clinical Significance */}
              {lookupResults.clinical_significance?.length > 0 && (
                <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                  <h4 className={`font-bold ${t.text.primary} mb-3 flex items-center gap-2`}>
                    <AlertTriangle className="h-4 w-4 text-amber-500" />
                    Clinical Significance
                    {lookupResults.basic_info?.clinvar_count > 0 && (
                      <span className={`text-xs font-normal ${t.text.muted}`}>({lookupResults.basic_info.clinvar_count} ClinVar entries)</span>
                    )}
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {lookupResults.clinical_significance.map((sig: string, i: number) => {
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
                      const pops = lookupResults.population_data.populations as Record<string, { allele: string; frequency: number }>
                      const sorted = Object.entries(pops)
                        .sort(([, a], [, b]) => b.frequency - a.frequency)
                        .slice(0, 12)
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
                  {Object.keys(lookupResults.population_data.populations).length > 12 && (
                    <p className={`text-xs ${t.text.muted} mt-3`}>
                      Showing top 12 of {Object.keys(lookupResults.population_data.populations).length} populations
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
              {lookupResults.pharmacogenomics?.found && (
                <div className={`${t.glass} border ${t.glassBorder} rounded-xl p-5`}>
                  <h4 className={`font-bold ${t.text.primary} mb-3 flex items-center gap-2`}>
                    <Info className="h-4 w-4 text-purple-500" />
                    Pharmacogenomic Data
                  </h4>
                  <pre className={`text-xs ${t.text.secondary} whitespace-pre-wrap font-mono p-3 rounded-lg ${isDarkMode ? 'bg-slate-700/30' : 'bg-gray-100/60'}`}>
                    {JSON.stringify(lookupResults.pharmacogenomics.data, null, 2)}
                  </pre>
                </div>
              )}

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
              <p className={t.text.secondary}>Query Ensembl, ClinVar, ClinPGx, SNPedia, and PubMed</p>
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
