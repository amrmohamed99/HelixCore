/* ================================================================
   UndoRedoBar — compact undo/redo controls
   ================================================================ */

import s from '@/styles/shared.module.css'

interface UndoRedoBarProps {
  canUndo: boolean
  canRedo: boolean
  onUndo: () => void
  onRedo: () => void
  historyIndex: number
  historyLength: number
}

/** Compact undo/redo toolbar with keyboard shortcut hints. */
export default function UndoRedoBar({ canUndo, canRedo, onUndo, onRedo, historyIndex, historyLength }: UndoRedoBarProps) {
  if (historyLength <= 1) return null

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      fontSize: '0.75rem',
      color: 'var(--text-secondary)',
    }}>
      <button
        className={s.btnSecondary}
        style={{ fontSize: '0.7rem', padding: '2px 8px' }}
        onClick={onUndo}
        disabled={!canUndo}
        title="Undo (Ctrl+Z)"
      >
        ↩ Undo
      </button>
      <button
        className={s.btnSecondary}
        style={{ fontSize: '0.7rem', padding: '2px 8px' }}
        onClick={onRedo}
        disabled={!canRedo}
        title="Redo (Ctrl+Shift+Z)"
      >
        ↪ Redo
      </button>
      <span style={{ opacity: 0.5 }}>
        {historyIndex + 1}/{historyLength}
      </span>
    </div>
  )
}
