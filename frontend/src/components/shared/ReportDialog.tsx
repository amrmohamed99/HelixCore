/* ================================================================
   ReportDialog — Generate PDF / HTML reports from screening data
   ================================================================ */

import { useState, useEffect, useCallback } from 'react'
import * as api from '@/lib/api'
import s from '@/styles/shared.module.css'
import css from './ReportDialog.module.css'

type ReportFormat = 'pdf' | 'html' | 'both'

interface ReportDialogProps {
  open: boolean
  onClose: () => void
  /** Auto-scan docking results from this directory */
  resultsDir?: string
  /** Pre-fill project name */
  projectName?: string
}

export default function ReportDialog({ open, onClose, resultsDir, projectName }: ReportDialogProps) {
  const [format, setFormat] = useState<ReportFormat>('both')
  const [title, setTitle] = useState('Screening Report')
  const [author, setAuthor] = useState('')
  const [notes, setNotes] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<{ paths: string[]; message: string } | null>(null)
  const [error, setError] = useState('')

  /* Close on Escape key */
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() },
    [onClose],
  )
  useEffect(() => {
    if (!open) return
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, handleKeyDown])

  if (!open) return null

  const handleGenerate = async () => {
    setLoading(true)
    setError('')
    setResult(null)

    try {
      const res = await api.generateReport({
        title,
        format,
        results_dir: resultsDir || undefined,
        project_name: projectName || undefined,
        author: author || undefined,
        custom_text: notes || undefined,
      })
      setResult(res)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Report generation failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={css.overlay} onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className={css.dialog} role="dialog" aria-modal="true" aria-labelledby="report-dialog-title">
        <div className={css.header}>
          <span className={css.title} id="report-dialog-title">📄 Generate Report</span>
          <button className={css.closeBtn} onClick={onClose} aria-label="Close dialog">✕</button>
        </div>

        <div className={css.field}>
          <label className={css.fieldLabel} htmlFor="report-title">Report Title</label>
          <input id="report-title" className={s.input} value={title} onChange={e => setTitle(e.target.value)} placeholder="Screening Report" />
        </div>

        <div className={css.field}>
          <label className={css.fieldLabel} htmlFor="report-author">Author (optional)</label>
          <input id="report-author" className={s.input} value={author} onChange={e => setAuthor(e.target.value)} placeholder="Your name" />
        </div>

        <div className={css.field}>
          <label className={css.fieldLabel}>Format</label>
          <div className={css.formatPicker} role="radiogroup" aria-label="Report format">
            {(['pdf', 'html', 'both'] as ReportFormat[]).map(f => (
              <button
                key={f}
                className={`${css.formatOption} ${format === f ? css.formatOptionActive : ''}`}
                onClick={() => setFormat(f)}
                role="radio"
                aria-checked={format === f}
              >
                {f === 'pdf' && '📑 PDF'}
                {f === 'html' && '🌐 HTML'}
                {f === 'both' && '📑+🌐 Both'}
              </button>
            ))}
          </div>
        </div>

        <div className={css.field}>
          <label className={css.fieldLabel} htmlFor="report-notes">Notes (optional)</label>
          <textarea
            id="report-notes"
            className={s.input}
            value={notes}
            onChange={e => setNotes(e.target.value)}
            placeholder="Add any observations or notes…"
            rows={3}
            style={{ resize: 'vertical' }}
          />
        </div>

        {resultsDir && (
          <div className={css.field}>
            <label className={css.fieldLabel}>Data Source</label>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>{resultsDir}</span>
          </div>
        )}

        {error && <div style={{ color: 'var(--rose)', fontSize: '0.82rem', marginTop: 8 }}>⚠ {error}</div>}

        {result && (
          <div className={css.result}>
            <span style={{ color: 'var(--green)', fontSize: '0.82rem', fontWeight: 600 }}>✓ {result.message}</span>
            {result.paths.map((p, i) => (
              <div key={i} className={css.resultPath} style={{ marginTop: 6 }}>{p}</div>
            ))}
          </div>
        )}

        <div className={css.actions}>
          <button className={s.btnSecondary} onClick={onClose}>Cancel</button>
          <button className={s.btnPrimary} onClick={handleGenerate} disabled={loading}>
            {loading ? 'Generating…' : '📄 Generate'}
          </button>
        </div>
      </div>
    </div>
  )
}
