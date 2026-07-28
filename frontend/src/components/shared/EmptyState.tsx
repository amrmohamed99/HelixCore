/* ================================================================
   EmptyState — Friendly placeholder for pages with no data
   ================================================================ */

import s from '@/styles/shared.module.css'
import es from './EmptyState.module.css'

interface Props {
  /** Large emoji icon */
  icon: string
  /** Short heading */
  title: string
  /** Descriptive text below the heading */
  description?: string
  /** Optional action button */
  action?: {
    label: string
    onClick: () => void
  }
}

export default function EmptyState({ icon, title, description, action }: Props) {
  return (
    <div className={es.wrapper}>
      <span className={es.icon}>{icon}</span>
      <h3 className={es.title}>{title}</h3>
      {description && <p className={es.description}>{description}</p>}
      {action && (
        <button className={s.btnPrimary} onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  )
}
