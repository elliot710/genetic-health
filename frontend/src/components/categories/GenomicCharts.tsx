'use client'

/**
 * Reusable Recharts-based visualization components for the genetic dashboard.
 * All charts respect dark/light mode via the isDarkMode prop.
 */

import React, { useMemo } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  AreaChart, Area,
} from 'recharts'
import type { PieLabelRenderProps } from 'recharts'
import type { Payload } from 'recharts/types/component/DefaultTooltipContent'

// ── Theme-aware colour palettes ────────────────────────────────────
const RISK_COLORS = { high: '#ef4444', moderate: '#f59e0b', low: '#22c55e', unknown: '#94a3b8' }
const RESPONSE_COLORS = { poor: '#ef4444', rapid: '#f59e0b', normal: '#22c55e', intermediate: '#3b82f6', ultrarapid: '#8b5cf6' }
const CAPACITY_COLORS = { impaired: '#ef4444', reduced: '#f59e0b', variant: '#f59e0b', normal: '#22c55e', enhanced: '#06b6d4' }
const PALETTE = ['#06b6d4', '#8b5cf6', '#f59e0b', '#22c55e', '#ef4444', '#ec4899', '#3b82f6', '#14b8a6', '#f97316', '#a855f7', '#64748b', '#d946ef']

interface ChartBase { isDarkMode: boolean; height?: number }

const axisStyle = (dark: boolean) => ({ fill: dark ? '#94a3b8' : '#64748b', fontSize: 11 })
const gridStroke = (dark: boolean) => dark ? 'rgba(148,163,184,0.12)' : 'rgba(100,116,139,0.15)'

// Custom tooltip matching the glassmorphism theme
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

// ── 1. Risk Distribution – horizontal bar ──────────────────────────
interface RiskDistributionProps extends ChartBase {
  data: { condition: string; risk_level: string; risk_score?: string | number }[]
}

