import type { ReactNode } from 'react'
import Navbar from './Navbar'
import Footer from './Footer'

interface MarketingLayoutProps {
  children: ReactNode
}

export default function MarketingLayout({ children }: MarketingLayoutProps) {
  return (
    <div className="min-h-screen bg-white dark:bg-slate-950 text-slate-900 dark:text-white">
      <Navbar />
      {children}
      <Footer />
    </div>
  )
}
