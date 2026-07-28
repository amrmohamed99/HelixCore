/* ================================================================
   useUndoable — generic undo/redo history for any state value
   ================================================================ */

import { useState, useCallback, useEffect, useRef } from 'react'

interface UndoableOptions {
  /** Maximum history depth (default: 50) */
  maxHistory?: number
  /** Enable Ctrl+Z / Ctrl+Shift+Z keyboard shortcuts (default: true) */
  keyboard?: boolean
}

interface UndoableReturn<T> {
  /** Current value */
  value: T
  /** Update value and push to history */
  set: (next: T | ((prev: T) => T)) => void
  /** Undo to previous value */
  undo: () => void
  /** Redo to next value */
  redo: () => void
  /** Whether undo is available */
  canUndo: boolean
  /** Whether redo is available */
  canRedo: boolean
  /** Reset history to a new initial value */
  reset: (initial: T) => void
  /** Current history index */
  historyIndex: number
  /** Total history length */
  historyLength: number
}

/**
 * Wraps any state value with undo/redo history.
 *
 * @example
 * const { value, set, undo, redo, canUndo, canRedo } = useUndoable<string[]>([], { maxHistory: 30 })
 */
export function useUndoable<T>(initialValue: T, options: UndoableOptions = {}): UndoableReturn<T> {
  const { maxHistory = 50, keyboard = true } = options

  const [history, setHistory] = useState<T[]>([initialValue])
  const [index, setIndex] = useState(0)
  const isUndoRedo = useRef(false)

  const value = history[index]

  const set = useCallback((next: T | ((prev: T) => T)) => {
    setHistory(prev => {
      const current = prev[index]
      const resolved = typeof next === 'function' ? (next as (p: T) => T)(current) : next
      // Skip if identical (shallow comparison)
      if (resolved === current) return prev
      // Truncate any redo history
      const truncated = prev.slice(0, index + 1)
      const updated = [...truncated, resolved]
      // Enforce max history
      if (updated.length > maxHistory) {
        const excess = updated.length - maxHistory
        setIndex(i => i - excess)
        return updated.slice(excess)
      }
      setIndex(truncated.length)
      return updated
    })
  }, [index, maxHistory])

  const undo = useCallback(() => {
    setIndex(i => {
      if (i > 0) {
        isUndoRedo.current = true
        return i - 1
      }
      return i
    })
  }, [])

  const redo = useCallback(() => {
    setIndex(i => {
      if (i < history.length - 1) {
        isUndoRedo.current = true
        return i + 1
      }
      return i
    })
  }, [history.length])

  const reset = useCallback((initial: T) => {
    setHistory([initial])
    setIndex(0)
  }, [])

  /* ---- Keyboard shortcuts ---- */
  useEffect(() => {
    if (!keyboard) return

    const handler = (e: KeyboardEvent) => {
      // Only handle when no input/textarea is focused (unless Ctrl is pressed)
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault()
        undo()
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'z' && e.shiftKey) {
        e.preventDefault()
        redo()
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'y') {
        e.preventDefault()
        redo()
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [keyboard, undo, redo])

  return {
    value,
    set,
    undo,
    redo,
    canUndo: index > 0,
    canRedo: index < history.length - 1,
    reset,
    historyIndex: index,
    historyLength: history.length,
  }
}
