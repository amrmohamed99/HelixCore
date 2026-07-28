/* ================================================================
   Minimization — Energy minimization of ligand structures
   ================================================================ */

import { useState, useEffect } from 'react'
import * as api from '@/lib/api'
import type { MinimizeResponse } from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { usePipelineStep } from '@/hooks/usePipelineStep'
import { useWorkspace } from '@/hooks/useWorkspace'
import { useTimer } from '@/hooks/useTimer'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useAbortController } from '@/hooks/useAbortController'
import { PageShell, FilePicker, Alert, PathDisplay, Tooltip, ElapsedTimer, EmptyState, FailureDetails } from '@/components/shared'
import s from '@/styles/shared.module.css'

export default function Minimization() {
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const { markRunning, markDone, markError } = usePipelineStep('minimize')
  const { paths, ready } = useWorkspace()
  const timer = useTimer()
  const { getSignal, abort, isAborted } = useAbortController()
  const [directory, setDirectory] = useState('')
  const [forceField, setForceField] = useState('MMFF94')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<MinimizeResponse | null>(null)
  const [error, setError] = useState('')

  useKeyboardShortcuts([
    { key: 'Enter', ctrl: true, action: () => handleMinimize(), enabled: !loading && !!directory },
  ])

  useEffect(() => {
    if (ready && !directory) setDirectory(paths.ligands3d)
  }, [ready])

  const handleMinimize = async () => {
    if (!directory) return
    markRunning()
    setLoading(true)
    setError('')
    setResult(null)
    timer.start()
    addLog(`Minimizing structures in ${directory} with ${forceField}…`)

    try {
      const signal = getSignal()
      const res = await api.minimize({ directory, force_field: forceField }, signal)
      setResult(res)
      addLog(`✓ Minimized ${res.processed} files (${res.failed} failed)`)
      addToast(`Minimized ${res.processed} structures`, 'success')
      markDone()
    } catch (err: unknown) {
      if (isAborted()) { addLog('⚠ Minimization cancelled'); addToast('Minimization cancelled', 'info'); markError(); return }
      const msg = err instanceof Error ? err.message : 'Minimization failed'
      setError(msg)
      addLog(`✗ Minimize error: ${msg}`)
      addToast(msg, 'error')
      markError()
    } finally {
      setLoading(false)
      timer.stop()
    }
  }

  return (
    <PageShell
      emoji="⚡"
      title="Minimization"
      subtitle="Optimize ligand geometry with force field energy minimization"
      infoTooltip="Optimize ligand 3D geometries using molecular mechanics force field energy minimization to remove steric clashes and find low-energy conformations."
      helpUrl="https://www.rdkit.org/docs/GettingStartedInPython.html#working-with-3d-molecules"
      nextStep={{ label: 'Convert', path: '/convert' }}
    >
      <div className={s.card}>
        <div className={s.cardHeader}><span className={s.cardTitle}>Configuration</span></div>
        <div className={s.formGrid}>
          <FilePicker
            label="Input Directory"
            value={directory}
            onChange={setDirectory}
            directory
            placeholder="Select folder with PDB files…"
          />
          <div className={s.formGroup}>
            <label className={s.label} htmlFor="min-ff">Force Field <Tooltip text="Molecular mechanics force field — MMFF94 is recommended for drug-like molecules, UFF is a universal fallback">ⓘ</Tooltip></label>
            <select id="min-ff" className={s.select} value={forceField} onChange={(e) => setForceField(e.target.value)}>
              <option value="MMFF94">MMFF94</option>
              <option value="MMFF94s">MMFF94s</option>
              <option value="UFF">UFF</option>
            </select>
          </div>
        </div>
        <div className={s.actions} style={{ marginTop: 16 }}>
          <button className={s.btnPrimary} onClick={handleMinimize} disabled={loading || !directory}>
            {loading ? <><span className={s.spinnerSmall} /> Minimizing…</> : '⚡ Run Minimization'}
          </button>
          {loading && <button className={s.btnDanger} onClick={() => { abort(); setLoading(false); timer.stop() }}>✕ Cancel</button>}
          <ElapsedTimer time={timer.formatted} running={timer.running} />
          <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
        </div>
      </div>

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {!result && !loading && !error && (
        <EmptyState icon="⚡" title="No Minimization Results" description="Select a directory of 3D structures from the Batch Generate step to energy-minimize with RDKit force fields." />
      )}

      {result && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Results</span>
            <span className={s.badgeGreen}>Complete</span>
          </div>
          <div className={s.statsGrid}>
            <div className={s.card} style={{ textAlign: 'center' }}>
              <strong style={{ color: 'var(--green)', fontSize: '1.5rem' }}>{result.processed}</strong>
              <p className={s.label}>Processed <Tooltip text="Number of ligand PDB files successfully energy-minimized">ⓘ</Tooltip></p>
            </div>
            <div className={s.card} style={{ textAlign: 'center' }}>
              <strong style={{ color: result.failed > 0 ? 'var(--rose)' : 'var(--text-muted)', fontSize: '1.5rem' }}>{result.failed}</strong>
              <p className={s.label}>Failed <Tooltip text="Files that could not be minimized — often due to missing atoms or unsupported atom types">ⓘ</Tooltip></p>
            </div>
          </div>
          <PathDisplay label="Output Directory" path={result.output_dir} />
          <FailureDetails failures={result.failures} />
        </div>
      )}
    </PageShell>
  )
}
