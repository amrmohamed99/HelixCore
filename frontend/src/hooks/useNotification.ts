/* ================================================================
   useNotification — send native system notifications
   Works in both Electron (via Notification API) and browser contexts.
   ================================================================ */

import { useCallback } from 'react'
import helixIcon from '@/assets/helix-icon.png'

interface NotifyOptions {
  /** Notification title */
  title: string
  /** Body text */
  body: string
  /** Whether to only fire when the window is not focused */
  onlyWhenHidden?: boolean
}

export function useNotification() {
  const notify = useCallback(({ title, body, onlyWhenHidden = true }: NotifyOptions) => {
    /* Skip if window is focused and onlyWhenHidden is set */
    if (onlyWhenHidden && document.hasFocus()) return

    /* Check for Notification API support */
    if (!('Notification' in window)) return

    if (Notification.permission === 'granted') {
      new Notification(title, { body, icon: helixIcon })
    } else if (Notification.permission !== 'denied') {
      Notification.requestPermission().then((perm) => {
        if (perm === 'granted') {
          new Notification(title, { body, icon: helixIcon })
        }
      })
    }
  }, [])

  return { notify }
}
