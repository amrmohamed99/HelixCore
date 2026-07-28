/* ================================================================
   Statusbar — bottom status bar with system stats
   ================================================================ */

import { useApp } from '@/context/AppContext'
import styles from './Statusbar.module.css'

export default function Statusbar() {
  const { state } = useApp()
  const stats = state.systemStats

  return (
    <footer className={styles.statusbar}>
      <div className={styles.left}>
        <span className={styles.item}>
          <span
            className={styles.dot}
            style={{
              background:
                state.backendStatus === 'online' ? 'var(--green)' : 'var(--amber)',
            }}
          />
          Backend {state.backendStatus}
        </span>
      </div>
      <div className={styles.right}>
        {stats && (
          <>
            <span className={styles.item}>
              CPU {stats.cpu_percent.toFixed(0)}%
            </span>
            <span className={styles.separator}>|</span>
            <span className={styles.item}>
              RAM {stats.ram_percent.toFixed(0)}%
            </span>
            <span className={styles.separator}>|</span>
            <span className={styles.item}>
              {stats.cores} cores
            </span>
          </>
        )}
        <span className={styles.separator}>|</span>
        <span className={styles.item}>Helix Core v3.0.0</span>
      </div>
    </footer>
  )
}
