/* ================================================================
   Sidebar — navigation with emoji icons (BioScouter Core style)
   ================================================================ */

import { NavLink } from 'react-router-dom'
import { useApp, type PipelineStep, type StepStatus } from '@/context/AppContext'
import styles from './Sidebar.module.css'

interface NavItem {
  path: string
  label: string
  emoji: string
  pipelineKey?: PipelineStep
  isNew?: boolean
}

interface NavCategory {
  title: string
  items: NavItem[]
}

const navCategories: NavCategory[] = [
  {
    title: 'OVERVIEW',
    items: [
      { path: '/dashboard', label: 'Dashboard', emoji: '📊' },
      { path: '/projects', label: 'Projects', emoji: '📁', isNew: true },
    ],
  },
  {
    title: 'PREPARATION',
    items: [
      { path: '/fetch', label: 'PDB Fetch', emoji: '🔬', pipelineKey: 'fetch' },
      { path: '/prepare', label: 'Prepare Receptor', emoji: '🧹', isNew: true },
      { path: '/pocket', label: 'Pocket Analysis', emoji: '🎯', pipelineKey: 'pocket' },
      { path: '/batch', label: 'Batch Generate', emoji: '⚗️', pipelineKey: 'batch' },
      { path: '/filters', label: 'Filters', emoji: '🛡️', isNew: true },
      { path: '/analogs', label: 'Analogs', emoji: '🧬', isNew: true },
      { path: '/fragments', label: 'Fragments', emoji: '🧪', isNew: true },
    ],
  },
  {
    title: 'PROCESSING',
    items: [
      { path: '/minimize', label: 'Minimization', emoji: '⚡', pipelineKey: 'minimize' },
      { path: '/convert', label: 'Format Convert', emoji: '🔄', pipelineKey: 'convert' },
      { path: '/pipeline', label: 'Auto Pipeline', emoji: '🚀' },
    ],
  },
  {
    title: 'SCREENING',
    items: [
      { path: '/docking', label: 'Docking', emoji: '🧲', pipelineKey: 'docking' },
      { path: '/similarity', label: 'Similarity', emoji: '🔍' },
      { path: '/oracle', label: 'Oracle AI', emoji: '🤖', pipelineKey: 'oracle' },
      { path: '/admet', label: 'ADMET', emoji: '💊', isNew: true },
      { path: '/pharmacophore', label: 'Pharmacophore', emoji: '💎', isNew: true },
      { path: '/scaffold', label: 'Scaffold Hop', emoji: '🔀', isNew: true },
    ],
  },
  {
    title: 'OUTPUT',
    items: [
      { path: '/results', label: 'Results', emoji: '📋', pipelineKey: 'results' },
      { path: '/compare', label: 'Compare', emoji: '⚖️', isNew: true },
      { path: '/cluster', label: 'Clustering', emoji: '🧩', isNew: true },
    ],
  },
  {
    title: 'SYSTEM',
    items: [
      { path: '/about', label: 'About', emoji: '👤' },
    ],
  },
]

interface SidebarProps {
  onStartTour?: () => void
}

export default function Sidebar({ onStartTour }: SidebarProps) {
  const { state, toggleDock, toggleSidebar } = useApp()
  const collapsed = state.sidebarCollapsed

  const badgeColor = (status: StepStatus): string | null => {
    if (status === 'done') return 'var(--accent)'
    if (status === 'running') return 'var(--amber)'
    if (status === 'error') return 'var(--red)'
    return null
  }

  return (
    <aside className={`${styles.sidebar} ${collapsed ? styles.collapsed : ''}`}>
      <nav className={styles.nav} data-tour="sidebar-nav">
        {navCategories.map((category) => (
          <div key={category.title} className={styles.category}>
            {!collapsed && <span className={styles.categoryTitle}>{category.title}</span>}
            {category.items.map((item) => {
              const stepStatus = item.pipelineKey ? state.pipelineSteps[item.pipelineKey] : null
              const dotColor = stepStatus ? badgeColor(stepStatus) : null
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={({ isActive }) =>
                    `${styles.navItem} ${isActive ? styles.navItemActive : ''}`
                  }
                  title={collapsed ? item.label : undefined}
                >
                  <span className={styles.navEmoji}>{item.emoji}</span>
                  {!collapsed && <span className={styles.navLabel}>{item.label}</span>}
                  {!collapsed && item.isNew && <span className={styles.newBadge}>NEW</span>}
                  {dotColor && <span className={styles.navBadge} style={{ background: dotColor }} />}
                </NavLink>
              )
            })}
          </div>
        ))}
      </nav>

      <div className={styles.footer}>
        <button className={styles.kernelToggle} onClick={toggleDock} title={collapsed ? 'Kernel' : undefined} data-tour="kernel-toggle">
          <span>⚙️</span>
          {!collapsed && <span>Kernel</span>}
          <span
            className={styles.kernelDot}
            style={{
              background:
                state.backendStatus === 'online' ? 'var(--green)' : 'var(--amber)',
            }}
          />
        </button>
        {onStartTour && (
          <button className={styles.tourBtn} onClick={onStartTour} title={collapsed ? 'Tour' : 'Show guided tour'} data-tour="tour-btn">
            <span>🎓</span>
            {!collapsed && <span>Tour Guide</span>}
          </button>
        )}
        <button className={styles.collapseBtn} onClick={toggleSidebar} title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
          <span className={collapsed ? styles.expandIcon : styles.collapseIcon}>‹</span>
        </button>
      </div>
    </aside>
  )
}
