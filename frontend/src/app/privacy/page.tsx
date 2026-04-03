import Navbar from '@/components/marketing/Navbar'
import Footer from '@/components/marketing/Footer'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Privacy Policy — Epigenic',
  description: 'How Epigenic handles, stores, and protects your genetic data.',
  openGraph: {
    title: 'Privacy Policy — Epigenic',
    description: 'How Epigenic handles, stores, and protects your genetic data.',
    url: 'https://epigenic.xyz/privacy',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Privacy Policy — Epigenic',
    description: 'How Epigenic handles, stores, and protects your genetic data.',
  },
}

const LAST_UPDATED = 'April 3, 2026'

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <Navbar />

      <section className="pt-32 pb-20 max-w-3xl mx-auto px-4 sm:px-6">
        {/* Header */}
        <div className="mb-12">
          <p className="text-xs font-semibold text-teal-400 uppercase tracking-widest mb-3">Legal</p>
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight mb-4">Privacy Policy</h1>
          <p className="text-slate-400">Last updated: {LAST_UPDATED}</p>
        </div>

        <div className="prose prose-invert prose-slate max-w-none space-y-10 text-slate-300">

          <div>
            <h2 className="text-xl font-bold text-white mb-3">1. Overview</h2>
            <p className="leading-relaxed">
              Epigenic (&quot;we&quot;, &quot;us&quot;, or &quot;our&quot;) takes your privacy seriously — especially when it comes to genetic data. This Privacy Policy explains what data we collect, how we use it, and what rights you have. By using Epigenic at <strong>epigenic.xyz</strong> (&quot;the Service&quot;), you agree to the terms below.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">2. Data We Collect</h2>
            <p className="leading-relaxed mb-3">We collect the minimum data required to operate the Service:</p>
            <ul className="list-disc list-inside space-y-2 text-slate-400">
              <li><strong className="text-slate-200">Account data:</strong> Email address and username at registration.</li>
              <li><strong className="text-slate-200">Genetic data:</strong> VCF or CSV files you upload for analysis.</li>
              <li><strong className="text-slate-200">Derived analysis data:</strong> The variant annotations and insight records generated from your file.</li>
              <li><strong className="text-slate-200">Usage data:</strong> Server access logs (IP address, timestamp, endpoint) for security and debugging, retained for 30 days.</li>
            </ul>
            <p className="mt-3 leading-relaxed">We do <strong>not</strong> collect payment information, sell advertising, or use third-party tracking pixels.</p>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">3. How We Use Your Data</h2>
            <ul className="list-disc list-inside space-y-2 text-slate-400">
              <li>To perform genetic analysis and display results in your dashboard.</li>
              <li>To authenticate your account and maintain session security.</li>
              <li>To send transactional emails (password resets, account confirmations) when you request them.</li>
              <li>To detect and prevent abuse, fraud, or unauthorized access.</li>
            </ul>
            <p className="mt-3 leading-relaxed">We never use your genetic data for aggregate research, marketing profiling, or any purpose beyond the analysis you explicitly requested.</p>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">4. Data Storage &amp; Security</h2>
            <p className="leading-relaxed mb-3">
              All data is stored on servers within the European Union (or equivalent jurisdiction with adequate data protection). We apply:
            </p>
            <ul className="list-disc list-inside space-y-2 text-slate-400">
              <li>AES-256 encryption at rest for all genetic data.</li>
              <li>TLS 1.2+ (HTTPS) for all data in transit.</li>
              <li>Access control: only your account can access your data.</li>
              <li>Automated backups with 90-day retention, encrypted with the same standard.</li>
            </ul>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">5. Data Sharing</h2>
            <p className="leading-relaxed">
              We <strong>do not sell, rent, or trade</strong> your personal or genetic data to any third party. Limited sharing may occur only in the following narrow circumstances:
            </p>
            <ul className="list-disc list-inside space-y-2 mt-3 text-slate-400">
              <li><strong className="text-slate-200">Infrastructure providers:</strong> Hosting and storage providers (e.g., cloud infrastructure) that process data solely on our behalf under strict data processing agreements.</li>
              <li><strong className="text-slate-200">Legal requirements:</strong> When required by law, court order, or governmental authority, and only to the extent required.</li>
            </ul>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">6. Your Rights</h2>
            <p className="leading-relaxed mb-3">You have the right to:</p>
            <ul className="list-disc list-inside space-y-2 text-slate-400">
              <li><strong className="text-slate-200">Access:</strong> Request a copy of all personal data we hold about you.</li>
              <li><strong className="text-slate-200">Deletion:</strong> Delete your genetic data and account at any time via the dashboard settings. Deletion is immediate and permanent.</li>
              <li><strong className="text-slate-200">Rectification:</strong> Correct any inaccurate account information.</li>
              <li><strong className="text-slate-200">Portability:</strong> Export your raw analysis data in JSON format.</li>
              <li><strong className="text-slate-200">Objection:</strong> Object to any processing we may conduct on the basis of legitimate interest.</li>
            </ul>
            <p className="mt-3 leading-relaxed">To exercise these rights, contact us at <a href="mailto:privacy@epigenic.xyz" className="text-teal-400 hover:text-teal-300">privacy@epigenic.xyz</a>.</p>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">7. Cookies</h2>
            <p className="leading-relaxed">
              We use a single HTTP-only session cookie for authentication. This cookie is strictly necessary, contains no personal information, and is deleted when you log out or your session expires. We do not use analytics, advertising, or third-party cookies.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">8. Children</h2>
            <p className="leading-relaxed">
              The Service is not directed at children under 16. We do not knowingly collect data from minors. If you believe a minor has registered, contact us and we will delete the account promptly.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">9. Changes to This Policy</h2>
            <p className="leading-relaxed">
              We may update this policy when our practices change. We will notify registered users by email at least 14 days before material changes take effect. Continued use of the Service after the effective date constitutes acceptance.
            </p>
          </div>

          <div>
            <h2 className="text-xl font-bold text-white mb-3">10. Contact</h2>
            <p className="leading-relaxed">
              Questions about this policy? Email us at{' '}
              <a href="mailto:privacy@epigenic.xyz" className="text-teal-400 hover:text-teal-300">privacy@epigenic.xyz</a>.
            </p>
          </div>

        </div>
      </section>

      <Footer />
    </div>
  )
}
