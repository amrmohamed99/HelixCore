/* ================================================================
   WorkspaceError — blocking overlay when workspace is invalid
   ================================================================ */

import styles from './WorkspaceError.module.css'

interface WorkspaceErrorProps {
  error: string | null
  onChooseNew: () => void
  onRetry: () => void
}

export default function WorkspaceError({ error, onChooseNew, onRetry }: WorkspaceErrorProps) {
  return (
    <div className={styles.overlay}>
      <div className={styles.card}>
        <div className={styles.icon}>
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <rect x="8" y="12" width="32" height="28" rx="3" stroke="var(--red)" strokeWidth="2" />
            <path d="M8 20h32" stroke="var(--red)" strokeWidth="2" />
            <circle cx="14" cy="16" r="1.5" fill="var(--red)" opacity="0.5" />
            <circle cx="19" cy="16" r="1.5" fill="var(--red)" opacity="0.5" />
            <path d="M20 30l8 8M28 30l-8 8" stroke="var(--red)" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </div>
        <h2 className={styles.title}>Workspace Error</h2>
        <p className={styles.desc}>
          The workspace directory is missing or not writable. Please choose a valid location.
        </p>
        {error && <p className={styles.detail}>{error}</p>}
        <div className={styles.actions}>
          <button className={styles.primaryBtn} onClick={onChooseNew}>
            Choose New Location
          </button>
          <button className={styles.secondaryBtn} onClick={onRetry}>
            Retry
          </button>
        </div>
      </div>
    </div>
  )
}
