/* ================================================================
   Toast Context — app-wide toast notification system
   ================================================================ */

import { createContext, useContext, useCallback, useState, useRef, type ReactNode } from 'react'
import ToastContainer from '@/components/shared/ToastContainer'

export type ToastVariant = 'success' | 'error' | 'warning' | 'info'

export interface Toast {
  id: number
  message: string
  variant: ToastVariant
  duration: number
}

interface ToastContextValue {
  addToast: (message: string, variant?: ToastVariant, duration?: number) => void
  removeToast: (id: number) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

let toastIdCounter = 0

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
    const timer = timers.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.current.delete(id)
    }
  }, [])

  const addToast = useCallback(
    (message: string, variant: ToastVariant = 'info', duration = 4000) => {
      const id = ++toastIdCounter
      const toast: Toast = { id, message, variant, duration }
      setToasts((prev) => [...prev.slice(-4), toast])

      if (duration > 0) {
        const timer = setTimeout(() => removeToast(id), duration)
        timers.current.set(id, timer)
      }
    },
    [removeToast]
  )

  return (
    <ToastContext.Provider value={{ addToast, removeToast }}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={removeToast} />
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
