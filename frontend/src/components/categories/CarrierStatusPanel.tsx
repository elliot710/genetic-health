'use client'

import React, { useState, useMemo } from 'react'
import { ShieldCheck, ChevronRight, ChevronDown, Search, Filter, LayoutGrid } from 'lucide-react'
import { Badge } from '../ui/badge'
import { CarrierStatusChart, CategoryDistributionChart } from './GenomicCharts'
import {
  useThemeClasses,
  CategoryHeader,
  EmptyState,
  SectionCard,
  StatusBadge,
  DisclaimerCard,
  VariantLinks,
  PathogenicityBar,
  ClickableRsidBadge,
  carrierStatusToSeverity,
  MasonryLayout,
  cleanCondition,
} from './shared'
import VariantDetailDialog from './VariantDetailDialog'
import type { CategoryPanelProps, CarrierCondition } from './types'

type CarrierGroupBy = 'none' | 'inheritance' | 'gene' | 'status'

const GROUP_BY_LABELS: Record<CarrierGroupBy, string> = {
  none: 'No Grouping',
  inheritance: 'Inheritance Pattern',
  gene: 'Gene',
  status: 'Carrier Status',
}

interface MappedCarrier {
  condition: string
  conditions: string[]
  gene: string
  rsids: string[]
  status: string
  inheritance: string
  counselingRecommended: boolean
}

/** Extract gene symbol from parenthetical in condition name, e.g. "Dilated Cardiomyopathy (TTN)" → "TTN" */
function extractGene(condition: string): string {
  const match = condition.match(/\(([A-Z0-9]+)\)\s*$/)
  return match ? match[1] : ''
}

/** Normalize status for comparison */
function normalizeStatus(s: string): string {
  const lower = s.toLowerCase().trim()
  if (lower === 'carrier') return 'carrier'
  if (lower === 'non-carrier' || lower === 'not a carrier' || lower === 'non_carrier') return 'non-carrier'
  if (lower === 'affected') return 'affected'
  return lower
}

/** Display label for a status */
function statusLabel(s: string): string {
  const n = normalizeStatus(s)
  if (n === 'carrier') return 'Carrier'
  if (n === 'non-carrier') return 'Non-Carrier'
  if (n === 'affected') return 'Affected'
  return s.charAt(0).toUpperCase() + s.slice(1)
}

