/* ================================================================
   Alert — reusable inline alert card (replaces inline error divs)
   ================================================================ */

import styles from './Alert.module.css'

type AlertVariant = 'error' | 'warning' | 'success' | 'info'

const variantIcons: Record<AlertVariant, string> = {
  error: '✗',
  warning: '⚠',
  success: '✓',
  info: 'ℹ',
}

interface Props {
  variant?: AlertVariant
  message: string
  onDismiss?: () => void
}

export default function Alert({ variant = 'error', message, onDismiss }: Props) {
  if (!message) return null

  return (
    <div className={`${styles.alert} ${styles[variant]}`} role="alert">
      <span className={styles.icon}>{variantIcons[variant]}</span>
      <span className={styles.text}>{message}</span>
      {onDismiss && (
        <button className={styles.dismiss} onClick={onDismiss} aria-label="Dismiss">
          ×
        </button>
      )}
    </div>
  )
}
