'use client'

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { Shield, Users, Settings, Plus, Trash2, Pencil, Check, X, ChevronRight, Download, Upload, Database, Lightbulb, RefreshCw, AlertTriangle, Minus, Info, Activity, Play, Square, Clock, FileText, Zap, Sparkles } from 'lucide-react'
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

const API = 'http://localhost:8000/api/admin'

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

interface PanelSummary {
  panel_id: string
  marker_count: number
  active_count: number
}

interface MarkerConfig {
  id: number
  panel_id: string
  rsid: string
  gene: string | null
  description: string | null
  category: string | null
  is_active: boolean
  created_at: string | null
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
  panel_marker_pending: number
  variant_mapping_pending: number
}

interface IncompleteAnnotation {
  id: number
  rsid: string
  annotation_status: string | null
  failed_sources: string[] | null
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

interface AnnotationSource {
  id: number
  source_name: string
  display_name: string
  is_enabled: boolean
  description: string | null
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

interface AdminPanelProps {
  token?: string
  isDarkMode: boolean
  theme: ReturnType<typeof import('@/utils/theme').getTheme>
}

const PANEL_LABELS: Record<string, string> = {
  methylation: 'Methylation',
  detox: 'Detoxification',
  health: 'Health & Wellness',
  sports: 'Sports & Fitness',
  drug_responses: 'Drug Responses',
  nutrition: 'Food & Nutrition',
  carrier: 'Carrier Status',
  ancestry: 'Ancestry & Origins',
  wellness: 'Wellness Reports',
  intelligence: 'Intelligence',
  personality: 'Personality',
  physical_traits: 'Physical Traits',
  rare_mutations: 'Rare Mutations',
  uncommon_mutations: 'Uncommon Mutations',
}

export default function AdminPanel({ token, isDarkMode, theme }: AdminPanelProps) {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [panels, setPanels] = useState<PanelSummary[]>([])
  const [selectedPanel, setSelectedPanel] = useState<string | null>(null)
  const [markers, setMarkers] = useState<MarkerConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Dialog states
  const [showAddMarker, setShowAddMarker] = useState(false)
  const [showDeleteUser, setShowDeleteUser] = useState<AdminUser | null>(null)
  const [showDeleteMarker, setShowDeleteMarker] = useState<MarkerConfig | null>(null)
  const [editingMarker, setEditingMarker] = useState<MarkerConfig | null>(null)

  // New marker form
  const [newMarker, setNewMarker] = useState({ rsid: '', gene: '', description: '', category: '', panel_id: '' })

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

  const headers = useMemo(() => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }), [token])

  const fetchUsers = useCallback(async () => {
    try {
      const res = await fetch(`${API}/users`, { headers })
      if (!res.ok) throw new Error('Failed to load users')
      setUsers(await res.json())
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    }
  }, [headers])

  const fetchPanels = useCallback(async () => {
    try {
      const res = await fetch(`${API}/panels`, { headers })
      if (!res.ok) throw new Error('Failed to load panels')
      setPanels(await res.json())
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    }
  }, [headers])

  const fetchMarkers = useCallback(async (panelId: string) => {
    try {
      const res = await fetch(`${API}/panels/${encodeURIComponent(panelId)}/markers`, { headers })
      if (!res.ok) throw new Error('Failed to load markers')
      setMarkers(await res.json())
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    }
  }, [headers])

  useEffect(() => {
    Promise.all([fetchUsers(), fetchPanels(), fetchRegistryCategories()]).finally(() => setLoading(false))
  }, [fetchUsers, fetchPanels])

  useEffect(() => {
    if (selectedPanel) fetchMarkers(selectedPanel)
  }, [selectedPanel, fetchMarkers])

  useEffect(() => {
    if (selectedRegistryCategory) fetchRegistryMappings(selectedRegistryCategory)
  }, [selectedRegistryCategory])

  // --- Registry fetch ---
  const fetchRegistryCategories = useCallback(async () => {
    try {
      const res = await fetch(`${API}/variant-mappings/categories`, { headers })
      if (!res.ok) return
      setRegistryCategories(await res.json())
    } catch { /* ignore */ }
  }, [headers])

