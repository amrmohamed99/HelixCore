/* ================================================================
   PageShell — standard page wrapper with title, subtitle, and optional action
   ================================================================ */

import { useNavigate } from 'react-router-dom'
import Breadcrumb from './Breadcrumb'
import Tooltip from './Tooltip'
import s from '@/styles/shared.module.css'
import styles from './PageShell.module.css'

interface Props {
  emoji: string
  title: string
  subtitle: string
  /** Detailed page description shown via tooltip on an info icon */
  infoTooltip?: string
  /** URL to external documentation / help for this page */
  helpUrl?: string
  /** Optional "Next Step" route path (e.g. '/pocket') */
  nextStep?: { label: string; path: string }
  children: React.ReactNode
}

export default function PageShell({ emoji, title, subtitle, infoTooltip, helpUrl, nextStep, children }: Props) {
  const navigate = useNavigate()

  return (
    <div className={s.page}>
      <Breadcrumb />
      <div className={s.pageHeader}>
        <div>
          <h1 className={s.pageTitle}>
            <span>{emoji}</span> {title}
            {infoTooltip && (
              <Tooltip text={infoTooltip} position="bottom">
                <svg className={styles.infoIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" /></svg>
              </Tooltip>
            )}
            {helpUrl && (
              <a
                href={helpUrl}
                target="_blank"
                rel="noopener noreferrer"
                className={styles.helpLink}
                title="Open documentation"
                aria-label="Open documentation"
              >
                <svg className={styles.helpIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3" /><line x1="12" y1="17" x2="12.01" y2="17" /></svg>
              </a>
            )}
          </h1>
          <p className={s.pageSubtitle}>{subtitle}</p>
        </div>
        {nextStep && (
          <button
            className={styles.nextStepBtn}
            onClick={() => navigate(nextStep.path)}
          >
            {nextStep.label} →
          </button>
        )}
      </div>
      {children}
    </div>
  )
}
