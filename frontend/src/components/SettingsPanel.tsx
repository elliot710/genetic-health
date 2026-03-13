'use client'

import { useState, useEffect, useRef } from 'react'
import { User, Mail, Key, Save, Check, Dna, Upload, Shield, Camera } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { DashboardData } from './categories/types'

const API = 'http://localhost:8000'

interface SettingsPanelProps {
  token?: string
  theme: ReturnType<typeof import('@/utils/theme').getTheme>
  data?: DashboardData
  onProfileUpdate?: () => void
}

export default function SettingsPanel({ token, theme, data, onProfileUpdate }: SettingsPanelProps) {
  const [profile, setProfile] = useState({ email: '', username: '', full_name: '', avatar_url: '' })
  const [passwords, setPasswords] = useState({ current: '', new_password: '', confirm: '' })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null)
  const [pwMessage, setPwMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const res = await fetch(`${API}/auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        if (res.ok) {
          const data = await res.json()
          setProfile({ email: data.email, username: data.username, full_name: data.full_name || '', avatar_url: data.avatar_url || '' })
        }
      } finally {
        setLoading(false)
      }
    }
    fetchProfile()
  }, [token])

  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setMessage({ text: 'Please select an image file', type: 'error' })
      return
    }
    if (file.size > 350_000) {
      setMessage({ text: 'Image must be under 350KB', type: 'error' })
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
    setMessage(null)
    try {
      const res = await fetch(`${API}/auth/me`, {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ full_name: profile.full_name, avatar_url: profile.avatar_url || '' }),
      })
      if (res.ok) {
        setMessage({ text: 'Profile updated successfully', type: 'success' })
        onProfileUpdate?.()
      } else {
        const err = await res.json().catch(() => ({ detail: 'Failed to update' }))
        setMessage({ text: err.detail || 'Failed to update', type: 'error' })
      }
    } catch {
      setMessage({ text: 'Network error', type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  const changePassword = async () => {
    setPwMessage(null)
    if (passwords.new_password !== passwords.confirm) {
      setPwMessage({ text: 'Passwords do not match', type: 'error' })
      return
    }
    if (passwords.new_password.length < 6) {
      setPwMessage({ text: 'Password must be at least 6 characters', type: 'error' })
      return
    }
    setSaving(true)
    try {
      const res = await fetch(`${API}/auth/change-password`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_password: passwords.current,
          new_password: passwords.new_password,
        }),
      })
      if (res.ok) {
        setPwMessage({ text: 'Password changed successfully', type: 'success' })
        setPasswords({ current: '', new_password: '', confirm: '' })
      } else {
        const err = await res.json().catch(() => ({ detail: 'Failed to change password' }))
        setPwMessage({ text: err.detail || 'Failed to change password', type: 'error' })
      }
    } catch {
      setPwMessage({ text: 'Network error', type: 'error' })
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
        <div className="p-3 bg-gradient-to-br from-blue-500/20 to-cyan-500/20 rounded-xl border border-blue-500/30">
          <User className="h-7 w-7 text-blue-400" />
        </div>
        <div>
          <h2 className={`text-2xl font-bold ${theme.text.primary}`}>Settings</h2>
          <p className={`text-sm ${theme.text.secondary}`}>Manage your profile and preferences</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left column */}
        <div className="space-y-6">
          {/* Avatar + Profile Card */}
          <Card className="glass-card">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Mail className="h-5 w-5" />
                Profile
              </CardTitle>
              <CardDescription>Your account information</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Avatar */}
              <div className="flex items-center gap-5">
                <div className="relative group">
                  <div
                    className="h-20 w-20 rounded-full border-2 border-blue-500/40 overflow-hidden flex items-center justify-center bg-gradient-to-br from-blue-500/20 to-cyan-500/20 cursor-pointer"
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
                  {message.text}
                </p>
              )}
              <Button onClick={saveProfile} disabled={saving} className="gap-2">
                <Save className="h-4 w-4" />
                {saving ? 'Saving...' : 'Save Profile'}
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Right column */}
        <div className="space-y-6">
          {/* Your Data Card */}
          {(data?.summary?.total_variants ?? 0) > 0 && (
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
                    <div key={index} className={`flex items-center justify-between p-3 glass-card rounded-lg`}>
                      <div className="flex items-center gap-2">
                        <item.icon className={`h-4 w-4 ${theme.text.muted}`} />
                        <span className={`text-sm ${theme.text.secondary}`}>{item.label}</span>
                      </div>
                      <span className={`text-sm font-medium ${theme.text.primary} truncate max-w-[200px]`} title={String(item.value)}>
                        {item.value}
                      </span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Password Card */}
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
                  {pwMessage.text}
                </p>
              )}
              <Button onClick={changePassword} disabled={saving || !passwords.current || !passwords.new_password} className="gap-2">
                <Key className="h-4 w-4" />
                {saving ? 'Changing...' : 'Change Password'}
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
