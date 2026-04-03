import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Contact — Epigenic',
  description: 'Get in touch with the Epigenic team for support, privacy requests, or partnership inquiries.',
  openGraph: {
    title: 'Contact — Epigenic',
    description: 'Get in touch with the Epigenic team for support, privacy requests, or partnership inquiries.',
    url: 'https://epigenic.xyz/contact',
  },
}

export default function ContactLayout({ children }: { children: React.ReactNode }) {
  return children
}
