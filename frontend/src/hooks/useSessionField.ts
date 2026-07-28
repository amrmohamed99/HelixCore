/* ================================================================
   useSessionField — useState backed by sessionStorage
   ================================================================ */

import { useState, useCallback, type Dispatch, type SetStateAction } from 'react'

/**
 * Drop-in replacement for `useState<T>` that persists the value in
 * `sessionStorage` under the given key.  The value survives in-page
 * navigations (React Router) and hot-module reloads but is cleared
 * when the browser / Electron window is closed.
 *
 * @param key      Unique sessionStorage key (prefix with page name).
 * @param fallback Default value when nothing is stored yet.
 *
 * @example
 * const [smiles, setSmiles] = useSessionField('similarity.smiles', '')
 */
export function useSessionField<T>(
  key: string,
  fallback: T,
): [T, Dispatch<SetStateAction<T>>] {
  const [value, setValueRaw] = useState<T>(() => {
    try {
      const stored = sessionStorage.getItem(key)
      if (stored !== null) return JSON.parse(stored) as T
    } catch {
      /* corrupt or missing — use fallback */
    }
    return fallback
  })

  const setValue: Dispatch<SetStateAction<T>> = useCallback(
    (action) => {
      setValueRaw((prev) => {
        const next =
          typeof action === 'function'
            ? (action as (prev: T) => T)(prev)
            : action
        try {
          sessionStorage.setItem(key, JSON.stringify(next))
        } catch {
          /* storage full — silently ignore */
        }
        return next
      })
    },
    [key],
  )

  return [value, setValue]
}
