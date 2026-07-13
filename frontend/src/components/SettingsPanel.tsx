'use client'

import { useState, useEffect, useRef } from 'react'
import { User, Mail, Key, Save, Check, Dna, Upload, Shield, Camera, Bookmark, Trash2, ExternalLink, Bell, Share2, UserCheck, Eye, EyeOff, X, Plus, Pencil, Printer, MessageSquare } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import type { DashboardData } from './categories/types'
import { apiFetch, ApiError } from '@/lib/api'
import { useFeedback } from '@/hooks/useFeedback'
import VariantDetailDialog from './categories/VariantDetailDialog'
import { DISCLAIMER_TEXT } from '@/components/Disclaimer'

interface SharedUser {
  id: number
  email: string
  full_name: string | null
  avatar_url: string | null
  shared_since: string | null
}

interface SettingsPanelProps {
  token?: string
  theme: ReturnType<typeof import('@/utils/theme').getTheme>
  data?: DashboardData
  onProfileUpdate?: () => void
  onViewSharedUser?: (user: { id: number; name: string; email: string } | null) => void
  viewingSharedUser?: { id: number; name: string; email: string } | null
}

const NOTIFICATION_LABELS: Record<string, string> = {
  analysis_queued: 'Analysis Queued',
  analysis_completed: 'Analysis Completed',
  analysis_failed: 'Analysis Failed',
  upload_complete: 'Upload Complete',
  upload_failed: 'Upload Failed',
  variant_saved: 'Variant Saved',
  discovery_approved: 'Discovery Approved',
  discovery_rejected: 'Discovery Rejected',
  data_deleted: 'Data Deleted',
  dashboard_shared: 'Dashboard Shared With Me',
}

