'use client'

import { useState, useEffect } from 'react'
import { Eye, EyeOff, Mail, Lock, User, Dna, Sparkles, Shield, Sun, Moon } from 'lucide-react'
import { getTheme } from '../utils/theme'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'

interface AuthFormProps {
  onLogin: (token: string) => void
  isDarkMode?: boolean
  isHydrated?: boolean
}

export default function AuthForm({ onLogin, isDarkMode: initialDarkMode = false, isHydrated = true }: AuthFormProps) {
  const [isLogin, setIsLogin] = useState(true)
  const [formData, setFormData] = useState({
    email: '',
    username: '',
    password: '',
    fullName: ''
  })
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  
  // Local dark mode state for auth form - initialize consistently
  const [isDarkMode, setIsDarkMode] = useState(initialDarkMode)

  // Load theme from localStorage after hydration
  useEffect(() => {
    if (isHydrated && typeof window !== 'undefined') {
      const saved = localStorage.getItem('darkMode')
      if (saved) {
        setIsDarkMode(JSON.parse(saved))
      }
    }
  }, [isHydrated])

  // Save theme preference to localStorage whenever it changes
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('darkMode', JSON.stringify(isDarkMode))
    }
  }, [isDarkMode])

  // Get theme object
  const theme = getTheme(isDarkMode)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    try {
      const endpoint = isLogin ? '/auth/login' : '/auth/register'
      const body = isLogin 
        ? { username: formData.email, password: formData.password }
        : { 
            email: formData.email, 
            username: formData.username || formData.email, 
            password: formData.password, 
            full_name: formData.fullName 
          }

      const response = await fetch(`http://localhost:8000${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || 'Authentication failed')
      }

      if (isLogin) {
        localStorage.setItem('token', data.access_token)
        onLogin(data.access_token)
      } else {
        setIsLogin(true)
        setError('')
        alert('Account created successfully! Please log in.')
      }
    } catch (err: unknown) {
      const error = err as Error
      setError(error.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={`min-h-screen flex items-center justify-center p-4 relative overflow-hidden ${theme.background}`}>
      {/* Glassmorphism Background Elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className={`absolute -top-40 -right-40 w-96 h-96 ${theme.blobs.primary} rounded-full filter blur-3xl animate-float`}></div>
        <div className={`absolute top-1/3 -left-40 w-80 h-80 ${theme.blobs.secondary} rounded-full filter blur-3xl animate-float-delayed`}></div>
        <div className={`absolute bottom-0 right-1/3 w-72 h-72 ${theme.blobs.tertiary} rounded-full filter blur-3xl animate-float-slow`}></div>
      </div>

      <div className="w-full max-w-md relative z-10">
        {/* Main Container - Glassmorphism design */}
        <Card className={`${theme.glass} border ${theme.glassBorder} rounded-2xl backdrop-blur-xl shadow-2xl relative`}>
          <CardContent className="p-8">
          {/* Theme Toggle - Inside wrapper */}
          <div className="absolute top-4 right-4">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setIsDarkMode(!isDarkMode)}
              className={`${theme.glassSecondary} border ${theme.glassSecondaryBorder} backdrop-blur-sm`}
            >
              {isDarkMode ? (
                <Sun className={`h-4 w-4 ${theme.warning.text}`} />
              ) : (
                <Moon className={`h-4 w-4 ${theme.text.secondary}`} />
              )}
            </Button>
          </div>

          {/* Header */}
          <div className="text-center mb-8">
            <div className={`inline-flex items-center justify-center w-16 h-16 backdrop-blur-xl rounded-xl mb-4 border shadow-lg ${theme.primary.gradient} ${theme.glassBorder}`}>
              <Dna className="w-8 h-8 text-white" />
            </div>
            <h1 className={`text-2xl font-bold ${theme.text.primary} mb-2`}>
              Genetic Health Analysis Toolkit
            </h1>
            <p className={`${theme.text.secondary} text-sm`}>
              {isLogin ? 'Welcome back' : 'Create your account'}
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email Field */}
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

            {/* Username Field (Registration Only) */}
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

            {/* Password Field */}
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
                className={`absolute inset-y-0 right-0 pr-3 flex items-center ${theme.text.muted} hover:${theme.text.secondary} transition-colors`}
              >
                {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
              </button>
            </div>

            {/* Error Message */}
            {error && (
              <div className={`p-3 ${theme.error.bg} border ${theme.error.border} rounded-lg backdrop-blur-sm`}>
                <p className={`${theme.error.text} text-sm text-center`}>{error}</p>
              </div>
            )}

            {/* Submit Button */}
            <Button
              type="submit"
              disabled={loading}
              className={`w-full py-3 h-auto backdrop-blur-xl shadow-lg ${
                loading 
                  ? 'bg-gray-400/80 text-white cursor-not-allowed border-gray-300' 
                  : theme.form.button.primary
              }`}
            >
              {loading ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
              ) : (
                <>
                  <Shield className="w-5 h-5 mr-2" />
                  <span>{isLogin ? 'Sign In' : 'Create Account'}</span>
                </>
              )}
            </Button>
          </form>

          {/* Toggle */}
          <div className="mt-6 text-center">
            <p className={`${theme.text.secondary} text-sm mb-3`}>
              {isLogin ? "Don't have an account?" : "Already have an account?"}
            </p>
            <button
              onClick={() => {
                setIsLogin(!isLogin)
                setError('')
                setFormData({ email: '', username: '', password: '', fullName: '' })
              }}
              className={`${theme.text.accent} hover:${theme.primary.text} font-medium transition-colors duration-200 text-sm`}
            >
              {isLogin ? 'Create new account' : 'Sign in instead'}
            </button>
          </div>

          {/* Security Notice */}
          <div className={`mt-6 p-3 ${theme.glassSecondary} border ${theme.glassSecondaryBorder} rounded-lg backdrop-blur-sm`}>
            <div className={`flex items-center space-x-2 ${theme.text.secondary} text-xs`}>
              <Shield className="w-4 h-4" />
              <span>Your genetic data is encrypted and secure</span>
            </div>
          </div>
          </CardContent>
        </Card>
      </div>

      {/* CSS Animations for Glassmorphism */}
      <style jsx>{`
        @keyframes float {
          0%, 100% { transform: translate(0px, 0px) scale(1) rotate(0deg); }
          33% { transform: translate(30px, -30px) scale(1.1) rotate(2deg); }
          66% { transform: translate(-20px, 20px) scale(0.9) rotate(-1deg); }
        }
        @keyframes float-delayed {
          0%, 100% { transform: translate(0px, 0px) scale(1) rotate(0deg); }
          33% { transform: translate(-25px, 25px) scale(1.05) rotate(-2deg); }
          66% { transform: translate(20px, -15px) scale(0.95) rotate(1deg); }
        }
        @keyframes float-slow {
          0%, 100% { transform: translate(0px, 0px) scale(1) rotate(0deg); }
          50% { transform: translate(15px, -15px) scale(1.03) rotate(1deg); }
        }
        .animate-float {
          animation: float 15s ease-in-out infinite;
        }
        .animate-float-delayed {
          animation: float-delayed 18s ease-in-out infinite;
          animation-delay: 2s;
        }
        .animate-float-slow {
          animation: float-slow 20s ease-in-out infinite;
          animation-delay: 4s;
        }
      `}</style>
    </div>
  )
}