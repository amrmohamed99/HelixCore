/* ================================================================
   Dashboard — main overview page (BioScouter Core style)
   ================================================================ */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp, type PipelineStep } from '@/context/AppContext'
import { downloadReport } from '@/lib/report'
import Skeleton from '@/components/shared/Skeleton'
import PipelineFlow from '@/components/shared/PipelineFlow'
import ConfirmDialog from '@/components/shared/ConfirmDialog'
import styles from './Dashboard.module.css'

const floatingPills = [
  { emoji: '🧬', label: 'RDKit Active' },
  { emoji: '⚗️', label: 'OpenBabel' },
  { emoji: '🧲', label: 'AutoDock Vina' },
  { emoji: '🤖', label: 'ML Engine' },
]

const pipelineSteps: { num: number; label: string; desc: string; key: PipelineStep; path: string }[] = [
  { num: 1, label: 'PDB Fetch', desc: 'Retrieve receptor PDB', key: 'fetch', path: '/fetch' },
  { num: 2, label: 'Pocket Scan', desc: 'Binding site analysis', key: 'pocket', path: '/pocket' },
  { num: 3, label: 'Ligand Gen', desc: 'SMILES → 3D structures', key: 'batch', path: '/batch' },
  { num: 4, label: 'Minimize', desc: 'Energy optimization', key: 'minimize', path: '/minimize' },
  { num: 5, label: 'Convert', desc: 'PDB → PDBQT format', key: 'convert', path: '/convert' },
  { num: 6, label: 'Docking', desc: 'AutoDock Vina scoring', key: 'docking', path: '/docking' },
  { num: 7, label: 'Oracle AI', desc: 'ML affinity rescoring', key: 'oracle', path: '/oracle' },
  { num: 8, label: 'Results', desc: 'Ranked candidates export', key: 'results', path: '/results' },
]

export default function Dashboard() {
  const { state, dispatch } = useApp()
  const navigate = useNavigate()
  const stats = state.systemStats
  const [time, setTime] = useState(new Date())
  const [showResetConfirm, setShowResetConfirm] = useState(false)
  const doneCount = Object.values(state.pipelineSteps).filter((s) => s === 'done').length

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>
            <span>📊</span> Mission Control
          </h1>
          <p className={styles.subtitle}>Drug discovery pipeline overview</p>
        </div>
        <div className={styles.headerRight}>
          <div className={styles.clock}>{time.toLocaleTimeString()}</div>
        </div>
      </div>

      {/* Floating pills */}
      <div className={styles.pills} data-tour="tools-pills">
        {floatingPills.map((p) => (
          <span key={p.label} className={styles.pill}>
            <span>{p.emoji}</span> {p.label}
          </span>
        ))}
      </div>

      {/* Stat cards */}
      <div className={styles.statsGrid} data-tour="stats-grid">
        <div className={styles.statCard}>
          <div className={`${styles.statIcon} ${styles.statIconBlue}`}>🔬</div>
          <div className={styles.statInfo}>
            <span className={styles.statLabel}>Backend</span>
            <span className={styles.statValue}>
              {state.backendStatus === 'online' ? 'Online' : state.backendStatus}
            </span>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={`${styles.statIcon} ${styles.statIconGreen}`}>⚡</div>
          <div className={styles.statInfo}>
            <span className={styles.statLabel}>CPU Usage</span>
            <span className={styles.statValue}>
              {stats ? `${stats.cpu_percent.toFixed(1)}%` : <Skeleton width="48px" height="1.2rem" />}
            </span>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={`${styles.statIcon} ${styles.statIconViolet}`}>💾</div>
          <div className={styles.statInfo}>
            <span className={styles.statLabel}>RAM Usage</span>
            <span className={styles.statValue}>
              {stats ? `${stats.ram_percent.toFixed(1)}%` : <Skeleton width="48px" height="1.2rem" />}
            </span>
          </div>
        </div>
        <div className={styles.statCard}>
          <div className={`${styles.statIcon} ${styles.statIconAmber}`}>🧮</div>
          <div className={styles.statInfo}>
            <span className={styles.statLabel}>Pipeline</span>
            <span className={styles.statValue}>{doneCount}/8</span>
          </div>
        </div>
      </div>

      {/* Pipeline steps */}
      <div className={styles.card} data-tour="pipeline-card">
        <div className={styles.cardHeader}>
          <h2 className={styles.cardTitle}>🚀 Virtual Screening Pipeline</h2>
          <div className={styles.cardActions}>
            {doneCount > 0 && (
              <>
                <button
                  className={styles.resetBtn}
                  onClick={() => downloadReport({ steps: state.pipelineSteps })}
                >
                  📄 Export Report
                </button>
                <button
                  className={styles.resetBtn}
                  onClick={() => setShowResetConfirm(true)}
                >
                  ↺ Reset
                </button>
              </>
            )}
            <button
              className={styles.pipelineBtn}
              onClick={() => navigate('/pipeline')}
            >
              Run Full Pipeline →
            </button>
          </div>
        </div>
        <PipelineFlow steps={state.pipelineSteps} />
        <div className={styles.stepsGrid}>
          {pipelineSteps.map((step) => {
            const status = state.pipelineSteps[step.key]
            const badgeClass = status === 'done' ? styles.stepBadgeDone
              : status === 'running' ? styles.stepBadgeRunning
              : status === 'error' ? styles.stepBadgeError
              : styles.stepBadge
            return (
              <button
                key={step.num}
                className={styles.step}
                onClick={() => navigate(step.path)}
              >
                <div className={styles.stepNum}>{step.num}</div>
                <div className={styles.stepBody}>
                  <span className={styles.stepLabel}>{step.label}</span>
                  <span className={styles.stepDesc}>{step.desc}</span>
                </div>
                <span className={badgeClass}>{status}</span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Quick actions */}
      <div className={styles.quickGrid}>
        <button className={styles.quickCard} onClick={() => navigate('/fetch')}>
          <span className={styles.quickEmoji}>🔬</span>
          <span className={styles.quickLabel}>Fetch PDB</span>
          <span className={styles.quickDesc}>Download receptor PDB</span>
        </button>
        <button className={styles.quickCard} onClick={() => navigate('/docking')}>
          <span className={styles.quickEmoji}>🧲</span>
          <span className={styles.quickLabel}>Run Docking</span>
          <span className={styles.quickDesc}>Vina molecular docking</span>
        </button>
        <button className={styles.quickCard} onClick={() => navigate('/oracle')}>
          <span className={styles.quickEmoji}>🤖</span>
          <span className={styles.quickLabel}>Oracle AI</span>
          <span className={styles.quickDesc}>ML affinity prediction</span>
        </button>
        <button className={styles.quickCard} onClick={() => navigate('/results')}>
          <span className={styles.quickEmoji}>📋</span>
          <span className={styles.quickLabel}>View Results</span>
          <span className={styles.quickDesc}>Explore & export data</span>
        </button>
      </div>

      <ConfirmDialog
        open={showResetConfirm}
        title="Reset Pipeline"
        message="This will reset all pipeline step statuses back to 'ready'. Your files and results will not be deleted."
        confirmLabel="Reset All"
        danger
        onConfirm={() => {
          dispatch({ type: 'RESET_PIPELINE' })
          setShowResetConfirm(false)
        }}
        onCancel={() => setShowResetConfirm(false)}
      />
    </div>
  )
}
