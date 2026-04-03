import Navbar from '@/components/marketing/Navbar'
import Footer from '@/components/marketing/Footer'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Terms of Use — Epigenic',
  description: 'Terms governing use of the Epigenic genetic analysis platform.',
  openGraph: {
    title: 'Terms of Use — Epigenic',
    description: 'Terms governing use of the Epigenic genetic analysis platform.',
    url: 'https://epigenic.xyz/terms',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Terms of Use — Epigenic',
    description: 'Terms governing use of the Epigenic genetic analysis platform.',
  },
}

const LAST_UPDATED = 'April 3, 2026'

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Navbar />

      <section className="pt-32 pb-20 max-w-3xl mx-auto px-4 sm:px-6">
        <div className="mb-12">
          <p className="text-xs font-semibold text-teal-400 uppercase tracking-widest mb-3">Legal</p>
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight mb-4">Terms of Use</h1>
          <p className="text-slate-400">Last updated: {LAST_UPDATED}</p>
        </div>

        <div className="prose prose-invert prose-slate max-w-none space-y-10 text-slate-300">

          <div>
            <h2 className="text-xl font-bold text-white mb-3">1. Acceptance of Terms</h2>
            <p className="leading-relaxed">
              By accessing or using Epigenic at <strong>epigenic.xyz</strong> (&quot;the Service&quot;), you agree to be bound by these Terms of Use (&quot;Terms&quot;). If you do not agree, do not use the Service. We may update these Terms at any time; continued use constitutes acceptance of updated Terms.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">2. Description of Service</h2>
            <p className="leading-relaxed">
              Epigenic is a web-based platform that accepts genetic data files (VCF, CSV) and generates personalized informational analysis across 13 health and trait categories. The Service is intended for <strong>informational and educational purposes only</strong>.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">3. Medical Disclaimer</h2>
            <div className="rounded-2xl bg-amber-500/5 border border-amber-500/20 p-5 not-prose">
              <p className="text-sm text-amber-200 leading-relaxed font-medium mb-2">Important notice</p>
              <p className="text-sm text-slate-400 leading-relaxed">
                The information provided by Epigenic does <strong className="text-slate-200">not</strong> constitute medical advice, diagnosis, or treatment recommendation. Genetic analysis results are based on population-level data and current evidence, which may be incomplete or subject to scientific reinterpretation. Always consult a qualified healthcare provider, physician, or licensed genetic counselor before making any health-related decisions. Do not disregard professional medical advice or delay seeking it based on information from this Service.
              </p>
            </div>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">4. Eligibility</h2>
            <p className="leading-relaxed">
              You must be at least 18 years old (or the age of majority in your jurisdiction) to use the Service. By using the Service, you represent that you meet this requirement and that all information you provide is accurate.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">5. Your Account</h2>
            <p className="leading-relaxed">
              You are responsible for maintaining the confidentiality of your account credentials and for all activity that occurs under your account. Notify us immediately at <a href="mailto:support@epigenic.xyz" className="text-teal-400 hover:text-teal-300">support@epigenic.xyz</a> if you suspect unauthorized use.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">6. Acceptable Use</h2>
            <p className="leading-relaxed mb-3">You agree not to:</p>
            <ul className="list-disc list-inside space-y-2 text-slate-400">
              <li>Upload genetic data for which you do not have the rights or explicit consent of the individual.</li>
              <li>Use the Service to make clinical decisions without independent qualified medical review.</li>
              <li>Attempt to reverse-engineer, scrape, or extract data from the platform in an automated manner.</li>
              <li>Circumvent authentication, access controls, or rate limits.</li>
              <li>Use the Service for any unlawful purpose or in violation of any applicable regulations (including HIPAA where applicable).</li>
            </ul>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">7. Intellectual Property</h2>
            <p className="leading-relaxed">
              The Service, including its design, code, algorithms, and analysis pipeline, is proprietary to Epigenic. Your <strong>genetic data and analysis results</strong> belong to you. We grant you a personal, non-transferable license to use the Service for personal, non-commercial purposes. You may not copy, modify, distribute, or create derivative works from Service content without our written permission.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">8. Data Accuracy</h2>
            <p className="leading-relaxed">
              Genetic interpretation is a rapidly evolving field. Epigenic makes no warranties that interpretations are complete, current, or free from error. Confidence levels and supporting evidence are displayed for each finding. The absence of a finding does not guarantee the absence of a condition.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">9. Limitation of Liability</h2>
            <p className="leading-relaxed">
              To the maximum extent permitted by applicable law, Epigenic shall not be liable for any indirect, incidental, special, consequential, or punitive damages arising from your use of the Service, including any health decisions made in reliance on analysis results. Our total liability for any claim shall not exceed the amount you paid for the Service in the preceding 12 months, or €50, whichever is greater.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">10. Third-Party Databases</h2>
            <p className="leading-relaxed">
              Analysis results reference data from ClinVar, gnomAD, Ensembl, AlphaMissense, and PharmGKB. These databases are maintained by independent organizations and are subject to their own terms. Epigenic does not control their accuracy or availability.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">11. Termination</h2>
            <p className="leading-relaxed">
              We reserve the right to suspend or terminate accounts that violate these Terms. You may delete your account at any time via dashboard settings. Upon termination, your genetic data and analysis records are permanently deleted within 30 days.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">12. Governing Law</h2>
            <p className="leading-relaxed">
              These Terms are governed by the laws of the jurisdiction in which Epigenic is incorporated, without regard to conflict-of-law principles. Disputes shall be resolved by the courts of that jurisdiction.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">13. Contact</h2>
            <p className="leading-relaxed">
              Questions about these Terms? Contact us at{' '}
              <a href="mailto:legal@epigenic.xyz" className="text-teal-400 hover:text-teal-300">legal@epigenic.xyz</a>.
            </p>
          </div>

        </div>
      </section>

      <Footer />
    </div>
  )
}
