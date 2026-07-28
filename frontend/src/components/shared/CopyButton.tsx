/* ================================================================
   CopyButton — Inline copy-to-clipboard button with feedback
   ================================================================ */

import { useState, useCallback } from 'react'
import s from '@/styles/shared.module.css'

interface CopyButtonProps {
  /** Text to copy to clipboard */
  text: string
  /** Optional label shown before copy icon (default: none) */
  label?: string
  /** Optional CSS class override */
  className?: string
}

/**
 * Small inline button that copies `text` to the clipboard on click.
 * Shows a brief "Copied!" tooltip state for 1.5 s after a successful copy.
 */
export default function CopyButton({ text, label, className }: CopyButtonProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard API unavailable — ignore silently */
    }
  }, [text])

  return (
    <button
      type="button"
      className={`${s.copyBtn} ${className ?? ''}`}
      onClick={handleCopy}
      title={copied ? 'Copied!' : 'Copy to clipboard'}
      aria-label="Copy to clipboard"
    >
      {label && <span className={s.copyLabel}>{label}</span>}
      <span className={s.copyIcon}>{copied ? '✓' : '📋'}</span>
    </button>
  )
}
