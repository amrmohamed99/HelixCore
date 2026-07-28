/* ================================================================
   ProgressBar — Real-time task progress with cancel/pause/skip
   Connects to the WebSocket progress stream via useWebSocket.
   ================================================================ */

import css from './ProgressBar.module.css'

export interface ProgressBarProps {
  /** Task label (e.g. "Docking") */
  label: string
  /** 0–100 percentage */
  progress: number
  /** Current step / total */
  current?: number
  total?: number
  /** Elapsed time in seconds */
  elapsed?: number
  /** Status message */
  message?: string
  /** Task status */
  status?: 'pending' | 'running' | 'paused' | 'cancelled' | 'completed' | 'error' | 'skipped'
  /** Callback: cancel */
  onCancel?: () => void
  /** Callback: pause */
  onPause?: () => void
  /** Callback: resume */
  onResume?: () => void
  /** Callback: skip current item */
  onSkip?: () => void
}

function formatElapsed(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}s`
  const m = Math.floor(sec / 60)
  const s = Math.round(sec % 60)
  return `${m}m ${s}s`
}

export default function ProgressBar({
  label,
  progress,
  current,
  total,
  elapsed,
  message,
  status = 'running',
  onCancel,
  onPause,
  onResume,
  onSkip,
}: ProgressBarProps) {
  const trackClass = status === 'paused' ? css.trackPaused
    : status === 'error' || status === 'cancelled' ? css.trackError
    : status === 'completed' ? css.trackComplete
    : css.trackRunning

  const pct = Math.min(100, Math.max(0, progress))
  const isPaused = status === 'paused'
  const isActive = status === 'running' || status === 'paused'

  return (
    <div className={css.container}>
      <div className={css.header}>
        <span className={css.label}>{label}</span>
        <div className={css.meta}>
          {current != null && total != null && total > 0 && (
            <span>{current}/{total}</span>
          )}
          <span>{pct.toFixed(0)}%</span>
          {elapsed != null && elapsed > 0 && (
            <span>{formatElapsed(elapsed)}</span>
          )}
        </div>
      </div>

      <div className={css.trackOuter}>
        <div
          className={`${css.trackInner} ${trackClass}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {message && <div className={css.message}>{message}</div>}

      {isActive && (onCancel || onPause || onResume || onSkip) && (
        <div className={css.footer}>
          {onSkip && (
            <button className={css.controlBtn} onClick={onSkip} title="Skip current item">
              ⏭ Skip
            </button>
          )}
          {isPaused && onResume && (
            <button className={css.controlBtn} onClick={onResume} title="Resume">
              ▶ Resume
            </button>
          )}
          {!isPaused && onPause && (
            <button className={css.controlBtn} onClick={onPause} title="Pause">
              ⏸ Pause
            </button>
          )}
          {onCancel && (
            <button className={`${css.controlBtn} ${css.controlBtnDanger}`} onClick={onCancel} title="Cancel">
              ✕ Cancel
            </button>
          )}
        </div>
      )}
    </div>
  )
}
