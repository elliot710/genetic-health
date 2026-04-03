import Link from 'next/link'
import {
  Dna, HeartPulse, Pill, Globe, Zap, Leaf, Baby, Brain, Smile, Fingerprint,
  FlaskConical, Shield, Star, ChevronRight, Upload, BarChart3, Sparkles,
  Lock, ArrowRight,
} from 'lucide-react'
import Navbar from '@/components/marketing/Navbar'
import Footer from '@/components/marketing/Footer'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Epigenic — Your Genetic Health Dashboard',
  description: 'Upload your VCF or CSV DNA data and explore 13 personalized health panels: disease risk, drug responses, ancestry, nutrition, sports, and more.',
  openGraph: {
    title: 'Epigenic — Your Genetic Health Dashboard',
    description: 'Upload your VCF or CSV DNA data and explore 13 personalized health panels: disease risk, drug responses, ancestry, nutrition, sports, and more.',
    url: 'https://epigenic.xyz',
    siteName: 'Epigenic',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Epigenic — Your Genetic Health Dashboard',
    description: 'Upload your VCF or CSV DNA data and explore 13 personalized health panels: disease risk, drug responses, ancestry, nutrition, sports, and more.',
  },
}

const PANELS = [
  { icon: HeartPulse, label: 'Health Risks', desc: 'Hereditary disease risk from ClinVar-backed variants', color: 'text-red-400', bg: 'bg-red-500/10 border-red-500/20' },
  { icon: Pill, label: 'Drug Responses', desc: 'Pharmacogenomics for 200+ medications', color: 'text-blue-400', bg: 'bg-blue-500/10 border-blue-500/20' },
  { icon: Globe, label: 'Ancestry', desc: 'Population ancestry & haplogroup estimation', color: 'text-yellow-400', bg: 'bg-yellow-500/10 border-yellow-500/20' },
  { icon: Zap, label: 'Sports Performance', desc: 'Athletic traits, VO2 max, muscle fiber composition', color: 'text-orange-400', bg: 'bg-orange-500/10 border-orange-500/20' },
  { icon: Leaf, label: 'Nutrition & Diet', desc: 'Nutrient metabolism, intolerances, sensitivities', color: 'text-green-400', bg: 'bg-green-500/10 border-green-500/20' },
  { icon: Baby, label: 'Carrier Status', desc: 'Autosomal & X-linked recessive disease carrier status', color: 'text-pink-400', bg: 'bg-pink-500/10 border-pink-500/20' },
  { icon: Brain, label: 'Cognitive Profile', desc: 'Neurodevelopmental factors, APOE, learning traits', color: 'text-purple-400', bg: 'bg-purple-500/10 border-purple-500/20' },
  { icon: Smile, label: 'Personality Traits', desc: 'Behavioral tendencies linked to dopamine & serotonin genes', color: 'text-indigo-400', bg: 'bg-indigo-500/10 border-indigo-500/20' },
  { icon: Fingerprint, label: 'Physical Traits', desc: 'Appearance: eye color, hair, skin pigmentation', color: 'text-cyan-400', bg: 'bg-cyan-500/10 border-cyan-500/20' },
  { icon: FlaskConical, label: 'Methylation', desc: 'MTHFR, B12, folate cycle & epigenetic markers', color: 'text-teal-400', bg: 'bg-teal-500/10 border-teal-500/20' },
  { icon: Shield, label: 'Detoxification', desc: 'Phase I/II enzyme activity & toxin sensitivity', color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/20' },
  { icon: Star, label: 'Rare Mutations', desc: 'Rare & clinically significant de novo variants', color: 'text-amber-400', bg: 'bg-amber-500/10 border-amber-500/20' },
  { icon: HeartPulse, label: 'Wellness Metrics', desc: 'Sleep, circadian rhythm, inflammation markers', color: 'text-lime-400', bg: 'bg-lime-500/10 border-lime-500/20' },
]

const FEATURES = [
  { icon: Upload, title: 'Upload Any Format', desc: 'Supports VCF (clinical grade) and CSV files from 23andMe, AncestryDNA, and other consumer genotyping services.' },
  { icon: BarChart3, title: '13 Analysis Panels', desc: 'From health risks to personality traits — comprehensive coverage of every aspect of your genetic fingerprint.' },
  { icon: Sparkles, title: 'Multi-Source Evidence', desc: 'Every finding is cross-referenced against ClinVar, gnomAD, Ensembl VEP, AlphaMissense, and PharmGKB.' },
  { icon: Lock, title: 'Your Data, Your Control', desc: 'All data is encrypted at rest and in transit. Delete your genetic data permanently at any time with one click.' },
]

const STEPS = [
  { n: '01', title: 'Upload your DNA file', body: 'Drag & drop a VCF or CSV from any major sequencing provider. Typical processing time is under 2 minutes.' },
  { n: '02', title: 'We analyze your variants', body: 'Our pipeline annotates every variant against six curated databases and applies pharmacogenomic models.' },
  { n: '03', title: 'Explore your dashboard', body: 'Navigate 13 specialized panels. Click any variant for a deep-dive with literature, population frequency, and drug interactions.' },
]

const STATS = [
  { value: '13', label: 'Analysis panels' },
  { value: '200+', label: 'Medications covered' },
  { value: '6', label: 'Evidence databases' },
  { value: '100%', label: 'Private & encrypted' },
]

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-white overflow-x-hidden">
      <Navbar />

      {/* Hero */}
      <section className="relative min-h-screen flex items-center pt-16">
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-teal-500/15 rounded-full blur-3xl animate-pulse" />
          <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl animate-pulse [animation-delay:1.5s]" />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-150 h-150 bg-slate-800/30 rounded-full blur-3xl" />
          <div
            className="absolute inset-0 opacity-[0.03]"
            style={{
              backgroundImage: 'linear-gradient(rgba(20,184,166,1) 1px, transparent 1px), linear-gradient(90deg, rgba(20,184,166,1) 1px, transparent 1px)',
              backgroundSize: '60px 60px',
            }}
          />
        </div>

        <div className="relative max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-24 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-teal-500/10 border border-teal-500/25 text-teal-400 text-xs font-medium mb-8">
            <Dna className="w-3.5 h-3.5" />
            Genetic health analysis — powered by ClinVar, gnomAD &amp; more
          </div>

          <h1 className="text-5xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight leading-[1.08] mb-6">
            Unlock your{' '}
            <span className="bg-linear-to-r from-teal-400 via-cyan-400 to-blue-400 bg-clip-text text-transparent">
              genetic story
            </span>
          </h1>

          <p className="text-lg sm:text-xl text-slate-400 max-w-2xl mx-auto mb-10 leading-relaxed">
            Upload your DNA file and get personalized health insights across 13 panels — from drug responses and disease risk to ancestry and rare mutations. Evidence-based. Fully private.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              href="/app"
              className="inline-flex items-center gap-2 px-7 py-4 rounded-2xl bg-linear-to-r from-teal-500 to-cyan-500 text-white font-semibold text-base hover:from-teal-400 hover:to-cyan-400 transition-all shadow-xl shadow-teal-500/30 hover:shadow-teal-500/50 hover:-translate-y-0.5 group"
            >
              Get started free
              <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
            </Link>
            <Link
              href="#how-it-works"
              className="inline-flex items-center gap-2 px-7 py-4 rounded-2xl bg-slate-800 border border-slate-700 text-slate-200 font-medium text-base hover:bg-slate-700 hover:border-slate-600 transition-all"
            >
              See how it works
            </Link>
          </div>

          <div className="mt-20 grid grid-cols-2 sm:grid-cols-4 gap-6 max-w-2xl mx-auto">
            {STATS.map(s => (
              <div key={s.label} className="text-center">
                <div className="text-3xl font-extrabold text-white mb-1">{s.value}</div>
                <div className="text-xs text-slate-500 uppercase tracking-widest">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-24 relative">
        <div className="absolute inset-0 bg-linear-to-b from-transparent via-slate-900/50 to-transparent pointer-events-none" />
        <div className="relative max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-14">
            <p className="text-xs font-semibold text-teal-400 uppercase tracking-widest mb-3">Why Epigenic</p>
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight">Built for depth, not just curiosity</h2>
            <p className="mt-4 text-slate-400 max-w-xl mx-auto">Consumer DNA kits give you a file. We give you answers.</p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {FEATURES.map(f => (
              <div key={f.title} className="group p-6 rounded-2xl bg-slate-800/50 border border-slate-700/50 hover:bg-slate-800 hover:border-teal-500/30 transition-all">
                <div className="flex items-center justify-center w-11 h-11 rounded-xl bg-teal-500/10 border border-teal-500/20 mb-4 group-hover:bg-teal-500/20 transition-colors">
                  <f.icon className="w-5 h-5 text-teal-400" />
                </div>
                <h3 className="font-semibold text-white mb-2">{f.title}</h3>
                <p className="text-sm text-slate-400 leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Panels */}
      <section id="panels" className="py-24">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-14">
            <p className="text-xs font-semibold text-teal-400 uppercase tracking-widest mb-3">Analysis Panels</p>
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight">13 specialized panels</h2>
            <p className="mt-4 text-slate-400 max-w-xl mx-auto">
              Every panel cross-references multiple evidence databases and highlights only the variants that matter for <em>you</em>.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {PANELS.map(p => (
              <div key={p.label} className={`flex items-start gap-4 p-5 rounded-2xl border ${p.bg} hover:scale-[1.01] transition-transform`}>
                <div className={`shrink-0 flex items-center justify-center w-10 h-10 rounded-xl bg-slate-950/40 ${p.color}`}>
                  <p.icon className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-semibold text-white text-sm">{p.label}</h3>
                  <p className="text-xs text-slate-400 mt-0.5 leading-relaxed">{p.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="py-24 relative">
        <div className="absolute inset-0 bg-linear-to-br from-teal-950/20 to-transparent pointer-events-none" />
        <div className="relative max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-14">
            <p className="text-xs font-semibold text-teal-400 uppercase tracking-widest mb-3">Getting started</p>
            <h2 className="text-3xl sm:text-4xl font-bold tracking-tight">From file to insights in minutes</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {STEPS.map((step, i) => (
              <div key={step.n} className="relative">
                {i < STEPS.length - 1 && (
                  <div className="hidden md:block absolute top-8 left-full w-full h-px bg-linear-to-r from-teal-500/40 to-transparent z-0" />
                )}
                <div className="relative z-10 flex flex-col gap-4">
                  <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-linear-to-br from-teal-500/20 to-cyan-500/10 border border-teal-500/25">
                    <span className="text-2xl font-extrabold text-teal-400">{step.n}</span>
                  </div>
                  <h3 className="text-lg font-bold text-white">{step.title}</h3>
                  <p className="text-sm text-slate-400 leading-relaxed">{step.body}</p>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-14 text-center">
            <Link
              href="/app"
              className="inline-flex items-center gap-2 px-8 py-4 rounded-2xl bg-linear-to-r from-teal-500 to-cyan-500 text-white font-semibold text-base hover:from-teal-400 hover:to-cyan-400 transition-all shadow-xl shadow-teal-500/30 group"
            >
              Try it now — it&apos;s free
              <ChevronRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
            </Link>
          </div>
        </div>
      </section>

      {/* Privacy */}
      <section className="py-20">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="rounded-3xl bg-linear-to-br from-slate-800/80 to-slate-900/80 border border-slate-700/50 p-10 sm:p-14 text-center relative overflow-hidden">
            <div className="absolute inset-0 bg-linear-to-br from-teal-500/5 to-cyan-500/5 pointer-events-none" />
            <div className="relative">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-teal-500/10 border border-teal-500/20 mb-6">
                <Lock className="w-7 h-7 text-teal-400" />
              </div>
              <h2 className="text-3xl sm:text-4xl font-bold tracking-tight mb-4">Your DNA never leaves your control</h2>
              <p className="text-slate-400 max-w-xl mx-auto mb-8 leading-relaxed">
                All genetic data is encrypted at rest and in transit. We never sell, share, or use your data for research without explicit consent. Delete everything in one click — permanently.
              </p>
              <div className="flex flex-wrap items-center justify-center gap-4 text-sm text-slate-400">
                {['AES-256 encryption', 'Never sold to third parties', 'One-click data deletion', 'GDPR-aligned'].map(item => (
                  <span key={item} className="inline-flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-teal-400" />
                    {item}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-24">
        <div className="max-w-2xl mx-auto px-4 sm:px-6 text-center">
          <h2 className="text-4xl sm:text-5xl font-extrabold tracking-tight mb-5">Ready to understand your genome?</h2>
          <p className="text-slate-400 mb-10 text-lg leading-relaxed">
            Upload your genetic data today and start exploring 13 panels of personalized insights backed by scientific evidence.
          </p>
          <Link
            href="/app"
            className="inline-flex items-center gap-2 px-8 py-4 rounded-2xl bg-linear-to-r from-teal-500 to-cyan-500 text-white font-bold text-base hover:from-teal-400 hover:to-cyan-400 transition-all shadow-2xl shadow-teal-500/30 hover:-translate-y-0.5 group"
          >
            Get started — free
            <ArrowRight className="w-5 h-5 group-hover:translate-x-0.5 transition-transform" />
          </Link>
        </div>
      </section>

      <Footer />
    </div>
  )
}
