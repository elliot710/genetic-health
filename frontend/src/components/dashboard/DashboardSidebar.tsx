'use client'

import { X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { getThemeClass, getTheme } from '@/utils/theme'

type Theme = ReturnType<typeof getTheme>

export interface SidebarCategory {
  id: string
  title: string
  icon: LucideIcon | null
  isSeparator?: boolean
}

interface DashboardSidebarProps {
  theme: Theme
  isDarkMode: boolean
  categories: SidebarCategory[]
  activeCategory: string
  setActiveCategory: (cat: string) => void
  isOpen?: boolean
  onClose?: () => void
}

export default function DashboardSidebar({
  theme,
  isDarkMode,
  categories,
  activeCategory,
  setActiveCategory,
  isOpen = false,
  onClose,
}: DashboardSidebarProps) {
  const handleSelect = (id: string) => {
    setActiveCategory(id)
    onClose?.()
  }

  const sidebarContent = (
    <div className="p-4 md:p-6">
      {/* Mobile close button */}
      <div className="flex items-center justify-between mb-4 md:hidden">
        <span className={`text-sm font-semibold ${isDarkMode ? 'text-gray-300' : 'text-gray-700'}`}>Categories</span>
        <button
          onClick={onClose}
          className={`p-1.5 rounded-lg transition-colors ${isDarkMode ? 'hover:bg-slate-700/60 text-gray-400' : 'hover:bg-gray-200/60 text-gray-500'}`}
          aria-label="Close menu"
        >
          <X className="h-5 w-5" />
        </button>
      </div>
      <div className="space-y-1.5">
        {categories.map((category) => {
          if (category.isSeparator) {
            return (
              <div
                key={category.id}
                className={`my-3 border-t ${isDarkMode ? 'border-gray-700/50' : 'border-gray-200/50'}`}
              ></div>
            )
          }

          const Icon = category.icon
          const isActive = activeCategory === category.id
          return (
            <button
              key={category.id}
              onClick={() => handleSelect(category.id)}
              className={`w-full flex items-center space-x-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-300 ${
                isActive
                  ? 'bg-gradient-to-r from-teal-500/80 to-cyan-500/80 text-white shadow-lg border border-white/20 backdrop-blur-xl'
                  : isDarkMode
                    ? 'text-gray-300 hover:bg-slate-700/40 hover:text-white border border-transparent hover:border-slate-600/30 backdrop-blur-sm'
                    : 'text-gray-600 hover:bg-gray-200/30 hover:text-gray-900 border border-transparent hover:border-gray-300/30 backdrop-blur-sm'
              }`}
            >
              {Icon && (
                <Icon
                  className={`h-5 w-5 shrink-0 ${isActive ? 'text-white' : getThemeClass('text-gray-500', isDarkMode)}`}
                />
              )}
              <span>{category.title}</span>
            </button>
          )
        })}
      </div>
    </div>
  )

  return (
    <>
      {/* Desktop sidebar — always visible */}
      <aside className={`hidden md:flex w-64 lg:w-72 flex-col ${theme.glass} border-r ${theme.glassBorder} overflow-y-auto relative z-10`}>
        {sidebarContent}
      </aside>

      {/* Mobile — slide-in drawer */}
      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm md:hidden"
            onClick={onClose}
            aria-hidden="true"
          />
          {/* Drawer */}
          <aside
            className={`fixed inset-y-0 left-0 z-50 w-72 ${theme.glass} border-r ${theme.glassBorder} overflow-y-auto md:hidden`}
            style={{ background: isDarkMode ? 'rgba(15,23,42,0.97)' : 'rgba(255,255,255,0.97)' }}
          >
            {sidebarContent}
          </aside>
        </>
      )}
    </>
  )
}
