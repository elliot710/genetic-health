import { Info } from 'lucide-react'

export const DISCLAIMER_TEXT =
  'This information is for educational purposes only and should not be used as a substitute for professional medical advice, diagnosis, or treatment. Always consult a qualified healthcare provider.'

interface DisclaimerProps {
  className?: string
}

export function Disclaimer({ className = '' }: DisclaimerProps) {
  return (
    <div
      role="note"
      className={`flex items-start gap-2 rounded-xl border border-blue-200 dark:border-blue-500/20 bg-blue-50/70 dark:bg-blue-500/5 px-4 py-3 ${className}`}
    >
      <Info className="h-4 w-4 mt-0.5 shrink-0 text-blue-500 dark:text-blue-400" />
      <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
        {DISCLAIMER_TEXT}
      </p>
    </div>
  )
}