export default function SettingsPanel({ token, theme, data, onProfileUpdate, onViewSharedUser, viewingSharedUser }: SettingsPanelProps) {
  const [profile, setProfile] = useState({ email: '', username: '', full_name: '', avatar_url: '' })
  const [passwords, setPasswords] = useState({ current: '', new_password: '', confirm: '' })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const { feedback: message, showFeedback: showMessage, clearFeedback: clearMessage } = useFeedback()
  const { feedback: pwMessage, showFeedback: showPwMessage, clearFeedback: clearPwMessage } = useFeedback()
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Saved variants state
  interface SavedVariantItem {
    id: number
    rsid: string
    gene: string | null
    genotype: string | null
    most_severe_consequence: string | null
    clinical_significance: string | null
    note: string | null
    created_at: string
  }
  const [savedVariants, setSavedVariants] = useState<SavedVariantItem[]>([])
  const [savedLoading, setSavedLoading] = useState(false)
  const [variantDialogRsid, setVariantDialogRsid] = useState<string | null>(null)
  const [variantDialogGene, setVariantDialogGene] = useState<string | undefined>(undefined)
  const [variantDialogGenotype, setVariantDialogGenotype] = useState<string | undefined>(undefined)
  const [editingNote, setEditingNote] = useState<{ rsid: string; text: string } | null>(null)
  const [noteSaving, setNoteSaving] = useState(false)

  // Notification preferences state
  const [notifPrefs, setNotifPrefs] = useState<Record<string, boolean>>({})
  const [notifLoading, setNotifLoading] = useState(false)
  const [notifSaving, setNotifSaving] = useState<string | null>(null)

  // Dashboard sharing state
  const [shareEmail, setShareEmail] = useState('')
  const [shareLoading, setShareLoading] = useState(false)
  const { feedback: shareMessage, showFeedback: showShareMessage, clearFeedback: clearShareMessage } = useFeedback()
  const [myShares, setMyShares] = useState<SharedUser[]>([])
  const [sharedWithMe, setSharedWithMe] = useState<SharedUser[]>([])
  const [sharesLoading, setSharesLoading] = useState(false)

  const fetchSavedVariants = async () => {
    setSavedLoading(true)
    try {
      const res = await apiFetch('/auth/saved-variants')
      setSavedVariants(await res.json())
    } catch { /* ignore */ }
    finally { setSavedLoading(false) }
  }

  const removeSavedVariant = async (rsid: string) => {
    try {
      await apiFetch(`/auth/saved-variants/${rsid}`, { method: 'DELETE' })
      setSavedVariants(prev => prev.filter(v => v.rsid !== rsid))
    } catch { /* ignore */ }
  }

  const saveNote = async (rsid: string, note: string) => {
    setNoteSaving(true)
    try {
      const res = await apiFetch(`/auth/saved-variants/${rsid}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note: note.trim() || null }),
      })
      const updated = await res.json()
      setSavedVariants(prev => prev.map(v => v.rsid === rsid ? { ...v, note: updated.note } : v))
      setEditingNote(null)
    } catch { /* ignore */ }
    finally { setNoteSaving(false) }
  }

  const [printLoading, setPrintLoading] = useState(false)

  const printVariants = async () => {
    setPrintLoading(true)
    const date = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })

    // Fetch full annotation details for all variants in parallel (served from cache)
    const details = await Promise.all(
      savedVariants.map(v =>
        apiFetch(`/api/annotations/variant-details/${v.rsid}`)
          .then(r => r.json())
          .catch(() => null)
      )
    )

    const rows = savedVariants.map((v, i) => {
      const d = details[i]
      const desc = d?.description || ''
      // Collect unique conditions from ClinVar entries
      const conditions = d?.clinvar?.entries
        ? [...new Set(d.clinvar.entries.flatMap((e: { conditions: string[] }) => e.conditions).filter(Boolean))] as string[]
        : []
      // Pathogenicity
      const ps = d?.pathogenicity_score
      const pathLabel = ps
        ? `${Math.round(ps.composite_score * 100)}% — ${ps.classification.replace(/_/g, ' ')}`
        : ''
      // ClinVar entry links
      const cvLinks = d?.clinvar?.entries
        ? (d.clinvar.entries as { uid: string; accession: string; clinical_significance: string[] }[])
            .map(e => `<a href="https://www.ncbi.nlm.nih.gov/clinvar/variation/${e.uid}" target="_blank" rel="noopener noreferrer">${e.accession || e.uid}</a> (${e.clinical_significance.join(', ')})`)
            .join('<br/>')
        : ''
      const noteHtml = v.note ? `<em class="note">${v.note.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</em>` : ''

      return `
      <tr>
        <td class="variant-cell">
          <strong class="rsid">${v.rsid}</strong>${v.gene ? `<br/><span class="muted">${v.gene}</span>` : ''}
          ${v.genotype ? `<br/><span class="genotype">${v.genotype}</span>` : ''}
        </td>
        <td>${v.clinical_significance || '—'}${cvLinks ? `<br/><div class="cv-links">${cvLinks}</div>` : ''}</td>
        <td>${conditions.length > 0 ? conditions.map(c => `<div class="condition">${c}</div>`).join('') : (desc ? '<span class="muted">See description</span>' : '—')}</td>
        <td class="desc-cell">${desc || '—'}</td>
        <td>${ps ? `<span class="${ps.classification.includes('pathogenic') && !ps.classification.includes('benign') ? 'path-high' : ps.classification.includes('uncertain') ? 'path-uncertain' : 'path-benign'}">${pathLabel}</span>` : (v.most_severe_consequence ? v.most_severe_consequence.replace(/_/g, ' ') : '—')}</td>
        <td>${noteHtml}</td>
      </tr>`
    }).join('')

    const html = `<!DOCTYPE html><html><head><meta charset="UTF-8">
        <title>Saved Variants — Epigenic</title>
        <style>
          * { box-sizing: border-box; }
          body { font-family: Georgia, serif; max-width: 1050px; margin: 40px auto; color: #1a1a1a; font-size: 12.5px; line-height: 1.5; }
          h1 { font-size: 22px; margin-bottom: 4px; }
          .meta { color: #555; font-size: 12px; margin-bottom: 28px; }
          table { width: 100%; border-collapse: collapse; margin-bottom: 28px; }
          th { background: #f0f0f0; text-align: left; padding: 7px 9px; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.06em; border-bottom: 2px solid #bbb; }
          td { padding: 8px 9px; border-bottom: 1px solid #e0e0e0; vertical-align: top; }
          tr:last-child td { border-bottom: none; }
          .rsid { font-size: 13px; }
          .muted { color: #777; font-size: 11px; }
          .genotype { font-family: monospace; color: #333; font-size: 11.5px; }
          .variant-cell { min-width: 90px; }
          .desc-cell { max-width: 240px; font-size: 11.5px; color: #333; }
          .condition { margin-bottom: 2px; }
          .cv-links { font-size: 10.5px; margin-top: 4px; color: #666; }
          .cv-links a { color: #c35e00; text-decoration: none; }
          .cv-links a:hover { text-decoration: underline; }
          .note { color: #444; display: block; margin-top: 3px; font-size: 11.5px; }
          .path-high { color: #c00; font-weight: bold; }
          .path-uncertain { color: #b56800; font-weight: bold; }
          .path-benign { color: #1a7a1a; font-weight: bold; }
          .disclaimer { border-top: 1px solid #ccc; padding-top: 12px; color: #888; font-size: 11px; font-style: italic; margin-top: 8px; }
          @media print {
            body { margin: 14mm; font-size: 11px; }
            .cv-links a { color: #c35e00; }
            button { display: none; }
          }
        </style>
      </head><body>
        <h1>Saved Variants — Genetic Health Summary</h1>
        <p class="meta">Generated: ${date} &nbsp;&middot;&nbsp; Patient: ${profile.full_name || profile.username || profile.email} &nbsp;&middot;&nbsp; Total variants: ${savedVariants.length}</p>
        <table>
          <thead>
            <tr>
              <th>Variant / Gene<br/>Genotype</th>
              <th>Clinical Significance<br/>ClinVar Reports</th>
              <th>Associated Conditions</th>
              <th>Description</th>
              <th>Pathogenicity</th>
              <th>Your Notes</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
        <p class="disclaimer">${DISCLAIMER_TEXT}</p>
        <script>window.onload=function(){window.print()}<\/script>
      </body></html>`

    setPrintLoading(false)
    const w = window.open('', '_blank')
    if (w) { w.document.write(html); w.document.close() }
  }

  const fetchNotifPrefs = async () => {
    setNotifLoading(true)
    try {
      const res = await apiFetch('/auth/notification-preferences')
      setNotifPrefs(await res.json())
    } catch { /* ignore */ }
    finally { setNotifLoading(false) }
  }

  const toggleNotifPref = async (key: string, value: boolean) => {
    setNotifPrefs(prev => ({ ...prev, [key]: value }))
    setNotifSaving(key)
    try {
      await apiFetch('/auth/notification-preferences', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preferences: { [key]: value } }),
      })
    } catch { /* ignore */ }
    finally { setNotifSaving(null) }
  }

  const fetchShares = async () => {
    setSharesLoading(true)
    try {
      const [mine, withMe] = await Promise.all([
        apiFetch('/api/sharing/my-shares').then(r => r.json()).catch(() => null),
        apiFetch('/api/sharing/shared-with-me').then(r => r.json()).catch(() => null),
      ])
      if (mine) setMyShares(mine)
      if (withMe) setSharedWithMe(withMe)
    } catch { /* ignore */ }
    finally { setSharesLoading(false) }
  }

  const handleShare = async () => {
    if (!shareEmail.trim()) return
    setShareLoading(true)
    clearShareMessage()
    try {
      const res = await apiFetch('/api/sharing/share', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: shareEmail.trim() }),
      })
      const json = await res.json().catch(() => ({}))
      showShareMessage({ message: json.detail || 'Dashboard shared!', type: 'success' })
      setShareEmail('')
      fetchShares()
    } catch (e) {
      showShareMessage({ message: e instanceof ApiError ? e.message : 'Network error', type: 'error' })
    } finally {
      setShareLoading(false)
    }
  }

  const handleRevoke = async (recipientId: number) => {
    try {
      await apiFetch(`/api/sharing/share/${recipientId}`, { method: 'DELETE' })
      setMyShares(prev => prev.filter(u => u.id !== recipientId))
    } catch { /* ignore */ }
  }

  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const res = await apiFetch('/auth/me')
        const data = await res.json()
        setProfile({ email: data.email, username: data.username, full_name: data.full_name || '', avatar_url: data.avatar_url || '' })
      } catch { /* ignore */ }
      finally {
        setLoading(false)
      }
    }
    fetchProfile()
    fetchSavedVariants()
    fetchNotifPrefs()
    fetchShares()
  }, [token])

  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.type.startsWith('image/')) {
      showMessage({ message: 'Please select an image file', type: 'error' })
      return
    }
    if (file.size > 350_000) {
      showMessage({ message: 'Image must be under 350KB', type: 'error' })
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      const dataUrl = reader.result as string
      setProfile(prev => ({ ...prev, avatar_url: dataUrl }))
    }
    reader.readAsDataURL(file)
  }

  const saveProfile = async () => {
    setSaving(true)
    clearMessage()
    try {
      await apiFetch('/auth/me', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ full_name: profile.full_name, avatar_url: profile.avatar_url || '' }),
      })
      showMessage({ message: 'Profile updated successfully', type: 'success' })
      onProfileUpdate?.()
    } catch (e) {
      showMessage({ message: e instanceof ApiError ? e.message : 'Network error', type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  const changePassword = async () => {
    clearPwMessage()
    if (passwords.new_password !== passwords.confirm) {
      showPwMessage({ message: 'Passwords do not match', type: 'error' })
      return
    }
    if (passwords.new_password.length < 6) {
      showPwMessage({ message: 'Password must be at least 6 characters', type: 'error' })
      return
    }
    setSaving(true)
    try {
      await apiFetch('/auth/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_password: passwords.current,
          new_password: passwords.new_password,
        }),
      })
      showPwMessage({ message: 'Password changed successfully', type: 'success' })
      setPasswords({ current: '', new_password: '', confirm: '' })
    } catch (e) {
      showPwMessage({ message: e instanceof ApiError ? e.message : 'Network error', type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-t-transparent border-blue-500" />
      </div>
    )
  }

  return (
    <div className="space-y-6 w-full">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-3 bg-linear-to-br from-blue-500/20 to-cyan-500/20 rounded-xl border border-blue-500/30">
          <User className="h-7 w-7 text-blue-400" />
        </div>
        <div>
          <h2 className={`text-2xl font-bold ${theme.text.primary}`}>Profile</h2>
          <p className={`text-sm ${theme.text.secondary}`}>Manage your profile and preferences</p>
        </div>
      </div>

      {/* ── Profile + Your Data ─────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Avatar + Profile Card */}
        <Card className="glass-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Mail className="h-5 w-5" />
              Account Information
            </CardTitle>
            <CardDescription>Your personal details</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Avatar */}
            <div className="flex items-center gap-5">
              <div className="relative group">
                <div
                  className="h-20 w-20 rounded-full border-2 border-blue-500/40 overflow-hidden flex items-center justify-center bg-linear-to-br from-blue-500/20 to-cyan-500/20 cursor-pointer"
                  onClick={() => fileInputRef.current?.click()}
                >
                  {profile.avatar_url ? (
                    <img src={profile.avatar_url} alt="Avatar" className="h-full w-full object-cover" />
                  ) : (
                    <User className="h-8 w-8 text-blue-400" />
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="absolute -bottom-1 -right-1 p-1.5 rounded-full bg-blue-600 hover:bg-blue-500 text-white border-2 border-gray-900 transition-colors"
                >
                  <Camera className="h-3 w-3" />
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={handleAvatarChange}
                />
              </div>
              <div className="flex-1">
                <p className={`text-sm ${theme.text.secondary}`}>Click avatar to upload a photo</p>
                <p className={`text-xs ${theme.text.muted}`}>JPG, PNG, or GIF &middot; Max 350KB</p>
                {profile.avatar_url && (
                  <button
                    type="button"
                    onClick={() => setProfile(prev => ({ ...prev, avatar_url: '' }))}
                    className="text-xs text-red-400 hover:text-red-300 mt-1 transition-colors"
                  >
                    Remove avatar
                  </button>
                )}
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input id="email" value={profile.email} disabled className="opacity-60" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input id="username" value={profile.username} disabled className="opacity-60" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="full_name">Full Name</Label>
              <Input
                id="full_name"
                value={profile.full_name}
                onChange={e => setProfile({ ...profile, full_name: e.target.value })}
                placeholder="Your full name"
              />
            </div>
            {message && (
              <p className={`text-sm flex items-center gap-1 ${message.type === 'success' ? 'text-green-500' : 'text-red-500'}`}>
                {message.type === 'success' && <Check className="h-4 w-4" />}
                {message.message}
              </p>
            )}
            <Button onClick={saveProfile} disabled={saving} className="gap-2">
              <Save className="h-4 w-4" />
              {saving ? 'Saving...' : 'Save Profile'}
            </Button>
          </CardContent>
        </Card>

        {/* Your Data Card */}
        {(data?.summary?.total_variants ?? 0) > 0 ? (
          <Card className="glass-card">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Dna className="h-5 w-5 text-green-500" />
                Your Data
              </CardTitle>
              <CardDescription>Your uploaded genetic data overview</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="text-center py-2">
                <div className="text-4xl font-bold text-green-500 mb-1">
                  {data!.summary!.total_variants.toLocaleString()}
                </div>
                <div className={`text-sm ${theme.text.secondary}`}>DNA Variants</div>
              </div>
              <div className="space-y-3">
                {[
                  { label: 'File', value: data!.summary?.filename || 'N/A', icon: Upload },
                  { label: 'Analysis ID', value: data!.summary?.analysis_id || 'N/A', icon: Shield },
                ].map((item, index) => (
                  <div key={index} className="flex items-center justify-between p-3 glass-card rounded-lg">
                    <div className="flex items-center gap-2">
                      <item.icon className={`h-4 w-4 ${theme.text.muted}`} />
                      <span className={`text-sm ${theme.text.secondary}`}>{item.label}</span>
                    </div>
                    <span className={`text-sm font-medium ${theme.text.primary} truncate max-w-50`} title={String(item.value)}>
                      {item.value}
                    </span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        ) : (
          <div />
        )}
      </div>

      {/* ── Settings section ────────────────────────────────── */}
      <div className="flex items-center gap-3 pt-2">
        <div className="p-2 bg-linear-to-br from-gray-500/20 to-slate-500/20 rounded-lg border border-gray-500/30">
          <Key className="h-5 w-5 text-gray-400" />
        </div>
        <div>
          <h3 className={`text-lg font-semibold ${theme.text.primary}`}>Settings</h3>
          <p className={`text-xs ${theme.text.muted}`}>Security and notification preferences</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Change Password */}
        <Card className="glass-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Key className="h-5 w-5" />
              Change Password
            </CardTitle>
            <CardDescription>Update your account password</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="current_pw">Current Password</Label>
              <Input
                id="current_pw"
                type="password"
                value={passwords.current}
                onChange={e => setPasswords({ ...passwords, current: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new_pw">New Password</Label>
              <Input
                id="new_pw"
                type="password"
                value={passwords.new_password}
                onChange={e => setPasswords({ ...passwords, new_password: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm_pw">Confirm Password</Label>
              <Input
                id="confirm_pw"
                type="password"
                value={passwords.confirm}
                onChange={e => setPasswords({ ...passwords, confirm: e.target.value })}
              />
            </div>
            {pwMessage && (
              <p className={`text-sm flex items-center gap-1 ${pwMessage.type === 'success' ? 'text-green-500' : 'text-red-500'}`}>
                {pwMessage.type === 'success' && <Check className="h-4 w-4" />}
                {pwMessage.message}
              </p>
            )}
            <Button onClick={changePassword} disabled={saving || !passwords.current || !passwords.new_password} className="gap-2">
              <Key className="h-4 w-4" />
              {saving ? 'Changing...' : 'Change Password'}
            </Button>
          </CardContent>
        </Card>

        {/* Notification Preferences */}
        <Card className="glass-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bell className="h-5 w-5 text-purple-400" />
              Notification Preferences
            </CardTitle>
            <CardDescription>Choose which events trigger notifications</CardDescription>
          </CardHeader>
          <CardContent>
            {notifLoading ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-6 w-6 border-2 border-purple-500 border-t-transparent" />
              </div>
            ) : (
              <div className="space-y-2">
                {Object.entries(NOTIFICATION_LABELS).map(([key, label]) => (
                  <div key={key} className="flex items-center justify-between p-3 glass-card rounded-lg">
                    <Label htmlFor={`notif-${key}`} className={`text-sm cursor-pointer select-none ${theme.text.secondary}`}>
                      {label}
                    </Label>
                    <Switch
                      id={`notif-${key}`}
                      checked={notifPrefs[key] !== false}
                      disabled={notifSaving === key}
                      onCheckedChange={val => toggleNotifPref(key, val)}
                    />
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Dashboard Sharing section ─────────────────────── */}
      <div className="flex items-center gap-3 pt-2">
        <div className="p-2 bg-linear-to-br from-blue-500/20 to-indigo-500/20 rounded-lg border border-blue-500/30">
          <Share2 className="h-5 w-5 text-blue-400" />
        </div>
        <div>
          <h3 className={`text-lg font-semibold ${theme.text.primary}`}>Dashboard Sharing</h3>
          <p className={`text-xs ${theme.text.muted}`}>Share your insights or view others</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Share my dashboard */}
        <Card className="glass-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Share2 className="h-5 w-5 text-blue-400" />
              Share My Dashboard
            </CardTitle>
            <CardDescription>Let another user view your genetic insights</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2">
              <Input
                placeholder="Enter user's email address"
                value={shareEmail}
                onChange={e => setShareEmail(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleShare() }}
                type="email"
              />
              <Button onClick={handleShare} disabled={shareLoading || !shareEmail.trim()} className="gap-1 shrink-0">
                <Plus className="h-4 w-4" />
                Share
              </Button>
            </div>
            {shareMessage && (
              <p className={`text-sm flex items-center gap-1 ${shareMessage.type === 'success' ? 'text-green-500' : 'text-red-500'}`}>
                {shareMessage.type === 'success' && <Check className="h-4 w-4" />}
                {shareMessage.message}
              </p>
            )}
            {sharesLoading ? (
              <div className="flex items-center justify-center py-4">
                <div className="animate-spin rounded-full h-5 w-5 border-2 border-blue-500 border-t-transparent" />
              </div>
            ) : myShares.length === 0 ? (
              <p className={`text-sm ${theme.text.muted} text-center py-2`}>Not shared with anyone yet</p>
            ) : (
              <div className="space-y-2">
                {myShares.map(user => (
                  <div key={user.id} className="flex items-center justify-between p-2.5 glass-card rounded-lg group">
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="h-8 w-8 rounded-full border border-blue-500/30 overflow-hidden shrink-0 bg-linear-to-br from-blue-500/20 to-cyan-500/20 flex items-center justify-center">
                        {user.avatar_url
                          ? <img src={user.avatar_url} alt="" className="h-full w-full object-cover" />
                          : <User className="h-4 w-4 text-blue-400" />}
                      </div>
                      <div className="min-w-0">
                        <p className={`text-sm font-medium truncate ${theme.text.primary}`}>{user.full_name || user.email}</p>
                        <p className={`text-xs truncate ${theme.text.muted}`}>{user.email}</p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleRevoke(user.id)}
                      title="Revoke access"
                      className="p-1.5 rounded-lg hover:bg-red-500/15 transition-colors ml-2 opacity-0 group-hover:opacity-100 shrink-0"
                    >
                      <X className="h-3.5 w-3.5 text-red-400" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Shared with me */}
        <Card className="glass-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <UserCheck className="h-5 w-5 text-green-400" />
              Shared With Me
            </CardTitle>
            <CardDescription>View another user&apos;s genetic insights</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {sharesLoading ? (
              <div className="flex items-center justify-center py-4">
                <div className="animate-spin rounded-full h-5 w-5 border-2 border-green-500 border-t-transparent" />
              </div>
            ) : sharedWithMe.length === 0 ? (
              <p className={`text-sm ${theme.text.muted} text-center py-2`}>No one has shared their dashboard with you yet</p>
            ) : (
              sharedWithMe.map(user => {
                const isViewing = viewingSharedUser?.id === user.id
                return (
                  <div key={user.id} className={`flex items-center justify-between p-2.5 rounded-lg transition-colors ${isViewing ? 'bg-green-500/10 border border-green-500/30' : 'glass-card'}`}>
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="h-8 w-8 rounded-full border border-green-500/30 overflow-hidden shrink-0 bg-linear-to-br from-green-500/20 to-emerald-500/20 flex items-center justify-center">
                        {user.avatar_url
                          ? <img src={user.avatar_url} alt="" className="h-full w-full object-cover" />
                          : <User className="h-4 w-4 text-green-400" />}
                      </div>
                      <div className="min-w-0">
                        <p className={`text-sm font-medium truncate ${theme.text.primary}`}>{user.full_name || user.email}</p>
                        <p className={`text-xs truncate ${theme.text.muted}`}>{user.email}</p>
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant={isViewing ? 'default' : 'outline'}
                      className={`gap-1.5 shrink-0 ml-2 text-xs ${isViewing ? 'bg-green-600 hover:bg-green-700' : ''}`}
                      onClick={() => onViewSharedUser?.(isViewing ? null : { id: user.id, name: user.full_name || user.email, email: user.email })}
                    >
                      {isViewing ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                      {isViewing ? 'Switch to my data' : 'View insights'}
                    </Button>
                  </div>
                )
              })
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Saved Variants ───────────────────────────────────── */}
      <Card className="glass-card">
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Bookmark className="h-5 w-5 text-blue-400" />
                Saved Variants
              </CardTitle>
              <CardDescription>
                Variants you bookmarked from the variant detail dialog
              </CardDescription>
            </div>
            {savedVariants.length > 0 && (
              <button
                type="button"
                onClick={printVariants}
                disabled={printLoading}
                title="Export for doctor (print)"
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-blue-500/30 text-blue-400 hover:bg-blue-500/10 transition-colors shrink-0 mt-1 disabled:opacity-50"
              >
                {printLoading
                  ? <><div className="h-3.5 w-3.5 rounded-full border border-blue-400 border-t-transparent animate-spin" /> Preparing…</>
                  : <><Printer className="h-3.5 w-3.5" /> Print / Export</>
                }
              </button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {savedLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-6 w-6 border-2 border-blue-500 border-t-transparent" />
            </div>
          ) : savedVariants.length === 0 ? (
            <p className={`text-sm ${theme.text.secondary} text-center py-6`}>
              No saved variants yet. Open a variant detail dialog and click the bookmark icon to save it here.
            </p>
          ) : (
            <div className="space-y-2">
              {savedVariants.map(v => (
                <div
                  key={v.id}
                  className="flex flex-col p-3 glass-card rounded-lg group gap-2"
                >
                  {/* Top row: variant info + actions */}
                  <div className="flex items-center justify-between gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setVariantDialogRsid(v.rsid)
                        setVariantDialogGene(v.gene || undefined)
                        setVariantDialogGenotype(v.genotype || undefined)
                      }}
                      className="flex-1 flex items-center gap-3 text-left min-w-0"
                    >
                      <Dna className="h-4 w-4 text-blue-400 shrink-0" />
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className={`font-medium ${theme.text.primary}`}>{v.rsid}</span>
                          {v.gene && (
                            <span className={`text-xs ${theme.text.muted}`}>({v.gene})</span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          {v.most_severe_consequence && (
                            <span className={`text-xs ${theme.text.secondary}`}>
                              {v.most_severe_consequence.replace(/_/g, ' ')}
                            </span>
                          )}
                          {v.clinical_significance && (
                            <span className={`text-xs px-1.5 py-0.5 rounded ${
                              v.clinical_significance.toLowerCase().includes('pathogenic')
                                ? 'bg-red-500/15 text-red-400'
                                : v.clinical_significance.toLowerCase().includes('benign')
                                  ? 'bg-green-500/15 text-green-400'
                                  : 'bg-yellow-500/15 text-yellow-400'
                            }`}>
                              {v.clinical_significance}
                            </span>
                          )}
                        </div>
                      </div>
                      <ExternalLink className={`h-3.5 w-3.5 ${theme.text.muted} opacity-0 group-hover:opacity-100 transition-opacity shrink-0`} />
                    </button>
                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        type="button"
                        onClick={() => setEditingNote(editingNote?.rsid === v.rsid ? null : { rsid: v.rsid, text: v.note || '' })}
                        title={v.note ? 'Edit note' : 'Add note'}
                        className={`p-1.5 rounded-lg transition-colors ${editingNote?.rsid === v.rsid ? 'bg-blue-500/20 text-blue-400' : `hover:bg-blue-500/10 ${v.note ? 'text-blue-400' : `${theme.text.muted} opacity-0 group-hover:opacity-100`}`}`}
                      >
                        {v.note ? <MessageSquare className="h-3.5 w-3.5" /> : <Pencil className="h-3.5 w-3.5" />}
                      </button>
                      <button
                        type="button"
                        onClick={() => removeSavedVariant(v.rsid)}
                        title="Remove from saved"
                        className={`p-1.5 rounded-lg hover:bg-red-500/15 transition-colors opacity-0 group-hover:opacity-100`}
                      >
                        <Trash2 className="h-3.5 w-3.5 text-red-400" />
                      </button>
                    </div>
                  </div>

                  {/* Existing note display (when not editing) */}
                  {v.note && editingNote?.rsid !== v.rsid && (
                    <div className={`text-xs ${theme.text.secondary} italic pl-7 leading-relaxed`}>
                      &ldquo;{v.note}&rdquo;
                    </div>
                  )}

                  {/* Inline note editor */}
                  {editingNote?.rsid === v.rsid && (
                    <div className="pl-7 flex flex-col gap-1.5">
                      <textarea
                        value={editingNote.text}
                        onChange={e => setEditingNote({ rsid: v.rsid, text: e.target.value })}
                        placeholder="Add a note for your doctor… (e.g. Ask about this variant at next appointment)"
                        rows={2}
                        className={`w-full text-xs px-2.5 py-2 rounded-lg border ${theme.text.secondary} resize-none focus:outline-none focus:ring-2 focus:ring-blue-500/40 ${theme.glass}`}
                        style={{ borderColor: 'rgba(99,102,241,0.3)', background: 'rgba(99,102,241,0.05)' }}
                        autoFocus
                        onKeyDown={e => {
                          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) saveNote(v.rsid, editingNote.text)
                          if (e.key === 'Escape') setEditingNote(null)
                        }}
                      />
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => saveNote(v.rsid, editingNote.text)}
                          disabled={noteSaving}
                          className="text-xs px-2.5 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white transition-colors disabled:opacity-50"
                        >
                          {noteSaving ? 'Saving…' : 'Save note'}
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingNote(null)}
                          className={`text-xs px-2.5 py-1 rounded hover:bg-gray-500/10 transition-colors ${theme.text.muted}`}
                        >
                          Cancel
                        </button>
                        <span className={`text-[10px] ${theme.text.muted}`}>⌘Enter to save · Esc to cancel</span>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Variant Detail Dialog for saved item */}
      {variantDialogRsid && (
        <VariantDetailDialog
          rsid={variantDialogRsid}
          gene={variantDialogGene}
          genotype={variantDialogGenotype}
          token={token}
          isDarkMode={theme.glass.includes('slate')}
          open={!!variantDialogRsid}
          onOpenChange={(open) => {
            if (!open) {
              setVariantDialogRsid(null)
              setVariantDialogGene(undefined)
              setVariantDialogGenotype(undefined)
              fetchSavedVariants()
            }
          }}
        />
      )}
    </div>
  )
}
