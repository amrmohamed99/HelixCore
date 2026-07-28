/* ================================================================
   useActivity — log user actions to the persistent activity trail
   ================================================================ */

import { useCallback } from 'react'

const BASE_URL = 'http://127.0.0.1:8299'

interface ActivityOptions {
  details?: Record<string, unknown>
  duration_ms?: number
}

/**
 * Provides a `logActivity()` helper that fires-and-forgets an
 * activity entry to the backend. Never throws — failures are
 * silently ignored so they don't disrupt the UI.
 */
export function useActivity() {
  const logActivity = useCallback(
    (action: string, page: string, opts?: ActivityOptions) => {
      fetch(`${BASE_URL}/api/activity/log`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          page,
          details: opts?.details ?? null,
          duration_ms: opts?.duration_ms ?? null,
        }),
      }).catch(() => {
        /* silently ignore — activity logging is best-effort */
      })
    },
    [],
  )

  return { logActivity }
}
