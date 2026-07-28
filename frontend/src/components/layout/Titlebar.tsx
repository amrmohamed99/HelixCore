/* ================================================================
   Titlebar — custom frameless window title bar
   ================================================================ */

import { useState, useEffect } from 'react'
import { useApp } from '@/context/AppContext'
import styles from './Titlebar.module.css'
import appIcon from '@/assets/app-icon.png'

export default function Titlebar() {
  const { state, toggleTheme } = useApp()
  const [isMaximized, setIsMaximized] = useState(false)

  useEffect(() => {
    if (!window.electronAPI) return
    window.electronAPI.isMaximized().then(setIsMaximized)
    const unsub = window.electronAPI.onMaximizeChange(setIsMaximized)
    return unsub
  }, [])

  const statusColor =
    state.backendStatus === 'online'
      ? 'var(--green)'
      : state.backendStatus === 'error'
        ? 'var(--red)'
        : 'var(--amber)'

  return (
    <header className={`${styles.titlebar} drag-region`}>
      <div className={styles.left}>
        <div className={styles.logo} data-tour="titlebar-logo">
          <img src={appIcon} alt="Helix Core" className={styles.logoIcon} />
          <span className={styles.logoText}>HELIX CORE</span>
          <span className={styles.version}>v3.0.0</span>
        </div>
      </div>

      <div className={styles.center}>
        <div className={styles.statusPill} data-tour="status-pill">
          <span className={styles.statusDot} style={{ background: statusColor }} />
          <span className={styles.statusLabel}>{state.backendStatus.toUpperCase()}</span>
        </div>
      </div>

      <div className={`${styles.right} no-drag`}>
        <button
          className={styles.themeBtn}
          onClick={toggleTheme}
          title={`Theme: ${state.theme}`}
          aria-label={`Switch theme (current: ${state.theme})`}
          data-tour="theme-toggle"
        >
          {state.theme === 'dark' ? '☀️' : state.theme === 'light' ? '🌙' : '💻'}
        </button>
        <div className={styles.windowControls}>
          <button
            className={styles.winBtn}
            onClick={() => window.electronAPI?.minimize()}
            title="Minimize"
            aria-label="Minimize window"
          >
            <svg width="10" height="1" viewBox="0 0 10 1"><rect width="10" height="1" fill="currentColor" /></svg>
          </button>
          <button
            className={styles.winBtn}
            onClick={() => window.electronAPI?.maximize()}
            title={isMaximized ? 'Restore' : 'Maximize'}
            aria-label={isMaximized ? 'Restore window' : 'Maximize window'}
          >
            {isMaximized ? (
              <svg width="10" height="10" viewBox="0 0 10 10"><path d="M2 0v2H0v8h8V8h2V0H2zm6 8H1V3h7v5zm1-6H3V1h6v1z" fill="currentColor" /></svg>
            ) : (
              <svg width="10" height="10" viewBox="0 0 10 10"><rect x="0" y="0" width="10" height="10" rx="1" fill="none" stroke="currentColor" strokeWidth="1" /></svg>
            )}
          </button>
          <button
            className={`${styles.winBtn} ${styles.winBtnClose}`}
            onClick={() => window.electronAPI?.close()}
            title="Close"
            aria-label="Close window"
          >
            <svg width="10" height="10" viewBox="0 0 10 10"><path d="M1 1l8 8M9 1l-8 8" stroke="currentColor" strokeWidth="1.2" /></svg>
          </button>
        </div>
      </div>
    </header>
  )
}
