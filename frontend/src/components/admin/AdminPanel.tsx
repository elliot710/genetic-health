'use client'

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { Shield, Users, Settings, Plus, Trash2, Pencil, Check, X, ChevronRight, Download, Upload, Database } from 'lucide-react'
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

const API = 'http://localhost:8000/api/admin'

interface AdminUser {
  id: number
  email: string
  username: string
  full_name: string | null
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

export default function AdminPanel({ token, theme }: AdminPanelProps) {
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
        <TabsList className="grid w-full max-w-lg grid-cols-3">
          <TabsTrigger value="users" className="gap-2">
            <Users className="h-4 w-4" />
            Users
          </TabsTrigger>
          <TabsTrigger value="markers" className="gap-2">
            <Settings className="h-4 w-4" />
            Panel Markers
          </TabsTrigger>
          <TabsTrigger value="registry" className="gap-2">
            <Database className="h-4 w-4" />
            Variant Registry
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
                        {user.full_name || user.username}
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
      </Tabs>

      {/* ===== DIALOGS ===== */}

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
    </div>
  )
}
