/* ================================================================
   PathDisplay — shows a file/dir path with copy + open-in-explorer
   ================================================================ */

import { useState } from 'react'
import styles from './PathDisplay.module.css'

interface Props {
  /** Label shown above the path */
  label?: string
  /** The file or directory path */
  path: string
}

export default function PathDisplay({ label, path }: Props) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(path)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard unavailable in some contexts */
    }
  }

  const handleOpenFolder = () => {
    if (window.electronAPI) {
      window.electronAPI.showItemInFolder(path)
    }
  }

  if (!path) return null

  return (
    <div className={styles.wrapper}>
      {label && <span className={styles.label}>{label}</span>}
      <div className={styles.pathRow}>
        <span className={styles.path}>{path}</span>
        <button
          className={styles.actionBtn}
          onClick={handleCopy}
          title="Copy path"
          type="button"
        >
          {copied ? '✓' : '📋'}
        </button>
        {window.electronAPI && (
          <button
            className={styles.actionBtn}
            onClick={handleOpenFolder}
            title="Open in Explorer"
            type="button"
          >
            📂
          </button>
        )}
      </div>
    </div>
  )
}
