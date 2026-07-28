/* ================================================================
   About — Creator profile inspired by BioScouter concept
   ================================================================ */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '@/context/AppContext'
import styles from './About.module.css'

export default function About() {
  const { state } = useApp()
  const navigate = useNavigate()
  const stats = state.systemStats
  const [appVersion, setAppVersion] = useState('3.0.0')
  const [platform, setPlatform] = useState('')

  useEffect(() => {
    if (window.electronAPI) {
      window.electronAPI.getAppVersion().then(setAppVersion)
      window.electronAPI.getPlatform().then(setPlatform)
    }
  }, [])

  const today = new Date().toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })

  const quickLinks = [
    { emoji: '🔬', label: 'Fetch PDB', desc: 'Retrieve receptor', path: '/fetch' },
    { emoji: '🎯', label: 'Pocket Scan', desc: 'Binding analysis', path: '/pocket' },
    { emoji: '🚀', label: 'Run Pipeline', desc: 'Full screening', path: '/pipeline' },
    { emoji: '📊', label: 'Dashboard', desc: 'Mission control', path: '/dashboard' },
  ]

  return (
    <div className={styles.page}>
      {/* ---- Creator card ---- */}
      <div className={styles.profileCard}>
        <div className={styles.profileTop}>
          <div className={styles.avatar}>
            <span className={styles.avatarInitials}>AM</span>
          </div>
          <div className={styles.profileInfo}>
            <h1 className={styles.name}>Amr Mohamed</h1>
            <p className={styles.role}>Bioinformatician | Computational Biologist</p>
            <p className={styles.email}>
              AAlhfnawy@nu.edu.eg&nbsp;&nbsp;•&nbsp;&nbsp;amrmo211999@gmail.com
            </p>
          </div>
          <div className={styles.profileMeta}>
            <span className={styles.statusBadge}>
              <span className={styles.statusGlow} />
              STATUS: ACTIVE
            </span>
            <span className={styles.date}>{today}</span>
          </div>
        </div>
      </div>

      {/* ---- Mission Directive ---- */}
      <div className={styles.card}>
        <h2 className={styles.cardTitle}>📋 MISSION DIRECTIVE</h2>
        <p className={styles.missionText}>
          <strong>Helix Core v{appVersion}</strong> accelerates early-stage pharmaceutical research by
          integrating receptor preparation, ligand generation, molecular docking, and AI-powered
          affinity rescoring into a single streamlined desktop application. Designed for computational
          biologists and medicinal chemists, the platform eliminates the friction of tool switching
          and manual file management across the virtual screening pipeline.
        </p>
        <div className={styles.techPills}>
          <span className={styles.pill}>🐍 Python 3.12+</span>
          <span className={styles.pill}>⚡ FastAPI</span>
          <span className={styles.pill}>⚛️ React</span>
          <span className={styles.pill}>🖥️ Electron</span>
          <span className={styles.pill}>🧬 RDKit</span>
          <span className={styles.pill}>⚗️ OpenBabel</span>
          <span className={styles.pill}>🧲 AutoDock Vina</span>
          <span className={styles.pill}>🤖 scikit-learn</span>
        </div>
      </div>

      <div className={styles.bottomGrid}>
        {/* ---- System Resources ---- */}
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>💻 SYSTEM RESOURCES</h2>
          <div className={styles.resourceList}>
            <div className={styles.resourceRow}>
              <span className={styles.resourceLabel}>CPU</span>
              <div className={styles.barTrack}>
                <div
                  className={styles.barFill}
                  style={{
                    width: `${stats?.cpu_percent ?? 0}%`,
                    background: (stats?.cpu_percent ?? 0) > 80 ? 'var(--rose)' : 'var(--accent)',
                  }}
                />
              </div>
              <span className={styles.resourceValue}>{stats?.cpu_percent.toFixed(0) ?? 0}%</span>
            </div>
            <div className={styles.resourceRow}>
              <span className={styles.resourceLabel}>RAM</span>
              <div className={styles.barTrack}>
                <div
                  className={styles.barFill}
                  style={{
                    width: `${stats?.ram_percent ?? 0}%`,
                    background: (stats?.ram_percent ?? 0) > 80 ? 'var(--rose)' : 'var(--green)',
                  }}
                />
              </div>
              <span className={styles.resourceValue}>{stats?.ram_percent.toFixed(0) ?? 0}%</span>
            </div>
            <div className={styles.resourceMeta}>
              <span>Cores: {stats?.cores ?? '—'}</span>
              <span>RAM: {stats?.ram_total_gb ?? '—'} GB</span>
              <span>Platform: {platform || '—'}</span>
            </div>
          </div>
        </div>

        {/* ---- Quick Deployment ---- */}
        <div className={styles.card}>
          <h2 className={styles.cardTitle}>🚀 QUICK DEPLOYMENT</h2>
          <div className={styles.quickGrid}>
            {quickLinks.map((link) => (
              <button
                key={link.path}
                className={styles.quickCard}
                onClick={() => navigate(link.path)}
              >
                <span className={styles.quickEmoji}>{link.emoji}</span>
                <div>
                  <span className={styles.quickLabel}>{link.label}</span>
                  <span className={styles.quickDesc}>{link.desc}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ---- Footer ---- */}
      <div className={styles.footer}>
        <span>Helix Core v{appVersion}</span>
        <span>•</span>
        <span>Built with precision for drug discovery</span>
        <span>•</span>
        <span>© {new Date().getFullYear()} Amr Mohamed</span>
      </div>
    </div>
  )
}
