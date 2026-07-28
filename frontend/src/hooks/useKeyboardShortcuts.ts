/* ================================================================
   useKeyboardShortcuts — register global keyboard shortcuts
   ================================================================ */

import { useEffect } from 'react'

interface Shortcut {
  /** Key to match (e.g. 'Enter', 's', 'k') */
  key: string
  /** Require Ctrl/Cmd modifier */
  ctrl?: boolean
  /** Require Shift modifier */
  shift?: boolean
  /** Handler function */
  action: () => void
  /** Whether the shortcut is currently enabled (default: true) */
  enabled?: boolean
}

/**
 * Attach global keyboard shortcuts. Automatically cleans up on unmount.
 *
 * @param shortcuts - Array of shortcut definitions.
 */
export function useKeyboardShortcuts(shortcuts: Shortcut[]) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      /* Skip when user is typing in an input/textarea */
      const tag = (e.target as HTMLElement)?.tagName
      const isInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'

      for (const sc of shortcuts) {
        if (sc.enabled === false) continue
        if (sc.key.toLowerCase() !== e.key.toLowerCase()) continue
        if (sc.ctrl && !(e.ctrlKey || e.metaKey)) continue
        if (!sc.ctrl && (e.ctrlKey || e.metaKey)) continue
        if (sc.shift && !e.shiftKey) continue

        /* Allow Ctrl+shortcuts even in inputs, but block plain key shortcuts */
        if (isInput && !sc.ctrl) continue

        e.preventDefault()
        sc.action()
        return
      }
    }

    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [shortcuts])
}
