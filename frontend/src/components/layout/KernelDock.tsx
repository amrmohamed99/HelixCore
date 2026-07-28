/* ================================================================
   KernelDock — collapsible bottom panel showing backend logs + activity
   ================================================================ */

import { useRef, useEffect, useState, useMemo, useCallback } from 'react'
import { useKernel } from '@/hooks/useKernel'
import styles from './KernelDock.module.css'

const BASE_URL = 'http://127.0.0.1:8299'

interface ActivityRecord {
  id: number
  timestamp: string
  action: string
  page: string
  details: Record<string, unknown> | null
  duration_ms: number | null
}

type DockTab = 'logs' | 'activity'

export default function KernelDock() {
  const { logs, isOpen, toggle, clearLogs, backendStatus } = useKernel()
  const logsEndRef = useRef<HTMLDivElement>(null)
  const [filter, setFilter] = useState('')
  const [tab, setTab] = useState<DockTab>('logs')
  const [activities, setActivities] = useState<ActivityRecord[]>([])
  const [activityLoading, setActivityLoading] = useState(false)

  const filteredLogs = useMemo(() => {
    if (!filter) return logs
    const lower = filter.toLowerCase()
    return logs.filter((l) => l.message.toLowerCase().includes(lower))
  }, [logs, filter])

  const filteredActivities = useMemo(() => {
    if (!filter) return activities
    const lower = filter.toLowerCase()
    return activities.filter(
      (a) =>
        a.action.toLowerCase().includes(lower) ||
        a.page.toLowerCase().includes(lower),
    )
  }, [activities, filter])

  const fetchActivities = useCallback(async () => {
    setActivityLoading(true)
    try {
      const res = await fetch(`${BASE_URL}/api/activity/list?per_page=100`)
      if (res.ok) {
        const data = await res.json()
        setActivities(data.entries || [])
      }
    } catch { /* ignore */ }
    setActivityLoading(false)
  }, [])

  const handleClearActivity = useCallback(async () => {
    try {
      await fetch(`${BASE_URL}/api/activity/clear`, { method: 'POST' })
      setActivities([])
    } catch { /* ignore */ }
  }, [])

  const handleExportActivity = useCallback(async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/activity/export`)
      if (res.ok) {
        const data = await res.json()
        const blob = new Blob([data.content], { type: 'application/jsonl' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = data.filename || 'activity.jsonl'
        a.click()
        URL.revokeObjectURL(url)
      }
    } catch { /* ignore */ }
  }, [])

  // Load activities when tab switches
  useEffect(() => {
    if (isOpen && tab === 'activity') fetchActivities()
  }, [isOpen, tab, fetchActivities])

  const handleExportLogs = () => {
    const text = logs
      .map((l) => `[${l.timestamp}] ${l.message}`)
      .join('\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `helix-kernel-${new Date().toISOString().slice(0, 10)}.log`
    a.click()
    URL.revokeObjectURL(url)
  }

  useEffect(() => {
    if (isOpen && tab === 'logs' && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [filteredLogs, isOpen, tab])

  if (!isOpen) return null

  const statusColor =
    backendStatus === 'online'
      ? 'var(--green)'
      : backendStatus === 'error'
        ? 'var(--red)'
        : 'var(--amber)'

  return (
    <div className={styles.dock}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.headerDot} style={{ background: statusColor }} />
          <button
            className={`${styles.tabBtn} ${tab === 'logs' ? styles.tabBtnActive : ''}`}
            onClick={() => setTab('logs')}
          >
            KERNEL
          </button>
          <button
            className={`${styles.tabBtn} ${tab === 'activity' ? styles.tabBtnActive : ''}`}
            onClick={() => setTab('activity')}
          >
            ACTIVITY
          </button>
          <span className={styles.logCount}>
            {tab === 'logs' ? `${logs.length} lines` : `${activities.length} entries`}
          </span>
        </div>
        <div className={styles.headerRight}>
          <input
            className={styles.filterInput}
            type="text"
            placeholder={tab === 'logs' ? 'Filter logs…' : 'Filter activity…'}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          {tab === 'logs' ? (
            <>
              <button className={styles.headerBtn} onClick={handleExportLogs} title="Export logs">📥</button>
              <button className={styles.headerBtn} onClick={clearLogs} title="Clear logs">🗑️</button>
            </>
          ) : (
            <>
              <button className={styles.headerBtn} onClick={fetchActivities} title="Refresh">🔄</button>
              <button className={styles.headerBtn} onClick={handleExportActivity} title="Export activity">📥</button>
              <button className={styles.headerBtn} onClick={handleClearActivity} title="Clear activity">🗑️</button>
            </>
          )}
          <button className={styles.headerBtn} onClick={toggle} title="Close dock">✕</button>
        </div>
      </div>

      {tab === 'logs' && (
        <div className={styles.logsContainer}>
          {filteredLogs.length === 0 ? (
            <div className={styles.empty}>{filter ? 'No matching logs' : 'Waiting for kernel output…'}</div>
          ) : (
            filteredLogs.map((log) => (
              <div key={log.id} className={styles.logLine}>
                <span className={styles.logTime}>{log.timestamp}</span>
                <span className={styles.logMsg}>{log.message}</span>
              </div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      )}

      {tab === 'activity' && (
        <div className={styles.logsContainer}>
          {activityLoading ? (
            <div className={styles.empty}>Loading activity…</div>
          ) : filteredActivities.length === 0 ? (
            <div className={styles.empty}>{filter ? 'No matching activity' : 'No activity recorded yet'}</div>
          ) : (
            filteredActivities.map((a) => (
              <div key={a.id} className={styles.logLine}>
                <span className={styles.logTime}>
                  {new Date(a.timestamp + 'Z').toLocaleTimeString()}
                </span>
                <span className={styles.activityPage}>{a.page}</span>
                <span className={styles.logMsg}>{a.action}</span>
                {a.duration_ms != null && (
                  <span className={styles.activityDuration}>{a.duration_ms}ms</span>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
