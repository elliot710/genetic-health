'use client'

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
}

export default function DashboardSidebar({
  theme,
  isDarkMode,
  categories,
  activeCategory,
  setActiveCategory,
}: DashboardSidebarProps) {
  return (
    <aside className={`w-72 ${theme.glass} border-r ${theme.glassBorder} overflow-y-auto relative z-10`}>
      <div className="p-6">
        <div className="space-y-2">
          {categories.map((category) => {
            if (category.isSeparator) {
              return (
                <div
                  key={category.id}
                  className={`my-4 border-t ${isDarkMode ? 'border-gray-700/50' : 'border-gray-200/50'}`}
                ></div>
              )
            }

            const Icon = category.icon
            const isActive = activeCategory === category.id
            return (
              <button
                key={category.id}
                onClick={() => setActiveCategory(category.id)}
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
                    className={`h-5 w-5 ${isActive ? 'text-white' : getThemeClass('text-gray-500', isDarkMode)}`}
                  />
                )}
                <span>{category.title}</span>
              </button>
            )
          })}
        </div>
      </div>
    </aside>
  )
}
