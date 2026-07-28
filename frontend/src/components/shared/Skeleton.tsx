/* ================================================================
   Skeleton — pulse loading placeholder for content that's loading
   ================================================================ */

import sk from './Skeleton.module.css'

interface Props {
  /** Preset shape */
  variant?: 'text' | 'circle' | 'card'
  /** Custom width (CSS value) */
  width?: string
  /** Custom height (CSS value) */
  height?: string
}

export default function Skeleton({ variant = 'text', width, height }: Props) {
  const cls = variant === 'circle' ? sk.circle : variant === 'card' ? sk.card : sk.text
  return <div className={cls} style={{ width, height }} />
}
