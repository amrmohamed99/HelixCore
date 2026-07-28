import { useMemo } from 'react'
import { useGlobalJob } from '@/hooks/useGlobalJob'
import styles from './FloatingJobTracker.module.css'

const ACTIVE_STATUSES = new Set(['running', 'paused', 'terminating', 'cancelled', 'error'])

function formatElapsed(startedAt: number): string {
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - startedAt))
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}:${String(secs).padStart(2, '0')}`
}

export default function FloatingJobTracker() {
  const { job, controlBusy, pause, resume, terminate } = useGlobalJob()

  const visible = job && ACTIVE_STATUSES.has(job.status)
  const progress = Math.max(0, Math.min(100, job?.progress ?? 0))
  const elapsed = useMemo(() => (job ? formatElapsed(job.started_at) : '0:00'), [job])

  if (!visible || !job) return null

  const isPaused = job.status === 'paused'
  const isTerminating = job.status === 'terminating'
  const isTerminal = job.status === 'cancelled' || job.status === 'error'
  const progressCount = job.total > 0 ? Math.min(job.current + 1, job.total) : 0

  return (
    <section className={`${styles.tracker} ${styles[job.status]}`} aria-live="polite">
      <div className={styles.pulse} />
      <div className={styles.main}>
        <div className={styles.topline}>
          <span className={styles.kicker}>GLOBAL TASK</span>
          <span className={styles.name}>{job.name}</span>
          <span className={styles.status}>{job.status}</span>
        </div>
        <div className={styles.message}>{job.message || 'Working...'}</div>
        <div className={styles.progressTrack} aria-label={`${progress}% complete`}>
          <div className={styles.progressFill} style={{ width: `${progress}%` }} />
        </div>
      </div>

      <div className={styles.meta}>
        <span className={styles.metaLabel}>Progress</span>
        <span>{progress}%</span>
        {job.total > 0 && <span>{progressCount}/{job.total}</span>}
        <span>{elapsed}</span>
      </div>

      {!isTerminal && (
        <div className={styles.controls}>
          <button
            className={styles.controlBtn}
            onClick={isPaused ? resume : pause}
            disabled={controlBusy || isTerminating}
            title={isPaused ? 'Resume task' : 'Pause after current item'}
            aria-label={isPaused ? 'Resume task' : 'Pause task'}
          >
            {isPaused ? 'Resume' : 'Pause'}
          </button>
          <button
            className={`${styles.controlBtn} ${styles.dangerBtn}`}
            onClick={terminate}
            disabled={controlBusy || isTerminating}
            title="Terminate current task and keep produced files"
            aria-label="Terminate task"
          >
            Stop
          </button>
        </div>
      )}
    </section>
  )
}
