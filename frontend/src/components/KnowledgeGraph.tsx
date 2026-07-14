'use client'

/**
 * Genomic Insights Explorer — replaces the unreadable force-directed graph
 * with multiple focused, interactive charts that surface actionable patterns
 * from gene → variant → condition → drug relationships.
 */

import React, { useState, useEffect, useMemo } from 'react'
import {
  Network, Dna, Pill, Activity, GitBranch, ChevronRight, Search, ArrowRight,
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts'
import type { Payload } from 'recharts/types/component/DefaultTooltipContent'
import { Badge } from './ui/badge'
import { useThemeClasses, CategoryHeader, EmptyState, SectionCard } from './categories/shared'
import { apiFetch, ApiError } from '@/lib/api'
import VariantDetailDialog from './categories/VariantDetailDialog'

// ── Types ──────────────────────────────────────────────────────────
interface GraphNode {
  id: string
  label: string
  type: string
  color: string
  size: number
  [key: string]: unknown
}

interface GraphEdge {
  source: string
  target: string
  relation: string
}

interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  stats: { total_nodes: number; total_edges: number; by_type: Record<string, number> }
}

interface KnowledgeGraphProps {
  isDarkMode: boolean
  token?: string
}

// ── Constants ──────────────────────────────────────────────────────
const TYPE_META: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  gene:      { label: 'Genes',      icon: <Dna className="h-5 w-5" />,        color: '#8b5cf6' },
  variant:   { label: 'Variants',   icon: <GitBranch className="h-5 w-5" />,  color: '#06b6d4' },
  condition: { label: 'Conditions', icon: <Activity className="h-5 w-5" />,   color: '#ef4444' },
  drug:      { label: 'Drugs',      icon: <Pill className="h-5 w-5" />,       color: '#f59e0b' },
  pathway:   { label: 'Pathways',   icon: <Network className="h-5 w-5" />,    color: '#22c55e' },
}

const RELATION_LABELS: Record<string, string> = {
  contains: 'Contains variant',
  metabolizes: 'Metabolizes drug',
  contributes_to: 'Contributes to condition',
  affects_response: 'Affects drug response',
  linked_to: 'Linked to condition',
  associated_with: 'Associated with condition',
  carrier_for: 'Carrier for condition',
  participates_in: 'Participates in pathway',
}

const RELATION_COLORS: Record<string, string> = {
  contains: '#64748b',
  metabolizes: '#f59e0b',
  contributes_to: '#ef4444',
  affects_response: '#f97316',
  linked_to: '#8b5cf6',
  associated_with: '#ec4899',
  carrier_for: '#f43f5e',
  participates_in: '#22c55e',
}

const PALETTE = ['#8b5cf6', '#06b6d4', '#ef4444', '#f59e0b', '#22c55e', '#ec4899', '#3b82f6', '#14b8a6', '#f97316', '#a855f7']

const GlassTooltip = ({ active, payload, label, isDarkMode }: { active?: boolean; payload?: ReadonlyArray<Payload>; label?: React.ReactNode; isDarkMode?: boolean }) => {
  if (!active || !payload?.length) return null
  return (
    <div className={`px-3 py-2 rounded-lg border text-xs shadow-xl backdrop-blur-xl ${
      isDarkMode ? 'bg-slate-800/90 border-slate-600/60 text-gray-200' : 'bg-white/90 border-gray-200 text-gray-800'
    }`}>
      {label && <p className="font-semibold mb-1">{String(label)}</p>}
      {payload.map((p, i: number) => (
        <p key={i} style={{ color: p.color || p.fill }}>
          {p.name}: <span className="font-bold">{typeof p.value === 'number' ? p.value.toLocaleString() : String(p.value)}</span>
        </p>
      ))}
    </div>
  )
}

const axisStyle = (dark: boolean) => ({ fill: dark ? '#94a3b8' : '#64748b', fontSize: 11 })
const gridStroke = (dark: boolean) => dark ? 'rgba(148,163,184,0.12)' : 'rgba(100,116,139,0.15)'

function cleanLabel(s: string): string {
  return s.split('|')[0].split(';')[0].trim()
}

