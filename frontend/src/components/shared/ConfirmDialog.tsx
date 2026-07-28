/* ================================================================
   ConfirmDialog — modal dialog for destructive action confirmation
   ================================================================ */

import { useEffect, useCallback } from 'react'
import cd from './ConfirmDialog.module.css'

interface Props {
  /** Whether the dialog is visible */
  open: boolean
  /** Dialog title */
  title: string
  /** Descriptive message */
  message: string
  /** Label for the confirm button (default: "Confirm") */
  confirmLabel?: string
  /** Label for the cancel button (default: "Cancel") */
  cancelLabel?: string
  /** Use red styling for destructive actions */
  danger?: boolean
  /** Called when user confirms */
  onConfirm: () => void
  /** Called when user cancels */
  onCancel: () => void
}

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  danger = false,
  onConfirm,
  onCancel,
}: Props) {
  /* Close on Escape key */
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    },
    [onCancel],
  )

  useEffect(() => {
    if (!open) return
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, handleKeyDown])

  if (!open) return null

  return (
    <div className={cd.overlay} onClick={onCancel}>
      <div className={cd.dialog} role="alertdialog" aria-modal="true" aria-labelledby="confirm-dialog-title" aria-describedby="confirm-dialog-msg" onClick={(e) => e.stopPropagation()}>
        <div id="confirm-dialog-title" className={cd.title}>{title}</div>
        <div id="confirm-dialog-msg" className={cd.message}>{message}</div>
        <div className={cd.actions}>
          <button className={cd.cancelBtn} onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            className={danger ? cd.confirmBtnDanger : cd.confirmBtn}
            onClick={onConfirm}
            autoFocus
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
