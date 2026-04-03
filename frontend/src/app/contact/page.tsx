'use client'

import { useState } from 'react'
import { Mail, MessageSquare, Clock } from 'lucide-react'
import Navbar from '@/components/marketing/Navbar'
import Footer from '@/components/marketing/Footer'

const TOPICS = [
  'General inquiry',
  'Technical support',
  'Privacy / data deletion request',
  'Bug report',
  'Partnership or press',
  'Other',
]

export default function ContactPage() {
  const [form, setForm] = useState({ name: '', email: '', topic: TOPICS[0], message: '' })
  const [sent, setSent] = useState(false)
  const [sending, setSending] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSending(true)
    // Simulate form submission — wire to a real backend/email service as needed
    await new Promise(r => setTimeout(r, 900))
    setSending(false)
    setSent(true)
  }

  return (
    <div className="min-h-screen bg-white dark:bg-slate-950 text-slate-900 dark:text-white">
      <Navbar />

      <section className="pt-32 pb-20">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
          {/* Header */}
          <div className="text-center mb-14">
            <p className="text-xs font-semibold text-teal-400 uppercase tracking-widest mb-3">Get in touch</p>
            <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight mb-4">Contact us</h1>
            <p className="text-slate-500 dark:text-slate-400 max-w-lg mx-auto">
              Have a question, found a bug, or need help with your data? We typically respond within one business day.
            </p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[1fr_2fr] gap-10">
            {/* Left sidebar */}
            <div className="space-y-5">
              {[
                { icon: Mail, title: 'Email us', body: 'hello@epigenic.xyz', href: 'mailto:hello@epigenic.xyz' },
                { icon: MessageSquare, title: 'Privacy & data', body: 'privacy@epigenic.xyz', href: 'mailto:privacy@epigenic.xyz' },
                { icon: Clock, title: 'Response time', body: 'Within 1 business day', href: null },
              ].map(item => (
                <div key={item.title} className="flex gap-4 p-5 rounded-2xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700/40">
                  <div className="shrink-0 flex items-center justify-center w-10 h-10 rounded-xl bg-teal-500/10 border border-teal-500/20">
                    <item.icon className="w-5 h-5 text-teal-400" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-slate-900 dark:text-white text-sm mb-0.5">{item.title}</h3>
                    {item.href ? (
                      <a href={item.href} className="text-sm text-teal-400 hover:text-teal-300 transition-colors">{item.body}</a>
                    ) : (
                      <p className="text-sm text-slate-500 dark:text-slate-400">{item.body}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Form */}
              <div className="rounded-3xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700/40 p-7 sm:p-10">
              {sent ? (
                <div className="h-full flex flex-col items-center justify-center text-center py-10">
                  <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-teal-500/10 border border-teal-500/20 mb-4">
                    <Mail className="w-7 h-7 text-teal-400" />
                  </div>
                  <h2 className="text-xl font-bold mb-2">Message sent!</h2>
                  <p className="text-slate-500 dark:text-slate-400">Thanks for reaching out. We&apos;ll get back to you within one business day.</p>
                </div>
              ) : (
                <form onSubmit={handleSubmit} className="space-y-5">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                    <div>
                      <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Your name</label>
                      <input
                        type="text"
                        required
                        value={form.name}
                        onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                        placeholder="Jane Smith"
                        className="w-full px-4 py-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500/30 transition-colors text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Email address</label>
                      <input
                        type="email"
                        required
                        value={form.email}
                        onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                        placeholder="jane@example.com"
                        className="w-full px-4 py-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500/30 transition-colors text-sm"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Topic</label>
                    <select
                      value={form.topic}
                      onChange={e => setForm(f => ({ ...f, topic: e.target.value }))}
                      className="w-full px-4 py-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 text-slate-900 dark:text-white focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500/30 transition-colors text-sm"
                    >
                      {TOPICS.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Message</label>
                    <textarea
                      required
                      rows={5}
                      value={form.message}
                      onChange={e => setForm(f => ({ ...f, message: e.target.value }))}
                      placeholder="Tell us how we can help..."
                      className="w-full px-4 py-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 text-slate-900 dark:text-white placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:border-teal-500 focus:ring-1 focus:ring-teal-500/30 transition-colors text-sm resize-none"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={sending}
                    className="w-full py-3 rounded-xl bg-linear-to-r from-teal-500 to-cyan-500 text-white font-semibold hover:from-teal-400 hover:to-cyan-400 transition-all shadow-lg shadow-teal-500/25 disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  >
                    {sending ? (
                      <>
                        <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        Sending…
                      </>
                    ) : 'Send message'}
                  </button>
                </form>
              )}
            </div>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  )
}
