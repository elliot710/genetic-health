/**
 * Centralized theme utility for consistent dark/light mode styling
 */

export interface ThemeProps {
  isDarkMode: boolean;
}

/**
 * Comprehensive theme object with all colors and gradients
 */
export const getTheme = (isDarkMode: boolean) => ({
  // Main background
  background: isDarkMode 
    ? 'bg-gradient-to-br from-slate-900 via-teal-900 to-slate-900' 
    : 'bg-gradient-to-br from-teal-50 via-cyan-50 to-blue-50',
  
  // Glassmorphism with better contrast
  glass: isDarkMode ? 'bg-slate-800/60' : 'bg-white/70',
  glassBorder: isDarkMode ? 'border-slate-600/60' : 'border-gray-300/60',
  glassHover: isDarkMode ? 'hover:bg-slate-700/70' : 'hover:bg-white/80',
  
  // Secondary glass for layered elements
  glassSecondary: isDarkMode ? 'bg-slate-700/50' : 'bg-white/50',
  glassSecondaryBorder: isDarkMode ? 'border-slate-500/50' : 'border-gray-400/50',
  
  // Text colors
  text: {
    primary: isDarkMode ? 'text-gray-100' : 'text-gray-900',
    secondary: isDarkMode ? 'text-gray-300' : 'text-gray-700',
    tertiary: isDarkMode ? 'text-gray-400' : 'text-gray-600',
    muted: isDarkMode ? 'text-gray-500' : 'text-gray-500',
    accent: isDarkMode ? 'text-teal-300' : 'text-teal-700',
    error: isDarkMode ? 'text-red-400' : 'text-red-700',
    success: isDarkMode ? 'text-green-400' : 'text-green-700',
    warning: isDarkMode ? 'text-yellow-400' : 'text-yellow-700',
  },
  
  // Primary theme colors (teal/cyan)
  primary: {
    bg: isDarkMode ? 'bg-teal-600' : 'bg-teal-500',
    text: isDarkMode ? 'text-teal-400' : 'text-teal-600',
    border: isDarkMode ? 'border-teal-500/30' : 'border-teal-200',
    gradient: isDarkMode 
      ? 'bg-gradient-to-r from-teal-500/80 to-cyan-500/80' 
      : 'bg-gradient-to-r from-teal-500/90 to-cyan-500/90',
    gradientHover: isDarkMode 
      ? 'hover:from-teal-600/80 hover:to-cyan-600/80' 
      : 'hover:from-teal-600/90 hover:to-cyan-600/90',
  },
  
  // Secondary theme colors
  secondary: {
    gradient: isDarkMode 
      ? 'bg-gradient-to-r from-cyan-500/80 to-teal-500/80' 
      : 'bg-gradient-to-r from-cyan-500/90 to-teal-500/90',
    gradientHover: isDarkMode 
      ? 'hover:from-cyan-600/80 hover:to-teal-600/80' 
      : 'hover:from-cyan-600/90 hover:to-teal-600/90',
  },
  
  // Background blobs for glassmorphism
  blobs: {
    primary: isDarkMode ? 'bg-gradient-to-br from-teal-500/30 to-cyan-500/20' : 'bg-gradient-to-br from-teal-300/40 to-cyan-300/30',
    secondary: isDarkMode ? 'bg-gradient-to-br from-cyan-500/25 to-teal-500/20' : 'bg-gradient-to-br from-cyan-300/35 to-teal-300/25',
    tertiary: isDarkMode ? 'bg-gradient-to-br from-teal-500/20 to-cyan-500/15' : 'bg-gradient-to-br from-teal-300/30 to-cyan-300/20',
  },
  
  // Status colors
  success: {
    bg: isDarkMode ? 'bg-green-500/20' : 'bg-green-50',
    text: isDarkMode ? 'text-green-400' : 'text-green-600',
    border: isDarkMode ? 'border-green-500/30' : 'border-green-200',
  },
  
  error: {
    bg: isDarkMode ? 'bg-red-500/20' : 'bg-red-50',
    text: isDarkMode ? 'text-red-400' : 'text-red-600',
    border: isDarkMode ? 'border-red-500/30' : 'border-red-200',
  },
  
  warning: {
    bg: isDarkMode ? 'bg-yellow-500/20' : 'bg-yellow-50',
    text: isDarkMode ? 'text-yellow-400' : 'text-yellow-600',
    border: isDarkMode ? 'border-yellow-500/30' : 'border-yellow-200',
  },
  
  // Category colors for data sections
  categories: {
    health: {
      bg: isDarkMode ? 'bg-red-500/20' : 'bg-red-50',
      text: isDarkMode ? 'text-red-400' : 'text-red-600',
      border: isDarkMode ? 'border-red-500/30' : 'border-red-200',
    },
    ancestry: {
      bg: isDarkMode ? 'bg-blue-500/20' : 'bg-blue-50',
      text: isDarkMode ? 'text-blue-400' : 'text-blue-600',
      border: isDarkMode ? 'border-blue-500/30' : 'border-blue-200',
    },
    wellness: {
      bg: isDarkMode ? 'bg-green-500/20' : 'bg-green-50',
      text: isDarkMode ? 'text-green-400' : 'text-green-600',
      border: isDarkMode ? 'border-green-500/30' : 'border-green-200',
    },
    // Add more categories as needed
  },
  
  // Interactive elements
  interactive: {
    hover: isDarkMode ? 'hover:bg-white/10' : 'hover:bg-white/20',
    active: isDarkMode ? 'active:bg-white/20' : 'active:bg-white/30',
    focus: 'focus:ring-2 focus:ring-teal-500/50 focus:outline-none',
  },
  
  // Form elements
  form: {
    input: {
      bg: isDarkMode ? 'bg-slate-700/70' : 'bg-white/80',
      border: isDarkMode ? 'border-slate-500/60' : 'border-gray-300/60',
      text: isDarkMode ? 'text-gray-100' : 'text-gray-900',
      placeholder: isDarkMode ? 'placeholder-gray-400' : 'placeholder-gray-500',
      focus: 'focus:ring-2 focus:ring-teal-500/50 focus:border-teal-400',
    },
    button: {
      primary: `${isDarkMode 
        ? 'bg-gradient-to-r from-teal-600/90 to-cyan-600/90 hover:from-teal-700/90 hover:to-cyan-700/90' 
        : 'bg-gradient-to-r from-teal-600/95 to-cyan-600/95 hover:from-teal-700/95 hover:to-cyan-700/95'
      } text-white font-semibold backdrop-blur-xl border ${isDarkMode ? 'border-slate-500/40' : 'border-teal-300/50'} shadow-lg`,
    },
  },
});

