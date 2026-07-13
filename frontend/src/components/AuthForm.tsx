'use client'

import { useState } from 'react'
import { Eye, EyeOff, Mail, Lock, User, Dna, Sparkles, Shield, Sun, Moon, CheckCircle, ArrowLeft } from 'lucide-react'
import { getTheme } from '../utils/theme'
import { useDarkMode } from '@/hooks/useDarkMode'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { apiFetch } from '@/lib/api'

interface AuthFormProps {
  onLogin: () => void
  isDarkMode?: boolean
  isHydrated?: boolean
  initialMode?: 'login' | 'reset'
  resetToken?: string
}

export default function AuthForm({ onLogin, isDarkMode: initialDarkMode = false, isHydrated = true, initialMode, resetToken }: AuthFormProps) {
  const [isLogin, setIsLogin] = useState(true)
  // 'login' | 'register' | 'forgot' | 'reset'
  const [authView, setAuthView] = useState<'login' | 'register' | 'forgot' | 'reset'>(
    initialMode === 'reset' && resetToken ? 'reset' : 'login'
  )
  const [formData, setFormData] = useState({
    email: '',
    username: '',
    password: '',
    fullName: '',
    newPassword: '',
    confirmPassword: '',
    forgotEmail: '',
  })
  const [showPassword, setShowPassword] = useState(false)
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [successMsg, setSuccessMsg] = useState('')
  const [showSuccessDialog, setShowSuccessDialog] = useState(false)
  
  const { isDarkMode, setIsDarkMode } = useDarkMode({
    initialValue: initialDarkMode,
    enabled: isHydrated,
    syncDocumentClass: false,
  })

  const theme = getTheme(isDarkMode)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    setSuccessMsg('')

    try {
      if (authView === 'forgot') {
        await apiFetch('/auth/forgot-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: formData.forgotEmail }),
        })
        setSuccessMsg('If that email is registered, a reset link has been sent. Check your inbox.')
        return
      }

      if (authView === 'reset') {
        if (formData.newPassword !== formData.confirmPassword) {
          setError('Passwords do not match')
          return
        }
        if (formData.newPassword.length < 6) {
          setError('Password must be at least 6 characters')
          return
        }
        await apiFetch('/auth/reset-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: resetToken, new_password: formData.newPassword }),
        })
        setSuccessMsg('Password reset! You can now sign in.')
        setTimeout(() => setAuthView('login'), 2000)
        return
      }

      const endpoint = isLogin ? '/auth/login' : '/auth/register'
      const body = isLogin
        ? { username: formData.email, password: formData.password }
        : {
            email: formData.email,
            username: formData.username || formData.email,
            password: formData.password,
            full_name: formData.fullName,
          }

      await apiFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (isLogin) {
        onLogin()
      } else {
        setIsLogin(true)
        setAuthView('login')
        setError('')
        setShowSuccessDialog(true)
      }
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const switchView = (view: 'login' | 'register' | 'forgot' | 'reset') => {
    setAuthView(view)
    setIsLogin(view === 'login')
    setError('')
    setSuccessMsg('')
  }

  const renderForm = () => {
    if (authView === 'forgot') {
      return (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Mail className={`h-5 w-5 ${theme.text.muted}`} />
            </div>
            <Input
              type="email"
              placeholder="Your email address"
              value={formData.forgotEmail}
              onChange={(e) => setFormData({...formData, forgotEmail: e.target.value})}
              className={`pl-10 pr-4 py-3 border ${theme.form.input.border} ${theme.form.input.text} ${theme.form.input.placeholder} ${theme.form.input.bg} ${theme.form.input.focus}`}
              required
            />
          </div>
          {error && <p className={`${theme.error.text} text-sm text-center`}>{error}</p>}
          {successMsg && <p className={`${theme.success?.text ?? 'text-green-500'} text-sm text-center`}>{successMsg}</p>}
          <Button type="submit" disabled={loading} className={`w-full py-3 h-auto ${loading ? 'bg-gray-400/80 text-white' : theme.form.button.primary}`}>
            {loading ? <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : 'Send Reset Link'}
          </Button>
          <button type="button" onClick={() => switchView('login')} className={`w-full text-sm ${theme.text.accent} flex items-center justify-center gap-1 mt-2`}>
            <ArrowLeft className="w-4 h-4" /> Back to sign in
          </button>
        </form>
      )
    }

    if (authView === 'reset') {
      return (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Lock className={`h-5 w-5 ${theme.text.muted}`} />
            </div>
            <Input
              type={showNewPassword ? 'text' : 'password'}
              placeholder="New password"
              value={formData.newPassword}
              onChange={(e) => setFormData({...formData, newPassword: e.target.value})}
              className={`pl-10 pr-12 py-3 border ${theme.form.input.border} ${theme.form.input.text} ${theme.form.input.placeholder} ${theme.form.input.bg} ${theme.form.input.focus}`}
              required
            />
            <button type="button" onClick={() => setShowNewPassword(!showNewPassword)} className={`absolute inset-y-0 right-0 pr-3 flex items-center ${theme.text.muted}`}>
              {showNewPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
            </button>
          </div>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <Lock className={`h-5 w-5 ${theme.text.muted}`} />
            </div>
            <Input
              type="password"
              placeholder="Confirm new password"
              value={formData.confirmPassword}
              onChange={(e) => setFormData({...formData, confirmPassword: e.target.value})}
              className={`pl-10 pr-4 py-3 border ${theme.form.input.border} ${theme.form.input.text} ${theme.form.input.placeholder} ${theme.form.input.bg} ${theme.form.input.focus}`}
              required
            />
          </div>
          {error && <p className={`${theme.error.text} text-sm text-center`}>{error}</p>}
          {successMsg && <p className={`text-green-500 text-sm text-center`}>{successMsg}</p>}
          <Button type="submit" disabled={loading} className={`w-full py-3 h-auto ${loading ? 'bg-gray-400/80 text-white' : theme.form.button.primary}`}>
            {loading ? <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : 'Reset Password'}
          </Button>
        </form>
      )
    }

    // login / register forms
    return (
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="relative">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Mail className={`h-5 w-5 ${theme.text.muted}`} />
          </div>
          <Input
            type="email"
            name="email"
            autoComplete="email"
            placeholder="Email address"
            value={formData.email}
            onChange={(e) => setFormData({...formData, email: e.target.value})}
            className={`pl-10 pr-4 py-3 border ${theme.form.input.border} ${theme.form.input.text} ${theme.form.input.placeholder} ${theme.form.input.bg} ${theme.form.input.focus} backdrop-blur-sm`}
            required
          />
        </div>

        {!isLogin && (
          <>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <User className={`h-5 w-5 ${theme.text.muted}`} />
              </div>
              <Input
                type="text"
                name="username"
                autoComplete="username"
                placeholder="Username (optional)"
                value={formData.username}
                onChange={(e) => setFormData({...formData, username: e.target.value})}
                className={`pl-10 pr-4 py-3 border ${theme.form.input.border} ${theme.form.input.text} ${theme.form.input.placeholder} ${theme.form.input.bg} ${theme.form.input.focus} backdrop-blur-sm`}
              />
            </div>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Sparkles className={`h-5 w-5 ${theme.text.muted}`} />
              </div>
              <Input
                type="text"
                name="fullName"
                autoComplete="name"
                placeholder="Full name"
                value={formData.fullName}
                onChange={(e) => setFormData({...formData, fullName: e.target.value})}
                className={`pl-10 pr-4 py-3 border ${theme.form.input.border} ${theme.form.input.text} ${theme.form.input.placeholder} ${theme.form.input.bg} ${theme.form.input.focus} backdrop-blur-sm`}
                required
              />
            </div>
          </>
        )}

        <div className="relative">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Lock className={`h-5 w-5 ${theme.text.muted}`} />
          </div>
          <Input
            type={showPassword ? 'text' : 'password'}
            name="password"
            autoComplete={isLogin ? 'current-password' : 'new-password'}
            placeholder="Password"
            value={formData.password}
            onChange={(e) => setFormData({...formData, password: e.target.value})}
            className={`pl-10 pr-12 py-3 border ${theme.form.input.border} ${theme.form.input.text} ${theme.form.input.placeholder} ${theme.form.input.bg} ${theme.form.input.focus} backdrop-blur-sm`}
            required
          />
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className={`absolute inset-y-0 right-0 pr-3 flex items-center ${theme.text.muted}`}
          >
            {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
          </button>
        </div>

        {isLogin && (
          <div className="text-right">
            <button type="button" onClick={() => switchView('forgot')} className={`text-sm ${theme.text.accent} hover:underline`}>
              Forgot password?
            </button>
          </div>
        )}

        {error && (
          <div className={`p-3 ${theme.error.bg} border ${theme.error.border} rounded-lg`}>
            <p className={`${theme.error.text} text-sm text-center`}>{error}</p>
          </div>
        )}

        <Button
          type="submit"
          disabled={loading}
          className={`w-full py-3 h-auto backdrop-blur-xl shadow-lg ${loading ? 'bg-gray-400/80 text-white cursor-not-allowed' : theme.form.button.primary}`}
        >
          {loading ? (
            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : (
            <><Shield className="w-5 h-5 mr-2" /><span>{isLogin ? 'Sign In' : 'Create Account'}</span></>
          )}
        </Button>

        {/* Google OAuth */}
        <div className="relative flex items-center gap-3 my-1">
          <div className={`flex-1 h-px ${isDarkMode ? 'bg-slate-600' : 'bg-gray-200'}`} />
          <span className={`text-xs ${theme.text.muted}`}>or</span>
          <div className={`flex-1 h-px ${isDarkMode ? 'bg-slate-600' : 'bg-gray-200'}`} />
        </div>

        <a
          href={`${process.env.NEXT_PUBLIC_API_URL || 'https://api.epigenic.xyz'}/auth/google`}
          className={`flex items-center justify-center gap-3 w-full py-3 rounded-lg border font-medium text-sm transition-all ${
            isDarkMode
              ? 'bg-white/5 border-slate-600 text-gray-200 hover:bg-white/10'
              : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
          }`}
        >
          <svg viewBox="0 0 24 24" className="w-5 h-5" xmlns="http://www.w3.org/2000/svg">
            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
          </svg>
          Continue with Google
        </a>
      </form>
    )
  }

  const getTitle = () => {
    if (authView === 'forgot') return 'Reset your password'
    if (authView === 'reset') return 'Choose new password'
    return isLogin ? 'Welcome back' : 'Create your account'
  }

  return (
    <div className={`min-h-screen flex items-center justify-center p-4 relative overflow-hidden ${theme.background}`}>
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className={`absolute -top-40 -right-40 w-96 h-96 ${theme.blobs.primary} rounded-full filter blur-3xl animate-float`}></div>
        <div className={`absolute top-1/3 -left-40 w-80 h-80 ${theme.blobs.secondary} rounded-full filter blur-3xl animate-float-delayed`}></div>
        <div className={`absolute bottom-0 right-1/3 w-72 h-72 ${theme.blobs.tertiary} rounded-full filter blur-3xl animate-float-slow`}></div>
      </div>

      <div className="w-full max-w-md relative z-10">
        <Card className={`${theme.glass} border ${theme.glassBorder} rounded-2xl backdrop-blur-xl shadow-2xl relative`}>
          <CardContent className="p-8">
            <div className="absolute top-4 right-4">
              <Button variant="ghost" size="icon" onClick={() => setIsDarkMode(!isDarkMode)} className={`${theme.glassSecondary} border ${theme.glassSecondaryBorder} backdrop-blur-sm`}>
                {isDarkMode ? <Sun className={`h-4 w-4 ${theme.warning.text}`} /> : <Moon className={`h-4 w-4 ${theme.text.secondary}`} />}
              </Button>
            </div>

            <div className="text-center mb-8">
              <div className={`inline-flex items-center justify-center w-16 h-16 backdrop-blur-xl rounded-xl mb-4 border shadow-lg ${theme.primary.gradient} ${theme.glassBorder}`}>
                <Dna className="w-8 h-8 text-white" />
              </div>
              <h1 className={`text-2xl font-bold ${theme.text.primary} mb-2`}>Genetic Health Analysis Toolkit</h1>
              <p className={`${theme.text.secondary} text-sm`}>{getTitle()}</p>
            </div>

            {renderForm()}

            {(authView === 'login' || authView === 'register') && (
              <div className="mt-6 text-center">
                <p className={`${theme.text.secondary} text-sm mb-3`}>
                  {isLogin ? "Don't have an account?" : "Already have an account?"}
                </p>
                <button
                  onClick={() => switchView(isLogin ? 'register' : 'login')}
                  className={`${theme.text.accent} font-medium transition-colors duration-200 text-sm`}
                >
                  {isLogin ? 'Create new account' : 'Sign in instead'}
                </button>
              </div>
            )}

            <div className={`mt-6 p-3 ${theme.glassSecondary} border ${theme.glassSecondaryBorder} rounded-lg backdrop-blur-sm`}>
              <div className={`flex items-center space-x-2 ${theme.text.secondary} text-xs`}>
                <Shield className="w-4 h-4" />
                <span>Your genetic data is encrypted and secure</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <style jsx>{`
        @keyframes float { 0%, 100% { transform: translate(0px, 0px) scale(1) rotate(0deg); } 33% { transform: translate(30px, -30px) scale(1.1) rotate(2deg); } 66% { transform: translate(-20px, 20px) scale(0.9) rotate(-1deg); } }
        @keyframes float-delayed { 0%, 100% { transform: translate(0px, 0px) scale(1) rotate(0deg); } 33% { transform: translate(-25px, 25px) scale(1.05) rotate(-2deg); } 66% { transform: translate(20px, -15px) scale(0.95) rotate(1deg); } }
        @keyframes float-slow { 0%, 100% { transform: translate(0px, 0px) scale(1) rotate(0deg); } 50% { transform: translate(15px, -15px) scale(1.03) rotate(1deg); } }
        .animate-float { animation: float 15s ease-in-out infinite; }
        .animate-float-delayed { animation: float-delayed 18s ease-in-out infinite; animation-delay: 2s; }
        .animate-float-slow { animation: float-slow 20s ease-in-out infinite; animation-delay: 4s; }
      `}</style>

      <Dialog open={showSuccessDialog} onOpenChange={setShowSuccessDialog}>
        <DialogContent className={`${theme.glass} border ${theme.glassBorder} backdrop-blur-xl sm:max-w-md`}>
          <DialogHeader>
            <div className="flex justify-center mb-2">
              <div className={`p-3 rounded-full ${isDarkMode ? 'bg-emerald-500/20' : 'bg-emerald-50'}`}>
                <CheckCircle className={`h-8 w-8 ${isDarkMode ? 'text-emerald-400' : 'text-emerald-500'}`} />
              </div>
            </div>
            <DialogTitle className={`text-center text-lg ${theme.text.primary}`}>Account Created Successfully</DialogTitle>
            <DialogDescription className={`text-center ${theme.text.secondary}`}>Your account has been created. Please log in with your credentials.</DialogDescription>
          </DialogHeader>
          <DialogFooter className="sm:justify-center">
            <Button onClick={() => setShowSuccessDialog(false)} className={`px-8 ${theme.form.button.primary}`}>Sign In</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