export default function CarrierStatusPanel({ isDarkMode = false, data, token }: CategoryPanelProps) {
  const theme = useThemeClasses(isDarkMode)
  const [selectedItem, setSelectedItem] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [inheritanceFilter, setInheritanceFilter] = useState<string>('all')
  const [groupBy, setGroupBy] = useState<CarrierGroupBy>('inheritance')
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())
  const [openDialogRsid, setOpenDialogRsid] = useState<string | null>(null)

  const carrierData: CarrierCondition[] = data?.carrier_status ?? []
  const hasRealData = carrierData.length > 0

  // Map raw API data to our display model, deduplicating by rsid set
  const allCarriers: MappedCarrier[] = useMemo(() => {
    if (!hasRealData) return []
    const raw = carrierData.map((c) => ({
      condition: c.condition,
      gene: c.gene || extractGene(c.condition),
      rsids: c.associated_variants || [],
      status: c.carrier_status || c.status || 'Unknown',
      inheritance: c.inheritance_pattern || c.inheritance || 'Unknown',
      counselingRecommended: c.genetic_counseling_recommended ?? false,
    }))

    // Deduplicate: merge entries that share the same rsid set
    const byRsidKey = new Map<string, MappedCarrier>()
    for (const item of raw) {
      const rsidKey = item.rsids.length > 0 ? [...item.rsids].sort().join(',') : `__no_rsid_${item.condition}`
      const existing = byRsidKey.get(rsidKey)
      if (existing) {
        // Merge condition names
        if (!existing.conditions.some(c => c.toLowerCase() === item.condition.toLowerCase())) {
          existing.conditions.push(item.condition)
          existing.condition = existing.conditions.map(c => cleanCondition(c)).join(' / ')
        }
        // Keep the more specific gene
        if (!existing.gene && item.gene) existing.gene = item.gene
        // Keep counseling flag if either recommends it
        if (item.counselingRecommended) existing.counselingRecommended = true
        // Keep the most severe status
        const severity = ['affected', 'carrier', 'non-carrier']
        if (severity.indexOf(normalizeStatus(item.status)) < severity.indexOf(normalizeStatus(existing.status))) {
          existing.status = item.status
        }
        // Keep the more specific inheritance
        if (existing.inheritance === 'Unknown' && item.inheritance !== 'Unknown') {
          existing.inheritance = item.inheritance
        }
      } else {
        byRsidKey.set(rsidKey, { ...item, conditions: [item.condition] })
      }
    }
    return Array.from(byRsidKey.values())
  }, [carrierData, hasRealData])

  // Unique statuses for filter dropdown
  const statusOptions = useMemo(() => {
    const set = new Set<string>()
    for (const c of allCarriers) set.add(normalizeStatus(c.status))
    return Array.from(set).sort()
  }, [allCarriers])

  // Unique inheritance patterns for filter
  const inheritanceOptions = useMemo(() => {
    const set = new Set<string>()
    for (const c of allCarriers) if (c.inheritance !== 'Unknown') set.add(c.inheritance)
    return Array.from(set).sort()
  }, [allCarriers])

  // Apply search + filter
  const filteredCarriers = useMemo(() => {
    let list = allCarriers
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      list = list.filter(c =>
        c.condition.toLowerCase().includes(q) ||
        c.gene.toLowerCase().includes(q) ||
        c.rsids.some(r => r.toLowerCase().includes(q))
      )
    }
    if (statusFilter !== 'all') {
      list = list.filter(c => normalizeStatus(c.status) === statusFilter)
    }
    if (inheritanceFilter !== 'all') {
      list = list.filter(c => c.inheritance === inheritanceFilter)
    }
    return list
  }, [allCarriers, searchQuery, statusFilter, inheritanceFilter])

  /** Group key extractor */
  const getGroupKey = (c: MappedCarrier): string => {
    switch (groupBy) {
      case 'inheritance': return c.inheritance !== 'Unknown' ? c.inheritance.replace(/_/g, ' ') : 'Unknown'
      case 'gene': return c.gene || 'Unknown Gene'
      case 'status': return statusLabel(c.status)
      default: return 'all'
    }
  }

  /** Grouped carriers — sorted by group size descending */
  const groupedCarriers = useMemo(() => {
    if (groupBy === 'none') return [{ key: 'all', label: 'All Conditions', items: filteredCarriers }]
    const groups = new Map<string, MappedCarrier[]>()
    for (const c of filteredCarriers) {
      const key = getGroupKey(c)
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push(c)
    }
    return Array.from(groups.entries())
      .map(([key, items]) => ({ key, label: key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()), items }))
      .sort((a, b) => b.items.length - a.items.length)
  }, [filteredCarriers, groupBy])

  const toggleGroup = (key: string) => {
    setCollapsedGroups(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  // Summary stats (from all, not filtered)
  const summary = useMemo(() => ({
    total: allCarriers.length,
    carrier: allCarriers.filter(c => normalizeStatus(c.status) === 'carrier').length,
    notCarrier: allCarriers.filter(c => normalizeStatus(c.status) === 'non-carrier').length,
    affected: allCarriers.filter(c => normalizeStatus(c.status) === 'affected').length,
  }), [allCarriers])

  // Chart data — carrier status donut (only renders if >1 status type)
  const statusChartData = useMemo(() => [
    { status: 'carrier', count: summary.carrier },
    { status: 'non-carrier', count: summary.notCarrier },
    { status: 'affected', count: summary.affected },
  ], [summary])

  // Chart data — inheritance pattern distribution
  const inheritanceChartData = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const c of allCarriers) {
      const pattern = c.inheritance !== 'Unknown'
        ? c.inheritance.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
        : 'Unknown'
      counts[pattern] = (counts[pattern] || 0) + 1
    }
    return Object.entries(counts).map(([label, count]) => ({ label, count }))
  }, [allCarriers])

  // Chart data — gene distribution (top genes with conditions)
  const geneChartData = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const c of allCarriers) {
      if (c.gene) counts[c.gene] = (counts[c.gene] || 0) + 1
    }
    return Object.entries(counts)
      .map(([label, count]) => ({ label, count }))
      .sort((a, b) => b.count - a.count)
  }, [allCarriers])

  // Gather counseling-recommended conditions
  const counselingConditions = useMemo(
    () => allCarriers.filter(c => c.counselingRecommended).map(c => cleanCondition(c.condition)),
    [allCarriers]
  )

  const headerProps = {
    icon: ShieldCheck,
    iconColorClass: 'text-teal-400',
    gradientFrom: 'from-teal-500/20',
    gradientTo: 'to-green-500/20',
    borderColor: 'border-teal-500/30',
    title: 'Carrier Status',
    description: 'Genetic carrier screening for inherited conditions',
    count: allCarriers.length,
    countLabel: allCarriers.length === 1 ? 'Condition' : 'Conditions',
    theme,
  }

  if (!hasRealData) {
    return (
      <div className="space-y-6">
        <CategoryHeader {...headerProps} />
        <EmptyState
          icon={ShieldCheck}
          iconColorClass="text-teal-400"
          gradientFrom="from-teal-500/20"
          gradientTo="to-green-500/20"
          borderColor="border-teal-500/30"
          title="No Carrier Status Data Available"
          description="Carrier status analysis is not yet available for your genetic data. This analysis requires specific disease-associated variants that may be added in future updates."
          theme={theme}
        />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <CategoryHeader {...headerProps} />

      {/* ── Charts ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Inheritance Pattern Distribution — always useful */}
        {inheritanceChartData.length > 0 && (
          <SectionCard title="Inheritance Patterns" theme={theme}>
            <CategoryDistributionChart data={inheritanceChartData} isDarkMode={isDarkMode} barLabel="Conditions" />
          </SectionCard>
        )}

        {/* Status Distribution — only shows when multiple status types exist */}
        {statusChartData.filter(d => d.count > 0).length > 1 && (
          <SectionCard title="Status Distribution" theme={theme}>
            <CarrierStatusChart data={statusChartData} isDarkMode={isDarkMode} />
          </SectionCard>
        )}

        {/* Gene Distribution — shows when status chart is hidden (single-status) and genes exist */}
        {statusChartData.filter(d => d.count > 0).length <= 1 && geneChartData.length > 1 && (
          <SectionCard title="Genes Screened" theme={theme}>
            <CategoryDistributionChart data={geneChartData} isDarkMode={isDarkMode} barLabel="Conditions" height={Math.max(180, geneChartData.length * 30)} />
          </SectionCard>
        )}
      </div>

      {/* ── Filter Bar ── */}
      <div className={`${theme.glass} border ${theme.border} rounded-xl p-4 flex flex-col gap-3`}>
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1 min-w-50">
            <Search className={`absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 ${theme.textSecondary}`} />
            <input
              type="text"
              placeholder="Search conditions, genes, or rsids…"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className={`w-full pl-10 pr-4 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} placeholder:${theme.textSecondary} focus:outline-none focus:ring-2 focus:ring-teal-500/40 text-sm`}
            />
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Filter className={`h-4 w-4 ${theme.textSecondary} shrink-0`} />
            <select
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
              className={`px-3 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} focus:outline-none focus:ring-2 focus:ring-teal-500/40 text-sm`}
            >
              <option value="all">All Statuses</option>
              {statusOptions.map(s => (
                <option key={s} value={s}>{statusLabel(s)}</option>
              ))}
            </select>
            {inheritanceOptions.length > 1 && (
              <select
                value={inheritanceFilter}
                onChange={e => setInheritanceFilter(e.target.value)}
                className={`px-3 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} focus:outline-none focus:ring-2 focus:ring-teal-500/40 text-sm`}
              >
                <option value="all">All Inheritance</option>
                {inheritanceOptions.map(p => (
                  <option key={p} value={p}>{p.replace(/_/g, ' ')}</option>
                ))}
              </select>
            )}
            <div className="flex items-center gap-1.5">
              <LayoutGrid className={`h-4 w-4 ${theme.textSecondary} shrink-0`} />
              <select
                value={groupBy}
                onChange={e => { setGroupBy(e.target.value as CarrierGroupBy); setCollapsedGroups(new Set()) }}
                className={`px-3 py-2 rounded-lg border ${theme.border} ${theme.glass} ${theme.textPrimary} focus:outline-none focus:ring-2 focus:ring-teal-500/40 text-sm`}
              >
                {Object.entries(GROUP_BY_LABELS).map(([key, label]) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
        {(searchQuery || statusFilter !== 'all' || inheritanceFilter !== 'all') && (
          <div className="flex items-center gap-2">
            <span className={`text-xs ${theme.textSecondary}`}>
              {filteredCarriers.length} of {allCarriers.length} conditions
              {groupBy !== 'none' && ` · ${groupedCarriers.length} groups`}
            </span>
            <button
              onClick={() => { setSearchQuery(''); setStatusFilter('all'); setInheritanceFilter('all') }}
              className="text-xs text-teal-400 hover:text-teal-300 underline"
            >
              Clear filters
            </button>
          </div>
        )}
      </div>

      {/* ── Cards ── */}
      <SectionCard title={`Carrier Screening Results${filteredCarriers.length !== allCarriers.length ? ` (${filteredCarriers.length} of ${allCarriers.length})` : ''}`} theme={theme}>
        {groupedCarriers.map(group => {
          const isGroupCollapsed = collapsedGroups.has(group.key)
          return (
            <div key={group.key} className="mb-4 last:mb-0">
              {groupBy !== 'none' && (
                <button
                  onClick={() => toggleGroup(group.key)}
                  className={`w-full flex items-center gap-2 px-3 py-2.5 rounded-lg ${theme.glass} border ${theme.border} mb-3 hover:border-teal-500/40 transition-colors`}
                >
                  {isGroupCollapsed
                    ? <ChevronRight className={`h-4 w-4 ${theme.textSecondary}`} />
                    : <ChevronDown className={`h-4 w-4 ${theme.textSecondary}`} />
                  }
                  <span className={`font-semibold text-sm ${theme.textPrimary}`}>{group.label}</span>
                  <Badge variant="secondary" className="text-xs ml-auto">{group.items.length}</Badge>
                </button>
              )}

              {!isGroupCollapsed && (
                <MasonryLayout>
                  {group.items.map((carrier: MappedCarrier, index: number) => {
            const itemKey = `carrier-${group.key}-${index}`
            const isExpanded = selectedItem === itemKey
            return (
              <div
                key={index}
                className={`${theme.glass} border ${theme.border} rounded-xl p-5 cursor-pointer hover:border-teal-500/50 transition-all duration-300`}
                onClick={() => setSelectedItem(isExpanded ? null : itemKey)}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <h4 className={`font-bold text-lg ${theme.textPrimary}`}>{cleanCondition(carrier.condition)}</h4>
                    <StatusBadge
                      label={statusLabel(carrier.status)}
                      severity={carrierStatusToSeverity(carrier.status)}
                    />
                  </div>
                  <ChevronRight className={`h-5 w-5 ${theme.textSecondary} transition-transform duration-300 ${isExpanded ? 'rotate-90' : ''}`} />
                </div>

                {/* Badges: gene + clickable rsids */}
                <div className="flex flex-wrap gap-1.5 mb-1">
                  {carrier.gene && <Badge variant="secondary" className="text-xs">{carrier.gene}</Badge>}
                  {carrier.rsids.map(rsid => (
                    <ClickableRsidBadge key={rsid} rsid={rsid} gene={carrier.gene} genotype={data?.genotype_map?.[rsid]} token={token} isDarkMode={isDarkMode} />
                  ))}
                </div>

                {/* Collapsed description */}
                <p className={`text-sm ${theme.textSecondary} line-clamp-2 mt-1`}>
                  {carrier.inheritance !== 'Unknown' ? `${carrier.inheritance.replace(/_/g, ' ')} inheritance` : 'Inheritance pattern not specified'}
                  {carrier.counselingRecommended ? ' · Genetic counseling recommended' : ''}
                </p>

                {isExpanded && (
                  <div className={`mt-4 pt-4 border-t ${theme.border} space-y-3`}>
                    <div className={`text-sm ${theme.textSecondary}`}>
                      <span className="font-medium">Inheritance Pattern:</span> {carrier.inheritance.replace(/_/g, ' ')}
                    </div>

                    {carrier.counselingRecommended && (
                      <div className="text-sm text-amber-500 font-medium">
                        ⚠ Genetic counseling is recommended for this condition
                      </div>
                    )}
                    
                    {carrier.rsids.length > 0 && carrier.rsids.map(rsid => (
                      <React.Fragment key={rsid}>
                        <PathogenicityBar rsid={rsid} pathogenicityMap={data?.pathogenicity_map} theme={theme} />
                        <div className="mb-2 flex items-center gap-2">
                          <VariantLinks rsid={rsid} gene={carrier.gene} token={token} isDarkMode={isDarkMode} />
                        </div>
                      </React.Fragment>
                    ))}

                    {/* Single dialog for the open rsid */}
                    {openDialogRsid && carrier.rsids.includes(openDialogRsid) && (
                      <VariantDetailDialog
                        rsid={openDialogRsid}
                        gene={carrier.gene}
                        token={token}
                        isDarkMode={isDarkMode}
                        open={true}
                        onOpenChange={open => { if (!open) setOpenDialogRsid(null) }}
                      />
                    )}
                  </div>
                )}
              </div>
            )
          })}
                </MasonryLayout>
              )}
            </div>
          )
        })}
      </SectionCard>

      {/* ── Summary ── */}
      <SectionCard title="Screening Summary" theme={theme}>
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center">
            <div className="text-2xl font-bold text-yellow-500 mb-1">{summary.carrier}</div>
            <div className={`text-sm ${theme.textSecondary}`}>Carrier</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-green-500 mb-1">{summary.notCarrier}</div>
            <div className={`text-sm ${theme.textSecondary}`}>Non-Carrier</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-red-500 mb-1">{summary.affected}</div>
            <div className={`text-sm ${theme.textSecondary}`}>Affected</div>
          </div>
        </div>
      </SectionCard>

      {/* ── Recommendations ── */}
      {counselingConditions.length > 0 && (
        <SectionCard title="Recommendations" theme={theme}>
          <div className="space-y-3">
            <p className={`text-sm ${theme.textSecondary}`}>
              Based on your carrier screening results, genetic counseling is recommended for the following conditions:
            </p>
            <ul className="list-disc list-inside space-y-1">
              {counselingConditions.map((cond, i) => (
                <li key={i} className={`text-sm ${theme.textPrimary}`}>{cond}</li>
              ))}
            </ul>
            <p className={`text-sm ${theme.textSecondary} mt-2`}>
              A genetic counselor can help you understand your carrier status, assess family planning implications, and discuss testing options for partners.
            </p>
          </div>
        </SectionCard>
      )}

      <DisclaimerCard theme={theme} />
    </div>
  )
}
