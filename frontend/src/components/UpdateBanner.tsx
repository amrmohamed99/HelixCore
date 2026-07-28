/* ================================================================
   UpdateBanner — Non-blocking notification for optional updates
   Shown at the top of the app when a non-forced update is available.
   ================================================================ */

import { useState } from 'react'
import styles from './UpdateBanner.module.css'

interface UpdateInfo {
  update_available: boolean
  latest_version?: string
  is_forced?: boolean
  changelog?: string
  download_url?: string
  file_hash?: string
  file_size?: number
}

interface UpdateBannerProps {
  update: UpdateInfo
}

export default function UpdateBanner({ update }: UpdateBannerProps) {
  const [dismissed, setDismissed] = useState(false)

  if (dismissed || !update.update_available || update.is_forced) return null

  return (
    <div className={styles.banner}>
      <div className={styles.content}>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className={styles.icon}>
          <path d="M8 2v8m0 0l3-3m-3 3L5 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M2 12h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <span>
          Update <strong>v{update.latest_version}</strong> is available.
        </span>
        {update.download_url && (
          <a
            href={update.download_url}
            target="_blank"
            rel="noopener noreferrer"
            className={styles.downloadLink}
          >
            Download
          </a>
        )}
      </div>
      <button className={styles.dismiss} onClick={() => setDismissed(true)} title="Dismiss">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>
    </div>
  )
}
