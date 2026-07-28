/* ================================================================
   FilePicker — reusable file/folder selection component
   ================================================================ */

import { useState, useRef, useEffect, type DragEvent } from 'react'
import { addRecentPath, getRecentPaths } from '@/lib/session'
import s from '@/styles/shared.module.css'
import fp from './FilePicker.module.css'

interface FileFilter {
  name: string
  extensions: string[]
}

interface Props {
  /** Current file/folder path value */
  value: string
  /** Called with the selected path */
  onChange: (path: string) => void
  /** Placeholder text for the input */
  placeholder?: string
  /** File filters for selectFile dialog — omit for directory picker */
  filters?: FileFilter[]
  /** Use directory picker instead of file picker */
  directory?: boolean
  /** Label text */
  label?: string
  /** Unique key for recent paths tracking (defaults to label) */
  recentKey?: string
}

export default function FilePicker({
  value,
  onChange,
  placeholder = 'Select file…',
  filters,
  directory = false,
  label,
  recentKey,
}: Props) {
  const [showRecent, setShowRecent] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const wrapperRef = useRef<HTMLDivElement>(null)
  const storageKey = recentKey || label || 'file'

  const recents = getRecentPaths(storageKey)

  const selectPath = (path: string) => {
    onChange(path)
    addRecentPath(storageKey, path)
    setShowRecent(false)
  }

  const handleBrowse = async () => {
    if (directory) {
      const dir = await window.electronAPI?.selectDirectory()
      if (dir) selectPath(dir)
    } else {
      const file = await window.electronAPI?.selectFile(filters)
      if (file) selectPath(file)
    }
  }

  /* Close dropdown on outside click */
  useEffect(() => {
    if (!showRecent) return
    const handleClick = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setShowRecent(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [showRecent])

  /* Drag & drop handlers */
  const handleDragOver = (e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragOver(true)
  }

  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragOver(false)
  }

  const handleDrop = (e: DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) {
      /* Electron exposes the full path on dropped files */
      const filePath = (file as File & { path?: string }).path ?? file.name
      selectPath(filePath)
    }
  }

  return (
    <div className={s.formGroup} ref={wrapperRef}>
      {label && <label className={s.label}>{label}</label>}
      <div
        className={`${s.fileInput} ${dragOver ? fp.dragOver : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <input
          className={s.fileInputPath}
          value={value}
          readOnly
          placeholder={placeholder}
          aria-label={value ? `Selected file: ${value}` : placeholder}
        />
        {recents.length > 0 && (
          <button
            className={`${s.btnSecondary} ${s.btnSmall}`}
            onClick={() => setShowRecent(!showRecent)}
            type="button"
            title="Recent paths"
            aria-label="Show recent paths"
            aria-expanded={showRecent}
          >
            ▾
          </button>
        )}
        <button
          className={`${s.btnSecondary} ${s.btnSmall}`}
          onClick={handleBrowse}
          type="button"
        >
          Browse
        </button>
      </div>
      {showRecent && recents.length > 0 && (
        <div className={fp.recentDropdown}>
          <span className={fp.recentTitle}>Recent</span>
          {recents.map((p) => (
            <button
              key={p}
              className={fp.recentItem}
              onClick={() => selectPath(p)}
              type="button"
            >
              {p}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