  const fetchRegistryMappings = useCallback(async (cat: string) => {
    try {
      const url = `${API}/variant-mappings/${encodeURIComponent(cat)}`
      const res = await fetch(url, { headers })
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
      const res = await fetch(`${API}/variant-mappings`, {
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
      const res = await fetch(`${API}/variant-mappings/${mapping.id}`, {
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
    const res = await fetch(`${API}/variant-mappings/${id}`, { method: 'DELETE', headers })
    if (res.ok) {
      setRegistryMappings(prev => prev.filter(m => m.id !== id))
      setShowDeleteMapping(null)
      fetchRegistryCategories()
    }
  }

  const toggleMappingActive = async (mapping: VariantMapping) => {
    const res = await fetch(`${API}/variant-mappings/${mapping.id}`, {
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
    const res = await fetch(`${API}/users/${userId}`, {
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
    const res = await fetch(`${API}/users/${userId}`, { method: 'DELETE', headers })
    if (res.ok) {
      setUsers(prev => prev.filter(u => u.id !== userId))
      setShowDeleteUser(null)
    }
  }

  // --- Marker actions ---
  const addMarker = async () => {
    const panelId = newMarker.panel_id || selectedPanel
    if (!panelId || !newMarker.rsid) return
    const res = await fetch(`${API}/panels/${encodeURIComponent(panelId)}/markers`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ ...newMarker, panel_id: panelId }),
    })
    if (res.ok) {
      setShowAddMarker(false)
      setNewMarker({ rsid: '', gene: '', description: '', category: '', panel_id: '' })
      fetchPanels()
      if (selectedPanel === panelId) fetchMarkers(panelId)
    }
  }

  const updateMarker = async (marker: MarkerConfig) => {
    const res = await fetch(`${API}/panels/markers/${marker.id}`, {
      method: 'PUT',
      headers,
      body: JSON.stringify({
        rsid: marker.rsid,
        gene: marker.gene,
        description: marker.description,
        category: marker.category,
        is_active: marker.is_active,
      }),
    })
    if (res.ok) {
      const updated = await res.json()
      setMarkers(prev => prev.map(m => m.id === marker.id ? updated : m))
      setEditingMarker(null)
    }
  }

  const deleteMarker = async (id: number) => {
    const res = await fetch(`${API}/panels/markers/${id}`, { method: 'DELETE', headers })
    if (res.ok) {
      setMarkers(prev => prev.filter(m => m.id !== id))
      setShowDeleteMarker(null)
      fetchPanels()
    }
  }

  const toggleMarkerActive = async (marker: MarkerConfig) => {
    updateMarker({ ...marker, is_active: !marker.is_active })
  }

  // --- Import / Export ---
  const importFileRef = useRef<HTMLInputElement>(null)
  const [importResult, setImportResult] = useState<string | null>(null)

  const exportMarkers = async (format: 'csv' | 'yaml') => {
    if (!selectedPanel) return
    const res = await fetch(
      `${API}/panels/${encodeURIComponent(selectedPanel)}/markers/export?format=${format}`,
      { headers }
    )
    if (!res.ok) return
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${selectedPanel}_markers.${format}`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !selectedPanel) return
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await fetch(
        `${API}/panels/${encodeURIComponent(selectedPanel)}/markers/import`,
        { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: formData }
      )
      const data = await res.json()
      if (res.ok) {
        setImportResult(data.detail)
        fetchMarkers(selectedPanel)
        fetchPanels()
      } else {
        setImportResult(`Error: ${data.detail}`)
      }
    } catch {
      setImportResult('Import failed')
    }
    // reset file input so same file can be re-imported
    if (importFileRef.current) importFileRef.current.value = ''
    setTimeout(() => setImportResult(null), 5000)
  }

  // --- Discoveries ---
  const fetchDiscoverySummary = useCallback(async () => {
    try {
      const res = await fetch(`${API}/discoveries/summary`, { headers })
      if (res.ok) setDiscoverySummary(await res.json())
    } catch { /* ignore */ }
  }, [headers])

  const fetchDiscoveries = useCallback(async () => {
    try {
      const params = new URLSearchParams()
      if (discoveryStatusFilter !== 'all') params.set('status_filter', discoveryStatusFilter)
      if (discoveryTypeFilter !== 'all') params.set('discovery_type', discoveryTypeFilter)
      const res = await fetch(`${API}/discoveries?${params}`, { headers })
      if (res.ok) setDiscoveries(await res.json())
    } catch { /* ignore */ }
  }, [headers, discoveryStatusFilter, discoveryTypeFilter])

  useEffect(() => { fetchDiscoverySummary() }, [fetchDiscoverySummary])
  useEffect(() => { fetchDiscoveries() }, [fetchDiscoveries])

  const reviewDiscovery = async (id: number, action: 'approve' | 'reject', reason?: string) => {
    setReviewingId(id)
    try {
      const res = await fetch(`${API}/discoveries/${id}/review`, {
        method: 'POST', headers,
        body: JSON.stringify({ action, rejection_reason: reason }),
      })
      if (res.ok) {
        fetchDiscoveries()
        fetchDiscoverySummary()
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
      const res = await fetch(`${API}/discoveries/bulk-review?${ids.map(id => `discovery_ids=${id}`).join('&')}`, {
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
      const res = await fetch(`${API}/annotations/incomplete/summary`, { headers })
      if (res.ok) setIncompleteSummary(await res.json())
    } catch { /* ignore */ }
  }, [headers])

  const fetchIncompleteAnnotations = useCallback(async () => {
    try {
      const res = await fetch(`${API}/annotations/incomplete?status_filter=${incompleteFilter}&limit=100`, { headers })
      if (res.ok) setIncompleteAnnotations(await res.json())
    } catch { /* ignore */ }
  }, [headers, incompleteFilter])

  useEffect(() => { fetchIncompleteSummary() }, [fetchIncompleteSummary])
  useEffect(() => { fetchIncompleteAnnotations() }, [fetchIncompleteAnnotations])

  const retriggerAnnotation = async (id: number) => {
    setRetriggeringIds(prev => new Set(prev).add(id))
    setRetriggerFeedback(null)
    try {
      const res = await fetch(`${API}/annotations/retrigger/${id}`, { method: 'POST', headers })
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
      const res = await fetch(`${API}/annotations/retrigger-bulk?retrigger_all=true&limit=50`, {
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
      const res = await fetch(`${API}/jobs/summary`, { headers })
      if (res.ok) setJobsSummary(await res.json())
    } catch { /* ignore */ }
  }, [headers])

  const fetchJobs = useCallback(async () => {
    try {
      const url = jobsStatusFilter === 'all' ? `${API}/jobs` : `${API}/jobs?status=${jobsStatusFilter}`
      const res = await fetch(url, { headers })
      if (res.ok) setJobs(await res.json())
    } catch { /* ignore */ }
  }, [headers, jobsStatusFilter])

  useEffect(() => { fetchJobsSummary() }, [fetchJobsSummary])
  useEffect(() => { fetchJobs() }, [fetchJobs])

  // Auto-refresh jobs when any are processing
  const jobsRefreshRef = useRef<ReturnType<typeof setInterval> | null>(null)
  useEffect(() => {
    const hasActive = jobs.some(j => j.analysis_status === 'processing' || j.analysis_status === 'pending')
    if (hasActive) {
      jobsRefreshRef.current = setInterval(() => { fetchJobs(); fetchJobsSummary() }, 5000)
    }
    return () => { if (jobsRefreshRef.current) clearInterval(jobsRefreshRef.current) }
  }, [jobs, fetchJobs, fetchJobsSummary])

  const cancelJob = async (id: number) => {
    setJobActionLoading(id)
    try {
      const res = await fetch(`${API}/jobs/${id}/cancel`, { method: 'POST', headers })
      if (res.ok) { fetchJobs(); fetchJobsSummary() }
    } catch { /* ignore */ }
    setJobActionLoading(null)
  }

  const restartJob = async (id: number) => {
    setJobActionLoading(id)
    try {
      const res = await fetch(`${API}/jobs/${id}/restart`, { method: 'POST', headers })
      if (res.ok) { fetchJobs(); fetchJobsSummary() }
    } catch { /* ignore */ }
    setJobActionLoading(null)
  }

  const deleteJob = async (id: number) => {
    setDeleteConfirmJobId(null)
    setJobActionLoading(id)
    try {
      const res = await fetch(`${API}/jobs/${id}`, { method: 'DELETE', headers })
      if (res.ok) { fetchJobs(); fetchJobsSummary() }
    } catch { /* ignore */ }
    setJobActionLoading(null)
  }

  const fetchJobLogs = useCallback(async (id: number) => {
    try {
      const res = await fetch(`${API}/jobs/${id}/logs`, { headers })
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
      logsRefreshRef.current = setInterval(() => fetchJobLogs(viewingLogs), 3000)
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
      const res = await fetch(`${API}/annotation-sources`, { headers })
      if (res.ok) setAnnotationSources(await res.json())
    } catch { /* ignore */ }
    setSourcesLoading(false)
  }, [headers])

  useEffect(() => { fetchAnnotationSources() }, [fetchAnnotationSources])

  const toggleSource = async (sourceName: string, enabled: boolean) => {
    setSourceToggling(sourceName)
    try {
      const res = await fetch(`${API}/annotation-sources/${encodeURIComponent(sourceName)}`, {
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
      const res = await fetch(`${API}/annotation-sources/${encodeURIComponent(sourceName)}/backfill?limit=${limit}`, {
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
      const res = await fetch('http://localhost:8000/api/insights/status', { headers })
      if (res.ok) setInsightsStatus(await res.json())
    } catch { /* ignore */ }
  }, [headers])

  useEffect(() => { fetchInsightsStatus() }, [fetchInsightsStatus])

  const toggleInsights = async (enabled: boolean) => {
    setInsightsToggling(true)
    try {
      const res = await fetch(`http://localhost:8000/api/insights/toggle?enabled=${enabled}`, {
        method: 'POST',
        headers,
      })
      if (res.ok) setInsightsStatus(await res.json())
    } catch { /* ignore */ }
    setInsightsToggling(false)
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

      <Tabs defaultValue="users" className="w-full">
        <TabsList className="grid w-full max-w-5xl grid-cols-7">
          <TabsTrigger value="users" className="gap-2">
            <Users className="h-4 w-4" />
            Users
          </TabsTrigger>
          <TabsTrigger value="markers" className="gap-2">
            <Settings className="h-4 w-4" />
            Markers
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
          <TabsTrigger value="sources" className="gap-2">
            <Zap className="h-4 w-4" />
            Sources
          </TabsTrigger>
          <TabsTrigger value="annotations" className="gap-2 relative">
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
            {jobsSummary && (jobsSummary.processing + jobsSummary.pending) > 0 && (
              <Badge className="ml-1 h-5 min-w-[20px] px-1 text-xs bg-blue-500 text-white">
                {jobsSummary.processing + jobsSummary.pending}
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
                  {users.map(user => (
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
            </CardContent>
          </Card>
        </TabsContent>

        {/* ===== PANEL MARKERS TAB ===== */}
        <TabsContent value="markers" className="mt-6">
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 min-h-[calc(100vh-280px)]">
            {/* Panel list */}
            <Card className="lg:col-span-1 glass-card flex flex-col">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Panels</CardTitle>
                <CardDescription>Select a panel to manage&apos;s markers</CardDescription>
              </CardHeader>
              <CardContent className="p-0 flex-1">
                <ScrollArea className="h-full">
                  <div className="space-y-1 px-4 pb-4">
                    {/* Show all possible panels, not just ones with data */}
                    {Object.entries(PANEL_LABELS).map(([id, label]) => {
                      const panel = panels.find(p => p.panel_id === id)
                      const isSelected = selectedPanel === id
                      return (
                        <button
                          key={id}
                          onClick={() => setSelectedPanel(id)}
                          className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-colors ${
                            isSelected
                              ? 'bg-primary text-primary-foreground'
                              : 'hover:bg-muted'
                          }`}
                        >
                          <span className="font-medium truncate">{label}</span>
                          <div className="flex items-center gap-2">
                            {panel && (
                              <Badge variant={isSelected ? 'outline' : 'secondary'} className="text-xs">
                                {panel.active_count}/{panel.marker_count}
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

            {/* Marker details */}
            <Card className="lg:col-span-3 glass-card flex flex-col">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>
                      {selectedPanel ? (PANEL_LABELS[selectedPanel] || selectedPanel) : 'Select a Panel'}
                    </CardTitle>
                    <CardDescription>
                      {selectedPanel
                        ? `${markers.length} marker${markers.length !== 1 ? 's' : ''} configured`
                        : 'Choose a panel from the left to manage its genetic markers'}
                    </CardDescription>
                  </div>
                  {selectedPanel && (
                    <div className="flex items-center gap-2">
                      <Button size="sm" variant="outline" onClick={() => exportMarkers('csv')}>
                        <Download className="h-4 w-4 mr-1" />
                        CSV
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => exportMarkers('yaml')}>
                        <Download className="h-4 w-4 mr-1" />
                        YAML
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => importFileRef.current?.click()}>
                        <Upload className="h-4 w-4 mr-1" />
                        Import
                      </Button>
                      <input
                        ref={importFileRef}
                        type="file"
                        accept=".csv,.yaml,.yml"
                        className="hidden"
                        onChange={handleImportFile}
                      />
                      <Button size="sm" onClick={() => {
                        setNewMarker(prev => ({ ...prev, panel_id: selectedPanel }))
                        setShowAddMarker(true)
                      }}>
                        <Plus className="h-4 w-4 mr-1" />
                        Add Marker
                      </Button>
                    </div>
                  )}
                </div>
              </CardHeader>
              {selectedPanel && (
                <CardContent>
                  {importResult && (
                    <div className={`mb-4 px-4 py-2.5 rounded-lg text-sm font-medium ${
                      importResult.startsWith('Error') ? 'bg-red-500/10 text-red-400 border border-red-500/20'
                        : 'bg-green-500/10 text-green-400 border border-green-500/20'
                    }`}>
                      {importResult}
                    </div>
                  )}
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>RSID</TableHead>
                        <TableHead>Gene</TableHead>
                        <TableHead>Description</TableHead>
                        <TableHead>Category</TableHead>
                        <TableHead className="text-center">Active</TableHead>
                        <TableHead></TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {markers.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                            No markers configured for this panel. Click &quot;Add Marker&quot; to get started.
                          </TableCell>
                        </TableRow>
                      ) : (
                        markers.map(marker => (
                          <TableRow key={marker.id}>
                            {editingMarker?.id === marker.id ? (
                              <>
                                <TableCell>
                                  <Input
                                    value={editingMarker.rsid}
                                    onChange={e => setEditingMarker({ ...editingMarker, rsid: e.target.value })}
                                    className="h-8 w-28"
                                  />
                                </TableCell>
                                <TableCell>
                                  <Input
                                    value={editingMarker.gene || ''}
                                    onChange={e => setEditingMarker({ ...editingMarker, gene: e.target.value })}
                                    className="h-8 w-24"
                                  />
                                </TableCell>
                                <TableCell>
                                  <Input
                                    value={editingMarker.description || ''}
                                    onChange={e => setEditingMarker({ ...editingMarker, description: e.target.value })}
                                    className="h-8"
                                  />
                                </TableCell>
                                <TableCell>
                                  <Input
                                    value={editingMarker.category || ''}
                                    onChange={e => setEditingMarker({ ...editingMarker, category: e.target.value })}
                                    className="h-8 w-28"
                                  />
                                </TableCell>
                                <TableCell className="text-center">
                                  <Switch
                                    checked={editingMarker.is_active}
                                    onCheckedChange={v => setEditingMarker({ ...editingMarker, is_active: v })}
                                  />
                                </TableCell>
                                <TableCell>
                                  <div className="flex gap-1">
                                    <Button size="sm" variant="ghost" onClick={() => updateMarker(editingMarker)}>
                                      <Check className="h-4 w-4 text-green-400" />
                                    </Button>
                                    <Button size="sm" variant="ghost" onClick={() => setEditingMarker(null)}>
                                      <X className="h-4 w-4 text-red-400" />
                                    </Button>
                                  </div>
                                </TableCell>
                              </>
                            ) : (
                              <>
                                <TableCell className="font-mono text-sm">{marker.rsid}</TableCell>
                                <TableCell>
                                  {marker.gene && <Badge variant="outline">{marker.gene}</Badge>}
                                </TableCell>
                                <TableCell className="text-sm text-muted-foreground max-w-xs truncate">
                                  {marker.description}
                                </TableCell>
                                <TableCell>
                                  {marker.category && (
                                    <Badge variant="secondary" className="text-xs">{marker.category}</Badge>
                                  )}
                                </TableCell>
                                <TableCell className="text-center">
                                  <Switch
                                    checked={marker.is_active}
                                    onCheckedChange={() => toggleMarkerActive(marker)}
                                  />
                                </TableCell>
                                <TableCell>
                                  <div className="flex gap-1">
                                    <Button size="sm" variant="ghost" onClick={() => setEditingMarker({ ...marker })}>
                                      <Pencil className="h-4 w-4" />
                                    </Button>
                                    <Button
                                      size="sm"
                                      variant="ghost"
                                      className="text-red-400 hover:text-red-300"
                                      onClick={() => setShowDeleteMarker(marker)}
                                    >
                                      <Trash2 className="h-4 w-4" />
                                    </Button>
                                  </div>
                                </TableCell>
                              </>
                            )}
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </CardContent>
              )}
            </Card>
          </div>
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
                          onClick={() => { setSelectedRegistryCategory(id); setRegistryFilter('all') }}
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
                        ? (() => {
                            const filtered = registryFilter === 'all' ? registryMappings : registryMappings.filter(m => m.map_type === registryFilter)
                            return `${filtered.length} mapping${filtered.length !== 1 ? 's' : ''}`
                          })()
                        : 'Choose a category to manage variant-to-condition mappings used by analysis'}
                    </CardDescription>
                  </div>
                  {selectedRegistryCategory && (
                    <div className="flex items-center gap-2">
                      <div className="flex rounded-lg border overflow-hidden">
                        {(['all', 'rsid', 'gene'] as const).map(f => (
                          <button
                            key={f}
                            onClick={() => setRegistryFilter(f)}
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
                        const filtered = registryFilter === 'all' ? registryMappings : registryMappings.filter(m => m.map_type === registryFilter)
                        if (filtered.length === 0) return (
                          <TableRow>
                            <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                              No mappings found. Click &quot;Add Mapping&quot; to create one.
                            </TableCell>
                          </TableRow>
                        )
                        return filtered.map(mapping => (
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
                    onChange={e => setDiscoveryStatusFilter(e.target.value)}
                  >
                    <option value="pending">Pending</option>
                    <option value="approved">Approved</option>
                    <option value="rejected">Rejected</option>
                    <option value="all">All</option>
                  </select>
                  <select
                    className="text-sm rounded-md border px-2 py-1 bg-background"
                    value={discoveryTypeFilter}
                    onChange={e => setDiscoveryTypeFilter(e.target.value)}
                  >
                    <option value="all">All Types</option>
                    <option value="panel_marker">Panel Markers</option>
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
                    {discoveries.map(d => (
                      <TableRow key={d.id}>
                        <TableCell>
                          <Badge variant={d.discovery_type === 'panel_marker' ? 'default' : 'secondary'}>
                            {d.discovery_type === 'panel_marker' ? 'Panel Marker' : 'Variant Mapping'}
                          </Badge>
                        </TableCell>
                        <TableCell
                          className="font-mono text-sm cursor-pointer text-blue-500 hover:text-blue-400 hover:underline"
                          onClick={() => setSelectedDiscoveryRsid({ rsid: d.rsid, gene: d.gene || undefined })}
                        >{d.rsid}</TableCell>
                        <TableCell>{d.gene || '—'}</TableCell>
                        <TableCell>
                          {d.discovery_type === 'panel_marker'
                            ? PANEL_LABELS[d.panel_id || ''] || d.panel_id
                            : CATEGORY_LABELS[d.mapping_category || ''] || d.mapping_category}
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
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ===== INCOMPLETE ANNOTATIONS TAB ===== */}
        {/* ===== SOURCES TAB ===== */}
        <TabsContent value="sources" className="mt-6">
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
              {annotationSources.length === 0 ? (
                <p className={`text-center py-8 ${theme.text.tertiary}`}>
                  {sourcesLoading ? 'Loading sources...' : 'No annotation sources configured'}
                </p>
              ) : (
                <div className="space-y-4">
                  {annotationSources.map(src => {
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
                                {src.rate_limit ? (
                                  <Badge variant="outline" className="text-xs">
                                    {src.rate_limit} req/s
                                  </Badge>
                                ) : (
                                  <Badge variant="outline" className="text-xs text-emerald-600 border-emerald-500/30">
                                    Local
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
                          </div>
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
        </TabsContent>

        <TabsContent value="annotations" className="mt-6">
          <Card className="glass-card">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2">
                    <AlertTriangle className="h-5 w-5" />
                    Incomplete Annotations
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
                    onChange={e => setIncompleteFilter(e.target.value)}
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
                      <TableHead>Failed Sources</TableHead>
                      <TableHead>Uses</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {incompleteAnnotations.map(a => (
                      <TableRow key={a.id}>
                        <TableCell className="font-mono text-sm">{a.rsid}</TableCell>
                        {(incompleteSummary?.enabled_sources ?? []).map(src => {
                          const status = (a as Record<string, unknown>)[src] as string | undefined
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
                            {(a.failed_sources || []).map(src => (
                              <Badge key={src} variant="destructive" className="text-xs">{src}</Badge>
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
                    onChange={e => setJobsStatusFilter(e.target.value)}
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
                    {jobs.map(job => (
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
                              className="h-7 px-2 text-xs text-violet-400 border-violet-500/30 hover:bg-violet-500/10"
                              onClick={() => openLogs(job.id)}
                            >
                              <FileText className="h-3 w-3 mr-1" /> Logs
                            </Button>
                            {(job.analysis_status === 'processing' || job.analysis_status === 'pending') && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 px-2 text-xs text-amber-400 border-amber-500/30 hover:bg-amber-500/10"
                                disabled={jobActionLoading === job.id}
                                onClick={() => cancelJob(job.id)}
                              >
                                <Square className="h-3 w-3 mr-1" /> Cancel
                              </Button>
                            )}
                            {(job.analysis_status === 'failed' || job.analysis_status === 'completed') && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 px-2 text-xs text-blue-400 border-blue-500/30 hover:bg-blue-500/10"
                                disabled={jobActionLoading === job.id}
                                onClick={() => restartJob(job.id)}
                              >
                                <Play className="h-3 w-3 mr-1" /> Restart
                              </Button>
                            )}
                            {job.analysis_status !== 'processing' && (
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 px-2 text-xs text-red-400 border-red-500/30 hover:bg-red-500/10"
                                disabled={jobActionLoading === job.id}
                                onClick={() => setDeleteConfirmJobId(job.id)}
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

      {/* Add Marker Dialog */}
      <Dialog open={showAddMarker} onOpenChange={setShowAddMarker}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Genetic Marker</DialogTitle>
            <DialogDescription>
              Add a new genetic marker to the {PANEL_LABELS[newMarker.panel_id || selectedPanel || ''] || 'selected'} panel.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="rsid">RSID *</Label>
                <Input
                  id="rsid"
                  placeholder="rs1801133"
                  value={newMarker.rsid}
                  onChange={e => setNewMarker({ ...newMarker, rsid: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="gene">Gene</Label>
                <Input
                  id="gene"
                  placeholder="MTHFR"
                  value={newMarker.gene}
                  onChange={e => setNewMarker({ ...newMarker, gene: e.target.value })}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Input
                id="description"
                placeholder="C677T - Reduced folate metabolism"
                value={newMarker.description}
                onChange={e => setNewMarker({ ...newMarker, description: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="category">Category</Label>
              <Input
                id="category"
                placeholder="e.g. folate_cycle, phase1"
                value={newMarker.category}
                onChange={e => setNewMarker({ ...newMarker, category: e.target.value })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowAddMarker(false)}>Cancel</Button>
            <Button onClick={addMarker} disabled={!newMarker.rsid}>Add Marker</Button>
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

      {/* Delete Marker Dialog */}
      <Dialog open={!!showDeleteMarker} onOpenChange={() => setShowDeleteMarker(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Marker</DialogTitle>
            <DialogDescription>
              Remove <strong>{showDeleteMarker?.rsid}</strong> ({showDeleteMarker?.gene}) from this panel?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteMarker(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => showDeleteMarker && deleteMarker(showDeleteMarker.id)}>
              Delete Marker
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
              Reject <strong>{showRejectDialog?.rsid}</strong> ({showRejectDialog?.discovery_type === 'panel_marker' ? 'Panel Marker' : 'Variant Mapping'})? Optionally provide a reason.
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
    </div>
  )
}