/**
 * Get theme-aware class for a base class
 */
export const getThemeClass = (baseClass: string, isDarkMode: boolean): string => {
  const themeMap: { [key: string]: string } = {
    // Background colors
    'bg-white': isDarkMode ? 'bg-slate-800/40' : 'bg-white/40',
    'bg-gray-50': isDarkMode ? 'bg-slate-700/40' : 'bg-gray-50',
    'bg-gray-100': isDarkMode ? 'bg-slate-700/60' : 'bg-gray-100',
    'bg-gray-200': isDarkMode ? 'bg-slate-700' : 'bg-gray-200',
    
    // Text colors
    'text-gray-900': isDarkMode ? 'text-white' : 'text-gray-900',
    'text-gray-800': isDarkMode ? 'text-slate-100' : 'text-gray-800',
    'text-gray-700': isDarkMode ? 'text-slate-300' : 'text-gray-700',
    'text-gray-600': isDarkMode ? 'text-slate-300' : 'text-gray-600',
    'text-gray-500': isDarkMode ? 'text-slate-400' : 'text-gray-500',
    'text-gray-400': isDarkMode ? 'text-slate-400' : 'text-gray-400',
    
    // Border colors
    'border-gray-200': isDarkMode ? 'border-slate-700/50' : 'border-gray-200',
    'border-gray-300': isDarkMode ? 'border-slate-600/50' : 'border-gray-300',
    
    // Colored backgrounds for dark mode variants
    'bg-blue-50': isDarkMode ? 'bg-blue-500/20' : 'bg-blue-50',
    'text-blue-700': isDarkMode ? 'text-blue-300' : 'text-blue-700',
    'bg-purple-50': isDarkMode ? 'bg-purple-500/20' : 'bg-purple-50',
    'text-purple-700': isDarkMode ? 'text-purple-300' : 'text-purple-700',
    'bg-green-50': isDarkMode ? 'bg-green-500/20' : 'bg-green-50',
    'text-green-700': isDarkMode ? 'text-green-300' : 'text-green-700',
    'bg-pink-50': isDarkMode ? 'bg-pink-500/20' : 'bg-pink-50',
    'text-pink-700': isDarkMode ? 'text-pink-300' : 'text-pink-700',
    'bg-yellow-50': isDarkMode ? 'bg-yellow-500/20' : 'bg-yellow-50',
    'text-yellow-700': isDarkMode ? 'text-yellow-300' : 'text-yellow-700',
    'bg-orange-50': isDarkMode ? 'bg-orange-500/20' : 'bg-orange-50',
    'text-orange-700': isDarkMode ? 'text-orange-300' : 'text-orange-700',
    'bg-red-50': isDarkMode ? 'bg-red-500/20' : 'bg-red-50',
    'text-red-700': isDarkMode ? 'text-red-300' : 'text-red-700',
    'bg-indigo-50': isDarkMode ? 'bg-indigo-500/20' : 'bg-indigo-50',
    'text-indigo-700': isDarkMode ? 'text-indigo-300' : 'text-indigo-700',
    'bg-teal-50': isDarkMode ? 'bg-teal-500/20' : 'bg-teal-50',
    'text-teal-700': isDarkMode ? 'text-teal-300' : 'text-teal-700',
    
    // Icon colors
    'text-blue-500': isDarkMode ? 'text-blue-400' : 'text-blue-500',
    'text-blue-600': isDarkMode ? 'text-blue-400' : 'text-blue-600',
    'text-purple-500': isDarkMode ? 'text-purple-400' : 'text-purple-500',
    'text-purple-600': isDarkMode ? 'text-purple-400' : 'text-purple-600',
    'text-green-500': isDarkMode ? 'text-green-400' : 'text-green-500',
    'text-green-600': isDarkMode ? 'text-green-400' : 'text-green-600',
    'text-red-500': isDarkMode ? 'text-red-400' : 'text-red-500',
    'text-red-600': isDarkMode ? 'text-red-400' : 'text-red-600',
    'text-yellow-500': isDarkMode ? 'text-yellow-400' : 'text-yellow-500',
    'text-yellow-600': isDarkMode ? 'text-yellow-400' : 'text-yellow-600',
    'text-orange-600': isDarkMode ? 'text-orange-400' : 'text-orange-600',
    'text-pink-500': isDarkMode ? 'text-pink-400' : 'text-pink-500',
    'text-pink-600': isDarkMode ? 'text-pink-400' : 'text-pink-600',
    'text-teal-600': isDarkMode ? 'text-teal-400' : 'text-teal-600',
    
    // Border colors for categories
    'border-green-200': isDarkMode ? 'border-green-500/30' : 'border-green-200',
    'border-blue-200': isDarkMode ? 'border-blue-500/30' : 'border-blue-200',
    'border-yellow-200': isDarkMode ? 'border-yellow-500/30' : 'border-yellow-200',
    'border-red-200': isDarkMode ? 'border-red-500/30' : 'border-red-200',
    
    // Text colors for categories
    'text-green-800': isDarkMode ? 'text-green-300' : 'text-green-800',
    'text-blue-800': isDarkMode ? 'text-blue-300' : 'text-blue-800',
    'text-yellow-800': isDarkMode ? 'text-yellow-300' : 'text-yellow-800',
    'text-red-900': isDarkMode ? 'text-red-300' : 'text-red-900',
    'text-orange-900': isDarkMode ? 'text-orange-300' : 'text-orange-900',
    'text-yellow-900': isDarkMode ? 'text-yellow-300' : 'text-yellow-900',
    'text-blue-900': isDarkMode ? 'text-blue-300' : 'text-blue-900',
    'text-teal-900': isDarkMode ? 'text-teal-300' : 'text-teal-900',
    'text-green-900': isDarkMode ? 'text-green-300' : 'text-green-900',
    
    // Additional stat/metric colors for overview
    'text-amber-600': isDarkMode ? 'text-amber-400' : 'text-amber-600',
    'bg-amber-50': isDarkMode ? 'bg-amber-500/20' : 'bg-amber-50',
    
    // Additional colors for auth form
    'placeholder-gray-500': isDarkMode ? 'placeholder-slate-400' : 'placeholder-gray-500',
    'hover:text-gray-600': isDarkMode ? 'hover:text-slate-300' : 'hover:text-gray-600',
    
    // Teal hover colors for auth form
    'hover:text-teal-700': isDarkMode ? 'hover:text-teal-300' : 'hover:text-teal-700',
  };
  
  return themeMap[baseClass] || baseClass;
};

