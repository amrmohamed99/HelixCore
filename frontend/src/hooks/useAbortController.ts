/* ================================================================
   useAbortController — manage AbortController for cancellable API calls
   ================================================================ */

import { useRef, useCallback } from 'react'

/**
 * Returns helpers to create AbortController signals and cancel them.
 *
 * Usage:
 *   const { getSignal, abort, isAborted } = useAbortController()
 *
 *   const handleRun = async () => {
 *     const signal = getSignal()
 *     try {
 *       await fetch(url, { signal })
 *     } catch (e) {
 *       if (isAborted()) return // user cancelled
 *       throw e
 *     }
 *   }
 *
 *   <button onClick={abort}>Cancel</button>
 */
export function useAbortController() {
  const controllerRef = useRef<AbortController | null>(null)

  /** Create a new AbortController and return its signal. Aborts the previous one. */
  const getSignal = useCallback((): AbortSignal => {
    if (controllerRef.current) {
      controllerRef.current.abort()
    }
    controllerRef.current = new AbortController()
    return controllerRef.current.signal
  }, [])

  /** Abort the current request */
  const abort = useCallback(() => {
    if (controllerRef.current) {
      controllerRef.current.abort()
      controllerRef.current = null
    }
  }, [])

  /** Check whether the last controller was aborted */
  const isAborted = useCallback((): boolean => {
    return controllerRef.current?.signal.aborted ?? false
  }, [])

  return { getSignal, abort, isAborted }
}
