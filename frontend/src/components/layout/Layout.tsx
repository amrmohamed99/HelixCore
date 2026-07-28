/* ================================================================
   Layout — main application shell (Titlebar + Sidebar + Content + Dock + Statusbar)
   ================================================================ */

import { useState, useCallback } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import Titlebar from './Titlebar'
import Sidebar from './Sidebar'
import KernelDock from './KernelDock'
import Statusbar from './Statusbar'
import FloatingJobTracker from './FloatingJobTracker'
import { ErrorBoundary } from '@/components/shared'
import WorkspaceError from '@/components/shared/WorkspaceError'
import PageTransition from '@/components/shared/PageTransition'
import GuidedTour, { type TourStep } from '@/components/shared/GuidedTour'
import { useWorkspace } from '@/hooks/useWorkspace'
import styles from './Layout.module.css'

const TOUR_KEY = 'helix:tour-done'

const TOUR_STEPS: TourStep[] = [
  {
    target: '[data-tour="titlebar-logo"]',
    emoji: '🧬',
    title: 'Welcome to Helix Core',
    description: 'Your all-in-one drug discovery workbench. This tour will walk you through the key areas of the app.',
    route: '/dashboard',
    placement: 'bottom',
  },
  {
    target: '[data-tour="stats-grid"]',
    emoji: '📊',
    title: 'System Dashboard',
    description: 'Live system metrics — CPU, memory, and backend health at a glance.',
    route: '/dashboard',
    placement: 'bottom',
  },
  {
    target: '[data-tour="pipeline-card"]',
    emoji: '🚀',
    title: 'Pipeline Progress',
    description: 'Track every stage of your virtual screening pipeline from fetch to results.',
    route: '/dashboard',
    placement: 'left',
  },
  {
    target: '[data-tour="sidebar-nav"]',
    emoji: '🧭',
    title: 'Navigation',
    description: 'All workflow modules are organized in the sidebar — preparation, processing, screening, and output.',
    placement: 'right',
  },
  {
    target: '[data-tour="tools-pills"]',
    emoji: '🛠️',
    title: 'Active Tools',
    description: 'Quick status of installed scientific tools like RDKit, OpenBabel, and AutoDock Vina.',
    route: '/dashboard',
    placement: 'top',
  },
  {
    target: '[data-tour="status-pill"]',
    emoji: '🟢',
    title: 'Backend Status',
    description: 'Shows whether the Python backend API is online and responsive.',
    placement: 'bottom',
  },
  {
    target: '[data-tour="theme-toggle"]',
    emoji: '🎨',
    title: 'Theme Switcher',
    description: 'Toggle between dark, light, and system themes to suit your preference.',
    placement: 'bottom',
  },
  {
    target: '[data-tour="kernel-toggle"]',
    emoji: '⚙️',
    title: 'Kernel Logs',
    description: 'Open the kernel dock to inspect backend logs, filter entries, and export them.',
    placement: 'top',
  },
]

export default function Layout() {
  const location = useLocation()
  const { valid: wsValid, error: wsError, revalidate: wsRevalidate } = useWorkspace()
  const [showTour, setShowTour] = useState(
    () => !localStorage.getItem(TOUR_KEY)
  )

  const completeTour = useCallback(() => {
    localStorage.setItem(TOUR_KEY, '1')
    setShowTour(false)
  }, [])

  const startTour = useCallback(() => setShowTour(true), [])

  const handleChooseNewWorkspace = useCallback(async () => {
    if (window.electronAPI?.setWorkspace) {
      const selected = await window.electronAPI.setWorkspace()
      if (selected) wsRevalidate()
    }
  }, [wsRevalidate])

  return (
    <div className={styles.shell}>
      <Titlebar />
      <div className={styles.body}>
        <Sidebar onStartTour={startTour} />
        <div className={styles.mainColumn}>
          <main className={styles.content}>
            <ErrorBoundary>
              <PageTransition key={location.pathname}>
                <Outlet />
              </PageTransition>
            </ErrorBoundary>
          </main>
          <KernelDock />
        </div>
      </div>
      <FloatingJobTracker />
      <Statusbar />
      {showTour && <GuidedTour steps={TOUR_STEPS} onComplete={completeTour} />}
      {!wsValid && (
        <WorkspaceError
          error={wsError}
          onChooseNew={handleChooseNewWorkspace}
          onRetry={wsRevalidate}
        />
      )}
    </div>
  )
}