export function RiskDistributionChart({ data, isDarkMode, height = 280 }: RiskDistributionProps) {
  const chartData = useMemo(() => {
    const counts: Record<string, number> = { high: 0, moderate: 0, low: 0 }
    data.forEach(d => { const l = (d.risk_level || 'unknown').toLowerCase(); counts[l] = (counts[l] || 0) + 1 })
    return Object.entries(counts).filter(([, v]) => v > 0).map(([level, count]) => ({ level: level.charAt(0).toUpperCase() + level.slice(1), count, fill: RISK_COLORS[level as keyof typeof RISK_COLORS] || RISK_COLORS.unknown }))
  }, [data])

  if (!chartData.length) return null
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 16, top: 8, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={gridStroke(isDarkMode)} horizontal={false} />
        <XAxis type="number" tick={axisStyle(isDarkMode)} allowDecimals={false} />
        <YAxis type="category" dataKey="level" tick={axisStyle(isDarkMode)} width={80} />
        <Tooltip content={<GlassTooltip isDarkMode={isDarkMode} />} />
        <Bar dataKey="count" name="Conditions" radius={[0, 6, 6, 0]} barSize={28}>
          {chartData.map((d, i) => <Cell key={i} fill={d.fill} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── 2. Ancestry Composition – donut chart ──────────────────────────
interface AncestryChartProps extends ChartBase {
  data: { population: string; percentage: string | number }[]
}

export function AncestryDonutChart({ data, isDarkMode, height = 300 }: AncestryChartProps) {
  const chartData = useMemo(() =>
    data.map((d, i) => ({
      name: d.population,
      value: parseFloat(String(d.percentage)),
      fill: PALETTE[i % PALETTE.length],
    })).filter(d => d.value > 0).sort((a, b) => b.value - a.value),
  [data])

  if (!chartData.length) return null
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%" cy="50%"
          innerRadius="45%" outerRadius="75%"
          paddingAngle={2}
          dataKey="value"
          nameKey="name"
          label={({ name, value }) => `${name} ${value.toFixed(1)}%`}
          labelLine={{ stroke: isDarkMode ? '#64748b' : '#94a3b8' }}
        >
          {chartData.map((d, i) => <Cell key={i} fill={d.fill} stroke="none" />)}
        </Pie>
        <Tooltip content={<GlassTooltip isDarkMode={isDarkMode} />} />
        <Legend
          wrapperStyle={{ fontSize: 11, color: isDarkMode ? '#cbd5e1' : '#475569' }}
          iconType="circle" iconSize={8}
        />
      </PieChart>
    </ResponsiveContainer>
  )
}

// ── 3. Personality / Cognitive Radar ───────────────────────────────
interface RadarChartProps extends ChartBase {
  data: { label: string; value: number; fullMark?: number }[]
  fillColor?: string
  strokeColor?: string
}

export function TraitRadarChart({ data, isDarkMode, height = 320, fillColor, strokeColor }: RadarChartProps) {
  const fill = fillColor || (isDarkMode ? 'rgba(20,184,166,0.25)' : 'rgba(13,148,136,0.20)')
  const stroke = strokeColor || (isDarkMode ? '#14b8a6' : '#0d9488')
  if (data.length < 3) return null
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RadarChart cx="50%" cy="50%" outerRadius="70%" data={data}>
        <PolarGrid stroke={gridStroke(isDarkMode)} />
        <PolarAngleAxis dataKey="label" tick={{ ...axisStyle(isDarkMode), fontSize: 10 }} />
        <PolarRadiusAxis tick={false} axisLine={false} />
        <Radar dataKey="value" fill={fill} stroke={stroke} strokeWidth={2} dot={{ r: 3, fill: stroke }} />
        <Tooltip content={<GlassTooltip isDarkMode={isDarkMode} />} />
      </RadarChart>
    </ResponsiveContainer>
  )
}

// ── 4. Percentile Bar Chart (Intelligence) ─────────────────────────
interface PercentileBarProps extends ChartBase {
  data: { name: string; percentile: number }[]
}

export function PercentileBarChart({ data, isDarkMode, height = 280 }: PercentileBarProps) {
  const chartData = useMemo(() =>
    data.map(d => ({
      ...d,
      fill: d.percentile >= 75 ? '#22c55e' : d.percentile >= 50 ? '#06b6d4' : d.percentile >= 25 ? '#f59e0b' : '#94a3b8',
    })),
  [data])

  if (!chartData.length) return null
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData} layout="vertical" margin={{ left: 4, right: 16, top: 8, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={gridStroke(isDarkMode)} horizontal={false} />
        <XAxis type="number" domain={[0, 100]} tick={axisStyle(isDarkMode)} />
        <YAxis type="category" dataKey="name" tick={axisStyle(isDarkMode)} width={100} />
        <Tooltip content={<GlassTooltip isDarkMode={isDarkMode} />} />
        <Bar dataKey="percentile" name="Percentile" radius={[0, 6, 6, 0]} barSize={22}>
          {chartData.map((d, i) => <Cell key={i} fill={d.fill} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── 5. Drug Response Distribution – grouped bar ────────────────────
interface DrugResponseChartProps extends ChartBase {
  data: { gene: string; drug: string; response_type: string }[]
}

export function DrugResponseChart({ data, isDarkMode, height = 260 }: DrugResponseChartProps) {
  const chartData = useMemo(() => {
    const counts: Record<string, number> = {}
    data.forEach(d => { const t = (d.response_type || 'unknown').toLowerCase(); counts[t] = (counts[t] || 0) + 1 })
    return Object.entries(counts).filter(([, v]) => v > 0)
      .map(([type, count]) => ({
        type: type.charAt(0).toUpperCase() + type.slice(1).replace(/_/g, ' '),
        count,
        fill: RESPONSE_COLORS[type as keyof typeof RESPONSE_COLORS] || '#94a3b8',
      }))
      .sort((a, b) => b.count - a.count)
  }, [data])

  if (!chartData.length) return null
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData} margin={{ left: 8, right: 16, top: 8, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={gridStroke(isDarkMode)} />
        <XAxis dataKey="type" tick={axisStyle(isDarkMode)} />
        <YAxis tick={axisStyle(isDarkMode)} allowDecimals={false} />
        <Tooltip content={<GlassTooltip isDarkMode={isDarkMode} />} />
        <Bar dataKey="count" name="Drugs" radius={[6, 6, 0, 0]} barSize={40}>
          {chartData.map((d, i) => <Cell key={i} fill={d.fill} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── 6. Capacity Bar (Methylation / Detox) ──────────────────────────
interface CapacityChartProps extends ChartBase {
  data: { name: string; capacity: string }[]
  phaseLabel?: string
}

export function CapacityChart({ data, isDarkMode, height = 240 }: CapacityChartProps) {
  const chartData = useMemo(() => {
    const counts: Record<string, number> = {}
    data.forEach(d => { const c = (d.capacity || 'unknown').toLowerCase(); counts[c] = (counts[c] || 0) + 1 })
    return Object.entries(counts).filter(([, v]) => v > 0)
      .map(([cap, count]) => ({
        capacity: cap.charAt(0).toUpperCase() + cap.slice(1),
        count,
        fill: CAPACITY_COLORS[cap as keyof typeof CAPACITY_COLORS] || '#94a3b8',
      }))
  }, [data])

  if (!chartData.length) return null
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData} margin={{ left: 8, right: 16, top: 8, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={gridStroke(isDarkMode)} />
        <XAxis dataKey="capacity" tick={axisStyle(isDarkMode)} />
        <YAxis tick={axisStyle(isDarkMode)} allowDecimals={false} />
        <Tooltip content={<GlassTooltip isDarkMode={isDarkMode} />} />
        <Bar dataKey="count" name="Genes" radius={[6, 6, 0, 0]} barSize={40}>
          {chartData.map((d, i) => <Cell key={i} fill={d.fill} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── 7. Variant Functional Categories – area sparkline ──────────────
interface FunctionalCategoriesProps extends ChartBase {
  data: { name: string; count: number }[]
}

export function FunctionalCategoriesChart({ data, isDarkMode, height = 200 }: FunctionalCategoriesProps) {
  if (!data.length) return null
  const sorted = [...data].sort((a, b) => b.count - a.count)
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={sorted} margin={{ left: 4, right: 16, top: 8, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={gridStroke(isDarkMode)} />
        <XAxis dataKey="name" tick={{ ...axisStyle(isDarkMode), fontSize: 10 }} interval={0} angle={-30} textAnchor="end" height={50} />
        <YAxis tick={axisStyle(isDarkMode)} />
        <Tooltip content={<GlassTooltip isDarkMode={isDarkMode} />} />
        <Bar dataKey="count" name="Variants" radius={[6, 6, 0, 0]}>
          {sorted.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── 8. Wellness Scores – small multiples area chart ────────────────
interface WellnessAreaProps extends ChartBase {
  data: { metric: string; score: number }[]
}

export function WellnessScoreChart({ data, isDarkMode, height = 240 }: WellnessAreaProps) {
  if (data.length < 2) return null
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ left: 4, right: 16, top: 8, bottom: 8 }}>
        <defs>
          <linearGradient id="wellnessGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#14b8a6" stopOpacity={0.4} />
            <stop offset="95%" stopColor="#14b8a6" stopOpacity={0.05} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={gridStroke(isDarkMode)} />
        <XAxis dataKey="metric" tick={{ ...axisStyle(isDarkMode), fontSize: 10 }} interval={0} angle={-20} textAnchor="end" height={50} />
        <YAxis tick={axisStyle(isDarkMode)} domain={[0, 100]} />
        <Tooltip content={<GlassTooltip isDarkMode={isDarkMode} />} />
        <Area type="monotone" dataKey="score" name="Score" stroke="#14b8a6" strokeWidth={2} fill="url(#wellnessGrad)" dot={{ r: 3, fill: '#14b8a6' }} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

// ── 9. Generic Category Distribution – reusable horizontal bar ─────
interface CategoryDistributionChartProps extends ChartBase {
  data: { label: string; count: number; color?: string }[]
  barLabel?: string
}

/**
 * Reusable horizontal bar chart for any categorical distribution.
 * Used by carrier status (inheritance patterns), and available for any panel
 * that needs a category→count breakdown.
 */
export function CategoryDistributionChart({ data, isDarkMode, height = 220, barLabel = 'Count' }: CategoryDistributionChartProps) {
  const chartData = useMemo(() =>
    data.filter(d => d.count > 0)
      .map((d, i) => ({ ...d, fill: d.color || PALETTE[i % PALETTE.length] }))
      .sort((a, b) => b.count - a.count),
  [data])

  if (!chartData.length) return null
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 16, top: 8, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={gridStroke(isDarkMode)} horizontal={false} />
        <XAxis type="number" tick={axisStyle(isDarkMode)} allowDecimals={false} />
        <YAxis type="category" dataKey="label" tick={axisStyle(isDarkMode)} width={140} />
        <Tooltip content={<GlassTooltip isDarkMode={isDarkMode} />} />
        <Bar dataKey="count" name={barLabel} radius={[0, 6, 6, 0]} barSize={24}>
          {chartData.map((d, i) => <Cell key={i} fill={d.fill} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── 10. Carrier Status Distribution – donut (only when > 1 status) ─
const CARRIER_COLORS: Record<string, string> = { carrier: '#f59e0b', 'non-carrier': '#22c55e', affected: '#ef4444', unknown: '#94a3b8' }

interface CarrierStatusChartProps extends ChartBase {
  data: { status: string; count: number }[]
}

export function CarrierStatusChart({ data, isDarkMode, height = 240 }: CarrierStatusChartProps) {
  const chartData = useMemo(() =>
    data.filter(d => d.count > 0).map(d => ({
      name: d.status.charAt(0).toUpperCase() + d.status.slice(1),
      value: d.count,
      fill: CARRIER_COLORS[d.status.toLowerCase()] || '#94a3b8',
    })),
  [data])

  // Don't render a single-slice donut — it's not informative
  if (chartData.length <= 1) return null
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%" cy="50%"
          innerRadius="40%" outerRadius="70%"
          paddingAngle={3}
          dataKey="value"
          nameKey="name"
          label={({ name, value }) => `${name}: ${value}`}
          labelLine={{ stroke: isDarkMode ? '#64748b' : '#94a3b8' }}
        >
          {chartData.map((d, i) => <Cell key={i} fill={d.fill} stroke="none" />)}
        </Pie>
        <Tooltip content={<GlassTooltip isDarkMode={isDarkMode} />} />
        <Legend wrapperStyle={{ fontSize: 11, color: isDarkMode ? '#cbd5e1' : '#475569' }} />
      </PieChart>
    </ResponsiveContainer>
  )
}

// ── 10. Overview Summary Pie – high-level category breakdown ───────
interface OverviewPieProps extends ChartBase {
  counts: { label: string; count: number; color: string }[]
}

export function OverviewSummaryPie({ counts, isDarkMode, height = 240 }: OverviewPieProps) {
  const chartData = counts.filter(c => c.count > 0)
  if (!chartData.length) return null
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie data={chartData} cx="50%" cy="50%" outerRadius="75%" dataKey="count" nameKey="label" label={(props: PieLabelRenderProps & { label?: string; count?: number }) => `${props.label || ''}: ${props.count || 0}`} labelLine={{ stroke: isDarkMode ? '#64748b' : '#94a3b8' }}>
          {chartData.map((d, i) => <Cell key={i} fill={d.color} />)}
        </Pie>
        <Tooltip content={<GlassTooltip isDarkMode={isDarkMode} />} />
      </PieChart>
    </ResponsiveContainer>
  )
}
