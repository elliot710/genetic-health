'use client'

/**
 * Interactive Knowledge Graph — force-directed SVG visualization
 * of gene → variant → condition → drug relationships.
 */

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { Network, ZoomIn, ZoomOut, Maximize2, Filter, X } from 'lucide-react'
import { useThemeClasses, CategoryHeader, EmptyState, SectionCard } from './categories/shared'

// ── Types ──────────────────────────────────────────────────────────
interface GraphNode {
  id: string
  label: string
  type: string
  color: string
  size: number
  // Force simulation state
  x: number
  y: number
  vx: number
  vy: number
  fx?: number | null
  fy?: number | null
  [key: string]: unknown
}

interface GraphEdge {
  source: string
  target: string
  relation: string
}

interface GraphData {
  nodes: Omit<GraphNode, 'x' | 'y' | 'vx' | 'vy'>[]
  edges: GraphEdge[]
  stats: { total_nodes: number; total_edges: number; by_type: Record<string, number> }
}

interface KnowledgeGraphProps {
  isDarkMode: boolean
  token?: string
}

// ── Constants ──────────────────────────────────────────────────────
const NODE_TYPE_META: Record<string, { label: string; icon: string }> = {
  gene: { label: 'Gene', icon: '🧬' },
  variant: { label: 'Variant', icon: '🔬' },
  condition: { label: 'Condition', icon: '🏥' },
  drug: { label: 'Drug', icon: '💊' },
  pathway: { label: 'Pathway', icon: '🔄' },
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

// ── Simple force simulation ────────────────────────────────────────
function initPositions(nodes: GraphNode[], width: number, height: number) {
  const cx = width / 2, cy = height / 2
  nodes.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / nodes.length
    const r = Math.min(width, height) * 0.35
    n.x = cx + r * Math.cos(angle) + (Math.random() - 0.5) * 40
    n.y = cy + r * Math.sin(angle) + (Math.random() - 0.5) * 40
    n.vx = 0
    n.vy = 0
  })
}

function simulateForces(
  nodes: GraphNode[],
  edges: GraphEdge[],
  width: number,
  height: number,
  alpha: number = 0.1,
) {
  const nodeMap: Record<string, GraphNode> = {}
  nodes.forEach(n => { nodeMap[n.id] = n })

  // Repulsion between all node pairs
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j]
      const dx = b.x - a.x, dy = b.y - a.y
      const dist = Math.sqrt(dx * dx + dy * dy) || 1
      const force = 800 / (dist * dist)
      const fx = (dx / dist) * force, fy = (dy / dist) * force
      a.vx -= fx; a.vy -= fy
      b.vx += fx; b.vy += fy
    }
  }

  // Attraction along edges
  edges.forEach(e => {
    const a = nodeMap[e.source], b = nodeMap[e.target]
    if (!a || !b) return
    const dx = b.x - a.x, dy = b.y - a.y
    const dist = Math.sqrt(dx * dx + dy * dy) || 1
    const ideal = 120
    const force = (dist - ideal) * 0.005
    const fx = (dx / dist) * force, fy = (dy / dist) * force
    a.vx += fx; a.vy += fy
    b.vx -= fx; b.vy -= fy
  })

  // Center gravity
  const cx = width / 2, cy = height / 2
  nodes.forEach(n => {
    n.vx += (cx - n.x) * 0.002
    n.vy += (cy - n.y) * 0.002
  })

  // Apply with damping
  nodes.forEach(n => {
    if (n.fx != null) { n.x = n.fx; n.vx = 0 }
    else { n.vx *= 0.6; n.x += n.vx * alpha }
    if (n.fy != null) { n.y = n.fy; n.vy = 0 }
    else { n.vy *= 0.6; n.y += n.vy * alpha }
    // Keep in bounds
    n.x = Math.max(30, Math.min(width - 30, n.x))
    n.y = Math.max(30, Math.min(height - 30, n.y))
  })
}

