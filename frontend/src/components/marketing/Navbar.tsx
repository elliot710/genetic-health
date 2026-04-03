'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Dna, Menu, X } from 'lucide-react'
import { apiUrl } from '@/lib/api'

const NAV_LINKS = [
  { href: '/#features', label: 'Features' },
  { href: '/#how-it-works', label: 'How it works' },
  { href: '/about', label: 'About' },
]

export default function Navbar() {
  const [isOpen, setIsOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const [isSignedIn, setIsSignedIn] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    fetch(apiUrl('/auth/me'), { credentials: 'include' })
      .then(r => setIsSignedIn(r.ok))
      .catch(() => setIsSignedIn(false))
  }, [])

  return (
    <header
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled
          ? 'bg-slate-950/90 backdrop-blur-xl border-b border-slate-700/50 shadow-lg shadow-black/20'
          : 'bg-transparent'
      }`}
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="flex items-center justify-center w-9 h-9 rounded-xl bg-linear-to-br from-teal-500 to-cyan-500 shadow-lg shadow-teal-500/30 group-hover:shadow-teal-500/50 transition-shadow">
              <Dna className="w-5 h-5 text-white" />
            </div>
            <span className="text-lg font-bold text-white tracking-tight">
              Epigenic
            </span>
          </Link>

          {/* Desktop nav */}
          <nav className="hidden md:flex items-center gap-8">
            {NAV_LINKS.map(link => (
              <Link
                key={link.href}
                href={link.href}
                className="text-sm text-slate-300 hover:text-white transition-colors"
              >
                {link.label}
              </Link>
            ))}
          </nav>

          {/* CTA */}
          <div className="hidden md:flex items-center gap-3">
            {isSignedIn ? (
              <Link
                href="/app"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-linear-to-r from-teal-500 to-cyan-500 text-white text-sm font-semibold hover:from-teal-400 hover:to-cyan-400 transition-all shadow-lg shadow-teal-500/25 hover:shadow-teal-500/40 hover:-translate-y-px"
              >
                Launch App
              </Link>
            ) : (
              <Link
                href="/app"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-linear-to-r from-teal-500 to-cyan-500 text-white text-sm font-semibold hover:from-teal-400 hover:to-cyan-400 transition-all shadow-lg shadow-teal-500/25 hover:shadow-teal-500/40 hover:-translate-y-px"
              >
                Sign in
              </Link>
            )}
          </div>

          {/* Mobile toggle */}
          <button
            onClick={() => setIsOpen(!isOpen)}
            className="md:hidden p-2 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800 transition-colors"
            aria-label="Toggle menu"
          >
            {isOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {isOpen && (
        <div className="md:hidden bg-slate-950/95 backdrop-blur-xl border-t border-slate-700/50">
          <div className="px-4 py-4 space-y-3">
            {NAV_LINKS.map(link => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setIsOpen(false)}
                className="block text-sm text-slate-300 hover:text-white py-2 transition-colors"
              >
                {link.label}
              </Link>
            ))}
            <div className="pt-3 border-t border-slate-700/50 flex flex-col gap-2">
              <Link
                href="/app"
                onClick={() => setIsOpen(false)}
                className="text-center py-2.5 rounded-xl bg-linear-to-r from-teal-500 to-cyan-500 text-white text-sm font-semibold"
              >
                {isSignedIn ? 'Launch App' : 'Sign in'}
              </Link>
            </div>
          </div>
        </div>
      )}
    </header>
  )
}
