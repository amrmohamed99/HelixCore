/* ================================================================
   Format Convert — Batch PDB → PDBQT conversion
   ================================================================ */

import { useState, useEffect } from 'react'
import * as api from '@/lib/api'
import type { ConvertResponse } from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { usePipelineStep } from '@/hooks/usePipelineStep'
import { useWorkspace } from '@/hooks/useWorkspace'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { PageShell, FilePicker, Alert, PathDisplay, Tooltip, EmptyState, FailureDetails } from '@/components/shared'
import s from '@/styles/shared.module.css'

export default function FormatConvert() {
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const { markRunning, markDone, markError } = usePipelineStep('convert')
  const { paths, ready } = useWorkspace()
  const [directory, setDirectory] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ConvertResponse | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (ready && !directory) setDirectory(paths.ligands3d)
  }, [ready])

  const handleConvert = async () => {
    if (!directory) return
    markRunning()
    setLoading(true)
    setError('')
    setResult(null)
    addLog(`Converting PDB → PDBQT in ${directory}…`)

    try {
      const res = await api.convert({ directory })
      setResult(res)
      addLog(`✓ Converted ${res.converted} files${res.failed ? ` (${res.failed} failed)` : ''}`)
      addToast(`Converted ${res.converted} files`, 'success')
      markDone()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Conversion failed'
      setError(msg)
      addLog(`✗ Convert error: ${msg}`)
      addToast(msg, 'error')
      markError()
    } finally {
      setLoading(false)
    }
  }

  useKeyboardShortcuts([{ key: 'Enter', ctrl: true, action: handleConvert, enabled: !loading && !!directory }])

  return (
    <PageShell
      emoji="🔄"
      title="Format Convert"
      subtitle="Batch convert PDB files to PDBQT format via OpenBabel"
      infoTooltip="Batch convert PDB ligand files to PDBQT format required by AutoDock Vina, using OpenBabel for atom typing and partial charge assignment."
      helpUrl="https://openbabel.org/docs/FileFormats/Overview.html"
      nextStep={{ label: 'Docking', path: '/docking' }}
    >
      <div className={s.card}>
        <div className={s.cardHeader}><span className={s.cardTitle}>Input</span></div>
        <FilePicker
          label="Directory with PDB Files"
          value={directory}
          onChange={setDirectory}
          directory
          placeholder="Select folder…"
        />
        <div className={s.actions} style={{ marginTop: 16 }}>
          <button className={s.btnPrimary} onClick={handleConvert} disabled={loading || !directory}>
            {loading ? <><span className={s.spinnerSmall} /> Converting…</> : '🔄 Convert All'}
          </button>
          <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
        </div>
      </div>

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {!result && !loading && !error && (
        <EmptyState icon="🔄" title="No Conversions Yet" description="Select a directory of minimized PDB/SDF files to batch-convert to PDBQT format for docking." />
      )}

      {result && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Results</span>
            <span className={s.badgeGreen}>Complete</span>
          </div>
          <div className={s.statsGrid}>
            <div className={s.card} style={{ textAlign: 'center' }}>
              <strong style={{ color: 'var(--green)', fontSize: '1.5rem' }}>{result.converted}</strong>
              <p className={s.label}>Converted <Tooltip text="Number of PDB files successfully converted to PDBQT format">ⓘ</Tooltip></p>
            </div>
            <div className={s.card} style={{ textAlign: 'center' }}>
              <strong style={{ color: result.failed ? 'var(--rose)' : 'var(--text-muted)', fontSize: '1.5rem' }}>{result.failed ?? 0}</strong>
              <p className={s.label}>Failed <Tooltip text="Files that failed conversion or did not produce valid ligand PDBQT tags">ⓘ</Tooltip></p>
            </div>
          </div>
          <PathDisplay label="Output Directory" path={result.output_dir} />
          <FailureDetails failures={result.failures} />
        </div>
      )}
    </PageShell>
  )
}
