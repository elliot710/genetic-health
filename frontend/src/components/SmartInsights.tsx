'use client'

import React, { useState, useCallback } from 'react'
import { Sparkles, RefreshCw, AlertCircle, Lightbulb, CheckCircle2, Brain, ChevronDown, ChevronUp } from 'lucide-react'
import { useThemeClasses, SectionCard } from './categories/shared'
import { apiUrl } from '@/lib/api'

interface InsightData {
  summary: string
  key_findings: string[]
  recommendations: string[]
  confidence: 'high' | 'medium' | 'low'
  provider?: string
  generated_at?: string
  error?: string
}

interface SmartInsightsProps {
  isDarkMode: boolean
  token?: string
  section?: string
  title?: string
  /** For variant-detail mode: pass rsid + full variant data directly */
  rsid?: string
  variantData?: Record<string, unknown>
  /** Compact mode for embedding inside dialogs (no outer SectionCard wrapper) */
  compact?: boolean
}

const confidenceColors: Record<string, { bg: string; text: string; label: string }> = {
  high: { bg: 'bg-green-500/15 border-green-500/30', text: 'text-green-400', label: 'High Confidence' },
  medium: { bg: 'bg-amber-500/15 border-amber-500/30', text: 'text-amber-400', label: 'Medium Confidence' },
  low: { bg: 'bg-slate-500/15 border-slate-500/30', text: 'text-slate-400', label: 'Low Confidence' },
}

