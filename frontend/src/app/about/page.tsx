import Link from 'next/link'
import { Dna, Heart, Shield, Zap, Users } from 'lucide-react'
import Navbar from '@/components/marketing/Navbar'
import Footer from '@/components/marketing/Footer'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'About — Epigenic',
  description: 'Learn about the mission behind Epigenic — making genomics accessible, evidence-based, and private.',
  openGraph: {
    title: 'About — Epigenic',
    description: 'Learn about the mission behind Epigenic — making genomics accessible, evidence-based, and private.',
    url: 'https://epigenic.xyz/about',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'About — Epigenic',
    description: 'Learn about the mission behind Epigenic — making genomics accessible, evidence-based, and private.',
  },
}

const VALUES = [
  { icon: Heart, title: 'Evidence first', body: 'Every insight maps to peer-reviewed databases: ClinVar, gnomAD, PharmGKB, Ensembl VEP, and AlphaMissense. We never speculate.' },
  { icon: Shield, title: 'Privacy by design', body: 'Your genetic data is yours. It is encrypted, never sold, and can be deleted permanently at any time.' },
  { icon: Zap, title: 'Actionable', body: 'We translate raw variant calls into plain-language findings with clear next steps — not just rsid lists.' },
  { icon: Users, title: 'Inclusive', body: 'We support VCF files from clinical sequencing and CSV exports from consumer kits like 23andMe and AncestryDNA.' },
]

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Navbar />

      {/* Hero */}
      <section className="relative pt-32 pb-20 overflow-hidden">
        <div className="absolute inset-0 bg-linear-to-br from-teal-950/30 to-slate-950 pointer-events-none" />
        <div className="absolute top-1/4 left-1/3 w-80 h-80 bg-teal-500/10 rounded-full blur-3xl" />
        <div className="relative max-w-3xl mx-auto px-4 sm:px-6 text-center">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-linear-to-br from-teal-500 to-cyan-500 shadow-lg shadow-teal-500/30 mb-8">
            <Dna className="w-7 h-7 text-white" />
          </div>
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight mb-5">
            About Epigenic
          </h1>
          <p className="text-lg text-slate-400 leading-relaxed">
            Epigenic makes clinical-grade genomic analysis accessible to everyone — without requiring a medical degree or a $10,000 sequencing contract.
          </p>
        </div>
      </section>

      {/* Mission */}
      <section className="py-16">
        <div className="max-w-3xl mx-auto px-4 sm:px-6">
          <div className="rounded-3xl bg-slate-800/40 border border-slate-700/50 p-8 sm:p-12">
            <h2 className="text-2xl font-bold mb-4">Our mission</h2>
            <p className="text-slate-400 leading-relaxed mb-4">
              The human genome contains enormous untapped potential for personal health guidance. Yet most people who have taken a consumer DNA test have barely scratched the surface of what their data can reveal.
            </p>
            <p className="text-slate-400 leading-relaxed mb-4">
              Epigenic was built to change that. We built a platform that ingests raw genetic data — whether from a clinical VCF or a 23andMe CSV — and runs it through a multi-source interpretation pipeline to produce 13 categories of personalized insights, from hereditary cancer risk to pharmacogenomics, methylation capacity, and neurodevelopmental traits.
            </p>
            <p className="text-slate-400 leading-relaxed">
              Every finding is grounded in peer-reviewed databases and is transparent about its confidence level. We are not a replacement for your physician or genetic counselor, but we are a powerful starting point for informed conversations with them.
            </p>
          </div>
        </div>
      </section>

      {/* Values */}
      <section className="py-16">
        <div className="max-w-4xl mx-auto px-4 sm:px-6">
          <h2 className="text-2xl font-bold text-center mb-10">What we stand for</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            {VALUES.map(v => (
              <div key={v.title} className="flex gap-4 p-6 rounded-2xl bg-slate-800/40 border border-slate-700/40 hover:border-teal-500/30 transition-colors">
                <div className="shrink-0 flex items-center justify-center w-10 h-10 rounded-xl bg-teal-500/10 border border-teal-500/20">
                  <v.icon className="w-5 h-5 text-teal-400" />
                </div>
                <div>
                  <h3 className="font-semibold text-white mb-1">{v.title}</h3>
                  <p className="text-sm text-slate-400 leading-relaxed">{v.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Disclaimer */}
      <section className="py-16">
        <div className="max-w-3xl mx-auto px-4 sm:px-6">
          <div className="rounded-2xl bg-amber-500/5 border border-amber-500/20 p-6 sm:p-8">
            <h3 className="font-semibold text-amber-400 mb-2">Medical disclaimer</h3>
            <p className="text-sm text-slate-400 leading-relaxed">
              Epigenic is an informational tool only. The analysis provided does not constitute medical advice, diagnosis, or treatment. Results should always be discussed with a qualified healthcare professional, genetic counselor, or physician before making any health decisions. Genetic variants are interpreted based on current published evidence, which may change as science evolves.
            </p>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-16 text-center">
        <div className="max-w-lg mx-auto px-4">
          <h2 className="text-2xl font-bold mb-4">Ready to explore your genome?</h2>
          <p className="text-slate-400 mb-8">Upload your DNA file and get started in minutes.</p>
          <Link
            href="/app"
            className="inline-flex items-center gap-2 px-7 py-3.5 rounded-2xl bg-linear-to-r from-teal-500 to-cyan-500 text-white font-semibold hover:from-teal-400 hover:to-cyan-400 transition-all shadow-lg shadow-teal-500/25"
          >
            Launch App
          </Link>
        </div>
      </section>

      <Footer />
    </div>
  )
}
