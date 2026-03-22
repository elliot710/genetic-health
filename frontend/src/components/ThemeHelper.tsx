// Helper function to generate theme-aware classes for category components
export const getThemeClasses = (isDarkMode: boolean = false) => {
  return {
    // Main containers
    container: isDarkMode ? 'bg-slate-800/40 backdrop-blur-xl border-slate-700/50' : 'bg-white/40 backdrop-blur-xl border-gray-200/30',
    // Text colors
    textPrimary: isDarkMode ? 'text-white' : 'text-slate-900',
    textSecondary: isDarkMode ? 'text-slate-300' : 'text-slate-600',
    textMuted: isDarkMode ? 'text-slate-400' : 'text-slate-500',
    // Background colors
    bgLight: isDarkMode ? 'bg-slate-700/40' : 'bg-gray-50',
    bgMedium: isDarkMode ? 'bg-slate-600/40' : 'bg-gray-100',
    // Color variants
    bgBlue: isDarkMode ? 'bg-blue-500/20' : 'bg-blue-50',
    textBlue: isDarkMode ? 'text-blue-300' : 'text-blue-700',
    bgGreen: isDarkMode ? 'bg-green-500/20' : 'bg-green-50',
    textGreen: isDarkMode ? 'text-green-300' : 'text-green-700',
    bgPurple: isDarkMode ? 'bg-purple-500/20' : 'bg-purple-50',
    textPurple: isDarkMode ? 'text-purple-300' : 'text-purple-700',
    bgYellow: isDarkMode ? 'bg-yellow-500/20' : 'bg-yellow-50',
    textYellow: isDarkMode ? 'text-yellow-300' : 'text-yellow-700',
    bgRed: isDarkMode ? 'bg-red-500/20' : 'bg-red-50',
    textRed: isDarkMode ? 'text-red-300' : 'text-red-700',
    bgPink: isDarkMode ? 'bg-pink-500/20' : 'bg-pink-50',
    textPink: isDarkMode ? 'text-pink-300' : 'text-pink-700',
  }
}