export default function SmartInsights({ isDarkMode, token, section, title, rsid, variantData, compact }: SmartInsightsProps) {
  const theme = useThemeClasses(isDarkMode)
  const [insight, setInsight] = useState<InsightData | null>(null)
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState(true)
  const [status, setStatus] = useState<{ provider: string; enabled: boolean; openai_configured: boolean; anthropic_configured: boolean; gemini_configured: boolean } | null>(null)

  const isVariantMode = !!(rsid && variantData)

  const fetchInsight = useCallback(async () => {
    if (!token) return
    setLoading(true)
    try {
      let resp: Response
      if (isVariantMode) {
        resp = await fetch(apiUrl('/api/insights/generate-variant'), {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ rsid, variant_data: variantData }),
        })
      } else if (section) {
        resp = await fetch(apiUrl(`/api/insights/generate/${section}`), {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
        })
      } else {
        return
      }
      if (resp.ok) {
        const data = await resp.json()
        setInsight(data)
      } else {
        const err = await resp.json().catch(() => ({ detail: 'Request failed' }))
        setInsight({ summary: err.detail || 'Failed to generate insight', key_findings: [], recommendations: [], confidence: 'low', error: err.detail })
      }
    } catch {
      setInsight({ summary: 'Could not reach the insights service.', key_findings: [], recommendations: [], confidence: 'low', error: 'Network error' })
    } finally {
      setLoading(false)
    }
  }, [token, section, isVariantMode, rsid, variantData])

  const fetchStatus = useCallback(async () => {
    if (!token || status) return
    try {
      const resp = await fetch(apiUrl('/api/insights/status'), {
        credentials: 'include',
      })
      if (resp.ok) setStatus(await resp.json())
    } catch { /* ignore */ }
  }, [token, status])

  // Fetch status on first render
  React.useEffect(() => { fetchStatus() }, [fetchStatus])

  const conf = insight ? confidenceColors[insight.confidence] || confidenceColors.low : null
  const isConfigured = status?.openai_configured || status?.anthropic_configured || status?.gemini_configured
  const isEnabled = status?.enabled !== false

  // Hide when: admin-disabled, no API keys configured, or status not yet loaded
  if (!status || !isEnabled || !isConfigured) return null

  const content = (
      <div className="space-y-4">
        {/* Header row */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Brain className={`h-5 w-5 ${isDarkMode ? 'text-purple-400' : 'text-purple-600'}`} />
            <span className={`text-sm font-medium ${theme.textSecondary}`}>
              {status?.provider ? `Provider: ${status.provider}` : 'Smart Analysis'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {insight && (
              <button onClick={() => setExpanded(!expanded)} className={`p-1.5 rounded-lg ${theme.glass} border ${theme.border} hover:opacity-80 transition-opacity`}>
                {expanded ? <ChevronUp className={`h-4 w-4 ${theme.textSecondary}`} /> : <ChevronDown className={`h-4 w-4 ${theme.textSecondary}`} />}
              </button>
            )}
            <button
              onClick={fetchInsight}
              disabled={loading || !isConfigured || !isEnabled}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                isConfigured && isEnabled
                  ? isDarkMode
                    ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30 hover:bg-purple-500/30'
                    : 'bg-purple-50 text-purple-700 border border-purple-200 hover:bg-purple-100'
                  : 'opacity-50 cursor-not-allowed bg-slate-500/10 text-slate-400 border border-slate-500/20'
              }`}
            >
              {loading ? (
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Sparkles className="h-3.5 w-3.5" />
              )}
              {insight ? 'Refresh' : 'Generate'}
            </button>
          </div>
        </div>

        {/* Not configured state */}
        {isEnabled && !isConfigured && !insight && (
          <div className={`flex items-start gap-3 p-4 rounded-xl border ${isDarkMode ? 'bg-amber-500/5 border-amber-500/20' : 'bg-amber-50 border-amber-200'}`}>
            <AlertCircle className={`h-5 w-5 shrink-0 mt-0.5 ${isDarkMode ? 'text-amber-400' : 'text-amber-600'}`} />
            <div>
              <p className={`text-sm font-medium ${theme.textPrimary}`}>LLM API Key Required</p>
              <p className={`text-xs ${theme.textSecondary} mt-1`}>
                Set <code className="font-mono text-xs">GEMINI_API_KEY</code>, <code className="font-mono text-xs">OPENAI_API_KEY</code>, or <code className="font-mono text-xs">ANTHROPIC_API_KEY</code> environment variable to enable AI-powered insights.
              </p>
            </div>
          </div>
        )}

        {/* Insight content */}
        {insight && expanded && (
          <div className="space-y-4 animate-in fade-in duration-300">
            {/* Summary */}
            <div className={`p-4 rounded-xl border ${
              insight.error
                ? isDarkMode ? 'bg-red-500/10 border-red-500/30' : 'bg-red-50 border-red-200'
                : isDarkMode ? 'bg-slate-800/40 border-slate-700/50' : 'bg-slate-50 border-slate-200'
            }`}>
              <div className="flex items-start gap-2">
                {insight.error && <AlertCircle className={`h-4 w-4 shrink-0 mt-0.5 ${isDarkMode ? 'text-red-400' : 'text-red-500'}`} />}
                <p className={`text-sm leading-relaxed ${theme.textPrimary}`}>{insight.summary}</p>
              </div>
              {insight.error && (
                <p className={`mt-2 text-xs font-mono ${isDarkMode ? 'text-red-300/70' : 'text-red-600/70'} break-all`}>
                  {insight.error}
                </p>
              )}
              {conf && !insight.error && (
                <div className={`inline-flex items-center gap-1.5 mt-3 px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase border ${conf.bg} ${conf.text}`}>
                  <CheckCircle2 className="h-3 w-3" />
                  {conf.label}
                </div>
              )}
            </div>

            {/* Key findings */}
            {insight.key_findings.length > 0 && (
              <div>
                <h4 className={`text-xs font-semibold uppercase tracking-wider ${theme.textSecondary} mb-2`}>Key Findings</h4>
                <div className="space-y-2">
                  {insight.key_findings.map((finding, i) => (
                    <div key={i} className="flex items-start gap-2.5">
                      <div className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${isDarkMode ? 'bg-purple-400' : 'bg-purple-500'}`} />
                      <p className={`text-sm ${theme.textPrimary}`}>{finding}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Recommendations */}
            {insight.recommendations.length > 0 && (
              <div>
                <h4 className={`text-xs font-semibold uppercase tracking-wider ${theme.textSecondary} mb-2`}>Recommendations</h4>
                <div className="space-y-2">
                  {insight.recommendations.map((rec, i) => (
                    <div key={i} className="flex items-start gap-2.5">
                      <Lightbulb className={`h-4 w-4 shrink-0 mt-0.5 ${isDarkMode ? 'text-amber-400' : 'text-amber-500'}`} />
                      <p className={`text-sm ${theme.textPrimary}`}>{rec}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Disclaimer */}
            <p className={`text-[10px] ${theme.textSecondary} italic`}>
              AI-generated insight — not a substitute for professional medical advice.
            </p>
          </div>
        )}
      </div>
  )

  if (compact) {
    return (
      <div className={`rounded-xl p-4 border ${isDarkMode ? 'bg-white/5 border-white/10' : 'bg-gray-50 border-gray-200'}`}>
        {content}
      </div>
    )
  }

  return (
    <SectionCard
      title={title || 'AI Insights'}
      description={!isConfigured ? 'Configure an LLM API key to enable' : undefined}
      theme={theme}
    >
      {content}
    </SectionCard>
  )
}
