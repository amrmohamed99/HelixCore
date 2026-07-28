/* ================================================================
   Tooltip — viewport-aware hover tooltip (portal-based)
   ================================================================ */

import { type ReactNode, useRef, useState, useCallback } from 'react'
import { createPortal } from 'react-dom'
import tt from './Tooltip.module.css'

interface Props {
  /** Tooltip text content */
  text: string
  /** Preferred position relative to the wrapped element */
  position?: 'top' | 'bottom' | 'left' | 'right'
  children: ReactNode
}

const InfoSvg = () => (
  <svg className={tt.infoTrigger} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="16" x2="12" y2="12" />
    <line x1="12" y1="8" x2="12.01" y2="8" />
  </svg>
)

const GAP = 8
const PAD = 8

function computePosition(
  rect: DOMRect,
  tip: DOMRect,
  preferred: 'top' | 'bottom' | 'left' | 'right'
): { top: number; left: number } {
  const vw = window.innerWidth
  const vh = window.innerHeight
  let top = 0
  let left = 0

  if (preferred === 'top' && rect.top - tip.height - GAP > PAD) {
    top = rect.top - tip.height - GAP
    left = rect.left + rect.width / 2 - tip.width / 2
  } else if (preferred === 'bottom' && rect.bottom + tip.height + GAP < vh - PAD) {
    top = rect.bottom + GAP
    left = rect.left + rect.width / 2 - tip.width / 2
  } else if (preferred === 'left' && rect.left - tip.width - GAP > PAD) {
    top = rect.top + rect.height / 2 - tip.height / 2
    left = rect.left - tip.width - GAP
  } else if (preferred === 'right' && rect.right + tip.width + GAP < vw - PAD) {
    top = rect.top + rect.height / 2 - tip.height / 2
    left = rect.right + GAP
  } else {
    top = rect.bottom + GAP
    left = rect.left + rect.width / 2 - tip.width / 2
  }

  /* Clamp to viewport */
  if (left < PAD) left = PAD
  if (left + tip.width > vw - PAD) left = vw - PAD - tip.width
  if (top < PAD) top = PAD
  if (top + tip.height > vh - PAD) top = vh - PAD - tip.height

  return { top, left }
}

export default function Tooltip({ text, position = 'top', children }: Props) {
  const isInfoIcon = typeof children === 'string' && children.trim() === 'ⓘ'
  const triggerRef = useRef<HTMLSpanElement>(null)
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null)
  const [visible, setVisible] = useState(false)

  /* Callback ref — fires the instant the portal <span> is in the DOM */
  const tipCallbackRef = useCallback(
    (node: HTMLSpanElement | null) => {
      if (!node || !triggerRef.current) return
      const rect = triggerRef.current.getBoundingClientRect()
      const tip = node.getBoundingClientRect()
      setCoords(computePosition(rect, tip, position))
    },
    [position]
  )

  const show = useCallback(() => setVisible(true), [])
  const hide = useCallback(() => {
    setVisible(false)
    setCoords(null)
  }, [])

  return (
    <span className={tt.wrapper} ref={triggerRef} onMouseEnter={show} onMouseLeave={hide}>
      {isInfoIcon ? <InfoSvg /> : children}
      {visible &&
        createPortal(
          <span
            ref={tipCallbackRef}
            className={tt.tip}
            style={{
              top: coords?.top ?? -9999,
              left: coords?.left ?? -9999,
              opacity: coords ? 1 : 0,
            }}
          >
            {text}
          </span>,
          document.body
        )}
    </span>
  )
}
