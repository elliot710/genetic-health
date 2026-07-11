import { useCallback, useRef, useState } from 'react'

export type FeedbackType = 'success' | 'error' | 'info'

interface FeedbackMessage {
  message: string
  type: FeedbackType
}

/**
 * Shared feedback-message state: a single "current message" slot with an
 * optional auto-dismiss timer. A later `showFeedback` call always invalidates
 * an earlier call's pending timer, so a fast-following message is never
 * clipped early by a slower one's timeout.
 */
export function useFeedback<TMeta extends object = object>() {
  const [feedback, setFeedback] = useState<(FeedbackMessage & TMeta) | null>(null)
  const latestTokenRef = useRef(0)

  const showFeedback = useCallback((next: FeedbackMessage & TMeta, durationMs?: number) => {
    const token = ++latestTokenRef.current
    setFeedback(next)
    if (durationMs !== undefined) {
      setTimeout(() => {
        if (latestTokenRef.current === token) setFeedback(null)
      }, durationMs)
    }
  }, [])

  const clearFeedback = useCallback(() => setFeedback(null), [])

  return { feedback, showFeedback, clearFeedback }
}
