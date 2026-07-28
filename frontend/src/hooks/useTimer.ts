/* ================================================================
   useTimer — elapsed time tracker for long-running operations.
   Returns a formatted mm:ss string and controls to start/stop/reset.
   ================================================================ */

import { useState, useRef, useCallback, useEffect } from 'react'

/** Format seconds to mm:ss */
function formatTime(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export function useTimer() {
  const [seconds, setSeconds] = useState(0)
  const [running, setRunning] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const start = useCallback(() => {
    setSeconds(0)
    setRunning(true)
  }, [])

  const stop = useCallback(() => {
    setRunning(false)
  }, [])

  const reset = useCallback(() => {
    setRunning(false)
    setSeconds(0)
  }, [])

  useEffect(() => {
    if (running) {
      intervalRef.current = setInterval(() => {
        setSeconds((prev) => prev + 1)
      }, 1000)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [running])

  return {
    seconds,
    formatted: formatTime(seconds),
    running,
    start,
    stop,
    reset,
  }
}
