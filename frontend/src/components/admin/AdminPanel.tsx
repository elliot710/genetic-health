'use client'

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { Shield, Users, Settings, Plus, Trash2, Pencil, Check, X, ChevronRight, Download, Upload, Database, Lightbulb, RefreshCw, AlertTriangle, Minus, Info, Activity, Play, Pause, Square, Clock, FileText, Zap, Sparkles, HardDrive, Scale, RotateCcw, Layers, CheckCircle, XCircle } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import VariantDetailDialog from '@/components/categories/VariantDetailDialog'
import { apiUrl } from '@/lib/api'

const API = apiUrl('/api/admin')

interface AdminUser {
  id: number
  email: string
  username: string
  full_name: string | null
  avatar_url: string | null
  is_active: boolean
  is_verified: boolean
  is_admin: boolean
  created_at: string
  analysis_count: number
}

interface VariantMapping {
  id: number
  category: string
  map_type: string
  key: string
  data: Record<string, unknown>
  is_active: boolean
  created_at: string | null
  updated_at: string | null
}

interface VariantMappingCategorySummary {
  category: string
  rsid_count: number
  gene_count: number
  total: number
}

interface PendingDiscoveryItem {
  id: number
  discovery_type: string
  rsid: string
  gene: string | null
  panel_id: string | null
  description: string | null
  category: string | null
  map_type: string | null
  mapping_category: string | null
  mapping_data: Record<string, unknown> | null
  source_data: Record<string, unknown> | null
  status: string
  rejection_reason: string | null
  lookup_count: number
  created_at: string | null
}

interface DiscoverySummary {
  total_pending: number
  total_approved: number
  total_rejected: number
  variant_mapping_pending: number
}

interface IncompleteAnnotation {
  id: number
  rsid: string
  annotation_status: string | null
  failed_sources: string[] | null
  missing_sources: string[]
  total_api_calls: number
  ensembl: string  // "found" | "no_data" | "missing"
  clinvar: string
  clinpgx: string
  snpedia: string
  litvar: string
  alpha_missense: string
  clinvar_local: string
  gnomad: string
  chembl: string
  fda_drug: string
  alphafold: string
  first_annotated_at: string | null
  last_updated_at: string | null
  usage_count: number
}

interface IncompleteAnnotationSummary {
  total_annotations: number
  complete: number
  partial: number
  failed: number
  enabled_sources: string[]   // all enabled sources (table columns)
  active_sources: string[]    // high-coverage sources (used for counts)
}

interface AdminJob {
  id: number
  user_id: number
  user_email: string
  username: string
  filename: string
  file_type: string
  analysis_status: string
  progress_percentage: number
  total_variants: number
  processed_variants: number
  current_step: string | null
  upload_date: string | null
  estimated_completion: string | null
}

interface AdminJobsSummary {
  total: number
  pending: number
  processing: number
  completed: number
  failed: number
}

interface WorkerJob {
  job_id: number
  job_type: string
  status: string
  params: Record<string, unknown> | null
  result: Record<string, unknown> | null
  error: string | null
  requested_by_email: string | null
  requested_by_username: string | null
  created_at: string | null
  started_at: string | null
  completed_at: string | null
}

interface AnnotationSource {
  id: number
  source_name: string
  display_name: string
  is_enabled: boolean
  description: string | null
  source_type: 'api' | 'database' | 'file' | 'hybrid' | 'bigquery'
  rate_limit: number | null
  priority: number
  annotated_count: number
  missing_count: number
}

const CATEGORY_LABELS: Record<string, string> = {
  health: 'Health Risks',
  drug: 'Drug Responses',
  physical: 'Physical Traits',
  nutrition: 'Nutrition',
  sports: 'Sports Performance',
  cognitive: 'Cognitive Profiles',
  personality: 'Personality Traits',
  wellness: 'Wellness Metrics',
  methylation: 'Methylation',
  detox: 'Detoxification',
  carrier: 'Carrier Status',
  rare: 'Rare Mutations',
  uncommon: 'Uncommon Mutations',
}

function formatCompactNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`
  if (n >= 10_000) return `${Math.round(n / 1000)}K`
  if (n >= 1_000) return `${(n / 1000).toFixed(1).replace(/\.0$/, '')}K`
  return String(n)
}

const SOURCE_DISPLAY_NAMES: Record<string, string> = {
  ensembl: 'Ensembl',
  clinvar: 'ClinVar',
  clinpgx: 'ClinPGx',
  snpedia: 'SNPedia',
  litvar: 'LitVar',
  alpha_missense: 'AlphaMiss',
  clinvar_local: 'ClinVar DB',
  gnomad: 'gnomAD',
  chembl: 'ChEMBL',
  fda_drug: 'FDA Drug',
  alphafold: 'AlphaFold',
}

const SOURCE_TYPE_CONFIG: Record<string, { label: string; className: string }> = {
  api:      { label: 'API',       className: 'text-blue-400 border-blue-500/30 bg-blue-500/10' },
  database: { label: 'Postgres',  className: 'text-cyan-400 border-cyan-500/30 bg-cyan-500/10' },
  file:     { label: 'File',      className: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10' },
  hybrid:   { label: 'File + DB', className: 'text-amber-400 border-amber-500/30 bg-amber-500/10' },
  bigquery: { label: 'BigQuery',  className: 'text-purple-400 border-purple-500/30 bg-purple-500/10' },
}

const SOURCE_GROUP_ORDER = ['api', 'file', 'hybrid', 'database', 'bigquery'] as const
const SOURCE_GROUP_LABELS: Record<string, string> = {
  api:      'Third-party APIs',
  file:     'Local Files (data_sources/)',
  hybrid:   'Local Files + PostgreSQL',
  database: 'PostgreSQL Only',
  bigquery: 'Google BigQuery',
}

interface AdminPanelProps {
  token?: string
  isDarkMode: boolean
  theme: ReturnType<typeof import('@/utils/theme').getTheme>
}

export default function AdminPanel({ token, isDarkMode, theme }: AdminPanelProps) {
  // --- Tab routing via URL hash ---
  const VALID_TABS = ['users', 'registry', 'discoveries', 'data', 'rules', 'annotations', 'jobs'] as const
  type AdminTab = typeof VALID_TABS[number]

  const [activeTab, setActiveTab] = useState<AdminTab>(() => {
    if (typeof window !== 'undefined') {
      const hash = window.location.hash.slice(1) // e.g. "admin/data"
      const sub = hash.startsWith('admin/') ? hash.slice(6) : ''
      const resolvedSub = sub === 'sources' ? 'data' : sub
      if (VALID_TABS.includes(resolvedSub as AdminTab)) return resolvedSub as AdminTab
    }
    return 'users'
  })

  const handleTabChange = useCallback((value: string) => {
    const tab = value as AdminTab
    setActiveTab(tab)
    if (typeof window !== 'undefined') {
      window.history.replaceState(null, '', `#admin/${tab}`)
    }
  }, [])

  // Listen for hash changes (browser back/forward)
  useEffect(() => {
    const onHashChange = () => {
      const hash = window.location.hash.slice(1)
      if (hash.startsWith('admin/')) {
        const sub = hash.slice(6)
        const resolvedSub = sub === 'sources' ? 'data' : sub
        if (VALID_TABS.includes(resolvedSub as AdminTab)) setActiveTab(resolvedSub as AdminTab)
      }
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Dialog states
  const [showDeleteUser, setShowDeleteUser] = useState<AdminUser | null>(null)

  // Variant registry state
  const [registryCategories, setRegistryCategories] = useState<VariantMappingCategorySummary[]>([])
  const [selectedRegistryCategory, setSelectedRegistryCategory] = useState<string | null>(null)
  const [registryMappings, setRegistryMappings] = useState<VariantMapping[]>([])
  const [registryFilter, setRegistryFilter] = useState<string>('all') // 'all' | 'rsid' | 'gene'
  const [showAddMapping, setShowAddMapping] = useState(false)
  const [showDeleteMapping, setShowDeleteMapping] = useState<VariantMapping | null>(null)
  const [editingMapping, setEditingMapping] = useState<VariantMapping | null>(null)
  const [editingDataStr, setEditingDataStr] = useState('')
  const [newMapping, setNewMapping] = useState({ category: '', map_type: 'rsid' as 'rsid' | 'gene', key: '', data: '{}' })

  // Discoveries state
  const [discoveries, setDiscoveries] = useState<PendingDiscoveryItem[]>([])
  const [discoverySummary, setDiscoverySummary] = useState<DiscoverySummary | null>(null)
  const [discoveryStatusFilter, setDiscoveryStatusFilter] = useState<string>('pending')
  const [discoveryTypeFilter, setDiscoveryTypeFilter] = useState<string>('all')
  const [reviewingId, setReviewingId] = useState<number | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [showRejectDialog, setShowRejectDialog] = useState<PendingDiscoveryItem | null>(null)
  const [selectedDiscoveryRsid, setSelectedDiscoveryRsid] = useState<{ rsid: string; gene?: string } | null>(null)

  // Incomplete annotations state
  const [incompleteAnnotations, setIncompleteAnnotations] = useState<IncompleteAnnotation[]>([])
  const [incompleteSummary, setIncompleteSummary] = useState<IncompleteAnnotationSummary | null>(null)
  const [incompleteFilter, setIncompleteFilter] = useState<string>('partial')
  const [incompletePage, setIncompletePage] = useState(0)
  const [incompleteTotalCount, setIncompleteTotalCount] = useState(0)
  const INCOMPLETE_PAGE_SIZE = 50
  const [retriggeringIds, setRetriggeringIds] = useState<Set<number>>(new Set())
  const [bulkRetriggering, setBulkRetriggering] = useState(false)
  const [retriggerFeedback, setRetriggerFeedback] = useState<{ id: number; message: string; type: 'success' | 'info' | 'error' } | null>(null)

  // Jobs state
  const [jobs, setJobs] = useState<AdminJob[]>([])
  const [jobsSummary, setJobsSummary] = useState<AdminJobsSummary | null>(null)
  const [jobsStatusFilter, setJobsStatusFilter] = useState<string>('all')
  const [jobActionLoading, setJobActionLoading] = useState<number | null>(null)
  const [viewingLogs, setViewingLogs] = useState<number | null>(null)
  const [jobLogs, setJobLogs] = useState<{ ts: string; level: string; msg: string }[]>([])
  const [logsLoading, setLogsLoading] = useState(false)
  const [deleteConfirmJobId, setDeleteConfirmJobId] = useState<number | null>(null)

  // Worker jobs state
  const [workerJobs, setWorkerJobs] = useState<WorkerJob[]>([])
  const [workerJobsExpanded, setWorkerJobsExpanded] = useState<number | null>(null)
  const logsEndRef = useRef<HTMLDivElement>(null)
  const logsRefreshRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Annotation sources state
  const [annotationSources, setAnnotationSources] = useState<AnnotationSource[]>([])
  const [sourcesLoading, setSourcesLoading] = useState(false)
  const [sourceToggling, setSourceToggling] = useState<string | null>(null)
  const [backfillingSource, setBackfillingSource] = useState<string | null>(null)
  const [backfillFeedback, setBackfillFeedback] = useState<{ source: string; message: string; type: 'success' | 'error' } | null>(null)
  const [backfillLimits, setBackfillLimits] = useState<Record<string, string>>({})

  // AI Insights state
  const [insightsStatus, setInsightsStatus] = useState<{ provider: string; enabled: boolean; model: string; gemini_configured: boolean; openai_configured: boolean; anthropic_configured: boolean; cache_entries: number } | null>(null)
  const [insightsToggling, setInsightsToggling] = useState(false)

  // Client-side pagination for all tabs
  const PAGE_SIZE = 25
  const [usersPage, setUsersPage] = useState(0)
  const [registryPage, setRegistryPage] = useState(0)
  const [discoveriesPage, setDiscoveriesPage] = useState(0)
  const [jobsPage, setJobsPage] = useState(0)
  const [rulesPage, setRulesPage] = useState(0)

  // ETL state
  const [etlStatuses, setEtlStatuses] = useState<Record<string, Record<string, unknown>>>({})
  const [etlLoading, setEtlLoading] = useState<Record<string, boolean>>({})
  const [etlRunning, setEtlRunning] = useState<Record<string, boolean>>({})
  const [etlFeedback, setEtlFeedback] = useState<{ source: string; message: string; type: 'success' | 'error' } | null>(null)
  const [etlProgress, setEtlProgress] = useState<{ running: boolean; step: string | null; rows: number; pct: number; total_elapsed: number; error: string | null; steps: { step: string; count: number; elapsed_s: number }[] } | null>(null)
  const etlPollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // BigQuery state
  const [bqStatus, setBqStatus] = useState<Record<string, unknown> | null>(null)
  const [bqLoading, setBqLoading] = useState(false)
  const [bqRunning, setBqRunning] = useState(false)
  const [bqBatchSize, setBqBatchSize] = useState('200')
  const [bqMaxVariants, setBqMaxVariants] = useState('10000')
  const [bqChromosome, setBqChromosome] = useState('')
  const [bqFeedback, setBqFeedback] = useState<{ message: string; type: 'success' | 'error' } | null>(null)

  // Category Rules state
  const [categoryRules, setCategoryRules] = useState<{ id: number; category: string; rule_type: string; rule_value: string; priority: number; is_active: boolean; mapping_data_template: Record<string, unknown> | null; created_at: string | null }[]>([])
  const [rulesLoading, setRulesLoading] = useState(false)
  const [rulesCategoryFilter, setRulesCategoryFilter] = useState<string>('all')
  const [showAddRule, setShowAddRule] = useState(false)
  const [newRule, setNewRule] = useState({ category: '', rule_type: 'gene_symbol', rule_value: '', priority: '50' })
  const [editingRule, setEditingRule] = useState<number | null>(null)
  const [editingRulePriority, setEditingRulePriority] = useState('')
  const [deleteRuleId, setDeleteRuleId] = useState<number | null>(null)
  const [seedingRules, setSeedingRules] = useState(false)
  const [rulesFeedback, setRulesFeedback] = useState<{ message: string; type: 'success' | 'error' } | null>(null)

  // Utility state
  const [autoCategorizing, setAutoCategorizing] = useState(false)
  const [autoCatStatus, setAutoCatStatus] = useState<string | null>(null)
  const [enrichingMappings, setEnrichingMappings] = useState<'dry_run' | 'apply' | null>(null)
  const [enrichReviseAll, setEnrichReviseAll] = useState(false)
  const [purgingDeleted, setPurgingDeleted] = useState(false)
  const [purgeOlderThanDays, setPurgeOlderThanDays] = useState('0')
  const [utilityFeedback, setUtilityFeedback] = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  const [resettingSentinels, setResettingSentinels] = useState<string | null>(null)
  const [sentinelFeedback, setSentinelFeedback] = useState<{ source: string; message: string; type: 'success' | 'error' } | null>(null)
  const [gnomadCacheJobId, setGnomadCacheJobId] = useState<number | null>(null)
  const [gnomadCacheStatus, setGnomadCacheStatus] = useState<string | null>(null)
  const [gnomadAncestryJobId, setGnomadAncestryJobId] = useState<number | null>(null)
  const [gnomadAncestryStatus, setGnomadAncestryStatus] = useState<string | null>(null)

  const headers = useMemo(() => ({ 'Content-Type': 'application/json' }), [])
  // Wrap fetch to always send HttpOnly auth cookie
  const authFetch = useCallback((url: string, init?: RequestInit) =>
    fetch(url, { ...init, credentials: 'include' }), []
  )

  const fetchUsers = useCallback(async () => {
    try {
      const res = await authFetch(`${API}/users`, { headers })
      if (!res.ok) throw new Error('Failed to load users')
      setUsers(await res.json())
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    }
  }, [headers])

  useEffect(() => {
    Promise.all([fetchUsers(), fetchRegistryCategories()]).finally(() => setLoading(false))
  }, [fetchUsers])

  useEffect(() => {
    if (selectedRegistryCategory) fetchRegistryMappings(selectedRegistryCategory)
  }, [selectedRegistryCategory])

  // --- Registry fetch ---
  const fetchRegistryCategories = useCallback(async () => {
    try {
      const res = await authFetch(`${API}/variant-mappings/categories`, { headers })
      if (!res.ok) return
      setRegistryCategories(await res.json())
    } catch { /* ignore */ }
  }, [headers])

  const fetchRegistryMappings = useCallback(async (cat: string) => {
    try {
      const url = `${API}/variant-mappings/${encodeURIComponent(cat)}`
      const res = await authFetch(url, { headers })
      if (!res.ok) return
      setRegistryMappings(await res.json())
    } catch { /* ignore */ }
  }, [headers])

  // --- Registry actions ---
  const addMapping = async () => {
    const cat = newMapping.category || selectedRegistryCategory
    if (!cat || !newMapping.key) return
    try {
      const data = JSON.parse(newMapping.data)
      const res = await authFetch(`${API}/variant-mappings`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ category: cat, map_type: newMapping.map_type, key: newMapping.key, data }),
      })
      if (res.ok) {
        setShowAddMapping(false)
        setNewMapping({ category: '', map_type: 'rsid', key: '', data: '{}' })
        fetchRegistryCategories()
        if (selectedRegistryCategory === cat) fetchRegistryMappings(cat)
      }
    } catch { /* invalid JSON */ }
  }

  const updateMapping = async (mapping: VariantMapping) => {
    try {
      const data = JSON.parse(editingDataStr)
      const res = await authFetch(`${API}/variant-mappings/${mapping.id}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify({ key: mapping.key, data, is_active: mapping.is_active }),
      })
      if (res.ok) {
        const updated = await res.json()
        setRegistryMappings(prev => prev.map(m => m.id === mapping.id ? updated : m))
        setEditingMapping(null)
      }
    } catch { /* invalid JSON */ }
  }

  const deleteMapping = async (id: number) => {
    const res = await authFetch(`${API}/variant-mappings/${id}`, { method: 'DELETE', headers })
    if (res.ok) {
      setRegistryMappings(prev => prev.filter(m => m.id !== id))
      setShowDeleteMapping(null)
      fetchRegistryCategories()
    }
  }

  const toggleMappingActive = async (mapping: VariantMapping) => {
    const res = await authFetch(`${API}/variant-mappings/${mapping.id}`, {
      method: 'PUT',
      headers,
      body: JSON.stringify({ is_active: !mapping.is_active }),
    })
    if (res.ok) {
      const updated = await res.json()
      setRegistryMappings(prev => prev.map(m => m.id === mapping.id ? updated : m))
      fetchRegistryCategories()
    }
  }

  // --- User actions ---
  const toggleUserFlag = async (userId: number, field: 'is_active' | 'is_admin' | 'is_verified', value: boolean) => {
    const res = await authFetch(`${API}/users/${userId}`, {
      method: 'PUT',
      headers,
      body: JSON.stringify({ [field]: value }),
    })
    if (res.ok) {
      const updated = await res.json()
      setUsers(prev => prev.map(u => u.id === userId ? updated : u))
    }
  }

  const deleteUser = async (userId: number) => {
    const res = await authFetch(`${API}/users/${userId}`, { method: 'DELETE', headers })
    if (res.ok) {
      setUsers(prev => prev.filter(u => u.id !== userId))
      setShowDeleteUser(null)
    }
  }

  // --- Discoveries ---
  const fetchDiscoverySummary = useCallback(async () => {
    try {
      const res = await authFetch(`${API}/discoveries/summary`, { headers })
      if (res.ok) setDiscoverySummary(await res.json())
    } catch { /* ignore */ }
  }, [headers])

  const fetchDiscoveries = useCallback(async () => {
    try {
      const params = new URLSearchParams()
      if (discoveryStatusFilter !== 'all') params.set('status_filter', discoveryStatusFilter)
      if (discoveryTypeFilter !== 'all') params.set('discovery_type', discoveryTypeFilter)
      const res = await authFetch(`${API}/discoveries?${params}`, { headers })
      if (res.ok) setDiscoveries(await res.json())
    } catch { /* ignore */ }
  }, [headers, discoveryStatusFilter, discoveryTypeFilter])

  useEffect(() => { fetchDiscoverySummary() }, [fetchDiscoverySummary])
  useEffect(() => { fetchDiscoveries() }, [fetchDiscoveries])

  const reviewDiscovery = async (id: number, action: 'approve' | 'reject', reason?: string) => {
    setReviewingId(id)
    try {
      const res = await authFetch(`${API}/discoveries/${id}/review`, {
        method: 'POST', headers,
        body: JSON.stringify({ action, rejection_reason: reason }),
      })
      // Always refresh — even on conflict the backend may have updated the discovery status
      fetchDiscoveries()
      fetchDiscoverySummary()
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Review failed' }))
        setError(err.detail || `Review failed (${res.status})`)
      }
    } catch { /* ignore */ }
    setReviewingId(null)
    setShowRejectDialog(null)
    setRejectReason('')
  }

  const bulkReviewDiscoveries = async (action: 'approve' | 'reject') => {
    const ids = discoveries.filter(d => d.status === 'pending').map(d => d.id)
    if (!ids.length) return
    try {
      const res = await authFetch(`${API}/discoveries/bulk-review?${ids.map(id => `discovery_ids=${id}`).join('&')}`, {
        method: 'POST', headers,
        body: JSON.stringify({ action }),
      })
      if (res.ok) {
        fetchDiscoveries()
        fetchDiscoverySummary()
      }
    } catch { /* ignore */ }
  }

  // --- Incomplete Annotations ---
  const fetchIncompleteSummary = useCallback(async () => {
    try {
      const res = await authFetch(`${API}/annotations/incomplete/summary`, { headers })
      if (res.ok) setIncompleteSummary(await res.json())
    } catch { /* ignore */ }
  }, [headers])

  const fetchIncompleteAnnotations = useCallback(async () => {
    try {
      const res = await authFetch(`${API}/annotations/incomplete?status_filter=${incompleteFilter}&limit=${INCOMPLETE_PAGE_SIZE}&offset=${incompletePage * INCOMPLETE_PAGE_SIZE}`, { headers })
      if (res.ok) {
        const data = await res.json()
        setIncompleteAnnotations(data.items)
        setIncompleteTotalCount(data.total_count)
      }
    } catch { /* ignore */ }
  }, [headers, incompleteFilter, incompletePage])

  useEffect(() => { fetchIncompleteSummary() }, [fetchIncompleteSummary])
  useEffect(() => { fetchIncompleteAnnotations() }, [fetchIncompleteAnnotations])

  const retriggerAnnotation = async (id: number) => {
    setRetriggeringIds(prev => new Set(prev).add(id))
    setRetriggerFeedback(null)
    try {
      const res = await authFetch(`${API}/annotations/retrigger/${id}`, { method: 'POST', headers })
      if (res.ok) {
        const data = await res.json()
        const noData = data.confirmed_no_data || []
        const updated = data.updated_sources || []
        const failed = data.still_failed || []
        if (updated.length > 0) {
          setRetriggerFeedback({ id, message: `Updated: ${updated.join(', ')}${noData.length ? `. No data available: ${noData.join(', ')}` : ''}`, type: 'success' })
        } else if (noData.length > 0 && failed.length === 0) {
          setRetriggerFeedback({ id, message: `Providers confirmed no data exists for: ${noData.join(', ')}. Marked complete.`, type: 'info' })
        } else if (failed.length > 0) {
          setRetriggerFeedback({ id, message: `Still failing: ${failed.join(', ')}${noData.length ? `. No data: ${noData.join(', ')}` : ''}`, type: 'error' })
        }
        await fetchIncompleteAnnotations()
        await fetchIncompleteSummary()
      }
    } catch { /* ignore */ }
    setRetriggeringIds(prev => { const s = new Set(prev); s.delete(id); return s })
    setTimeout(() => setRetriggerFeedback(prev => prev?.id === id ? null : prev), 8000)
  }

  const retriggerAllIncomplete = async () => {
    setBulkRetriggering(true)
    try {
      const res = await authFetch(`${API}/annotations/retrigger-bulk?retrigger_all=true&limit=50`, {
        method: 'POST', headers, body: JSON.stringify([]),
      })
      if (res.ok) {
        await fetchIncompleteAnnotations()
        await fetchIncompleteSummary()
      }
    } catch { /* ignore */ }
    setBulkRetriggering(false)
  }

  // --- Jobs Management ---
  const fetchJobsSummary = useCallback(async () => {
    try {
      const res = await authFetch(`${API}/jobs/summary`, { headers })
      if (res.ok) setJobsSummary(await res.json())
    } catch { /* ignore */ }
  }, [headers])

  const fetchJobs = useCallback(async () => {
    try {
      const url = jobsStatusFilter === 'all' ? `${API}/jobs` : `${API}/jobs?status=${jobsStatusFilter}`
      const res = await authFetch(url, { headers })
      if (res.ok) setJobs(await res.json())
    } catch { /* ignore */ }
  }, [headers, jobsStatusFilter])

  useEffect(() => { fetchJobsSummary() }, [fetchJobsSummary])
  useEffect(() => { fetchJobs() }, [fetchJobs])

  const fetchWorkerJobs = useCallback(async () => {
    try {
      const res = await authFetch(`${API}/worker-jobs`, { headers })
      if (res.ok) setWorkerJobs(await res.json())
    } catch { /* ignore */ }
  }, [headers])

  useEffect(() => { fetchWorkerJobs() }, [fetchWorkerJobs])

  // Auto-refresh jobs when any are processing
  const jobsRefreshRef = useRef<ReturnType<typeof setInterval> | null>(null)
  useEffect(() => {
    const hasActive = jobs.some(j => j.analysis_status === 'processing' || j.analysis_status === 'pending')
    if (hasActive) {
      jobsRefreshRef.current = setInterval(() => { fetchJobs(); fetchJobsSummary() }, 15000)
    }
    return () => { if (jobsRefreshRef.current) clearInterval(jobsRefreshRef.current) }
  }, [jobs, fetchJobs, fetchJobsSummary])

  // Auto-refresh worker jobs when any are active
  const workerJobsRefreshRef = useRef<ReturnType<typeof setInterval> | null>(null)
  useEffect(() => {
    const hasActive = workerJobs.some(j => j.status === 'processing' || j.status === 'pending')
    if (hasActive) {
      workerJobsRefreshRef.current = setInterval(() => fetchWorkerJobs(), 5000)
    }
    return () => { if (workerJobsRefreshRef.current) clearInterval(workerJobsRefreshRef.current) }
  }, [workerJobs, fetchWorkerJobs])

  const cancelJob = async (id: number) => {
    setJobActionLoading(id)
    try {
      const res = await authFetch(`${API}/jobs/${id}/cancel`, { method: 'POST', headers })
      if (res.ok) { fetchJobs(); fetchJobsSummary() }
    } catch { /* ignore */ }
    setJobActionLoading(null)
  }

  const restartJob = async (id: number) => {
    setJobActionLoading(id)
    try {
      const res = await authFetch(`${API}/jobs/${id}/restart`, { method: 'POST', headers })
      if (res.ok) { fetchJobs(); fetchJobsSummary() }
    } catch { /* ignore */ }
    setJobActionLoading(null)
  }

  const regenInsights = async (id: number) => {
    setJobActionLoading(id)
    try {
      const res = await authFetch(`${API}/jobs/${id}/regenerate-insights`, { method: 'POST', headers })
      if (res.ok) { fetchJobs(); fetchJobsSummary() }
    } catch { /* ignore */ }
    setJobActionLoading(null)
  }

  const pauseJob = async (id: number) => {
    setJobActionLoading(id)
    try {
      const res = await authFetch(`${API}/jobs/${id}/pause`, { method: 'POST', headers })
      if (res.ok) { fetchJobs(); fetchJobsSummary() }
    } catch { /* ignore */ }
    setJobActionLoading(null)
  }

  const resumeJob = async (id: number) => {
    setJobActionLoading(id)
    try {
      const res = await authFetch(`${API}/jobs/${id}/resume`, { method: 'POST', headers })
      if (res.ok) { fetchJobs(); fetchJobsSummary() }
    } catch { /* ignore */ }
    setJobActionLoading(null)
  }

  const deleteJob = async (id: number) => {
    setDeleteConfirmJobId(null)
    setJobActionLoading(id)
    try {
      const res = await authFetch(`${API}/jobs/${id}`, { method: 'DELETE', headers })
      if (res.ok) { fetchJobs(); fetchJobsSummary() }
    } catch { /* ignore */ }
    setJobActionLoading(null)
  }

  const fetchJobLogs = useCallback(async (id: number) => {
    try {
      const res = await authFetch(`${API}/jobs/${id}/logs`, { headers })
      if (res.ok) {
        const data = await res.json()
        setJobLogs(data.logs || [])
      }
    } catch { /* ignore */ }
  }, [headers])

  const openLogs = async (id: number) => {
    setViewingLogs(id)
    setJobLogs([])
    setLogsLoading(true)
    await fetchJobLogs(id)
    setLogsLoading(false)
  }

  // Auto-refresh logs when viewing an active job
  useEffect(() => {
    if (viewingLogs == null) return
    const job = jobs.find(j => j.id === viewingLogs)
    const isActive = job?.analysis_status === 'processing' || job?.analysis_status === 'pending'
    if (isActive) {
      logsRefreshRef.current = setInterval(() => fetchJobLogs(viewingLogs), 8000)
    }
    return () => { if (logsRefreshRef.current) { clearInterval(logsRefreshRef.current); logsRefreshRef.current = null } }
  }, [viewingLogs, jobs, fetchJobLogs])

  // Auto-scroll logs to bottom
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [jobLogs])

  // --- Annotation Sources ---
  const fetchAnnotationSources = useCallback(async () => {
    setSourcesLoading(true)
    try {
      const res = await authFetch(`${API}/annotation-sources`, { headers })
      if (res.ok) setAnnotationSources(await res.json())
    } catch { /* ignore */ }
    setSourcesLoading(false)
  }, [headers])

  useEffect(() => { fetchAnnotationSources() }, [fetchAnnotationSources])

  const toggleSource = async (sourceName: string, enabled: boolean) => {
    setSourceToggling(sourceName)
    try {
      const res = await authFetch(`${API}/annotation-sources/${encodeURIComponent(sourceName)}`, {
        method: 'PUT',
        headers,
        body: JSON.stringify({ is_enabled: enabled }),
      })
      if (res.ok) {
        const updated = await res.json()
        setAnnotationSources(prev => prev.map(s => s.source_name === sourceName ? updated : s))
      }
    } catch { /* ignore */ }
    setSourceToggling(null)
  }

  const backfillSource = async (sourceName: string, limit: number = 5000) => {
    setBackfillingSource(sourceName)
    setBackfillFeedback(null)
    try {
      const res = await authFetch(`${API}/annotation-sources/${encodeURIComponent(sourceName)}/backfill?limit=${limit}`, {
        method: 'POST',
        headers,
      })
      if (res.ok) {
        const data = await res.json()
        setBackfillFeedback({ source: sourceName, message: data.detail, type: 'success' })
        await fetchAnnotationSources()
      } else {
        const err = await res.json().catch(() => ({ detail: 'Backfill failed' }))
        setBackfillFeedback({ source: sourceName, message: err.detail, type: 'error' })
      }
    } catch {
      setBackfillFeedback({ source: sourceName, message: 'Network error during backfill', type: 'error' })
    }
    setBackfillingSource(null)
    setTimeout(() => setBackfillFeedback(prev => prev?.source === sourceName ? null : prev), 10000)
  }

  // AI Insights
  const fetchInsightsStatus = useCallback(async () => {
    try {
      const res = await authFetch(apiUrl('/api/insights/status'), { headers })
      if (res.ok) setInsightsStatus(await res.json())
    } catch { /* ignore */ }
  }, [headers])

  useEffect(() => { fetchInsightsStatus() }, [fetchInsightsStatus])

  const toggleInsights = async (enabled: boolean) => {
    setInsightsToggling(true)
    try {
      const res = await authFetch(apiUrl(`/api/insights/toggle?enabled=${enabled}`), {
        method: 'POST',
        headers,
      })
      if (res.ok) setInsightsStatus(await res.json())
    } catch { /* ignore */ }
    setInsightsToggling(false)
  }

  // --- ETL Management ---
  const ETL_SOURCES = [
    {
      key: 'clinvar', label: 'ClinVar',
      statusEndpoint: '/clinvar-etl/status', importEndpoint: '/clinvar-etl/import',
      description: 'Clinical variant database (VCF → PostgreSQL)',
      displayConfig: {
        primaryKey: 'clinvar_variants',
        countKeys: ['clinvar_gene_conditions', 'clinvar_gene_stats'] as string[],
        fileKeys: ['tsv_file_exists', 'vcf_file_exists'] as string[],
        arrayKeys: [] as string[],
      },
    },
    {
      key: 'gnomad', label: 'gnomAD',
      statusEndpoint: '/gnomad-etl/status', importEndpoint: '/gnomad-etl/import',
      description: 'Genome aggregation database (TSV → PostgreSQL)',
      displayConfig: {
        primaryKey: 'gnomad_variants',
        countKeys: ['gnomad_gene_constraints'] as string[],
        fileKeys: [] as string[],
        arrayKeys: ['variant_files'] as string[],
      },
    },
    {
      key: '1kg', label: '1000 Genomes',
      statusEndpoint: '/1kg-etl/status', importEndpoint: '/1kg-etl/import',
      description: 'Phase 3 population frequencies (VCF → PostgreSQL)',
      displayConfig: {
        primaryKey: 'thousand_genomes_variants',
        countKeys: [] as string[],
        fileKeys: [] as string[],
        arrayKeys: [] as string[],
      },
    },
    {
      key: 'vep', label: 'Ensembl VEP',
      statusEndpoint: '/ensembl-vep-etl/status', importEndpoint: '/ensembl-vep-etl/import',
      description: 'Variant Effect Predictor annotations (VCF → PostgreSQL)',
      displayConfig: {
        primaryKey: 'variant_count',
        countKeys: [] as string[],
        fileKeys: ['loaded'] as string[],
        arrayKeys: ['available_vcf_files'] as string[],
      },
    },
    {
      key: 'ensembl', label: 'Ensembl Genes',
      statusEndpoint: '/ensembl-etl/status', importEndpoint: '/ensembl-etl/import',
      description: 'Gene models from cDNA/ncRNA FASTA headers',
      displayConfig: {
        primaryKey: 'ensembl_genes',
        countKeys: ['protein_coding_genes', 'chromosomes'] as string[],
        fileKeys: ['cdna_file_exists', 'ncrna_file_exists'] as string[],
        arrayKeys: [] as string[],
      },
    },
    {
      key: 'gnomad_v2', label: 'gnomAD v2 Exome',
      statusEndpoint: '/gnomad-v2-etl/status', importEndpoint: '/gnomad-v2-etl/import',
      description: 'v2.1.1 exome population AFs — GRCh37 (VCF → PostgreSQL)',
      displayConfig: {
        primaryKey: 'gnomad_v2_variants',
        countKeys: ['with_rsid'] as string[],
        fileKeys: [] as string[],
        arrayKeys: ['vcf_files'] as string[],
      },
    },
    {
      key: 'alphafold', label: 'AlphaFold',
      statusEndpoint: '/alphafold-etl/status', importEndpoint: '/alphafold-etl/import',
      description: 'Protein structure confidence (EBI tar → SQLite)',
      displayConfig: {
        primaryKey: 'alphafold_proteins',
        countKeys: [] as string[],
        fileKeys: ['loaded', 'db_exists'] as string[],
        arrayKeys: [] as string[],
      },
    },
  ]

  const fetchEtlStatus = useCallback(async (key: string, endpoint: string) => {
    setEtlLoading(prev => ({ ...prev, [key]: true }))
    try {
      const res = await authFetch(`${API}${endpoint}`, { headers })
      if (res.ok) {
        const data = await res.json()
        setEtlStatuses(prev => ({ ...prev, [key]: data }))
      }
    } catch { /* ignore */ }
    setEtlLoading(prev => ({ ...prev, [key]: false }))
  }, [headers])

  const startEtlProgressPolling = useCallback(() => {
    if (etlPollRef.current) clearInterval(etlPollRef.current)
    etlPollRef.current = setInterval(async () => {
      try {
        const res = await authFetch(`${API}/clinvar-etl/progress`, { headers })
        if (res.ok) {
          const data = await res.json()
          setEtlProgress(data)
          if (!data.running) {
            clearInterval(etlPollRef.current!)
            etlPollRef.current = null
            setEtlRunning(prev => ({ ...prev, clinvar: false }))
            if (data.step === 'complete') {
              setEtlFeedback({ source: 'clinvar', message: `Import complete in ${data.total_elapsed}s`, type: 'success' })
              const src = ETL_SOURCES.find(s => s.key === 'clinvar')
              if (src?.statusEndpoint) fetchEtlStatus('clinvar', src.statusEndpoint)
            } else if (data.step === 'error') {
              setEtlFeedback({ source: 'clinvar', message: data.error || 'Import failed', type: 'error' })
            }
            setTimeout(() => setEtlFeedback(prev => prev?.source === 'clinvar' ? null : prev), 15000)
          }
        }
      } catch { /* ignore */ }
    }, 2000)
  }, [authFetch, headers, fetchEtlStatus])

  const runEtlImport = async (key: string, endpoint: string) => {
    setEtlRunning(prev => ({ ...prev, [key]: true }))
    setEtlFeedback(null)

    // ClinVar uses fire-and-forget + progress polling
    if (key === 'clinvar') {
      try {
        const res = await authFetch(`${API}${endpoint}`, { method: 'POST', headers })
        const data = await res.json()
        if (data.status === 'already_running') {
          setEtlFeedback({ source: key, message: 'Import already running', type: 'error' })
          setEtlRunning(prev => ({ ...prev, [key]: false }))
          return
        }
        // started — begin polling
        startEtlProgressPolling()
      } catch {
        setEtlFeedback({ source: key, message: 'Network error starting import', type: 'error' })
        setEtlRunning(prev => ({ ...prev, [key]: false }))
      }
      return
    }

    // Other ETL sources: dispatched to worker, returns immediately with job_id
    try {
      const res = await authFetch(`${API}${endpoint}`, { method: 'POST', headers })
      if (res.ok) {
        const data = await res.json()
        const msg = data.detail || JSON.stringify(data)
        setEtlFeedback({ source: key, message: msg, type: 'success' })
        // Refresh status after queuing
        const src = ETL_SOURCES.find(s => s.key === key)
        if (src?.statusEndpoint) fetchEtlStatus(key, src.statusEndpoint)
      } else {
        const err = await res.json().catch(() => ({ detail: 'Import failed' }))
        setEtlFeedback({ source: key, message: err.detail, type: 'error' })
      }
    } catch {
      setEtlFeedback({ source: key, message: 'Network error during import', type: 'error' })
    }
    setEtlRunning(prev => ({ ...prev, [key]: false }))
    setTimeout(() => setEtlFeedback(prev => prev?.source === key ? null : prev), 30000)
  }

  // On mount: check if ClinVar ETL is already running and resume polling
  useEffect(() => {
    authFetch(`${API}/clinvar-etl/progress`, { headers })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.running) {
          setEtlProgress(data)
          setEtlRunning(prev => ({ ...prev, clinvar: true }))
          startEtlProgressPolling()
        }
      })
      .catch(() => { /* ignore */ })
    return () => { if (etlPollRef.current) clearInterval(etlPollRef.current) }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch all ETL statuses on mount
  useEffect(() => {
    ETL_SOURCES.forEach(src => {
      if (src.statusEndpoint) fetchEtlStatus(src.key, src.statusEndpoint)
    })
  }, [fetchEtlStatus])

  // --- BigQuery ---
  const fetchBqStatus = useCallback(async () => {
    setBqLoading(true)
    try {
      const res = await authFetch(`${API}/gnomad-bigquery/status`, { headers })
      if (res.ok) setBqStatus(await res.json())
    } catch { /* ignore */ }
    setBqLoading(false)
  }, [headers])

  useEffect(() => { fetchBqStatus() }, [fetchBqStatus])

  const runBqBackfill = async () => {
    setBqRunning(true)
    setBqFeedback(null)
    try {
      const params = new URLSearchParams({
        batch_size: bqBatchSize,
        max_variants: bqMaxVariants,
      })
      if (bqChromosome) params.set('chromosome', bqChromosome)
      const res = await authFetch(`${API}/gnomad-bigquery/backfill?${params}`, { method: 'POST', headers })
      if (res.ok) {
        const data = await res.json()
        setBqFeedback({ message: data.detail || JSON.stringify(data), type: 'success' })
        fetchBqStatus()
      } else {
        const err = await res.json().catch(() => ({ detail: 'Backfill failed' }))
        setBqFeedback({ message: err.detail, type: 'error' })
      }
    } catch {
      setBqFeedback({ message: 'Network error during BigQuery backfill', type: 'error' })
    }
    setBqRunning(false)
    setTimeout(() => setBqFeedback(null), 15000)
  }

  // --- Category Rules ---
  const fetchCategoryRules = useCallback(async () => {
    setRulesLoading(true)
    try {
      const url = rulesCategoryFilter === 'all'
        ? `${API}/category-rules`
        : `${API}/category-rules?category=${encodeURIComponent(rulesCategoryFilter)}`
      const res = await authFetch(url, { headers })
      if (res.ok) setCategoryRules(await res.json())
    } catch { /* ignore */ }
    setRulesLoading(false)
  }, [headers, rulesCategoryFilter])

  useEffect(() => { fetchCategoryRules() }, [fetchCategoryRules])

  const addCategoryRule = async () => {
    if (!newRule.category || !newRule.rule_value) return
    try {
      const res = await authFetch(`${API}/category-rules`, {
        method: 'POST', headers,
        body: JSON.stringify({
          category: newRule.category,
          rule_type: newRule.rule_type,
          rule_value: newRule.rule_value,
          priority: parseInt(newRule.priority) || 50,
        }),
      })
      if (res.ok) {
        setShowAddRule(false)
        setNewRule({ category: '', rule_type: 'gene_symbol', rule_value: '', priority: '50' })
        fetchCategoryRules()
        setRulesFeedback({ message: 'Rule created', type: 'success' })
      } else {
        const err = await res.json().catch(() => ({ detail: 'Failed' }))
        setRulesFeedback({ message: err.detail, type: 'error' })
      }
    } catch { /* ignore */ }
    setTimeout(() => setRulesFeedback(null), 5000)
  }

  const updateCategoryRulePriority = async (ruleId: number) => {
    try {
      const res = await authFetch(`${API}/category-rules/${ruleId}`, {
        method: 'PUT', headers,
        body: JSON.stringify({ priority: parseInt(editingRulePriority) || 50 }),
      })
      if (res.ok) {
        setEditingRule(null)
        fetchCategoryRules()
      }
    } catch { /* ignore */ }
  }

  const toggleCategoryRuleActive = async (ruleId: number, isActive: boolean) => {
    try {
      const res = await authFetch(`${API}/category-rules/${ruleId}`, {
        method: 'PUT', headers,
        body: JSON.stringify({ is_active: !isActive }),
      })
      if (res.ok) fetchCategoryRules()
    } catch { /* ignore */ }
  }

  const deleteCategoryRule = async (ruleId: number) => {
    try {
      const res = await authFetch(`${API}/category-rules/${ruleId}`, { method: 'DELETE', headers })
      if (res.ok) {
        setDeleteRuleId(null)
        fetchCategoryRules()
        setRulesFeedback({ message: 'Rule deleted', type: 'success' })
      }
    } catch { /* ignore */ }
    setTimeout(() => setRulesFeedback(null), 5000)
  }

  const seedCategoryRules = async (force: boolean = false) => {
    setSeedingRules(true)
    try {
      const res = await authFetch(`${API}/category-rules/seed?force=${force}`, { method: 'POST', headers })
      if (res.ok) {
        const data = await res.json()
        setRulesFeedback({ message: data.detail || JSON.stringify(data), type: 'success' })
        fetchCategoryRules()
      } else {
        const err = await res.json().catch(() => ({ detail: 'Seed failed' }))
        setRulesFeedback({ message: err.detail, type: 'error' })
      }
    } catch { /* ignore */ }
    setSeedingRules(false)
    setTimeout(() => setRulesFeedback(null), 8000)
  }

  // --- Utility actions ---
  const runAutoCategorize = async () => {
    setAutoCategorizing(true)
    setAutoCatStatus('Queuing job…')
    setUtilityFeedback(null)
    try {
      const res = await authFetch(`${API}/auto-categorize`, { method: 'POST', headers })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Failed to queue job' }))
        setUtilityFeedback({ message: err.detail, type: 'error' })
        setAutoCategorizing(false)
        setAutoCatStatus(null)
        return
      }
      const { job_id } = await res.json()
      setAutoCatStatus(`Job #${job_id} running…`)
      // Poll until complete
      const startTime = Date.now()
      while (true) {
        await new Promise(r => setTimeout(r, 3000))
        try {
          const pollRes = await authFetch(`${API}/worker-jobs/${job_id}`, { headers })
          if (!pollRes.ok) break
          const job = await pollRes.json()
          if (job.status === 'completed') {
            const r = job.result || {}
            const total = r.total_new_mappings ?? 0
            const elapsed = r.total_elapsed_s != null ? ` in ${r.total_elapsed_s}s` : ''
            setUtilityFeedback({ message: `Auto-categorize complete: ${total} new mappings${elapsed}`, type: 'success' })
            fetchWorkerJobs()
            break
          } else if (job.status === 'failed') {
            setUtilityFeedback({ message: `Auto-categorize failed: ${job.error || 'Unknown error'}`, type: 'error' })
            break
          }
          const elapsed = Math.round((Date.now() - startTime) / 1000)
          setAutoCatStatus(`Job #${job_id} running… (${elapsed}s)`)
        } catch { break }
      }
    } catch { setUtilityFeedback({ message: 'Network error', type: 'error' }) }
    setAutoCategorizing(false)
    setAutoCatStatus(null)
    setTimeout(() => setUtilityFeedback(null), 15000)
  }

  const runEnrichMappings = async (dryRun: boolean = false) => {
    setEnrichingMappings(dryRun ? 'dry_run' : 'apply')
    setUtilityFeedback(null)
    try {
      const params = new URLSearchParams()
      if (dryRun) params.set('dry_run', 'true')
      if (enrichReviseAll) params.set('revise_all', 'true')
      const res = await authFetch(`${API}/enrich-mappings?${params}`, { method: 'POST', headers })
      if (res.ok) {
        const data = await res.json()
        const breakdown = Object.entries(data.by_source || {})
          .filter(([, n]) => (n as number) > 0)
          .map(([src, n]) => `${src}: ${n}`)
          .join(', ')
        const detail = breakdown ? ` (${breakdown})` : ''
        const msg = dryRun
          ? `[Dry run] Would update ${data.total_updated} of ${data.total_checked} checked mappings${detail}`
          : `Enriched ${data.total_updated} of ${data.total_checked} mappings${detail}`
        setUtilityFeedback({ message: msg, type: 'success' })
      } else {
        const err = await res.json().catch(() => ({ detail: 'Failed' }))
        setUtilityFeedback({ message: err.detail, type: 'error' })
      }
    } catch { setUtilityFeedback({ message: 'Network error', type: 'error' }) }
    setEnrichingMappings(null)
    setTimeout(() => setUtilityFeedback(null), 15000)
  }

  const runPurgeDeleted = async () => {
    setPurgingDeleted(true)
    setUtilityFeedback(null)
    try {
      const days = parseInt(purgeOlderThanDays)
      const res = await authFetch(`${API}/purge-deleted?older_than_days=${isNaN(days) ? 0 : days}`, {
        method: 'POST', headers,
      })
      if (res.ok) {
        const data = await res.json()
        setUtilityFeedback({ message: data.detail, type: 'success' })
        fetchJobs()
        fetchJobsSummary()
      } else {
        const err = await res.json().catch(() => ({ detail: 'Purge failed' }))
        setUtilityFeedback({ message: err.detail, type: 'error' })
      }
    } catch { setUtilityFeedback({ message: 'Network error', type: 'error' }) }
    setPurgingDeleted(false)
    setTimeout(() => setUtilityFeedback(null), 10000)
  }

  const pollWorkerJob = async (
    jobId: number,
    onStatus: (msg: string) => void,
    onComplete: (result: Record<string, unknown>) => void,
    onError: (msg: string) => void,
  ) => {
    const startTime = Date.now()
    while (true) {
      await new Promise(r => setTimeout(r, 4000))
      try {
        const pollRes = await authFetch(`${API}/worker-jobs/${jobId}`, { headers })
        if (!pollRes.ok) break
        const job = await pollRes.json()
        if (job.status === 'completed') { onComplete(job.result || {}); fetchWorkerJobs(); return }
        if (job.status === 'failed') { onError(job.error || 'Unknown error'); return }
        const elapsed = Math.round((Date.now() - startTime) / 1000)
        onStatus(`Job #${jobId} running… (${elapsed}s)`)
      } catch { break }
    }
    onError('Polling failed')
  }

  const runBuildCaddCache = async () => {
    if (gnomadCacheJobId) return
    setGnomadCacheStatus('Queuing…')
    setUtilityFeedback(null)
    try {
      const res = await authFetch(`${API}/gnomad/build-cadd-cache`, { method: 'POST', headers })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Failed' }))
        setUtilityFeedback({ message: err.detail, type: 'error' })
        setGnomadCacheStatus(null)
        return
      }
      const { job_id } = await res.json()
      setGnomadCacheJobId(job_id)
      await pollWorkerJob(
        job_id,
        msg => setGnomadCacheStatus(msg),
        result => {
          const n = result.variant_count as number ?? 0
          const s = result.elapsed_s as number ?? 0
          setUtilityFeedback({ message: `CADD cache built: ${n.toLocaleString()} variants cached in ${s}s`, type: 'success' })
          setGnomadCacheJobId(null)
          setGnomadCacheStatus(null)
        },
        err => {
          setUtilityFeedback({ message: `CADD cache build failed: ${err}`, type: 'error' })
          setGnomadCacheJobId(null)
          setGnomadCacheStatus(null)
        },
      )
    } catch { setUtilityFeedback({ message: 'Network error', type: 'error' }); setGnomadCacheStatus(null) }
    setTimeout(() => setUtilityFeedback(null), 20000)
  }

  const runRefreshAncestryAfs = async (indexFirst: boolean = false) => {
    if (gnomadAncestryJobId) return
    setGnomadAncestryStatus('Queuing…')
    setUtilityFeedback(null)
    try {
      const res = await authFetch(`${API}/gnomad/refresh-ancestry-afs?index_first=${indexFirst}`, { method: 'POST', headers })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Failed' }))
        setUtilityFeedback({ message: err.detail, type: 'error' })
        setGnomadAncestryStatus(null)
        return
      }
      const { job_id } = await res.json()
      setGnomadAncestryJobId(job_id)
      await pollWorkerJob(
        job_id,
        msg => setGnomadAncestryStatus(msg),
        result => {
          const updated = result.updated as number ?? 0
          const total = result.total as number ?? 0
          const s = result.elapsed_s as number ?? 0
          setUtilityFeedback({ message: `Ancestry AFs refreshed: ${updated}/${total} AIMs updated in ${s}s`, type: 'success' })
          setGnomadAncestryJobId(null)
          setGnomadAncestryStatus(null)
        },
        err => {
          setUtilityFeedback({ message: `Ancestry AF refresh failed: ${err}`, type: 'error' })
          setGnomadAncestryJobId(null)
          setGnomadAncestryStatus(null)
        },
      )
    } catch { setUtilityFeedback({ message: 'Network error', type: 'error' }); setGnomadAncestryStatus(null) }
    setTimeout(() => setUtilityFeedback(null), 20000)
  }

  const resetSentinels = async (sourceName: string) => {
    setResettingSentinels(sourceName)
    setSentinelFeedback(null)
    try {
      const res = await authFetch(`${API}/annotation-sources/${encodeURIComponent(sourceName)}/reset-sentinels`, {
        method: 'POST', headers,
      })
      if (res.ok) {
        const data = await res.json()
        setSentinelFeedback({ source: sourceName, message: data.detail, type: 'success' })
        await fetchAnnotationSources()
      } else {
        const err = await res.json().catch(() => ({ detail: 'Reset failed' }))
        setSentinelFeedback({ source: sourceName, message: err.detail, type: 'error' })
      }
    } catch {
      setSentinelFeedback({ source: sourceName, message: 'Network error', type: 'error' })
    }
    setResettingSentinels(null)
    setTimeout(() => setSentinelFeedback(prev => prev?.source === sourceName ? null : prev), 10000)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-t-transparent border-blue-500" />
      </div>
    )
  }

  if (error) {
    return (
      <Card className="glass-card">
        <CardContent className="py-10 text-center">
          <Shield className="h-12 w-12 mx-auto mb-4 text-red-400" />
          <p className={`text-lg font-medium text-red-400`}>{error}</p>
          <p className={`text-sm ${theme.text.muted} mt-2`}>
            You may not have admin access.
          </p>
        </CardContent>
      </Card>
    )
  }

  // --- Pagination helper ---
  const renderPagination = (totalItems: number, page: number, setPage: (fn: (p: number) => number) => void) => {
    if (totalItems <= PAGE_SIZE) return null
    const totalPages = Math.ceil(totalItems / PAGE_SIZE)
    return (
      <div className="flex items-center justify-between mt-4 pt-4 border-t">
        <span className="text-sm text-muted-foreground">
          Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, totalItems)} of {totalItems}
        </span>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" disabled={page === 0} onClick={() => setPage(p => p - 1)}>
            Previous
          </Button>
          <span className="text-sm">Page {page + 1} of {totalPages}</span>
          <Button size="sm" variant="outline" disabled={page + 1 >= totalPages} onClick={() => setPage(p => p + 1)}>
            Next
          </Button>
        </div>
      </div>
    )
  }

  // Paginated slices
  const paginatedUsers = users.slice(usersPage * PAGE_SIZE, (usersPage + 1) * PAGE_SIZE)
  const filteredRegistryMappings = registryMappings.filter(m => registryFilter === 'all' || m.map_type === registryFilter)
  const paginatedRegistry = filteredRegistryMappings.slice(registryPage * PAGE_SIZE, (registryPage + 1) * PAGE_SIZE)
  const paginatedDiscoveries = discoveries.slice(discoveriesPage * PAGE_SIZE, (discoveriesPage + 1) * PAGE_SIZE)
  const paginatedJobs = jobs.slice(jobsPage * PAGE_SIZE, (jobsPage + 1) * PAGE_SIZE)
  const paginatedRules = categoryRules.slice(rulesPage * PAGE_SIZE, (rulesPage + 1) * PAGE_SIZE)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-3 bg-gradient-to-br from-violet-500/20 to-fuchsia-500/20 rounded-xl border border-violet-500/30">
          <Shield className="h-7 w-7 text-violet-400" />
        </div>
        <div>
          <h2 className={`text-2xl font-bold ${theme.text.primary}`}>Admin Panel</h2>
          <p className={`text-sm ${theme.text.secondary}`}>Manage users and panel marker configurations</p>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange} className="w-full">
        <TabsList className="flex w-full max-w-5xl">
          <TabsTrigger value="users" className="gap-2">
            <Users className="h-4 w-4" />
            Users
          </TabsTrigger>
          <TabsTrigger value="registry" className="gap-2">
            <Database className="h-4 w-4" />
            Registry
          </TabsTrigger>
          <TabsTrigger value="discoveries" className="gap-2 relative">
            <Lightbulb className="h-4 w-4" />
            Discoveries
            {discoverySummary && discoverySummary.total_pending > 0 && (
              <Badge variant="destructive" className="ml-1 h-5 min-w-[20px] px-1 text-xs">
                {discoverySummary.total_pending}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="data" className="gap-2">
            <HardDrive className="h-4 w-4" />
            Ingestion
          </TabsTrigger>
          <TabsTrigger value="rules" className="gap-2">
            <Scale className="h-4 w-4" />
            Rules
          </TabsTrigger>
          <TabsTrigger value="annotations" className="gap-2 relative" title="Annotation quality monitor — incomplete and failed annotations">
            <AlertTriangle className="h-4 w-4" />
            Incomplete
            {incompleteSummary && (incompleteSummary.partial + incompleteSummary.failed) > 0 && (
              <Badge variant="secondary" className="ml-1 h-5 min-w-[20px] px-1 text-xs">
                {formatCompactNumber(incompleteSummary.partial + incompleteSummary.failed)}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="jobs" className="gap-2 relative">
            <Activity className="h-4 w-4" />
            Jobs
            {jobs.filter(j => j.analysis_status === 'processing' || j.analysis_status === 'pending').length > 0 && (
              <Badge className="ml-1 h-5 min-w-[20px] px-1 text-xs bg-blue-500 text-white">
                {jobs.filter(j => j.analysis_status === 'processing' || j.analysis_status === 'pending').length}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>

        {/* ===== USERS TAB ===== */}
        <TabsContent value="users" className="mt-6">
          <Card className="glass-card">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                User Management
              </CardTitle>
              <CardDescription>{users.length} registered user{users.length !== 1 ? 's' : ''}</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>User</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead className="text-center">Analyses</TableHead>
                    <TableHead className="text-center">Active</TableHead>
                    <TableHead className="text-center">Verified</TableHead>
                    <TableHead className="text-center">Admin</TableHead>
                    <TableHead className="text-center">Joined</TableHead>
                    <TableHead></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {paginatedUsers.map(user => (
                    <TableRow key={user.id}>
                      <TableCell className="font-medium">
                        <div className="flex items-center gap-2">
                          {user.avatar_url ? (
                            <img src={user.avatar_url} alt="" className="w-7 h-7 rounded-full object-cover flex-shrink-0" />
                          ) : (
                            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-teal-500 to-cyan-500 flex items-center justify-center flex-shrink-0">
                              <span className="text-white text-xs font-bold">{(user.full_name || user.username)[0].toUpperCase()}</span>
                            </div>
                          )}
                          {user.full_name || user.username}
                        </div>
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm">{user.email}</TableCell>
                      <TableCell className="text-center">
                        <Badge variant="secondary">{user.analysis_count}</Badge>
                      </TableCell>
                      <TableCell className="text-center">
                        <Switch
                          checked={user.is_active}
                          onCheckedChange={(v) => toggleUserFlag(user.id, 'is_active', v)}
                        />
                      </TableCell>
                      <TableCell className="text-center">
                        <Switch
                          checked={user.is_verified}
                          onCheckedChange={(v) => toggleUserFlag(user.id, 'is_verified', v)}
                        />
                      </TableCell>
                      <TableCell className="text-center">
                        <Switch
                          checked={user.is_admin}
                          onCheckedChange={(v) => toggleUserFlag(user.id, 'is_admin', v)}
                        />
                      </TableCell>
                      <TableCell className="text-center text-sm text-muted-foreground">
                        {new Date(user.created_at).toLocaleDateString()}
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                          onClick={() => setShowDeleteUser(user)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {renderPagination(users.length, usersPage, setUsersPage)}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ===== VARIANT REGISTRY TAB ===== */}
        <TabsContent value="registry" className="mt-6">
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 min-h-[calc(100vh-280px)]">
            {/* Category list */}
            <Card className="lg:col-span-1 glass-card flex flex-col">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Categories</CardTitle>
                <CardDescription>Analysis variant mappings</CardDescription>
              </CardHeader>
              <CardContent className="p-0 flex-1">
                <ScrollArea className="h-full">
                  <div className="space-y-1 px-4 pb-4">
                    {Object.entries(CATEGORY_LABELS).map(([id, label]) => {
                      const cat = registryCategories.find(c => c.category === id)
                      const isSelected = selectedRegistryCategory === id
                      return (
                        <button
                          key={id}
                          onClick={() => { setSelectedRegistryCategory(id); setRegistryFilter('all'); setRegistryPage(0) }}
                          className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-colors ${
                            isSelected ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'
                          }`}
                        >
                          <span className="font-medium truncate">{label}</span>
                          <div className="flex items-center gap-2">
                            {cat && (
                              <Badge variant={isSelected ? 'outline' : 'secondary'} className="text-xs">
                                {cat.total}
                              </Badge>
                            )}
                            <ChevronRight className="h-4 w-4 opacity-50" />
                          </div>
                        </button>
                      )
                    })}
                  </div>
                </ScrollArea>
              </CardContent>
            </Card>

            {/* Mapping details */}
            <Card className="lg:col-span-3 glass-card flex flex-col">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>
                      {selectedRegistryCategory ? (CATEGORY_LABELS[selectedRegistryCategory] || selectedRegistryCategory) : 'Select a Category'}
                    </CardTitle>
                    <CardDescription>
                      {selectedRegistryCategory
                        ? `${filteredRegistryMappings.length} mapping${filteredRegistryMappings.length !== 1 ? 's' : ''}`
                        : 'Choose a category to manage variant-to-condition mappings used by analysis'}
                    </CardDescription>
                  </div>
                  {selectedRegistryCategory && (
                    <div className="flex items-center gap-2">
                      <div className="flex rounded-lg border overflow-hidden">
                        {(['all', 'rsid', 'gene'] as const).map(f => (
                          <button
                            key={f}
                            onClick={() => { setRegistryFilter(f); setRegistryPage(0) }}
                            className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                              registryFilter === f ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'
                            }`}
                          >
                            {f === 'all' ? 'All' : f.toUpperCase()}
                          </button>
                        ))}
                      </div>
                      <Button size="sm" onClick={() => {
                        setNewMapping(prev => ({ ...prev, category: selectedRegistryCategory }))
                        setShowAddMapping(true)
                      }}>
                        <Plus className="h-4 w-4 mr-1" />
                        Add Mapping
                      </Button>
                    </div>
                  )}
                </div>
              </CardHeader>
              {selectedRegistryCategory && (
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-16">Type</TableHead>
                        <TableHead className="w-28">Key</TableHead>
                        <TableHead>Data</TableHead>
                        <TableHead className="text-center w-20">Active</TableHead>
                        <TableHead className="w-20"></TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(() => {
                        if (filteredRegistryMappings.length === 0) return (
                          <TableRow>
                            <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                              No mappings found. Click &quot;Add Mapping&quot; to create one.
                            </TableCell>
                          </TableRow>
                        )
                        return paginatedRegistry.map(mapping => (
                          <TableRow key={mapping.id}>
                            {editingMapping?.id === mapping.id ? (
                              <>
                                <TableCell>
                                  <Badge variant="outline" className="text-xs">{mapping.map_type}</Badge>
                                </TableCell>
                                <TableCell>
                                  <Input
                                    value={editingMapping.key}
                                    onChange={e => setEditingMapping({ ...editingMapping, key: e.target.value })}
                                    className="h-8 w-28 font-mono text-xs"
                                  />
                                </TableCell>
                                <TableCell>
                                  <textarea
                                    value={editingDataStr}
                                    onChange={e => setEditingDataStr(e.target.value)}
                                    className="w-full h-24 rounded-md border bg-background px-3 py-2 text-xs font-mono resize-y"
                                  />
                                </TableCell>
                                <TableCell className="text-center">
                                  <Switch
                                    checked={editingMapping.is_active}
                                    onCheckedChange={v => setEditingMapping({ ...editingMapping, is_active: v })}
                                  />
                                </TableCell>
                                <TableCell>
                                  <div className="flex gap-1">
                                    <Button size="sm" variant="ghost" onClick={() => updateMapping(editingMapping)}>
                                      <Check className="h-4 w-4 text-green-400" />
                                    </Button>
                                    <Button size="sm" variant="ghost" onClick={() => setEditingMapping(null)}>
                                      <X className="h-4 w-4 text-red-400" />
                                    </Button>
                                  </div>
                                </TableCell>
                              </>
                            ) : (
                              <>
                                <TableCell>
                                  <Badge variant={mapping.map_type === 'rsid' ? 'default' : 'secondary'} className="text-xs">
                                    {mapping.map_type}
                                  </Badge>
                                </TableCell>
                                <TableCell className="font-mono text-sm">{mapping.key}</TableCell>
                                <TableCell className="text-xs text-muted-foreground max-w-md">
                                  <pre className="whitespace-pre-wrap break-all">{JSON.stringify(mapping.data, null, 2).slice(0, 200)}{JSON.stringify(mapping.data).length > 200 ? '...' : ''}</pre>
                                </TableCell>
                                <TableCell className="text-center">
                                  <Switch
                                    checked={mapping.is_active}
                                    onCheckedChange={() => toggleMappingActive(mapping)}
                                  />
                                </TableCell>
                                <TableCell>
                                  <div className="flex gap-1">
                                    <Button size="sm" variant="ghost" onClick={() => {
                                      setEditingMapping({ ...mapping })
                                      setEditingDataStr(JSON.stringify(mapping.data, null, 2))
                                    }}>
                                      <Pencil className="h-4 w-4" />
                                    </Button>
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      className="text-red-400 hover:text-red-300"
                                      onClick={() => setShowDeleteMapping(mapping)}
                                    >
                                      <Trash2 className="h-4 w-4" />
                                    </Button>
                                  </div>
                                </TableCell>
                              </>
                            )}
                          </TableRow>
                        ))
                      })()}
                    </TableBody>
                  </Table>
                  {renderPagination(filteredRegistryMappings.length, registryPage, setRegistryPage)}
                </CardContent>
              )}
            </Card>
          </div>
        </TabsContent>

        {/* ===== DISCOVERIES TAB ===== */}
        <TabsContent value="discoveries" className="mt-6">
          <Card className="glass-card">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Lightbulb className="h-5 w-5" />
                    Pending Discoveries
                  </CardTitle>
                  <CardDescription>
                    Auto-discovered markers from user lookups awaiting review
                    {discoverySummary && (
                      <span className="ml-2">
                        — {discoverySummary.total_pending} pending, {discoverySummary.total_approved} approved, {discoverySummary.total_rejected} rejected
                      </span>
                    )}
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    className="text-sm rounded-md border px-2 py-1 bg-background"
                    value={discoveryStatusFilter}
                    onChange={e => { setDiscoveryStatusFilter(e.target.value); setDiscoveriesPage(0) }}
                  >
                    <option value="pending">Pending</option>
                    <option value="approved">Approved</option>
                    <option value="rejected">Rejected</option>
                    <option value="all">All</option>
                  </select>
                  <select
                    className="text-sm rounded-md border px-2 py-1 bg-background"
                    value={discoveryTypeFilter}
                    onChange={e => { setDiscoveryTypeFilter(e.target.value); setDiscoveriesPage(0) }}
                  >
                    <option value="all">All Types</option>
                    <option value="variant_mapping">Variant Mappings</option>
                  </select>
                  {discoveryStatusFilter === 'pending' && discoveries.length > 0 && (
                    <div className="flex gap-1 ml-2">
                      <Button size="sm" variant="default" onClick={() => bulkReviewDiscoveries('approve')}>
                        <Check className="h-3 w-3 mr-1" /> Approve All
                      </Button>
                      <Button size="sm" variant="destructive" onClick={() => bulkReviewDiscoveries('reject')}>
                        <X className="h-3 w-3 mr-1" /> Reject All
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {discoveries.length === 0 ? (
                <p className={`text-center py-8 ${theme.text.tertiary}`}>No discoveries found with current filters</p>
              ) : (
                <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Type</TableHead>
                      <TableHead>Variant</TableHead>
                      <TableHead>Gene</TableHead>
                      <TableHead>Panel / Category</TableHead>
                      <TableHead>Description</TableHead>
                      <TableHead>Lookups</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginatedDiscoveries.map(d => (
                      <TableRow key={d.id}>
                        <TableCell>
                          <Badge variant="secondary">
                            Variant Mapping
                          </Badge>
                        </TableCell>
                        <TableCell
                          className="font-mono text-sm cursor-pointer text-blue-500 hover:text-blue-400 hover:underline"
                          onClick={() => setSelectedDiscoveryRsid({ rsid: d.rsid, gene: d.gene || undefined })}
                        >{d.rsid}</TableCell>
                        <TableCell>{d.gene || '—'}</TableCell>
                        <TableCell>
                          {CATEGORY_LABELS[d.mapping_category || ''] || d.mapping_category}
                          {d.category && <span className={`ml-1 text-xs ${theme.text.tertiary}`}>({d.category})</span>}
                        </TableCell>
                        <TableCell className={`max-w-[200px] truncate text-sm ${theme.text.secondary}`}>
                          {d.description || '—'}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{d.lookup_count}</Badge>
                        </TableCell>
                        <TableCell>
                          <Badge variant={d.status === 'pending' ? 'outline' : d.status === 'approved' ? 'default' : 'destructive'}>
                            {d.status}
                          </Badge>
                          {d.rejection_reason && (
                            <p className={`text-xs mt-1 ${theme.text.tertiary}`}>{d.rejection_reason}</p>
                          )}
                        </TableCell>
                        <TableCell className="text-right">
                          {d.status === 'pending' && (
                            <div className="flex items-center justify-end gap-1">
                              <Button
                                size="sm" variant="default"
                                disabled={reviewingId === d.id}
                                onClick={() => reviewDiscovery(d.id, 'approve')}
                              >
                                {reviewingId === d.id ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
                              </Button>
                              <Button
                                size="sm" variant="destructive"
                                disabled={reviewingId === d.id}
                                onClick={() => setShowRejectDialog(d)}
                              >
                                <X className="h-3 w-3" />
                              </Button>
                            </div>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                {renderPagination(discoveries.length, discoveriesPage, setDiscoveriesPage)}
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ===== INGESTION TAB (API Sources + Local ETL + BigQuery + Maintenance) ===== */}
        <TabsContent value="data" className="mt-6">
          {/* ───── API Sources & AI Insights ───── */}
          <Card className="glass-card">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Zap className="h-5 w-5" />
                    Annotation Sources
                  </CardTitle>
                  <CardDescription>
                    Enable or disable external API sources used during variant annotation.
                    Disabled sources are skipped during analysis — enable them later and use Backfill to populate missing data.
                  </CardDescription>
                </div>
                <Button size="sm" variant="outline" onClick={fetchAnnotationSources} disabled={sourcesLoading}>
                  <RefreshCw className={`h-3 w-3 mr-1 ${sourcesLoading ? 'animate-spin' : ''}`} /> Refresh
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {backfillFeedback && (
                <div className={`mb-4 p-3 rounded-lg flex items-start gap-2 text-sm ${
                  backfillFeedback.type === 'success' ? 'bg-green-500/10 text-green-600 border border-green-500/20'
                    : 'bg-red-500/10 text-red-600 border border-red-500/20'
                }`}>
                  <Info className="h-4 w-4 mt-0.5 shrink-0" />
                  <span>{backfillFeedback.message}</span>
                </div>
              )}
              {sentinelFeedback && (
                <div className={`mb-4 p-3 rounded-lg flex items-start gap-2 text-sm ${
                  sentinelFeedback.type === 'success' ? 'bg-amber-500/10 text-amber-600 border border-amber-500/20'
                    : 'bg-red-500/10 text-red-600 border border-red-500/20'
                }`}>
                  <RotateCcw className="h-4 w-4 mt-0.5 shrink-0" />
                  <span>{sentinelFeedback.message}</span>
                </div>
              )}
              {annotationSources.length === 0 ? (
                <p className={`text-center py-8 ${theme.text.tertiary}`}>
                  {sourcesLoading ? 'Loading sources...' : 'No annotation sources configured'}
                </p>
              ) : (
                <div className="space-y-8">
                  {SOURCE_GROUP_ORDER.map(groupType => {
                    const groupSources = annotationSources.filter(s => (s.source_type || 'api') === groupType)
                    if (groupSources.length === 0) return null
                    const typeConfig = SOURCE_TYPE_CONFIG[groupType]
                    return (
                      <div key={groupType}>
                        <div className="flex items-center gap-3 mb-3">
                          <span className={`text-xs font-semibold uppercase tracking-widest px-2 py-0.5 rounded border ${typeConfig.className}`}>
                            {typeConfig.label}
                          </span>
                          <span className={`text-sm font-medium ${theme.text.secondary}`}>{SOURCE_GROUP_LABELS[groupType]}</span>
                        </div>
                        <div className="space-y-3">
                          {groupSources.map(src => {
                            const total = src.annotated_count + src.missing_count
                            const pct = total > 0 ? Math.round((src.annotated_count / total) * 100) : 0
                            const customLimit = backfillLimits[src.source_name]
                            const effectiveLimit = customLimit ? Math.min(parseInt(customLimit) || src.missing_count, src.missing_count) : src.missing_count
                            return (
                              <div
                                key={src.source_name}
                                className={`rounded-lg border p-4 transition-colors ${
                                  src.is_enabled
                                    ? isDarkMode ? 'border-white/10 bg-white/5' : 'border-gray-200 bg-gray-50'
                                    : isDarkMode ? 'border-white/5 bg-white/[0.02]' : 'border-gray-100 bg-gray-25'
                                }`}
                              >
                                <div className="flex items-center justify-between">
                                  <div className="flex items-center gap-4 flex-1">
                                    <Switch
                                      checked={src.is_enabled}
                                      onCheckedChange={(checked) => toggleSource(src.source_name, checked)}
                                      disabled={sourceToggling === src.source_name}
                                    />
                                    <div className={`flex-1 ${!src.is_enabled ? 'opacity-50' : ''}`}>
                                      <div className="flex items-center gap-2">
                                        <span className={`font-medium ${theme.text.primary}`}>{src.display_name}</span>
                                        {src.rate_limit && (
                                          <Badge variant="outline" className="text-xs">
                                            {src.rate_limit} req/s
                                          </Badge>
                                        )}
                                        <Badge variant={src.is_enabled ? 'default' : 'secondary'} className="text-xs">
                                          {src.is_enabled ? 'Enabled' : 'Disabled'}
                                        </Badge>
                                      </div>
                                      {src.description && (
                                        <p className={`text-sm mt-1 ${theme.text.muted}`}>{src.description}</p>
                                      )}
                                    </div>
                                  </div>
                                  <div className={`flex items-center gap-3 ml-4 ${!src.is_enabled ? 'opacity-50' : ''}`}>
                                    <div className="text-right min-w-[140px]">
                                      <div className="flex items-center gap-2 justify-end">
                                        <span className={`text-sm font-mono ${theme.text.secondary}`}>
                                          {src.annotated_count.toLocaleString()} / {total.toLocaleString()}
                                        </span>
                                        <span className={`text-xs ${theme.text.muted}`}>({pct}%)</span>
                                      </div>
                                      <div className="w-32 h-1.5 rounded-full bg-gray-700/30 mt-1 overflow-hidden">
                                        <div
                                          className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-400 transition-all duration-500"
                                          style={{ width: `${pct}%` }}
                                        />
                                      </div>
                                    </div>
                                    {src.missing_count > 0 && src.is_enabled && (
                                      <div className="flex items-center gap-2">
                                        <Input
                                          type="number"
                                          min={1}
                                          max={src.missing_count}
                                          placeholder={String(src.missing_count)}
                                          value={backfillLimits[src.source_name] ?? ''}
                                          onChange={(e) => setBackfillLimits(prev => ({ ...prev, [src.source_name]: e.target.value }))}
                                          className="w-20 h-8 text-xs text-center"
                                          disabled={backfillingSource === src.source_name}
                                        />
                                        <Button
                                          size="sm"
                                          variant="outline"
                                          disabled={backfillingSource === src.source_name}
                                          onClick={() => backfillSource(src.source_name, effectiveLimit)}
                                          title={`Backfill ${effectiveLimit.toLocaleString()} variants from ${src.display_name}`}
                                        >
                                          {backfillingSource === src.source_name
                                            ? <><RefreshCw className="h-3 w-3 mr-1 animate-spin" /> Backfilling...</>
                                            : <><Download className="h-3 w-3 mr-1" /> Backfill ({effectiveLimit > 999 ? `${Math.round(effectiveLimit / 1000)}k` : effectiveLimit})</>}
                                        </Button>
                                      </div>
                                    )}
                                    {['clinvar_local', 'gnomad', 'alpha_missense', 'ensembl', 'thousand_genomes', 'ensembl_vep'].includes(src.source_name) && (
                                      <Button
                                        size="sm"
                                        variant="outline"
                                        className="ml-2 text-xs text-amber-400 border-amber-500/30 hover:bg-amber-500/10"
                                        disabled={resettingSentinels === src.source_name}
                                        onClick={() => resetSentinels(src.source_name)}
                                        title="Reset 'not found' sentinels so backfill re-checks this source"
                                      >
                                        {resettingSentinels === src.source_name
                                          ? <><RotateCcw className="h-3 w-3 mr-1 animate-spin" /> Resetting...</>
                                          : <><RotateCcw className="h-3 w-3 mr-1" /> Reset Sentinels</>}
                                      </Button>
                                    )}
                                  </div>
                                </div>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* AI Insights Configuration */}
          <Card className="glass-card mt-6">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Sparkles className="h-5 w-5" />
                    AI Insights
                  </CardTitle>
                  <CardDescription>
                    Enable or disable LLM-powered AI insights for all users. Requires an API key (Gemini, OpenAI, or Anthropic).
                  </CardDescription>
                </div>
                <Button size="sm" variant="outline" onClick={fetchInsightsStatus}>
                  <RefreshCw className="h-3 w-3 mr-1" /> Refresh
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {insightsStatus ? (
                <div className="space-y-4">
                  <div className={`rounded-lg border p-4 ${isDarkMode ? 'border-white/10 bg-white/5' : 'border-gray-200 bg-gray-50'}`}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <Switch
                          checked={insightsStatus.enabled}
                          onCheckedChange={toggleInsights}
                          disabled={insightsToggling}
                        />
                        <div>
                          <div className="flex items-center gap-2">
                            <span className={`font-medium ${theme.text.primary}`}>AI-Powered Insights</span>
                            <Badge variant={insightsStatus.enabled ? 'default' : 'secondary'} className="text-xs">
                              {insightsStatus.enabled ? 'Enabled' : 'Disabled'}
                            </Badge>
                          </div>
                          <p className={`text-sm mt-1 ${theme.text.muted}`}>
                            When enabled, users can generate AI analysis of their genetic data on any dashboard panel.
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className={`rounded-lg border p-3 ${isDarkMode ? 'border-white/10 bg-white/[0.03]' : 'border-gray-200 bg-gray-50'}`}>
                      <p className={`text-xs uppercase tracking-wider ${theme.text.muted}`}>Provider</p>
                      <p className={`text-sm font-medium mt-1 ${theme.text.primary}`}>{insightsStatus.provider}</p>
                    </div>
                    <div className={`rounded-lg border p-3 ${isDarkMode ? 'border-white/10 bg-white/[0.03]' : 'border-gray-200 bg-gray-50'}`}>
                      <p className={`text-xs uppercase tracking-wider ${theme.text.muted}`}>Model</p>
                      <p className={`text-sm font-medium mt-1 ${theme.text.primary}`}>{insightsStatus.model}</p>
                    </div>
                    <div className={`rounded-lg border p-3 ${isDarkMode ? 'border-white/10 bg-white/[0.03]' : 'border-gray-200 bg-gray-50'}`}>
                      <p className={`text-xs uppercase tracking-wider ${theme.text.muted}`}>API Keys</p>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {insightsStatus.gemini_configured && <Badge className="text-[10px] bg-blue-500/20 text-blue-400 border-blue-500/30">Gemini</Badge>}
                        {insightsStatus.openai_configured && <Badge className="text-[10px] bg-green-500/20 text-green-400 border-green-500/30">OpenAI</Badge>}
                        {insightsStatus.anthropic_configured && <Badge className="text-[10px] bg-orange-500/20 text-orange-400 border-orange-500/30">Anthropic</Badge>}
                        {!insightsStatus.gemini_configured && !insightsStatus.openai_configured && !insightsStatus.anthropic_configured && (
                          <span className={`text-xs ${theme.text.muted}`}>None</span>
                        )}
                      </div>
                    </div>
                    <div className={`rounded-lg border p-3 ${isDarkMode ? 'border-white/10 bg-white/[0.03]' : 'border-gray-200 bg-gray-50'}`}>
                      <p className={`text-xs uppercase tracking-wider ${theme.text.muted}`}>Cached Insights</p>
                      <p className={`text-sm font-medium mt-1 ${theme.text.primary}`}>{insightsStatus.cache_entries}</p>
                    </div>
                  </div>
                </div>
              ) : (
                <p className={`text-center py-8 ${theme.text.tertiary}`}>Loading AI Insights status...</p>
              )}
            </CardContent>
          </Card>

          {/* ───── Local ETL, BigQuery & Maintenance ───── */}
          {/* ETL Import Sources */}
          <Card className="glass-card">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <HardDrive className="h-5 w-5" />
                    Local Data Sources (ETL)
                  </CardTitle>
                  <CardDescription>
                    Import and manage local data sources. These are long-running operations — large files may take 5-30+ minutes.
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {etlFeedback && (
                <div className={`mb-4 p-3 rounded-lg flex items-start gap-2 text-sm ${
                  etlFeedback.type === 'success' ? 'bg-green-500/10 text-green-600 border border-green-500/20'
                    : 'bg-red-500/10 text-red-600 border border-red-500/20'
                }`}>
                  <Info className="h-4 w-4 mt-0.5 shrink-0" />
                  <span><strong>{ETL_SOURCES.find(s => s.key === etlFeedback.source)?.label}:</strong> {etlFeedback.message}</span>
                </div>
              )}
              <div className="space-y-4">
                {ETL_SOURCES.map(src => {
                  const status = etlStatuses[src.key]
                  const isLoading = etlLoading[src.key]
                  const isRunning = etlRunning[src.key]
                  const showProgress = src.key === 'clinvar' && isRunning && etlProgress
                  const dc = src.displayConfig
                  return (
                    <div
                      key={src.key}
                      className={`rounded-lg border p-4 ${isDarkMode ? 'border-white/10 bg-white/5' : 'border-gray-200 bg-gray-50'}`}
                    >
                      {/* Header row */}
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={`font-semibold ${theme.text.primary}`}>{src.label}</span>
                            <Badge variant="outline" className="text-xs text-emerald-600 border-emerald-500/30">Local</Badge>
                            {status && !isLoading && dc.primaryKey && (
                              <Badge variant="outline" className="text-xs text-sky-500 border-sky-500/30">
                                {Number(status[dc.primaryKey] ?? 0).toLocaleString()} rows
                              </Badge>
                            )}
                          </div>
                          <p className={`text-sm mt-0.5 ${theme.text.muted}`}>{src.description}</p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          {src.statusEndpoint && (
                            <Button
                              size="sm" variant="outline"
                              disabled={!!isLoading}
                              title="Refresh status"
                              onClick={() => fetchEtlStatus(src.key, src.statusEndpoint!)}
                            >
                              <RefreshCw className={`h-3 w-3 ${isLoading ? 'animate-spin' : ''}`} />
                            </Button>
                          )}
                          <Button
                            size="sm" variant="default"
                            disabled={!!isRunning}
                            onClick={() => runEtlImport(src.key, src.importEndpoint)}
                            className="bg-violet-600 hover:bg-violet-700"
                          >
                            {isRunning
                              ? <><RefreshCw className="h-3 w-3 mr-1 animate-spin" /> Importing…</>
                              : <><Upload className="h-3 w-3 mr-1" /> Import</>}
                          </Button>
                        </div>
                      </div>

                      {/* Loading skeleton */}
                      {isLoading && !status && (
                        <div className="mt-3 flex gap-3">
                          <div className={`h-16 flex-1 rounded-lg animate-pulse ${isDarkMode ? 'bg-white/5' : 'bg-gray-200'}`} />
                          <div className={`h-16 w-28 rounded-lg animate-pulse ${isDarkMode ? 'bg-white/5' : 'bg-gray-200'}`} />
                          <div className={`h-16 w-28 rounded-lg animate-pulse ${isDarkMode ? 'bg-white/5' : 'bg-gray-200'}`} />
                        </div>
                      )}

                      {/* Stats cards */}
                      {status && !showProgress && (
                        <div className="mt-3 space-y-2">
                          <div className="flex flex-wrap gap-2">
                            {/* Primary hero stat */}
                            {dc.primaryKey && status[dc.primaryKey] !== undefined && (
                              <div className={`flex-1 min-w-32 rounded-lg p-3 ${isDarkMode ? 'bg-white/7 border border-white/10' : 'bg-white border border-gray-200'}`}>
                                <div className={`text-2xl font-bold tabular-nums tracking-tight ${theme.text.primary}`}>
                                  {Number(status[dc.primaryKey]).toLocaleString()}
                                </div>
                                <div className={`text-xs mt-0.5 ${theme.text.muted}`}>
                                  {dc.primaryKey.replace(/_/g, ' ')}
                                </div>
                              </div>
                            )}
                            {/* Secondary count stats */}
                            {dc.countKeys.filter(k => status[k] !== undefined).map(k => (
                              <div key={k} className={`flex-1 min-w-28 rounded-lg p-3 ${isDarkMode ? 'bg-white/4 border border-white/6' : 'bg-gray-50 border border-gray-100'}`}>
                                <div className={`text-lg font-semibold tabular-nums ${theme.text.primary}`}>
                                  {Number(status[k]).toLocaleString()}
                                </div>
                                <div className={`text-xs mt-0.5 ${theme.text.muted}`}>
                                  {k.replace(/_/g, ' ')}
                                </div>
                              </div>
                            ))}
                            {/* Array keys — show count */}
                            {dc.arrayKeys.filter(k => status[k] !== undefined).map(k => (
                              <div key={k} className={`flex-1 min-w-28 rounded-lg p-3 ${isDarkMode ? 'bg-white/4 border border-white/6' : 'bg-gray-50 border border-gray-100'}`}>
                                <div className={`text-lg font-semibold tabular-nums ${theme.text.primary}`}>
                                  {Array.isArray(status[k]) ? (status[k] as unknown[]).length : '—'}
                                </div>
                                <div className={`text-xs mt-0.5 ${theme.text.muted}`}>
                                  {k.replace(/_/g, ' ')}
                                </div>
                              </div>
                            ))}
                          </div>
                          {/* File existence badges */}
                          {dc.fileKeys.length > 0 && (
                            <div className="flex flex-wrap gap-2 pt-1">
                              {dc.fileKeys.map(k => {
                                const exists = Boolean(status[k])
                                return (
                                  <span key={k} className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full font-medium ${
                                    exists
                                      ? 'bg-green-500/10 text-green-600 border border-green-500/20'
                                      : 'bg-red-500/10 text-red-500 border border-red-500/20'
                                  }`}>
                                    {exists
                                      ? <CheckCircle className="h-3 w-3 shrink-0" />
                                      : <XCircle className="h-3 w-3 shrink-0" />}
                                    {k.replace(/_exists$/, '').replace(/_/g, ' ')}
                                  </span>
                                )
                              })}
                            </div>
                          )}
                        </div>
                      )}

                      {/* ClinVar live progress */}
                      {showProgress && etlProgress && (
                        <div className="mt-3 space-y-2">
                          <div className="flex items-center justify-between text-xs">
                            <span className={`font-medium capitalize ${theme.text.secondary}`}>
                              Step: <span className="text-violet-400">{etlProgress.step ?? '…'}</span>
                              {etlProgress.rows > 0 && (
                                <span className={`ml-2 ${theme.text.muted}`}>({etlProgress.rows.toLocaleString()} rows)</span>
                              )}
                            </span>
                            <span className={theme.text.muted}>{etlProgress.pct}% · {etlProgress.total_elapsed}s</span>
                          </div>
                          <div className={`w-full h-2 rounded-full overflow-hidden ${isDarkMode ? 'bg-white/10' : 'bg-gray-200'}`}>
                            <div
                              className="h-full rounded-full bg-linear-to-r from-violet-500 to-fuchsia-500 transition-all duration-500"
                              style={{ width: `${etlProgress.pct}%` }}
                            />
                          </div>
                          {etlProgress.steps.length > 0 && (
                            <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1">
                              {etlProgress.steps.map(s => (
                                <span key={s.step} className={`text-xs ${theme.text.muted}`}>
                                  ✓ {s.step}{s.count > 0 ? ` (${s.count.toLocaleString()})` : ''} {s.elapsed_s}s
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </CardContent>
          </Card>

          {/* BigQuery Backfill */}
          <Card className="glass-card mt-6">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Layers className="h-5 w-5" />
                    gnomAD BigQuery Backfill
                  </CardTitle>
                  <CardDescription>
                    Enrich local CADD variants with population allele frequencies from Google BigQuery. May incur costs.
                  </CardDescription>
                </div>
                <Button size="sm" variant="outline" onClick={fetchBqStatus} disabled={bqLoading}>
                  <RefreshCw className={`h-3 w-3 mr-1 ${bqLoading ? 'animate-spin' : ''}`} /> Refresh
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {bqFeedback && (
                <div className={`mb-4 p-3 rounded-lg flex items-start gap-2 text-sm ${
                  bqFeedback.type === 'success' ? 'bg-green-500/10 text-green-600 border border-green-500/20'
                    : 'bg-red-500/10 text-red-600 border border-red-500/20'
                }`}>
                  <Info className="h-4 w-4 mt-0.5 shrink-0" />
                  <span>{bqFeedback.message}</span>
                </div>
              )}
              {bqStatus && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                  {Object.entries(bqStatus).map(([k, v]) => (
                    <div key={k} className={`rounded-lg border p-3 ${isDarkMode ? 'border-white/10 bg-white/[0.03]' : 'border-gray-200 bg-gray-50'}`}>
                      <p className={`text-xs uppercase tracking-wider ${theme.text.muted}`}>{k.replace(/_/g, ' ')}</p>
                      <p className={`text-sm font-medium mt-1 ${theme.text.primary}`}>
                        {typeof v === 'number' ? v.toLocaleString() : typeof v === 'boolean' ? (v ? 'Yes' : 'No') : String(v ?? '—')}
                      </p>
                    </div>
                  ))}
                </div>
              )}
              <div className={`rounded-lg border p-4 ${isDarkMode ? 'border-white/10 bg-white/5' : 'border-gray-200 bg-gray-50'}`}>
                <div className="flex items-center gap-3 flex-wrap">
                  <div className="space-y-1">
                    <Label className="text-xs">Batch Size</Label>
                    <Input
                      type="number" min={10} max={1000}
                      value={bqBatchSize}
                      onChange={e => setBqBatchSize(e.target.value)}
                      className="w-24 h-8 text-xs text-center"
                      disabled={bqRunning}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Max Variants</Label>
                    <Input
                      type="number" min={100} max={1000000}
                      value={bqMaxVariants}
                      onChange={e => setBqMaxVariants(e.target.value)}
                      className="w-28 h-8 text-xs text-center"
                      disabled={bqRunning}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Chromosome (optional)</Label>
                    <Input
                      placeholder="e.g. 1, X"
                      value={bqChromosome}
                      onChange={e => setBqChromosome(e.target.value)}
                      className="w-24 h-8 text-xs text-center"
                      disabled={bqRunning}
                    />
                  </div>
                  <div className="pt-4">
                    <Button
                      size="sm"
                      variant="default"
                      disabled={bqRunning}
                      onClick={runBqBackfill}
                      className="bg-amber-600 hover:bg-amber-700"
                    >
                      {bqRunning
                        ? <><RefreshCw className="h-3 w-3 mr-1 animate-spin" /> Running BigQuery...</>
                        : <><Database className="h-3 w-3 mr-1" /> Run Backfill</>}
                    </Button>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Utility Operations */}
          <Card className="glass-card mt-6">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Settings className="h-5 w-5" />
                Utility Operations
              </CardTitle>
              <CardDescription>
                Database maintenance and automation tools.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {utilityFeedback && (
                <div className={`mb-4 p-3 rounded-lg flex items-start gap-2 text-sm ${
                  utilityFeedback.type === 'success' ? 'bg-green-500/10 text-green-600 border border-green-500/20'
                    : 'bg-red-500/10 text-red-600 border border-red-500/20'
                }`}>
                  <Info className="h-4 w-4 mt-0.5 shrink-0" />
                  <span>{utilityFeedback.message}</span>
                </div>
              )}
              <div className="space-y-3">
                {/* Auto-Categorize */}
                <div className={`rounded-lg border p-4 flex items-center justify-between ${isDarkMode ? 'border-white/10 bg-white/5' : 'border-gray-200 bg-gray-50'}`}>
                  <div>
                    <span className={`font-medium ${theme.text.primary}`}>Auto-Categorize</span>
                    <p className={`text-sm mt-0.5 ${theme.text.muted}`}>
                      Evaluate active category rules against ClinVar data to generate VariantMapping rows.
                    </p>
                  </div>
                  <Button
                    size="sm" variant="outline"
                    disabled={autoCategorizing}
                    onClick={runAutoCategorize}
                  >
                    {autoCategorizing
                      ? <><RefreshCw className="h-3 w-3 mr-1 animate-spin" /> {autoCatStatus || 'Running…'}</>
                      : <><Zap className="h-3 w-3 mr-1" /> Run</>}
                  </Button>
                </div>

                {/* Enrich Mappings */}
                <div className={`rounded-lg border p-4 ${isDarkMode ? 'border-white/10 bg-white/5' : 'border-gray-200 bg-gray-50'}`}>
                  <div className="flex items-center justify-between">
                    <div>
                      <span className={`font-medium ${theme.text.primary}`}>Enrich Mappings</span>
                      <p className={`text-sm mt-0.5 ${theme.text.muted}`}>
                        Replace generic &quot;{'{gene}'} variant&quot; names with proper conditions from ClinVar &amp; Ensembl.
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm" variant="outline"
                        disabled={enrichingMappings !== null}
                        onClick={() => runEnrichMappings(true)}
                      >
                        {enrichingMappings === 'dry_run'
                          ? <><RefreshCw className="h-3 w-3 mr-1 animate-spin" /> Running…</>
                          : <><Sparkles className="h-3 w-3 mr-1" /> Dry Run</>}
                      </Button>
                      <Button
                        size="sm" variant="default"
                        disabled={enrichingMappings !== null}
                        onClick={() => runEnrichMappings(false)}
                      >
                        {enrichingMappings === 'apply'
                          ? <><RefreshCw className="h-3 w-3 mr-1 animate-spin" /> Running…</>
                          : <><Sparkles className="h-3 w-3 mr-1" /> Apply</>}
                      </Button>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    <Switch
                      id="enrich-revise-all"
                      checked={enrichReviseAll}
                      onCheckedChange={setEnrichReviseAll}
                    />
                    <Label htmlFor="enrich-revise-all" className={`text-xs ${theme.text.muted}`}>
                      Revise all mappings (not just generic names)
                    </Label>
                  </div>
                </div>

                {/* Purge Deleted Analyses */}
                <div className={`rounded-lg border p-4 flex items-center justify-between ${isDarkMode ? 'border-white/10 bg-white/5' : 'border-gray-200 bg-gray-50'}`}>
                  <div>
                    <span className={`font-medium ${theme.text.primary}`}>Purge Deleted Analyses</span>
                    <p className={`text-sm mt-0.5 ${theme.text.muted}`}>
                      Hard-delete analyses (and cascaded children) that were soft-deleted more than N days ago. Use 0 for all.
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Input
                      type="number" min={0}
                      value={purgeOlderThanDays}
                      onChange={e => setPurgeOlderThanDays(e.target.value)}
                      className="w-16 h-8 text-xs text-center"
                      disabled={purgingDeleted}
                    />
                    <span className={`text-xs ${theme.text.muted}`}>days</span>
                    <Button
                      size="sm" variant="destructive"
                      disabled={purgingDeleted}
                      onClick={runPurgeDeleted}
                    >
                      {purgingDeleted
                        ? <><RefreshCw className="h-3 w-3 mr-1 animate-spin" /> Purging...</>
                        : <><Trash2 className="h-3 w-3 mr-1" /> Purge</>}
                    </Button>
                  </div>
                </div>

                {/* gnomAD CADD Cache Build */}
                <div className={`rounded-lg border p-4 flex items-center justify-between ${isDarkMode ? 'border-white/10 bg-white/5' : 'border-gray-200 bg-gray-50'}`}>
                  <div>
                    <span className={`font-medium ${theme.text.primary}`}>Build gnomAD CADD Cache</span>
                    <p className={`text-sm mt-0.5 ${theme.text.muted}`}>
                      Sequential chromosome scan of CADD TSV files → SQLite. Run once to make gnomAD annotation sub-second (instead of ~14 min per analysis).
                    </p>
                  </div>
                  <Button
                    size="sm" variant="outline"
                    disabled={gnomadCacheJobId !== null}
                    onClick={runBuildCaddCache}
                  >
                    {gnomadCacheJobId !== null
                      ? <><RefreshCw className="h-3 w-3 mr-1 animate-spin" /> {gnomadCacheStatus || 'Running…'}</>
                      : <><Zap className="h-3 w-3 mr-1" /> Build Cache</>}
                  </Button>
                </div>

                {/* gnomAD v2 Ancestry AF Refresh */}
                <div className={`rounded-lg border p-4 ${isDarkMode ? 'border-white/10 bg-white/5' : 'border-gray-200 bg-gray-50'}`}>
                  <div className="flex items-center justify-between">
                    <div>
                      <span className={`font-medium ${theme.text.primary}`}>Refresh Ancestry AFs (gnomAD v2)</span>
                      <p className={`text-sm mt-0.5 ${theme.text.muted}`}>
                        Update ancestry_aims_panel with population AFs from local gnomAD v2.1.1 GRCh37 VCF files (no network needed).
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm" variant="outline"
                        disabled={gnomadAncestryJobId !== null}
                        onClick={() => runRefreshAncestryAfs(true)}
                      >
                        {gnomadAncestryJobId !== null
                          ? <><RefreshCw className="h-3 w-3 mr-1 animate-spin" /> {gnomadAncestryStatus || 'Running…'}</>
                          : <><Zap className="h-3 w-3 mr-1" /> Index + Refresh</>}
                      </Button>
                      <Button
                        size="sm" variant="default"
                        disabled={gnomadAncestryJobId !== null}
                        onClick={() => runRefreshAncestryAfs(false)}
                      >
                        {gnomadAncestryJobId !== null
                          ? <><RefreshCw className="h-3 w-3 mr-1 animate-spin" /> {gnomadAncestryStatus || 'Running…'}</>
                          : <><Sparkles className="h-3 w-3 mr-1" /> Refresh</>}
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ===== CATEGORY RULES TAB ===== */}
        <TabsContent value="rules" className="mt-6">
          <Card className="glass-card">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Scale className="h-5 w-5" />
                    Category Rules
                  </CardTitle>
                  <CardDescription>
                    Rules that auto-categorize variants into panels based on gene symbols, pathways, or other criteria.
                    {categoryRules.length > 0 && ` ${categoryRules.length} rules loaded.`}
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={rulesCategoryFilter}
                    onChange={e => { setRulesCategoryFilter(e.target.value); setRulesPage(0) }}
                    className={`rounded-md border px-3 py-1.5 text-sm ${isDarkMode ? 'bg-white/5 border-white/10 text-white' : 'bg-white border-gray-300 text-gray-900'}`}
                  >
                    <option value="all">All Categories</option>
                    {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
                      <option key={k} value={k}>{v}</option>
                    ))}
                  </select>
                  <Button size="sm" variant="outline" onClick={fetchCategoryRules} disabled={rulesLoading}>
                    <RefreshCw className={`h-3 w-3 mr-1 ${rulesLoading ? 'animate-spin' : ''}`} /> Refresh
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setShowAddRule(true)}>
                    <Plus className="h-3 w-3 mr-1" /> Add Rule
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {rulesFeedback && (
                <div className={`mb-4 p-3 rounded-lg flex items-start gap-2 text-sm ${
                  rulesFeedback.type === 'success' ? 'bg-green-500/10 text-green-600 border border-green-500/20'
                    : 'bg-red-500/10 text-red-600 border border-red-500/20'
                }`}>
                  <Info className="h-4 w-4 mt-0.5 shrink-0" />
                  <span>{rulesFeedback.message}</span>
                </div>
              )}

              {/* Seed Rules Button */}
              <div className={`mb-4 rounded-lg border p-3 flex items-center justify-between ${isDarkMode ? 'border-white/10 bg-white/[0.03]' : 'border-gray-200 bg-gray-50'}`}>
                <div>
                  <span className={`text-sm font-medium ${theme.text.primary}`}>Seed Default Rules</span>
                  <p className={`text-xs ${theme.text.muted}`}>Populate with built-in default category rules (idempotent).</p>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" disabled={seedingRules} onClick={() => seedCategoryRules(false)}>
                    {seedingRules ? <RefreshCw className="h-3 w-3 mr-1 animate-spin" /> : <Download className="h-3 w-3 mr-1" />}
                    Seed
                  </Button>
                  <Button size="sm" variant="destructive" disabled={seedingRules} onClick={() => seedCategoryRules(true)}>
                    Force Re-seed
                  </Button>
                </div>
              </div>

              {categoryRules.length === 0 ? (
                <p className={`text-center py-8 ${theme.text.tertiary}`}>
                  {rulesLoading ? 'Loading rules...' : 'No category rules found. Try seeding defaults.'}
                </p>
              ) : (
                <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Category</TableHead>
                      <TableHead>Rule Type</TableHead>
                      <TableHead>Rule Value</TableHead>
                      <TableHead className="text-center">Priority</TableHead>
                      <TableHead className="text-center">Active</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginatedRules.map(rule => (
                      <TableRow key={rule.id}>
                        <TableCell>
                          <Badge variant="outline" className="text-xs">
                            {CATEGORY_LABELS[rule.category] || rule.category}
                          </Badge>
                        </TableCell>
                        <TableCell className={`text-sm ${theme.text.secondary}`}>{rule.rule_type}</TableCell>
                        <TableCell className="font-mono text-sm max-w-[300px] truncate">{rule.rule_value}</TableCell>
                        <TableCell className="text-center">
                          {editingRule === rule.id ? (
                            <div className="flex items-center gap-1 justify-center">
                              <Input
                                type="number"
                                value={editingRulePriority}
                                onChange={e => setEditingRulePriority(e.target.value)}
                                className="w-16 h-7 text-xs text-center"
                              />
                              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => updateCategoryRulePriority(rule.id)}>
                                <Check className="h-3 w-3" />
                              </Button>
                              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setEditingRule(null)}>
                                <X className="h-3 w-3" />
                              </Button>
                            </div>
                          ) : (
                            <span
                              className={`cursor-pointer hover:underline ${theme.text.primary}`}
                              onClick={() => { setEditingRule(rule.id); setEditingRulePriority(String(rule.priority)) }}
                            >
                              {rule.priority}
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="text-center">
                          <Switch
                            checked={rule.is_active}
                            onCheckedChange={() => toggleCategoryRuleActive(rule.id, rule.is_active)}
                          />
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            size="sm" variant="ghost"
                            className="h-7 w-7 p-0 text-red-400 hover:text-red-300"
                            onClick={() => setDeleteRuleId(rule.id)}
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                {renderPagination(categoryRules.length, rulesPage, setRulesPage)}
              </>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ===== QUALITY TAB ===== */}
        <TabsContent value="annotations" className="mt-6">
          <Card className="glass-card">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <AlertTriangle className="h-5 w-5" />
                    Annotation Quality
                  </CardTitle>
                  <CardDescription>
                    Variants with missing data from external API sources
                    {incompleteSummary && (
                      <span className="ml-2">
                        — {incompleteSummary.partial} partial, {incompleteSummary.failed} failed of {incompleteSummary.total_annotations} total
                      </span>
                    )}
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    className="text-sm rounded-md border px-2 py-1 bg-background"
                    value={incompleteFilter}
                    onChange={e => { setIncompleteFilter(e.target.value); setIncompletePage(0) }}
                  >
                    <option value="partial">Partial</option>
                    <option value="failed">Failed</option>
                    <option value="all">All Incomplete</option>
                  </select>
                  <Button
                    size="sm" variant="default"
                    disabled={bulkRetriggering || incompleteAnnotations.length === 0}
                    onClick={retriggerAllIncomplete}
                  >
                    {bulkRetriggering
                      ? <><RefreshCw className="h-3 w-3 mr-1 animate-spin" /> Retrying...</>
                      : <><RefreshCw className="h-3 w-3 mr-1" /> Retry All (up to 50)</>}
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {retriggerFeedback && (
                <div className={`mb-4 p-3 rounded-lg flex items-start gap-2 text-sm ${
                  retriggerFeedback.type === 'success' ? 'bg-green-500/10 text-green-600 border border-green-500/20'
                    : retriggerFeedback.type === 'info' ? 'bg-blue-500/10 text-blue-600 border border-blue-500/20'
                    : 'bg-red-500/10 text-red-600 border border-red-500/20'
                }`}>
                  <Info className="h-4 w-4 mt-0.5 shrink-0" />
                  <span>{retriggerFeedback.message}</span>
                </div>
              )}
              {incompleteAnnotations.length === 0 ? (
                <p className={`text-center py-8 ${theme.text.tertiary}`}>No incomplete annotations found</p>
              ) : (
                <>
                <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Variant</TableHead>
                      {(incompleteSummary?.enabled_sources ?? []).map(src => (
                        <TableHead key={src} className="text-center px-2">
                          {SOURCE_DISPLAY_NAMES[src] || src}
                        </TableHead>
                      ))}
                      <TableHead>Missing Sources</TableHead>
                      <TableHead>Uses</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {incompleteAnnotations.map(a => (
                      <TableRow key={a.id}>
                        <TableCell className="font-mono text-sm">{a.rsid}</TableCell>
                        {(incompleteSummary?.enabled_sources ?? []).map(src => {
                          const status = a[src as keyof IncompleteAnnotation] as string | undefined
                          return (
                            <TableCell key={src} className="text-center px-2">
                              {status === 'found'
                                ? <Check className="h-4 w-4 text-green-500 mx-auto" />
                                : status === 'no_data'
                                  ? <span title="Source has no data for this variant"><Minus className="h-4 w-4 text-yellow-500 mx-auto" /></span>
                                  : <X className="h-4 w-4 text-red-400 mx-auto" />}
                            </TableCell>
                          )
                        })}
                        <TableCell>
                          <div className="flex flex-wrap gap-1">
                            {(a.missing_sources || []).map(src => (
                              <Badge key={src} variant="destructive" className="text-xs">
                                {SOURCE_DISPLAY_NAMES[src] || src}
                              </Badge>
                            ))}
                          </div>
                        </TableCell>
                        <TableCell>{a.usage_count}</TableCell>
                        <TableCell className="text-right">
                          <Button
                            size="sm" variant="outline"
                            disabled={retriggeringIds.has(a.id) || bulkRetriggering}
                            onClick={() => retriggerAnnotation(a.id)}
                          >
                            {retriggeringIds.has(a.id)
                              ? <RefreshCw className="h-3 w-3 animate-spin" />
                              : <><RefreshCw className="h-3 w-3 mr-1" /> Retry</>}
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                </div>
                {/* Pagination controls */}
                {incompleteTotalCount > INCOMPLETE_PAGE_SIZE && (
                  <div className="flex items-center justify-between mt-4 pt-4 border-t">
                    <span className="text-sm text-muted-foreground">
                      Showing {incompletePage * INCOMPLETE_PAGE_SIZE + 1}–{Math.min((incompletePage + 1) * INCOMPLETE_PAGE_SIZE, incompleteTotalCount)} of {incompleteTotalCount}
                    </span>
                    <div className="flex items-center gap-2">
                      <Button
                        size="sm" variant="outline"
                        disabled={incompletePage === 0}
                        onClick={() => setIncompletePage(p => p - 1)}
                      >
                        Previous
                      </Button>
                      <span className="text-sm">
                        Page {incompletePage + 1} of {Math.ceil(incompleteTotalCount / INCOMPLETE_PAGE_SIZE)}
                      </span>
                      <Button
                        size="sm" variant="outline"
                        disabled={(incompletePage + 1) * INCOMPLETE_PAGE_SIZE >= incompleteTotalCount}
                        onClick={() => setIncompletePage(p => p + 1)}
                      >
                        Next
                      </Button>
                    </div>
                  </div>
                )}
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ===== JOBS TAB ===== */}
        <TabsContent value="jobs" className="mt-6">
          <Card className="glass-card">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Activity className="h-5 w-5" />
                    Analysis Jobs
                  </CardTitle>
                  <CardDescription>
                    {jobsSummary ? `${jobsSummary.total} total — ${jobsSummary.processing} processing, ${jobsSummary.pending} pending, ${jobsSummary.completed} completed, ${jobsSummary.failed} failed` : 'Loading...'}
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={jobsStatusFilter}
                    onChange={e => { setJobsStatusFilter(e.target.value); setJobsPage(0) }}
                    className={`rounded-md border px-3 py-1.5 text-sm ${isDarkMode ? 'bg-white/5 border-white/10 text-white' : 'bg-white border-gray-300 text-gray-900'}`}
                  >
                    <option value="all">All Statuses</option>
                    <option value="processing">Processing</option>
                    <option value="pending">Pending</option>
                    <option value="completed">Completed</option>
                    <option value="failed">Failed</option>
                  </select>
                  <Button size="sm" variant="outline" onClick={() => { fetchJobs(); fetchJobsSummary() }}>
                    <RefreshCw className="h-3 w-3 mr-1" /> Refresh
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {/* Summary badges */}
              {jobsSummary && (
                <div className="flex gap-3 mb-4">
                  <Badge className="bg-blue-500/20 text-blue-400 border-blue-500/30">
                    <Clock className="h-3 w-3 mr-1" /> {jobsSummary.pending} Pending
                  </Badge>
                  <Badge className="bg-amber-500/20 text-amber-400 border-amber-500/30">
                    <RefreshCw className="h-3 w-3 mr-1 animate-spin" /> {jobsSummary.processing} Processing
                  </Badge>
                  <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30">
                    <Check className="h-3 w-3 mr-1" /> {jobsSummary.completed} Completed
                  </Badge>
                  <Badge className="bg-red-500/20 text-red-400 border-red-500/30">
                    <X className="h-3 w-3 mr-1" /> {jobsSummary.failed} Failed
                  </Badge>
                </div>
              )}

              {jobs.length === 0 ? (
                <div className="text-center py-10">
                  <Activity className={`h-12 w-12 mx-auto mb-4 ${theme.text.muted}`} />
                  <p className={theme.text.muted}>No analysis jobs found</p>
                </div>
              ) : (
                <>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>ID</TableHead>
                      <TableHead>User</TableHead>
                      <TableHead>File</TableHead>
                      <TableHead className="text-center">Status</TableHead>
                      <TableHead className="text-center">Progress</TableHead>
                      <TableHead>Step</TableHead>
                      <TableHead>Started</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginatedJobs.map(job => (
                      <TableRow key={job.id}>
                        <TableCell className="font-mono text-xs">#{job.id}</TableCell>
                        <TableCell>
                          <div className="text-sm font-medium">{job.username}</div>
                          <div className={`text-xs ${theme.text.muted}`}>{job.user_email}</div>
                        </TableCell>
                        <TableCell>
                          <div className="text-sm">{job.filename}</div>
                          <div className={`text-xs ${theme.text.muted}`}>{job.file_type.toUpperCase()} — {job.total_variants} variants</div>
                        </TableCell>
                        <TableCell className="text-center">
                          <Badge className={
                            job.analysis_status === 'completed' ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' :
                            job.analysis_status === 'processing' ? 'bg-amber-500/20 text-amber-400 border-amber-500/30' :
                            job.analysis_status === 'pending' ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' :
                            job.analysis_status === 'paused' ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' :
                            'bg-red-500/20 text-red-400 border-red-500/30'
                          }>
                            {job.analysis_status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-center">
                          {job.analysis_status === 'processing' ? (
                            <div className="flex flex-col items-center gap-1">
                              <div className="w-20 h-2 rounded-full bg-gray-700/50 overflow-hidden">
                                <div
                                  className="h-full rounded-full bg-gradient-to-r from-blue-500 to-cyan-400 transition-all duration-500"
                                  style={{ width: `${job.progress_percentage}%` }}
                                />
                              </div>
                              <span className="text-xs font-mono">{job.progress_percentage}%</span>
                            </div>
                          ) : job.analysis_status === 'completed' ? (
                            <span className="text-xs font-mono text-emerald-400">100%</span>
                          ) : (
                            <span className={`text-xs ${theme.text.muted}`}>—</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <span className={`text-xs ${theme.text.muted}`}>
                            {job.current_step ? job.current_step.replace(/_/g, ' ') : '—'}
                          </span>
                          {job.analysis_status === 'processing' && job.processed_variants > 0 && (
                            <div className={`text-xs ${theme.text.muted}`}>
                              {job.processed_variants}/{job.total_variants} variants
                            </div>
                          )}
                        </TableCell>
                        <TableCell>
                          <span className={`text-xs ${theme.text.muted}`}>
                            {job.upload_date ? new Date(job.upload_date).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                          </span>
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-7 w-7 p-0 text-violet-400 border-violet-500/30 hover:bg-violet-500/10"
                              onClick={() => openLogs(job.id)}
                              title="View logs"
                            >
                              <FileText className="h-3 w-3" />
                            </Button>
                            {(job.analysis_status === 'processing' || job.analysis_status === 'pending') && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 w-7 p-0 text-yellow-400 border-yellow-500/30 hover:bg-yellow-500/10"
                                disabled={jobActionLoading === job.id}
                                onClick={() => pauseJob(job.id)}
                                title="Pause"
                              >
                                <Pause className="h-3 w-3" />
                              </Button>
                            )}
                            {job.analysis_status === 'paused' && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 w-7 p-0 text-green-400 border-green-500/30 hover:bg-green-500/10"
                                disabled={jobActionLoading === job.id}
                                onClick={() => resumeJob(job.id)}
                                title="Resume"
                              >
                                <Play className="h-3 w-3" />
                              </Button>
                            )}
                            {(job.analysis_status === 'processing' || job.analysis_status === 'pending' || job.analysis_status === 'paused') && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 w-7 p-0 text-amber-400 border-amber-500/30 hover:bg-amber-500/10"
                                disabled={jobActionLoading === job.id}
                                onClick={() => cancelJob(job.id)}
                                title="Cancel"
                              >
                                <Square className="h-3 w-3" />
                              </Button>
                            )}
                            {(job.analysis_status === 'failed' || job.analysis_status === 'completed') && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 px-2 text-xs text-blue-400 border-blue-500/30 hover:bg-blue-500/10"
                                disabled={jobActionLoading === job.id}
                                onClick={() => restartJob(job.id)}
                                title="Full re-analysis"
                              >
                                <Play className="h-3 w-3 mr-1" /> Restart
                              </Button>
                            )}
                            {(job.analysis_status === 'failed' || job.analysis_status === 'completed') && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 px-2 text-xs text-purple-400 border-purple-500/30 hover:bg-purple-500/10"
                                disabled={jobActionLoading === job.id}
                                onClick={() => regenInsights(job.id)}
                                title="Regenerate insights only (skip annotation pipeline)"
                              >
                                <Sparkles className="h-3 w-3 mr-1" /> Regen
                              </Button>
                            )}
                            {job.analysis_status !== 'processing' && job.analysis_status !== 'paused' && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 w-7 p-0 text-red-400 border-red-500/30 hover:bg-red-500/10"
                                disabled={jobActionLoading === job.id}
                                onClick={() => setDeleteConfirmJobId(job.id)}
                                title="Delete job"
                              >
                                <Trash2 className="h-3 w-3" />
                              </Button>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                {renderPagination(jobs.length, jobsPage, setJobsPage)}
                </>
              )}
            </CardContent>
          </Card>

          {/* Worker Jobs section */}
          <Card className="glass-card mt-6">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <Zap className="h-5 w-5" />
                    Background Worker Jobs
                  </CardTitle>
                  <CardDescription>
                    System tasks: auto-categorize, purge deleted analyses, etc.
                  </CardDescription>
                </div>
                <Button size="sm" variant="outline" onClick={() => fetchWorkerJobs()}>
                  <RefreshCw className="h-3 w-3 mr-1" /> Refresh
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {workerJobs.length === 0 ? (
                <div className="text-center py-8">
                  <Zap className={`h-10 w-10 mx-auto mb-3 ${theme.text.muted}`} />
                  <p className={theme.text.muted}>No background jobs found</p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>ID</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead className="text-center">Status</TableHead>
                      <TableHead>Requested By</TableHead>
                      <TableHead>Created</TableHead>
                      <TableHead>Completed</TableHead>
                      <TableHead>Details</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {workerJobs.map(job => (
                      <React.Fragment key={job.job_id}>
                      <TableRow className="cursor-pointer hover:bg-white/5" onClick={() => setWorkerJobsExpanded(workerJobsExpanded === job.job_id ? null : job.job_id)}>
                        <TableCell className="font-mono text-xs">#{job.job_id}</TableCell>
                        <TableCell>
                          <Badge className={`font-mono text-xs ${
                            job.job_type === 'auto_categorize' ? 'bg-violet-500/20 text-violet-400 border-violet-500/30' :
                            job.job_type === 'purge_deleted' ? 'bg-orange-500/20 text-orange-400 border-orange-500/30' :
                            'bg-blue-500/20 text-blue-400 border-blue-500/30'
                          }`}>
                            {job.job_type.replace(/_/g, ' ')}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-center">
                          <Badge className={
                            job.status === 'completed' ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' :
                            job.status === 'processing' ? 'bg-amber-500/20 text-amber-400 border-amber-500/30' :
                            job.status === 'pending' ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' :
                            job.status === 'failed' ? 'bg-red-500/20 text-red-400 border-red-500/30' :
                            'bg-gray-500/20 text-gray-400 border-gray-500/30'
                          }>
                            {job.status === 'processing' && <RefreshCw className="h-3 w-3 mr-1 inline animate-spin" />}
                            {job.status}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {job.requested_by_username ? (
                            <div>
                              <div className="text-sm font-medium">{job.requested_by_username}</div>
                              <div className={`text-xs ${theme.text.muted}`}>{job.requested_by_email}</div>
                            </div>
                          ) : (
                            <span className={`text-xs ${theme.text.muted}`}>system</span>
                          )}
                        </TableCell>
                        <TableCell>
                          <span className={`text-xs ${theme.text.muted}`}>
                            {job.created_at ? new Date(job.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                          </span>
                        </TableCell>
                        <TableCell>
                          <span className={`text-xs ${theme.text.muted}`}>
                            {job.completed_at ? new Date(job.completed_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                          </span>
                        </TableCell>
                        <TableCell>
                          <Button size="sm" variant="ghost" className="h-6 px-2 text-xs">
                            <ChevronRight className={`h-3 w-3 transition-transform ${workerJobsExpanded === job.job_id ? 'rotate-90' : ''}`} />
                          </Button>
                        </TableCell>
                      </TableRow>
                      {workerJobsExpanded === job.job_id && (
                        <TableRow key={`${job.job_id}-detail`}>
                          <TableCell colSpan={7} className="p-0">
                            <div className="mx-2 my-1 rounded-lg bg-gray-950 border border-white/10 px-4 py-3 space-y-2 text-xs font-mono">
                              {/* Duration */}
                              {job.started_at && (
                                <div>
                                  <span className="text-gray-400 font-sans font-medium">Duration: </span>
                                  <span className="text-cyan-400">
                                    {job.completed_at
                                      ? (() => {
                                          const s = Math.round((new Date(job.completed_at).getTime() - new Date(job.started_at!).getTime()) / 1000)
                                          return s >= 60 ? `${Math.floor(s/60)}m ${s%60}s` : `${s}s`
                                        })()
                                      : 'running…'}
                                  </span>
                                </div>
                              )}
                              {/* Params — filter out nulls/false defaults */}
                              {job.params && Object.entries(job.params).filter(([,v]) => v !== null && v !== false).length > 0 && (
                                <div>
                                  <span className="text-gray-400 font-sans font-medium">Params: </span>
                                  <span className="text-blue-400">
                                    {JSON.stringify(Object.fromEntries(Object.entries(job.params).filter(([,v]) => v !== null && v !== false)))}
                                  </span>
                                </div>
                              )}
                              {/* Result — pretty-print ETL stats */}
                              {job.result && Object.keys(job.result).length > 0 && (
                                <div className="space-y-0.5">
                                  <span className="text-gray-400 font-sans font-medium block">Result:</span>
                                  {Object.entries(job.result).map(([k, v]) => (
                                    <div key={k} className="pl-3">
                                      <span className="text-gray-500">{k}: </span>
                                      <span className="text-emerald-400">
                                        {Array.isArray(v) ? `[${(v as unknown[]).length} items]` : String(v)}
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              )}
                              {/* Error */}
                              {job.error && (
                                <div>
                                  <span className="text-gray-400 font-sans font-medium">Error: </span>
                                  <span className="text-red-400 whitespace-pre-wrap">{job.error}</span>
                                </div>
                              )}
                              {!job.started_at && !job.result && !job.error && !(job.params && Object.entries(job.params).filter(([,v]) => v !== null && v !== false).length > 0) && (
                                <span className="text-gray-500">No additional details</span>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      )}
                      </React.Fragment>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ===== DIALOGS ===== */}

      {/* Job Logs Dialog */}
      {/* Delete Job Confirmation Dialog */}
      <Dialog open={deleteConfirmJobId !== null} onOpenChange={(open) => { if (!open) setDeleteConfirmJobId(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Analysis Job</DialogTitle>
            <DialogDescription>
              Delete this analysis job and all associated data? This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirmJobId(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => deleteConfirmJobId !== null && deleteJob(deleteConfirmJobId)}>
              Delete Job
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={viewingLogs !== null} onOpenChange={(open) => { if (!open) setViewingLogs(null) }}>
        <DialogContent className="sm:max-w-5xl max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Job #{viewingLogs} — Logs
            </DialogTitle>
            <DialogDescription>
              {(() => {
                const job = jobs.find(j => j.id === viewingLogs)
                if (!job) return 'Loading...'
                return `${job.filename} — ${job.analysis_status} (${job.progress_percentage}%)`
              })()}
            </DialogDescription>
          </DialogHeader>
          <div className={`flex-1 overflow-auto rounded-lg border font-mono text-xs leading-5 p-3 min-h-[300px] max-h-[55vh] ${isDarkMode ? 'bg-black/60 border-white/10 text-gray-300' : 'bg-gray-950 border-gray-300 text-gray-300'}`}>
            {logsLoading ? (
              <div className="flex items-center justify-center py-10">
                <RefreshCw className="h-5 w-5 animate-spin text-gray-500" />
              </div>
            ) : jobLogs.length === 0 ? (
              <div className="text-center py-10 text-gray-500">
                No logs available. Logs are captured while the job is running.
              </div>
            ) : (
              <>
                {jobLogs.map((entry, i) => (
                  <div key={i} className="flex gap-2 hover:bg-white/5 px-1 rounded">
                    <span className="text-gray-500 shrink-0">{entry.ts}</span>
                    <span className={`shrink-0 w-14 ${
                      entry.level === 'ERROR' ? 'text-red-400' :
                      entry.level === 'WARNING' ? 'text-amber-400' :
                      'text-blue-400'
                    }`}>
                      {entry.level}
                    </span>
                    <span className="break-all">{entry.msg}</span>
                  </div>
                ))}
                <div ref={logsEndRef} />
              </>
            )}
          </div>
          <DialogFooter className="flex items-center justify-between sm:justify-between">
            <div className="flex items-center gap-2">
              {(() => {
                const job = jobs.find(j => j.id === viewingLogs)
                const isActive = job?.analysis_status === 'processing' || job?.analysis_status === 'pending'
                return isActive ? (
                  <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30">
                    <RefreshCw className="h-3 w-3 mr-1 animate-spin" /> Auto-refreshing
                  </Badge>
                ) : null
              })()}
              <span className={`text-xs ${theme.text.muted}`}>{jobLogs.length} entries</span>
            </div>
            <Button variant="outline" size="sm" onClick={() => viewingLogs && fetchJobLogs(viewingLogs)}>
              <RefreshCw className="h-3 w-3 mr-1" /> Refresh
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete User Dialog */}
      <Dialog open={!!showDeleteUser} onOpenChange={() => setShowDeleteUser(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete User</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete <strong>{showDeleteUser?.username}</strong>? This action cannot be undone and will remove all their data.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteUser(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => showDeleteUser && deleteUser(showDeleteUser.id)}>
              Delete User
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Add Mapping Dialog */}
      <Dialog open={showAddMapping} onOpenChange={setShowAddMapping}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Variant Mapping</DialogTitle>
            <DialogDescription>
              Add a new variant-to-condition mapping for the {CATEGORY_LABELS[newMapping.category || selectedRegistryCategory || ''] || 'selected'} category.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="map_type">Type *</Label>
                <div className="flex rounded-lg border overflow-hidden">
                  {(['rsid', 'gene'] as const).map(t => (
                    <button
                      key={t}
                      onClick={() => setNewMapping(prev => ({ ...prev, map_type: t }))}
                      className={`flex-1 px-3 py-2 text-sm font-medium transition-colors ${
                        newMapping.map_type === t ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'
                      }`}
                    >
                      {t.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="mapping_key">Key *</Label>
                <Input
                  id="mapping_key"
                  placeholder={newMapping.map_type === 'rsid' ? 'rs1801133' : 'MTHFR'}
                  value={newMapping.key}
                  onChange={e => setNewMapping({ ...newMapping, key: e.target.value })}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="mapping_data">Data (JSON) *</Label>
              <textarea
                id="mapping_data"
                placeholder='{"condition": "...", "risk_level": "low", ...}'
                value={newMapping.data}
                onChange={e => setNewMapping({ ...newMapping, data: e.target.value })}
                className="w-full h-32 rounded-md border bg-background px-3 py-2 text-sm font-mono resize-y"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddMapping(false)}>Cancel</Button>
            <Button onClick={addMapping} disabled={!newMapping.key || !newMapping.data}>Add Mapping</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Mapping Dialog */}
      <Dialog open={!!showDeleteMapping} onOpenChange={() => setShowDeleteMapping(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Mapping</DialogTitle>
            <DialogDescription>
              Remove <strong>{showDeleteMapping?.map_type}</strong> mapping for <strong>{showDeleteMapping?.key}</strong>? This will affect future analyses.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteMapping(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => showDeleteMapping && deleteMapping(showDeleteMapping.id)}>
              Delete Mapping
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reject Discovery Dialog */}
      <Dialog open={!!showRejectDialog} onOpenChange={() => { setShowRejectDialog(null); setRejectReason('') }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject Discovery</DialogTitle>
            <DialogDescription>
              Reject <strong>{showRejectDialog?.rsid}</strong> (Variant Mapping)? Optionally provide a reason.
            </DialogDescription>
          </DialogHeader>
          <div className="py-2">
            <Label>Reason (optional)</Label>
            <Input
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value)}
              placeholder="e.g. Not clinically relevant"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowRejectDialog(null); setRejectReason('') }}>Cancel</Button>
            <Button variant="destructive" onClick={() => showRejectDialog && reviewDiscovery(showRejectDialog.id, 'reject', rejectReason || undefined)}>
              Reject
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Variant Detail Dialog for Discoveries */}
      {selectedDiscoveryRsid && (
        <VariantDetailDialog
          rsid={selectedDiscoveryRsid.rsid}
          gene={selectedDiscoveryRsid.gene}
          token={token}
          isDarkMode={isDarkMode}
          open={!!selectedDiscoveryRsid}
          onOpenChange={(open) => { if (!open) setSelectedDiscoveryRsid(null) }}
        />
      )}

      {/* Add Category Rule Dialog */}
      <Dialog open={showAddRule} onOpenChange={setShowAddRule}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Category Rule</DialogTitle>
            <DialogDescription>Create a new rule for automatic variant categorization.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-2">
              <Label>Category *</Label>
              <select
                value={newRule.category}
                onChange={e => setNewRule({ ...newRule, category: e.target.value })}
                className={`w-full rounded-md border px-3 py-2 text-sm ${isDarkMode ? 'bg-white/5 border-white/10 text-white' : 'bg-white border-gray-300 text-gray-900'}`}
              >
                <option value="">Select category...</option>
                {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
                  <option key={k} value={k}>{v}</option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label>Rule Type</Label>
              <select
                value={newRule.rule_type}
                onChange={e => setNewRule({ ...newRule, rule_type: e.target.value })}
                className={`w-full rounded-md border px-3 py-2 text-sm ${isDarkMode ? 'bg-white/5 border-white/10 text-white' : 'bg-white border-gray-300 text-gray-900'}`}
              >
                <option value="gene_symbol">Gene Symbol</option>
                <option value="gene_prefix">Gene Prefix</option>
                <option value="pathway">Pathway</option>
                <option value="clinvar_keyword">ClinVar Keyword</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label>Rule Value *</Label>
              <Input
                placeholder="e.g. CYP2D6, HLA-*, folate metabolism"
                value={newRule.rule_value}
                onChange={e => setNewRule({ ...newRule, rule_value: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>Priority</Label>
              <Input
                type="number"
                value={newRule.priority}
                onChange={e => setNewRule({ ...newRule, priority: e.target.value })}
                className="w-24"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddRule(false)}>Cancel</Button>
            <Button onClick={addCategoryRule} disabled={!newRule.category || !newRule.rule_value}>Add Rule</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Category Rule Confirmation */}
      <Dialog open={deleteRuleId !== null} onOpenChange={(open) => { if (!open) setDeleteRuleId(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Rule</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this category rule? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteRuleId(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => deleteRuleId && deleteCategoryRule(deleteRuleId)}>
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
