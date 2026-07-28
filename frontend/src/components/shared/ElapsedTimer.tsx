/* ================================================================
   ElapsedTimer — renders a pulsing elapsed-time indicator
   ================================================================ */

import et from './ElapsedTimer.module.css'

interface Props {
  /** Formatted time string (mm:ss) */
  time: string
  /** Whether the timer is actively running */
  running: boolean
}

export default function ElapsedTimer({ time, running }: Props) {
  if (!running) return null
  return (
    <span className={et.timer}>
      ⏱ {time}
    </span>
  )
}