/**
 * Get glassmorphism background class
 */
export const getGlassBackground = (isDarkMode: boolean): string => {
  return isDarkMode 
    ? 'bg-slate-800/40 backdrop-blur-xl border-slate-700/50' 
    : 'bg-white/40 backdrop-blur-xl border-white/50';
};

/**
 * Get glass border class
 */
export const getGlassBorder = (isDarkMode: boolean): string => {
  return isDarkMode ? 'border-slate-700/50' : 'border-white/50';
};

/**
 * Get primary text color
 */
export const getTextPrimary = (isDarkMode: boolean): string => {
  return isDarkMode ? 'text-white' : 'text-gray-900';
};

/**
 * Get secondary text color
 */
export const getTextSecondary = (isDarkMode: boolean): string => {
  return isDarkMode ? 'text-slate-300' : 'text-gray-600';
};

/**
 * Get tertiary text color
 */
export const getTextTertiary = (isDarkMode: boolean): string => {
  return isDarkMode ? 'text-slate-400' : 'text-gray-500';
};

/**
 * Get themed tag/badge class
 */
export const getTagClass = (isDarkMode: boolean): string => {
  return isDarkMode 
    ? 'bg-slate-700/60 text-slate-300' 
    : 'bg-gray-100 text-gray-600';
};

/**
 * Get themed progress bar background
 */
export const getProgressBarBg = (isDarkMode: boolean): string => {
  return isDarkMode ? 'bg-slate-700' : 'bg-gray-200';
};

/**
 * Get themed card background
 */
export const getCardBackground = (isDarkMode: boolean): string => {
  return isDarkMode ? 'bg-slate-700/40' : 'bg-gray-50';
};

/**
 * Combine multiple theme classes
 */
export const combineThemeClasses = (classes: string[], isDarkMode: boolean): string => {
  return classes.map(cls => getThemeClass(cls, isDarkMode)).join(' ');
};