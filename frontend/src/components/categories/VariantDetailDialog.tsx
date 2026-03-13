'use client'

import React, { useState, useEffect } from 'react'
import { ExternalLink, Dna, FlaskConical, BookOpen, Activity, X, ChevronDown, ChevronUp } from 'lucide-react'
import { Badge } from '../ui/badge'
import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
} from '../ui/dialog'

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
  most_severe_consequence?: string
  allele_string?: string
  chromosome?: string
  position?: number
  transcripts?: TranscriptConsequence[]
  total_transcripts?: number
  clinical_significance?: string[]
  clinvar_ids?: string[]
  population_frequencies?: Record<string, PopulationFrequency>
  clinvar?: { found: boolean; count: number; ids: string[] }
  pharmacogenomics?: { found: boolean; data?: Record<string, unknown> }
  snpedia?: { found: boolean; title?: string; summary?: string }
  publications?: { count: number; items: Publication[] }
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
  const [showAllFreqs, setShowAllFreqs] = useState(false)
  const [showPubs, setShowPubs] = useState(false)

  useEffect(() => {
    if (!open || !rsid || !token) return
    setDetails(null)
    setLoading(true)
    setShowAllFreqs(false)
    setShowPubs(false)

    fetch(`http://localhost:8000/api/annotations/variant-details/${rsid}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => res.json())
      .then((data) => setDetails(data))
      .catch(() => setDetails({ found: false, rsid }))
      .finally(() => setLoading(false))
  }, [open, rsid, token])

  const bg = isDarkMode ? 'bg-gray-900/95' : 'bg-white'
  const border = isDarkMode ? 'border-white/10' : 'border-gray-200'
  const textPrimary = isDarkMode ? 'text-gray-100' : 'text-gray-900'
  const textSecondary = isDarkMode ? 'text-gray-400' : 'text-gray-500'
  const cardBg = isDarkMode ? 'bg-white/5' : 'bg-gray-50'

  // Sort population frequencies: globals first, then by frequency desc
  const sortedFreqs = details?.population_frequencies
    ? Object.entries(details.population_frequencies).sort(([a], [b]) => {
        const aGlobal = a.includes('global') || a.includes('Global') ? 0 : 1
        const bGlobal = b.includes('global') || b.includes('Global') ? 0 : 1
        if (aGlobal !== bGlobal) return aGlobal - bGlobal
        return (details.population_frequencies![b]?.frequency || 0) - (details.population_frequencies![a]?.frequency || 0)
      })
    : []

  const displayFreqs = showAllFreqs ? sortedFreqs : sortedFreqs.slice(0, 6)

  return (
    <Dialog open={open} onOpenChange={() => {}}>
      <DialogPortal>
        <DialogOverlay className="pointer-events-none" />
        <div
          role="dialog"
          aria-modal="true"
          className={`fixed top-1/2 left-1/2 z-50 grid w-full max-w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 gap-6 p-6 ${bg} ${border} border max-w-2xl max-h-[85vh] overflow-y-auto sm:max-w-2xl rounded-2xl`}
        >
        <DialogHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-gradient-to-br from-blue-500/20 to-purple-500/20 border border-blue-500/30">
                <Dna className="h-5 w-5 text-blue-400" />
              </div>
              <div>
                <DialogTitle className={`text-lg font-bold ${textPrimary}`}>
                  {rsid}
                  {gene && gene !== 'Unknown' && !gene.startsWith('rs') && (
                    <span className={`ml-2 text-sm font-normal ${textSecondary}`}>({gene})</span>
                  )}
                </DialogTitle>
                <DialogDescription className={textSecondary}>
                  {loading ? 'Loading annotation data…' : details?.most_severe_consequence || 'Variant annotation details'}
                </DialogDescription>
              </div>
            </div>
            <button
              onClick={() => onOpenChange(false)}
              className={`p-1.5 rounded-lg ${isDarkMode ? 'hover:bg-white/10' : 'hover:bg-gray-100'} transition-colors`}
            >
              <X className={`h-4 w-4 ${textSecondary}`} />
            </button>
          </div>
        </DialogHeader>

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

            {/* ── Clinical Significance ── */}
            {details.clinical_significance && details.clinical_significance.length > 0 && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex items-center gap-1.5`}>
                  <Activity className="h-3.5 w-3.5" /> Clinical Significance
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {details.clinical_significance.map((sig) => (
                    <Badge key={sig} variant="outline" className={`${clinSigColor(sig)} text-xs`}>
                      {sig.replace(/_/g, ' ')}
                    </Badge>
                  ))}
                </div>
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
                    {details.clinvar?.ids?.map((id) => (
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

            {/* ── Population Frequencies ── */}
            {sortedFreqs.length > 0 && (
              <div>
                <h4 className={`text-xs font-semibold ${textSecondary} uppercase tracking-wider mb-2 flex items-center gap-1.5`}>
                  <Activity className="h-3.5 w-3.5" /> Population Frequencies
                </h4>
                <div className={`${cardBg} rounded-xl p-3 border ${border} space-y-1.5`}>
                  {displayFreqs.map(([pop, data]) => {
                    const pct = Math.min(data.frequency * 100, 100)
                    const barWidth = Math.max(pct * 10, pct > 0 ? 2 : 0) // Scale up for visibility
                    return (
                      <div key={pop} className="flex items-center gap-3 text-xs">
                        <span className={`${textSecondary} w-40 shrink-0 truncate`}>{formatPopName(pop)}</span>
                        <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-500 transition-all"
                            style={{ width: `${Math.min(barWidth, 100)}%` }}
                          />
                        </div>
                        <span className={`font-mono ${textPrimary} w-16 text-right`}>{formatFrequency(data.frequency)}</span>
                      </div>
                    )
                  })}
                  {sortedFreqs.length > 6 && (
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); e.preventDefault(); setShowAllFreqs(!showAllFreqs) }}
                      className={`flex items-center gap-1 text-xs ${isDarkMode ? 'text-blue-400 hover:text-blue-300' : 'text-blue-600 hover:text-blue-500'} mt-1 transition-colors`}
                    >
                      {showAllFreqs ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                      {showAllFreqs ? 'Show less' : `Show all ${sortedFreqs.length} populations`}
                    </button>
                  )}
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
                  <p className={`text-xs ${textPrimary}`}>PharmGKB data available for this variant.</p>
                  <a
                    href={`https://www.pharmgkb.org/variant/${rsid}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs text-purple-400 hover:text-purple-300 mt-1 transition-colors"
                  >
                    View on PharmGKB <ExternalLink className="h-3 w-3" />
                  </a>
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
                    onClick={(e) => { e.stopPropagation(); e.preventDefault(); setShowPubs(true) }}
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
                      onClick={(e) => { e.stopPropagation(); e.preventDefault(); setShowPubs(false) }}
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
      </DialogPortal>
    </Dialog>
  )
}
