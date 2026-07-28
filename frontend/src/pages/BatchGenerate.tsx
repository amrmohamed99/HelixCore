/* ================================================================
   Batch Generate — SMILES file → 3D PDB structures
   ================================================================ */

import { useState } from 'react'
import * as api from '@/lib/api'
import type { BatchResponse } from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { usePipelineStep } from '@/hooks/usePipelineStep'
import { useTimer } from '@/hooks/useTimer'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useAbortController } from '@/hooks/useAbortController'
import { PageShell, FilePicker, Alert, PathDisplay, Tooltip, ElapsedTimer, EmptyState, FailureDetails } from '@/components/shared'
import s from '@/styles/shared.module.css'

export default function BatchGenerate() {
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const { markRunning, markDone, markError } = usePipelineStep('batch')
  const timer = useTimer()
  const { getSignal, abort, isAborted } = useAbortController()
  const [smilesFile, setSmilesFile] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<BatchResponse | null>(null)
  const [error, setError] = useState('')

  useKeyboardShortcuts([
    { key: 'Enter', ctrl: true, action: () => handleGenerate(), enabled: !loading && !!smilesFile },
  ])

  const handleGenerate = async () => {
    if (!smilesFile) return
    markRunning()
    setLoading(true)
    setError('')
    setResult(null)
    timer.start()
    addLog(`Batch generation from: ${smilesFile}…`)

    try {
      const signal = getSignal()
      const res = await api.batchGenerate({ smiles_file: smilesFile }, signal)
      setResult(res)
      addLog(`✓ Generated ${res.generated} structures (${res.failed} failed)`)
      addToast(`Generated ${res.generated} 3D structures`, 'success')
      markDone()
    } catch (err: unknown) {
      if (isAborted()) { addLog('⚠ Generation cancelled'); addToast('Generation cancelled', 'info'); markError(); return }
      const msg = err instanceof Error ? err.message : 'Generation failed'
      setError(msg)
      addLog(`✗ Batch error: ${msg}`)
      addToast(msg, 'error')
      markError()
    } finally {
      setLoading(false)
      timer.stop()
    }
  }

  return (
    <PageShell emoji="⚗️" title="Batch Generate" subtitle="Convert SMILES file into 3D PDB structures via RDKit" infoTooltip="Convert a SMILES file into 3D PDB structures using RDKit's ETKDG conformer generation algorithm. Each line should contain one SMILES string, optionally tab-separated with a compound name." helpUrl="https://www.rdkit.org/docs/GettingStartedInPython.html#working-with-3d-molecules" nextStep={{ label: 'Minimize', path: '/minimize' }}>

      <div className={s.card}>
        <div className={s.cardHeader}><span className={s.cardTitle}>Input</span></div>
        <FilePicker label="SMILES File" value={smilesFile} onChange={setSmilesFile} filters={[{ name: 'SMILES Files', extensions: ['smi', 'txt', 'csv'] }]} placeholder="Select SMILES file…" />
        <div className={s.actions} style={{ marginTop: 16 }}>
          <button className={s.btnPrimary} onClick={handleGenerate} disabled={loading || !smilesFile}>
            {loading ? <><span className={s.spinnerSmall} /> Generating…</> : '⚗️ Generate 3D'}
          </button>
          {loading && <button className={s.btnDanger} onClick={() => { abort(); setLoading(false); timer.stop() }}>✕ Cancel</button>}
          <ElapsedTimer time={timer.formatted} running={timer.running} />
          <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
        </div>
      </div>

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {result && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Results</span>
            <span className={s.badgeGreen}>Complete</span>
          </div>
          <div className={s.statsGrid}>
            <div className={s.card}>
              <strong style={{ color: 'var(--green)', fontSize: '1.5rem' }}>{result.generated}</strong>
              <p className={s.label}>Generated <Tooltip text="Number of compounds successfully converted to 3D PDB structures">ⓘ</Tooltip></p>
            </div>
            <div className={s.card}>
              <strong style={{ color: result.failed > 0 ? 'var(--rose)' : 'var(--text-muted)', fontSize: '1.5rem' }}>{result.failed}</strong>
              <p className={s.label}>Failed <Tooltip text="Compounds that could not be converted — invalid SMILES or conformer generation failures">ⓘ</Tooltip></p>
            </div>
          </div>
          <PathDisplay label="Output Directory" path={result.output_dir} />
          <FailureDetails failures={result.failures} />
        </div>
      )}
    </PageShell>
  )
}