// ── Component ──────────────────────────────────────────────────────
export default function KnowledgeGraph({ isDarkMode, token }: KnowledgeGraphProps) {
  const theme = useThemeClasses(isDarkMode)
  const svgRef = useRef<SVGSVGElement>(null)
  const animRef = useRef<number>(0)

  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [nodes, setNodes] = useState<GraphNode[]>([])
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [dragNode, setDragNode] = useState<GraphNode | null>(null)
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set())
  const [showFilters, setShowFilters] = useState(false)

  const W = 900, H = 600

  // Fetch graph data
  useEffect(() => {
    if (!token) { setLoading(false); return }
    (async () => {
      try {
        const resp = await fetch('http://localhost:8000/api/insights/knowledge-graph', {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (resp.ok) {
          const data: GraphData = await resp.json()
          setGraphData(data)
        } else {
          setError('Failed to load graph')
        }
      } catch {
        setError('Network error')
      } finally {
        setLoading(false)
      }
    })()
  }, [token])

  // Initialize nodes when data arrives
  useEffect(() => {
    if (!graphData?.nodes.length) return
    const gNodes: GraphNode[] = graphData.nodes.map(n => ({
      ...n, x: 0, y: 0, vx: 0, vy: 0,
    } as GraphNode))
    initPositions(gNodes, W, H)
    setNodes(gNodes)
  }, [graphData])

  // Run force simulation
  useEffect(() => {
    if (!nodes.length || !graphData) return
    let frame = 0
    const maxFrames = 200

    const tick = () => {
      if (frame >= maxFrames) return
      simulateForces(nodes, graphData.edges, W, H, Math.max(0.01, 0.3 - frame * 0.0015))
      setNodes([...nodes])
      frame++
      animRef.current = requestAnimationFrame(tick)
    }
    animRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(animRef.current)
  }, [nodes.length]) // eslint-disable-line react-hooks/exhaustive-deps

  // Filtered data
  const filteredNodes = useMemo(() => {
    if (activeFilters.size === 0) return nodes
    return nodes.filter(n => activeFilters.has(n.type))
  }, [nodes, activeFilters])

  const filteredNodeIds = useMemo(() => new Set(filteredNodes.map(n => n.id)), [filteredNodes])

  const filteredEdges = useMemo(() => {
    if (!graphData) return []
    return graphData.edges.filter(e => filteredNodeIds.has(e.source) && filteredNodeIds.has(e.target))
  }, [graphData, filteredNodeIds])

  // Node map for edge rendering
  const nodeMap = useMemo(() => {
    const map: Record<string, GraphNode> = {}
    nodes.forEach(n => { map[n.id] = n })
    return map
  }, [nodes])

  // Mouse handlers
  const handleNodeMouseDown = useCallback((e: React.MouseEvent, node: GraphNode) => {
    e.stopPropagation()
    setDragNode(node)
    node.fx = node.x
    node.fy = node.y
  }, [])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragNode || !svgRef.current) return
    const rect = svgRef.current.getBoundingClientRect()
    const x = (e.clientX - rect.left - pan.x) / zoom
    const y = (e.clientY - rect.top - pan.y) / zoom
    dragNode.fx = x
    dragNode.fy = y
    dragNode.x = x
    dragNode.y = y
    setNodes([...nodes])
  }, [dragNode, zoom, pan, nodes])

  const handleMouseUp = useCallback(() => {
    if (dragNode) {
      dragNode.fx = null
      dragNode.fy = null
      setDragNode(null)
    }
  }, [dragNode])

  const toggleFilter = useCallback((type: string) => {
    setActiveFilters(prev => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }, [])

  // Header
  const headerProps = {
    icon: Network,
    iconColorClass: 'text-indigo-400',
    gradientFrom: 'from-indigo-500/20',
    gradientTo: 'to-purple-500/20',
    borderColor: 'border-indigo-500/30',
    title: 'Knowledge Graph',
    description: 'Interactive gene–variant–condition–drug relationship map',
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
          <p className={`text-sm ${theme.textSecondary}`}>Building knowledge graph...</p>
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
          title="No Graph Data"
          description={error || "Run an analysis first to build the knowledge graph."}
          theme={theme}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <CategoryHeader {...headerProps} />

      {/* Controls bar */}
      <div className={`${theme.glass} border ${theme.border} rounded-xl p-3 flex items-center justify-between flex-wrap gap-3`}>
        <div className="flex items-center gap-2">
          <button onClick={() => setZoom(z => Math.min(3, z + 0.2))} className={`p-2 rounded-lg ${theme.glass} border ${theme.border} hover:opacity-80 transition`}>
            <ZoomIn className={`h-4 w-4 ${theme.textSecondary}`} />
          </button>
          <button onClick={() => setZoom(z => Math.max(0.3, z - 0.2))} className={`p-2 rounded-lg ${theme.glass} border ${theme.border} hover:opacity-80 transition`}>
            <ZoomOut className={`h-4 w-4 ${theme.textSecondary}`} />
          </button>
          <button onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }) }} className={`p-2 rounded-lg ${theme.glass} border ${theme.border} hover:opacity-80 transition`}>
            <Maximize2 className={`h-4 w-4 ${theme.textSecondary}`} />
          </button>
          <span className={`text-xs ${theme.textSecondary} ml-2`}>{Math.round(zoom * 100)}%</span>
        </div>

        <div className="flex items-center gap-2">
          <button onClick={() => setShowFilters(!showFilters)} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium ${theme.glass} border ${theme.border} hover:opacity-80 transition`}>
            <Filter className={`h-3.5 w-3.5 ${theme.textSecondary}`} />
            <span className={theme.textSecondary}>Filter</span>
          </button>
          {/* Stats */}
          <span className={`text-xs ${theme.textSecondary}`}>
            {filteredNodes.length} nodes · {filteredEdges.length} edges
          </span>
        </div>
      </div>

      {/* Filter chips */}
      {showFilters && (
        <div className={`${theme.glass} border ${theme.border} rounded-xl p-4 flex flex-wrap gap-2`}>
          {Object.entries(NODE_TYPE_META).map(([type, meta]) => {
            const count = graphData.stats.by_type[type] || 0
            if (count === 0) return null
            const active = activeFilters.size === 0 || activeFilters.has(type)
            return (
              <button
                key={type}
                onClick={() => toggleFilter(type)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${
                  active
                    ? `${isDarkMode ? 'bg-indigo-500/20 border-indigo-500/40 text-indigo-300' : 'bg-indigo-50 border-indigo-200 text-indigo-700'}`
                    : `opacity-40 ${theme.glass} ${theme.border} ${theme.textSecondary}`
                }`}
              >
                <span>{meta.icon}</span>
                <span>{meta.label}</span>
                <span className="opacity-60">({count})</span>
              </button>
            )
          })}
          {activeFilters.size > 0 && (
            <button onClick={() => setActiveFilters(new Set())} className={`flex items-center gap-1 px-2 py-1 rounded-full text-[10px] ${isDarkMode ? 'text-red-400' : 'text-red-600'}`}>
              <X className="h-3 w-3" /> Clear
            </button>
          )}
        </div>
      )}

      {/* Graph canvas */}
      <SectionCard title="Relationship Map" theme={theme}>
        <div className={`relative rounded-xl overflow-hidden border ${theme.border} ${isDarkMode ? 'bg-slate-900/50' : 'bg-slate-50/50'}`}>
          <svg
            ref={svgRef}
            width="100%"
            height={H}
            viewBox={`0 0 ${W} ${H}`}
            className="cursor-grab active:cursor-grabbing"
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
          >
            <g transform={`translate(${pan.x},${pan.y}) scale(${zoom})`}>
              {/* Edges */}
              {filteredEdges.map((e, i) => {
                const src = nodeMap[e.source], tgt = nodeMap[e.target]
                if (!src || !tgt) return null
                const color = RELATION_COLORS[e.relation] || '#64748b'
                return (
                  <line
                    key={i}
                    x1={src.x} y1={src.y}
                    x2={tgt.x} y2={tgt.y}
                    stroke={color}
                    strokeWidth={1.2}
                    strokeOpacity={0.5}
                  />
                )
              })}

              {/* Nodes */}
              {filteredNodes.map(node => {
                const isSelected = selectedNode?.id === node.id
                return (
                  <g
                    key={node.id}
                    transform={`translate(${node.x},${node.y})`}
                    onMouseDown={(e) => handleNodeMouseDown(e, node)}
                    onClick={(e) => { e.stopPropagation(); setSelectedNode(isSelected ? null : node) }}
                    className="cursor-pointer"
                  >
                    <circle
                      r={node.size * (isSelected ? 1.3 : 1)}
                      fill={node.color}
                      fillOpacity={0.85}
                      stroke={isSelected ? '#fff' : node.color}
                      strokeWidth={isSelected ? 2.5 : 1}
                      strokeOpacity={isSelected ? 1 : 0.3}
                    />
                    <text
                      y={node.size + 12}
                      textAnchor="middle"
                      fill={isDarkMode ? '#cbd5e1' : '#334155'}
                      fontSize={9}
                      fontWeight={isSelected ? 700 : 500}
                    >
                      {node.label.length > 20 ? node.label.slice(0, 18) + '…' : node.label}
                    </text>
                  </g>
                )
              })}
            </g>
          </svg>
        </div>
      </SectionCard>

      {/* Selected node detail */}
      {selectedNode && (
        <SectionCard title="Node Details" theme={theme}>
          <div className="flex items-start gap-4">
            <div className="p-3 rounded-xl" style={{ backgroundColor: selectedNode.color + '20', borderColor: selectedNode.color + '40' }}>
              <span className="text-2xl">{NODE_TYPE_META[selectedNode.type]?.icon || '?'}</span>
            </div>
            <div className="flex-1 min-w-0">
              <h3 className={`text-lg font-bold ${theme.textPrimary}`}>{selectedNode.label}</h3>
              <p className={`text-xs ${theme.textSecondary} uppercase tracking-wider mt-0.5`}>{NODE_TYPE_META[selectedNode.type]?.label || selectedNode.type}</p>
              {/* Connected nodes */}
              <div className="mt-3 flex flex-wrap gap-1.5">
                {graphData.edges
                  .filter(e => e.source === selectedNode.id || e.target === selectedNode.id)
                  .map((e, i) => {
                    const otherId = e.source === selectedNode.id ? e.target : e.source
                    const other = nodeMap[otherId]
                    if (!other) return null
                    return (
                      <button
                        key={i}
                        onClick={() => setSelectedNode(other)}
                        className={`flex items-center gap-1 px-2 py-1 rounded-lg text-xs border ${theme.border} ${theme.glass} hover:opacity-80 transition`}
                      >
                        <span className="text-[10px]">{NODE_TYPE_META[other.type]?.icon}</span>
                        <span className={theme.textPrimary}>{other.label}</span>
                        <span className={`text-[9px] ${theme.textSecondary}`}>({e.relation.replace(/_/g, ' ')})</span>
                      </button>
                    )
                  })}
              </div>
            </div>
            <button onClick={() => setSelectedNode(null)} className={`p-1.5 rounded-lg ${theme.glass} border ${theme.border} hover:opacity-80`}>
              <X className={`h-4 w-4 ${theme.textSecondary}`} />
            </button>
          </div>
        </SectionCard>
      )}

      {/* Legend */}
      <SectionCard title="Legend" theme={theme}>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          {Object.entries(NODE_TYPE_META).map(([type, meta]) => {
            const count = graphData.stats.by_type[type] || 0
            if (count === 0) return null
            const color = graphData.nodes.find(n => n.type === type)?.color || '#94a3b8'
            return (
              <div key={type} className="flex items-center gap-2.5">
                <div className="w-3.5 h-3.5 rounded-full" style={{ backgroundColor: color as string }} />
                <div>
                  <span className={`text-xs font-medium ${theme.textPrimary}`}>{meta.icon} {meta.label}</span>
                  <span className={`text-[10px] ${theme.textSecondary} ml-1`}>({count})</span>
                </div>
              </div>
            )
          })}
        </div>
      </SectionCard>
    </div>
  )
}