// ── Component ──────────────────────────────────────────────────────
export default function KnowledgeGraph({ isDarkMode, token }: KnowledgeGraphProps) {
  const theme = useThemeClasses(isDarkMode)
  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedGene, setSelectedGene] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [dialogRsid, setDialogRsid] = useState('')
  const [dialogGene, setDialogGene] = useState<string | undefined>(undefined)
  const [dialogOpen, setDialogOpen] = useState(false)

  const openVariantDialog = (rsid: string, gene?: string) => {
    setDialogRsid(rsid)
    setDialogGene(gene)
    setDialogOpen(true)
  }

  useEffect(() => {
    if (!token) { setLoading(false); return }
    ;(async () => {
      try {
        const resp = await apiFetch('/api/insights/knowledge-graph')
        setGraphData(await resp.json())
      } catch (err) {
        setError(err instanceof ApiError ? 'Failed to load data' : 'Network error')
      } finally {
        setLoading(false)
      }
    })()
  }, [token])

  // ── Derived data ─────────────────────────────────────────────────
  const nodeMap = useMemo(() => {
    const m: Record<string, GraphNode> = {}
    graphData?.nodes.forEach(n => { m[n.id] = n })
    return m
  }, [graphData])

  const geneConnections = useMemo(() => {
    if (!graphData) return []
    const map: Record<string, { gene: string; variants: Set<string>; conditions: Set<string>; drugs: Set<string>; pathways: Set<string>; edges: number }> = {}

    for (const e of graphData.edges) {
      const geneId = e.source.startsWith('gene:') ? e.source : e.target.startsWith('gene:') ? e.target : null
      if (!geneId) continue
      const otherId = geneId === e.source ? e.target : e.source
      if (!map[geneId]) map[geneId] = { gene: nodeMap[geneId]?.label || geneId.replace('gene:', ''), variants: new Set(), conditions: new Set(), drugs: new Set(), pathways: new Set(), edges: 0 }
      map[geneId].edges++
      const other = nodeMap[otherId]
      if (!other) continue
      if (other.type === 'variant') map[geneId].variants.add(otherId)
      else if (other.type === 'condition') map[geneId].conditions.add(otherId)
      else if (other.type === 'drug') map[geneId].drugs.add(otherId)
      else if (other.type === 'pathway') map[geneId].pathways.add(otherId)
    }

    return Object.entries(map)
      .sort(([, a], [, b]) => b.edges - a.edges)
      .map(([id, d]) => ({
        id,
        gene: d.gene,
        variants: d.variants.size,
        conditions: d.conditions.size,
        drugs: d.drugs.size,
        pathways: d.pathways.size,
        edges: d.edges,
        variantIds: [...d.variants],
        conditionIds: [...d.conditions],
        drugIds: [...d.drugs],
        pathwayIds: [...d.pathways],
      }))
  }, [graphData, nodeMap])

  const relationData = useMemo(() => {
    if (!graphData) return []
    const counts: Record<string, number> = {}
    for (const e of graphData.edges) counts[e.relation] = (counts[e.relation] || 0) + 1
    return Object.entries(counts)
      .sort(([, a], [, b]) => b - a)
      .map(([rel, count]) => ({
        name: RELATION_LABELS[rel] || rel.replace(/_/g, ' '),
        value: count,
        fill: RELATION_COLORS[rel] || '#64748b',
      }))
  }, [graphData])

  const drugGeneLinks = useMemo(() => {
    if (!graphData) return []
    const links: { drug: string; gene: string; relation: string; drugId: string; geneId: string }[] = []
    for (const e of graphData.edges) {
      const drugNode = nodeMap[e.source]?.type === 'drug' ? nodeMap[e.source] : nodeMap[e.target]?.type === 'drug' ? nodeMap[e.target] : null
      const geneNode = nodeMap[e.source]?.type === 'gene' ? nodeMap[e.source] : nodeMap[e.target]?.type === 'gene' ? nodeMap[e.target] : null
      if (drugNode && geneNode) {
        links.push({ drug: drugNode.label, gene: geneNode.label, relation: e.relation, drugId: drugNode.id, geneId: geneNode.id })
      }
    }
    return links.sort((a, b) => a.drug.localeCompare(b.drug))
  }, [graphData, nodeMap])

  const variantConditionLinks = useMemo(() => {
    if (!graphData) return []
    const links: { variant: string; condition: string; relation: string }[] = []
    for (const e of graphData.edges) {
      const varNode = nodeMap[e.source]?.type === 'variant' ? nodeMap[e.source] : nodeMap[e.target]?.type === 'variant' ? nodeMap[e.target] : null
      const condNode = nodeMap[e.source]?.type === 'condition' ? nodeMap[e.source] : nodeMap[e.target]?.type === 'condition' ? nodeMap[e.target] : null
      if (varNode && condNode) {
        links.push({ variant: varNode.label, condition: cleanLabel(condNode.label), relation: e.relation })
      }
    }
    return links
  }, [graphData, nodeMap])

  const conditionTreemap = useMemo(() => {
    if (!graphData) return []
    const condEdgeCount: Record<string, number> = {}
    for (const e of graphData.edges) {
      for (const nid of [e.source, e.target]) {
        if (nid.startsWith('cond:')) condEdgeCount[nid] = (condEdgeCount[nid] || 0) + 1
      }
    }
    return Object.entries(condEdgeCount)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 30)
      .map(([id, count], i) => ({
        name: cleanLabel(nodeMap[id]?.label || id.replace('cond:', '')),
        size: count,
        fill: PALETTE[i % PALETTE.length],
      }))
  }, [graphData, nodeMap])

  const selectedGeneData = useMemo(() => {
    if (!selectedGene) return null
    return geneConnections.find(g => g.id === selectedGene) || null
  }, [selectedGene, geneConnections])

  const filteredGenes = useMemo(() => {
    if (!searchQuery.trim()) return geneConnections.slice(0, 25)
    const q = searchQuery.toLowerCase()
    return geneConnections.filter(g => g.gene.toLowerCase().includes(q))
  }, [geneConnections, searchQuery])

  // ── Render ───────────────────────────────────────────────────────
  const headerProps = {
    icon: Network,
    iconColorClass: 'text-indigo-400',
    gradientFrom: 'from-indigo-500/20',
    gradientTo: 'to-purple-500/20',
    borderColor: 'border-indigo-500/30',
    title: 'Genomic Insights',
    description: 'Gene\u2013variant\u2013condition\u2013drug relationship explorer',
    count: graphData?.stats?.total_nodes || 0,
    countLabel: 'Entities',
    theme,
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <CategoryHeader {...headerProps} />
        <div className={`${theme.glass} border ${theme.border} rounded-2xl p-12 text-center`}>
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-500 mx-auto mb-4" />
          <p className={`text-sm ${theme.textSecondary}`}>Analyzing genomic relationships...</p>
        </div>
      </div>
    )
  }

  if (error || !graphData?.nodes.length) {
    return (
      <div className="space-y-6">
        <CategoryHeader {...headerProps} />
        <EmptyState
          icon={Network}
          iconColorClass="text-indigo-400"
          gradientFrom="from-indigo-500/20"
          gradientTo="to-purple-500/20"
          borderColor="border-indigo-500/30"
          title="No Data Available"
          description={error || 'Run an analysis first to explore genomic relationships.'}
          theme={theme}
        />
      </div>
    )
  }

  const stats = graphData.stats

  return (
    <div className="space-y-6">
      <CategoryHeader {...headerProps} />

      {/* 1. Summary Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {Object.entries(TYPE_META).map(([type, meta]) => {
          const count = stats.by_type[type] || 0
          if (count === 0) return null
          return (
            <div key={type} className={`${theme.glass} border ${theme.border} rounded-xl p-4 flex items-center gap-3`}>
              <div className="p-2.5 rounded-lg" style={{ backgroundColor: meta.color + '15' }}>
                <span style={{ color: meta.color }}>{meta.icon}</span>
              </div>
              <div>
                <div className={`text-2xl font-bold ${theme.textPrimary}`}>{count}</div>
                <div className={`text-xs ${theme.textSecondary}`}>{meta.label}</div>
              </div>
            </div>
          )
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 2. Top Connected Genes bar chart */}
        <SectionCard title="Most Connected Genes" theme={theme}>
          <ResponsiveContainer width="100%" height={Math.max(280, geneConnections.slice(0, 15).length * 32)}>
            <BarChart
              data={geneConnections.slice(0, 15).map(g => ({ name: g.gene, connections: g.edges }))}
              layout="vertical"
              margin={{ left: 8, right: 16, top: 8, bottom: 8 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke={gridStroke(isDarkMode)} horizontal={false} />
              <XAxis type="number" tick={axisStyle(isDarkMode)} allowDecimals={false} />
              <YAxis type="category" dataKey="name" tick={axisStyle(isDarkMode)} width={65} />
              <Tooltip content={<GlassTooltip isDarkMode={isDarkMode} />} />
              <Bar dataKey="connections" name="Connections" radius={[0, 6, 6, 0]} barSize={22} fill="#8b5cf6" />
            </BarChart>
          </ResponsiveContainer>
        </SectionCard>

        {/* 3. Relationship Types donut chart */}
        <SectionCard title="Relationship Types" theme={theme}>
          {relationData.length > 0 && (
            <div className="flex flex-col items-center">
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie
                    data={relationData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={110}
                    paddingAngle={2}
                    dataKey="value"
                    nameKey="name"
                  >
                    {relationData.map((d, i) => <Cell key={i} fill={d.fill} strokeWidth={0} />)}
                  </Pie>
                  <Tooltip content={<GlassTooltip isDarkMode={isDarkMode} />} />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex flex-wrap justify-center gap-x-4 gap-y-1.5 mt-2">
                {relationData.map((d, i) => (
                  <div key={i} className="flex items-center gap-1.5">
                    <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: d.fill }} />
                    <span className={`text-xs ${theme.textSecondary}`}>{d.name} ({d.value})</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </SectionCard>
      </div>

      {/* 4. Gene Explorer */}
      <SectionCard title="Gene Explorer" theme={theme}>
        <div className="flex flex-col lg:flex-row gap-4">
          {/* Gene list */}
          <div className="lg:w-1/3 flex flex-col gap-3">
            <div className="relative">
              <Search className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
              <input
                type="text"
                placeholder="Search genes…"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 text-sm`}
              />
            </div>
            <div className="max-h-[400px] overflow-y-auto space-y-1 pr-1">
              {filteredGenes.map(g => (
                <button
                  key={g.id}
                  onClick={() => setSelectedGene(g.id === selectedGene ? null : g.id)}
                  className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-left transition-all ${
                    selectedGene === g.id
                      ? `${isDarkMode ? 'bg-indigo-500/20 border-indigo-500/40' : 'bg-indigo-50 border-indigo-200'} border`
                      : `${theme.glass} border ${theme.border} hover:border-indigo-500/30`
                  }`}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <Dna className="h-3.5 w-3.5 text-violet-400 shrink-0" />
                    <span className={`text-sm font-medium truncate ${theme.textPrimary}`}>{g.gene}</span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {g.drugs > 0 && <Badge variant="outline" className="text-[10px] bg-amber-500/10 text-amber-400 border-amber-500/20">{g.drugs} \uD83D\uDC8A</Badge>}
                    {g.conditions > 0 && <Badge variant="outline" className="text-[10px] bg-red-500/10 text-red-400 border-red-500/20">{g.conditions}</Badge>}
                    <span className={`text-xs ${theme.textSecondary}`}>{g.edges}</span>
                    <ChevronRight className={`h-3.5 w-3.5 ${theme.textSecondary} transition-transform ${selectedGene === g.id ? 'rotate-90' : ''}`} />
                  </div>
                </button>
              ))}
              {filteredGenes.length === 0 && (
                <p className={`text-sm text-center py-4 ${theme.textSecondary}`}>No genes found</p>
              )}
            </div>
          </div>

          {/* Gene detail panel */}
          <div className="lg:w-2/3">
            {selectedGeneData ? (
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 rounded-lg bg-violet-500/15">
                    <Dna className="h-5 w-5 text-violet-400" />
                  </div>
                  <div>
                    <h3 className={`text-lg font-bold ${theme.textPrimary}`}>{selectedGeneData.gene}</h3>
                    <p className={`text-xs ${theme.textSecondary}`}>{selectedGeneData.edges} connections across {selectedGeneData.variants + selectedGeneData.conditions + selectedGeneData.drugs + selectedGeneData.pathways} entities</p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  {selectedGeneData.variants > 0 && (
                    <div className={`${theme.glass} border ${theme.border} rounded-lg px-3 py-2 flex items-center gap-2`}>
                      <GitBranch className="h-4 w-4 text-cyan-400" />
                      <span className={`text-sm font-semibold ${theme.textPrimary}`}>{selectedGeneData.variants}</span>
                      <span className={`text-xs ${theme.textSecondary}`}>Variants</span>
                    </div>
                  )}
                  {selectedGeneData.conditions > 0 && (
                    <div className={`${theme.glass} border ${theme.border} rounded-lg px-3 py-2 flex items-center gap-2`}>
                      <Activity className="h-4 w-4 text-red-400" />
                      <span className={`text-sm font-semibold ${theme.textPrimary}`}>{selectedGeneData.conditions}</span>
                      <span className={`text-xs ${theme.textSecondary}`}>Conditions</span>
                    </div>
                  )}
                  {selectedGeneData.drugs > 0 && (
                    <div className={`${theme.glass} border ${theme.border} rounded-lg px-3 py-2 flex items-center gap-2`}>
                      <Pill className="h-4 w-4 text-amber-400" />
                      <span className={`text-sm font-semibold ${theme.textPrimary}`}>{selectedGeneData.drugs}</span>
                      <span className={`text-xs ${theme.textSecondary}`}>Drugs</span>
                    </div>
                  )}
                  {selectedGeneData.pathways > 0 && (
                    <div className={`${theme.glass} border ${theme.border} rounded-lg px-3 py-2 flex items-center gap-2`}>
                      <Network className="h-4 w-4 text-green-400" />
                      <span className={`text-sm font-semibold ${theme.textPrimary}`}>{selectedGeneData.pathways}</span>
                      <span className={`text-xs ${theme.textSecondary}`}>Pathways</span>
                    </div>
                  )}
                </div>

                <div className="space-y-3">
                  {selectedGeneData.variantIds.length > 0 && (
                    <div>
                      <h4 className={`text-xs font-semibold uppercase tracking-wider mb-2 ${theme.textSecondary}`}>Variants</h4>
                      <div className="flex flex-wrap gap-1.5">
                        {selectedGeneData.variantIds.map(vid => {
                          const label = nodeMap[vid]?.label || vid.replace('var:', '')
                          return (
                            <button key={vid} onClick={() => openVariantDialog(label, selectedGeneData.gene)}>
                              <Badge variant="outline" className="text-xs bg-cyan-500/10 text-cyan-400 border-cyan-500/20 font-mono cursor-pointer hover:bg-cyan-500/20 transition-colors">
                                {label}
                              </Badge>
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  {selectedGeneData.conditionIds.length > 0 && (
                    <div>
                      <h4 className={`text-xs font-semibold uppercase tracking-wider mb-2 ${theme.textSecondary}`}>Associated Conditions</h4>
                      <div className="space-y-1.5">
                        {selectedGeneData.conditionIds.map(cid => {
                          const node = nodeMap[cid]
                          return (
                            <div key={cid} className={`flex items-center gap-2 px-3 py-2 rounded-lg ${theme.glass} border ${theme.border}`}>
                              <div className="w-2 h-2 rounded-full bg-red-400 shrink-0" />
                              <span className={`text-sm ${theme.textPrimary}`}>{cleanLabel(node?.label || cid.replace('cond:', ''))}</span>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  {selectedGeneData.drugIds.length > 0 && (
                    <div>
                      <h4 className={`text-xs font-semibold uppercase tracking-wider mb-2 ${theme.textSecondary}`}>Drug Interactions</h4>
                      <div className="space-y-1.5">
                        {selectedGeneData.drugIds.map(did => {
                          const drug = nodeMap[did]
                          const rel = graphData.edges.find(e =>
                            (e.source === selectedGene && e.target === did) || (e.target === selectedGene && e.source === did)
                          )
                          return (
                            <div key={did} className={`flex items-center gap-2 px-3 py-2 rounded-lg ${theme.glass} border ${theme.border}`}>
                              <Pill className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                              <span className={`text-sm font-medium ${theme.textPrimary}`}>{drug?.label || did.replace('drug:', '')}</span>
                              {rel && <span className={`text-xs ${theme.textSecondary} ml-auto`}>{rel.relation.replace(/_/g, ' ')}</span>}
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )}

                  {selectedGeneData.pathwayIds.length > 0 && (
                    <div>
                      <h4 className={`text-xs font-semibold uppercase tracking-wider mb-2 ${theme.textSecondary}`}>Pathways</h4>
                      <div className="flex flex-wrap gap-1.5">
                        {selectedGeneData.pathwayIds.map(pid => (
                          <Badge key={pid} variant="outline" className="text-xs bg-green-500/10 text-green-400 border-green-500/20">
                            {nodeMap[pid]?.label || pid.replace('pathway:', '')}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className={`flex flex-col items-center justify-center py-16 ${theme.textSecondary}`}>
                <Dna className="h-10 w-10 mb-3 opacity-30" />
                <p className="text-sm">Select a gene to explore its connections</p>
              </div>
            )}
          </div>
        </div>
      </SectionCard>

      {/* 5. Drug-Gene Pharmacogenomic Map */}
      {drugGeneLinks.length > 0 && (
        <SectionCard title={`Pharmacogenomic Connections (${drugGeneLinks.length})`} theme={theme}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className={`border-b ${theme.border}`}>
                  <th className={`text-left py-2 px-3 text-xs font-semibold uppercase tracking-wider ${theme.textSecondary}`}>Drug</th>
                  <th className={`text-center py-2 px-3 text-xs ${theme.textSecondary}`} />
                  <th className={`text-left py-2 px-3 text-xs font-semibold uppercase tracking-wider ${theme.textSecondary}`}>Gene</th>
                  <th className={`text-left py-2 px-3 text-xs font-semibold uppercase tracking-wider ${theme.textSecondary}`}>Relationship</th>
                </tr>
              </thead>
              <tbody>
                {drugGeneLinks.map((link, i) => (
                  <tr key={i} className={`border-b ${theme.border} last:border-0 transition-colors`}>
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-2">
                        <Pill className="h-3.5 w-3.5 text-amber-400 shrink-0" />
                        <span className={`font-medium ${theme.textPrimary}`}>{link.drug}</span>
                      </div>
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      <ArrowRight className={`h-3.5 w-3.5 ${theme.textSecondary} mx-auto`} />
                    </td>
                    <td className="py-2.5 px-3">
                      <button
                        onClick={() => setSelectedGene(link.geneId)}
                        className="flex items-center gap-2 hover:text-violet-400 transition-colors"
                      >
                        <Dna className="h-3.5 w-3.5 text-violet-400 shrink-0" />
                        <span className={`font-medium ${theme.textPrimary}`}>{link.gene}</span>
                      </button>
                    </td>
                    <td className="py-2.5 px-3">
                      <Badge variant="outline" className="text-[10px]" style={{ borderColor: RELATION_COLORS[link.relation] + '40', color: RELATION_COLORS[link.relation] }}>
                        {link.relation.replace(/_/g, ' ')}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      {/* 6. Condition Landscape */}
      {conditionTreemap.length > 0 && (
        <SectionCard title="Condition Landscape" theme={theme}>
          <p className={`text-xs ${theme.textSecondary} mb-3`}>
            Top conditions sized by number of genetic connections.
          </p>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2.5">
            {conditionTreemap.map((item, i) => (
              <div
                key={i}
                className="relative rounded-xl p-3 min-h-[72px] flex flex-col justify-end overflow-hidden"
                style={{ backgroundColor: item.fill, opacity: 0.85 }}
              >
                <div className="absolute top-2.5 right-2.5 text-white/60 text-xs font-bold">{item.size}</div>
                <span className="text-white text-sm font-semibold leading-tight drop-shadow-md">
                  {item.name}
                </span>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      {/* 7. Variant-Condition Associations */}
      {variantConditionLinks.length > 0 && (
        <SectionCard title={`Variant\u2013Condition Associations (${variantConditionLinks.length})`} theme={theme}>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2 max-h-[400px] overflow-y-auto pr-1">
            {variantConditionLinks.map((link, i) => (
              <div key={i} className={`flex items-center gap-2 px-3 py-2 rounded-lg ${theme.glass} border ${theme.border}`}>
                <button onClick={() => openVariantDialog(link.variant)} className="shrink-0">
                  <Badge variant="outline" className="text-[10px] font-mono bg-cyan-500/10 text-cyan-400 border-cyan-500/20 cursor-pointer hover:bg-cyan-500/20 transition-colors">
                    {link.variant}
                  </Badge>
                </button>
                <ArrowRight className={`h-3 w-3 ${theme.textSecondary} shrink-0`} />
                <span className={`text-xs ${theme.textPrimary} truncate`}>{link.condition}</span>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      <VariantDetailDialog
        rsid={dialogRsid}
        gene={dialogGene}
        token={token}
        isDarkMode={isDarkMode}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
    </div>
  )
}
