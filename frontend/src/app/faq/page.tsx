'use client'

import { useState } from 'react'
import { ChevronDown, HelpCircle } from 'lucide-react'
import MarketingLayout from '@/components/marketing/MarketingLayout'

const FAQS = [
  {
    question: 'What is Epigenic?',
    answer: 'Epigenic is an educational tool that reads a raw genetic file — a clinical VCF or a consumer DNA export from services like 23andMe, AncestryDNA, or MyHeritage — and matches your variants against public, peer-reviewed databases to explain what current research says about them.',
  },
  {
    question: 'Is this medical advice?',
    answer: 'No. Epigenic is informational only and does not diagnose, treat, or predict any medical condition. Nothing in your results replaces a conversation with a physician or a certified genetic counselor, and no health decision should be based on it alone.',
  },
  {
    question: 'What file formats can I upload?',
    answer: 'VCF files from clinical or research sequencing, and raw-data CSV/TXT exports from consumer DNA kits such as 23andMe, AncestryDNA, and MyHeritage.',
  },
  {
    question: 'How does the analysis work?',
    answer: 'Your file is parsed and each variant is annotated against sources including ClinVar, gnomAD, PharmGKB, LitVar, SNPedia, and Ensembl VEP, then grouped into categories (e.g. hereditary risk, pharmacogenomics, methylation) and turned into plain-language findings with a stated confidence level.',
  },
  {
    question: 'How is my genetic data stored and protected?',
    answer: 'Uploaded files and derived results are encrypted and never sold or shared with third parties. See our Privacy Policy for the full breakdown of what we collect and why.',
  },
  {
    question: 'Can I delete my data?',
    answer: 'Yes. You can export or permanently delete your account and all associated genetic data at any time from your account settings — no need to contact support.',
  },
  {
    question: 'How accurate are the results?',
    answer: 'Findings are grounded in the current state of published research, which evolves — a variant considered uncertain today may be reclassified as evidence grows. Each result shows the databases and confidence level behind it so you can judge its strength.',
  },
  {
    question: 'Who should I talk to about my results?',
    answer: 'A physician or a certified genetic counselor is best placed to interpret your results in the context of your personal and family health history, especially for anything flagged as clinically significant.',
  },
]

export default function FaqPage() {
  const [openIndex, setOpenIndex] = useState<number | null>(0)

  return (
    <MarketingLayout>
      <section className="pt-32 pb-20">
        <div className="max-w-3xl mx-auto px-4 sm:px-6">
          <div className="text-center mb-14">
            <p className="text-xs font-semibold text-teal-400 uppercase tracking-widest mb-3">Support</p>
            <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight mb-4">Frequently asked questions</h1>
            <p className="text-slate-500 dark:text-slate-400 max-w-lg mx-auto">
              What Epigenic is, how it handles your data, and what its results do and don&apos;t mean.
            </p>
          </div>

          <div className="space-y-3">
            {FAQS.map((faq, index) => {
              const isOpen = openIndex === index
              return (
                <div
                  key={faq.question}
                  className="rounded-2xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700/40 overflow-hidden"
                >
                  <button
                    type="button"
                    onClick={() => setOpenIndex(isOpen ? null : index)}
                    aria-expanded={isOpen}
                    className="w-full flex items-center justify-between gap-4 p-5 sm:p-6 text-left"
                  >
                    <span className="font-semibold text-slate-900 dark:text-white">{faq.question}</span>
                    <ChevronDown
                      className={`w-5 h-5 shrink-0 text-teal-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
                    />
                  </button>
                  {isOpen && (
                    <p className="px-5 sm:px-6 pb-5 sm:pb-6 text-sm text-slate-500 dark:text-slate-400 leading-relaxed">
                      {faq.answer}
                    </p>
                  )}
                </div>
              )
            })}
          </div>

          <div className="mt-14 rounded-2xl bg-amber-50 dark:bg-amber-500/5 border border-amber-200 dark:border-amber-500/20 p-6 sm:p-8 flex gap-4">
            <div className="shrink-0 flex items-center justify-center w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20">
              <HelpCircle className="w-5 h-5 text-amber-400" />
            </div>
            <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed">
              Still have a question? Reach out through our <a href="/contact" className="text-teal-400 hover:text-teal-300 transition-colors">Contact page</a> — we typically respond within one business day.
            </p>
          </div>
        </div>
      </section>
    </MarketingLayout>
  )
}
