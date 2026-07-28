/* ================================================================
   PinButton — toggle pin/unpin for compound comparison
   ================================================================ */

import { useApp } from '@/context/AppContext'
import type { PinnedCompound } from '@/context/AppContext'

interface PinButtonProps {
  compound: PinnedCompound
  /** Optional extra class */
  className?: string
}

/**
 * Small toggle button that pins / unpins a compound in the global
 * pin-to-compare list managed by AppContext.
 */
export default function PinButton({ compound, className }: PinButtonProps) {
  const { state, pinCompound, unpinCompound } = useApp()
  const isPinned = state.pinnedCompounds.some(p => p.smiles === compound.smiles)

  const toggle = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (isPinned) {
      unpinCompound(compound.smiles)
    } else {
      pinCompound(compound)
    }
  }

  return (
    <button
      className={className}
      onClick={toggle}
      title={isPinned ? 'Unpin compound' : 'Pin for comparison'}
      aria-label={isPinned ? 'Unpin compound' : 'Pin for comparison'}
      style={{
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        fontSize: '1.1rem',
        padding: '2px 4px',
        opacity: isPinned ? 1 : 0.5,
        transition: 'opacity 0.15s',
      }}
    >
      {isPinned ? '📌' : '📍'}
    </button>
  )
}
