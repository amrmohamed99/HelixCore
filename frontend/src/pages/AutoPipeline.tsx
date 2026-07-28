/* ================================================================
   Auto Pipeline — End-to-end SMILES → docking pipeline
   ================================================================ */

import { useState, useEffect } from 'react'
import * as api from '@/lib/api'
import type { PipelineResponse, BatchPipelineResponse } from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { useTimer } from '@/hooks/useTimer'
import { useNotification } from '@/hooks/useNotification'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useSessionField } from '@/hooks/useSessionField'
import { useAbortController } from '@/hooks/useAbortController'
import { useSSE } from '@/hooks/useSSE'
import { PageShell, FilePicker, Alert, PathDisplay, Tooltip, ElapsedTimer } from '@/components/shared'
import s from '@/styles/shared.module.css'

type Mode = 'single' | 'batch'

export default function AutoPipeline() {
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const timer = useTimer()
  const { notify } = useNotification()
  const { getSignal, abort, isAborted } = useAbortController()
  const sse = useSSE()
  const [useStreaming, setUseStreaming] = useSessionField('pipeline.streaming', true)
  const [mode, setMode] = useSessionField<Mode>('pipeline.mode', 'single')
  const [smiles, setSmiles] = useSessionField('pipeline.smiles', '')
  const [name, setName] = useSessionField('pipeline.name', 'ligand')
  const [receptor, setReceptor] = useSessionField('pipeline.receptor', '')
  const [config, setConfig] = useSessionField('pipeline.config', '')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<PipelineResponse | null>(null)
  const [error, setError] = useState('')

  /* Batch-mode state */
  const [smilesFile, setSmilesFile] = useSessionField('pipeline.smilesFile', '')
  const [forceField, setForceField] = useSessionField('pipeline.forceField', 'MMFF94')
  const [runFilters, setRunFilters] = useSessionField('pipeline.runFilters', true)
  const [runAdmet, setRunAdmet] = useSessionField('pipeline.runAdmet', true)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [batchResult, setBatchResult] = useState<BatchPipelineResponse | null>(null)

  useKeyboardShortcuts([
    { key: 'Enter', ctrl: true, action: () => mode === 'single' ? handleRun() : handleBatch(), enabled: !loading && !sse.streaming },
  ])

  /* React to SSE stream completion */
  useEffect(() => {
    if (!sse.event) return
    if (sse.event.step === 'done') {
      timer.stop()
      addLog(`✓ ${sse.event.message}`)
      addToast('Pipeline completed', 'success')
      notify({ title: 'Pipeline Complete', body: sse.event.message })
      if (sse.event.detail?.score) {
        setResult({
          score: String(sse.event.detail.score),
          output_path: sse.event.detail.output_path as string | undefined ?? null,
          message: sse.event.message,
        })
      }
    } else if (sse.event.step === 'error') {
      timer.stop()
      setError(sse.event.message)
      addLog(`✗ ${sse.event.message}`)
      addToast(sse.event.message, 'error')
    }
  }, [sse.event])

  const handleRun = async () => {
    if (!smiles || !receptor || !config) return

    if (useStreaming) {
      setError('')
      setResult(null)
      timer.start()
      addLog('Running pipeline (streaming)…')
      sse.start('/api/pipeline/run-stream', { smiles, name, receptor, config })
      return
    }

    setLoading(true)
    setError('')
    setResult(null)
    timer.start()
    addLog(`Running pipeline: ${name}…`)

    try {
      const signal = getSignal()
      const res = await api.runPipeline({ smiles, name, receptor, config }, signal)
      setResult(res)
      addLog(`✓ Pipeline complete: ${res.message}`)
      addToast('Pipeline completed successfully', 'success')
      notify({ title: 'Pipeline Complete', body: res.message })
    } catch (err: unknown) {
      if (isAborted()) { addLog('⚠ Pipeline cancelled'); addToast('Pipeline cancelled', 'info'); return }
      const msg = err instanceof Error ? err.message : 'Pipeline failed'
      setError(msg)
      addLog(`✗ Pipeline error: ${msg}`)
      addToast(msg, 'error')
    } finally {
      setLoading(false)
      timer.stop()
    }
  }

  const handleBatch = async () => {
    if (!smilesFile || !receptor || !config) return

    if (useStreaming) {
      setError('')
      setBatchResult(null)
      timer.start()
      addLog('Running batch pipeline (streaming)…')
      sse.start('/api/pipeline/batch-stream', {
        smiles_file: smilesFile, receptor, config,
        force_field: forceField, run_filters: runFilters, run_admet: runAdmet,
      })
      return
    }

    setLoading(true)
    setError('')
    setBatchResult(null)
    timer.start()
    addLog(`Running batch pipeline on ${smilesFile}…`)

    try {
      const signal = getSignal()
      const res = await api.runBatchPipeline({
        smiles_file: smilesFile,
        receptor,
        config,
        force_field: forceField,
        run_filters: runFilters,
        run_admet: runAdmet,
      }, signal)
      setBatchResult(res)
      addLog(`✓ Batch complete: ${res.total_docked} docked, best score ${res.best_score}`)
      addToast(`Batch done: ${res.total_docked} docked`, 'success')
      notify({ title: 'Batch Pipeline Complete', body: `${res.total_docked} compounds docked` })
    } catch (err: unknown) {
      if (isAborted()) { addLog('⚠ Batch cancelled'); addToast('Batch cancelled', 'info'); return }
      const msg = err instanceof Error ? err.message : 'Batch pipeline failed'
      setError(msg)
      addLog(`✗ Batch error: ${msg}`)
      addToast(msg, 'error')
    } finally {
      setLoading(false)
      timer.stop()
    }
  }

  return (
    <PageShell
      emoji="🚀"
      title="Auto Pipeline"
      subtitle="End-to-end: SMILES → 3D generation → minimization → conversion → docking"
      infoTooltip="Run the complete virtual screening pipeline automatically — from SMILES input through 3D generation, energy minimization, format conversion, and molecular docking in one click."
      helpUrl="https://en.wikipedia.org/wiki/Virtual_screening"
      nextStep={{ label: 'Results', path: '/results' }}
    >
      {/* Mode Toggle */}
      <div className={s.card}>
        <div className={s.cardHeader}><span className={s.cardTitle}>Mode</span></div>
        <div className={s.actions}>
          <Tooltip text="Process one compound at a time from SMILES to docked score"><button className={mode === 'single' ? s.btnPrimary : s.btnSecondary} onClick={() => setMode('single')}>
            🚀 Single Pipeline
          </button></Tooltip>
          <Tooltip text="Process an entire SMILES file through the full pipeline in batch"><button className={mode === 'batch' ? s.btnPrimary : s.btnSecondary} onClick={() => setMode('batch')}>
            📦 Batch Pipeline
          </button></Tooltip>
          <label className={s.label} style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 'auto', fontSize: '0.8rem' }}>
            <input type="checkbox" checked={useStreaming} onChange={(e) => setUseStreaming(e.target.checked)} />
            Live progress <Tooltip text="Enable SSE streaming for real-time step-by-step progress updates">ⓘ</Tooltip>
          </label>
        </div>
      </div>

      {/* SSE Streaming Progress */}
      {sse.streaming && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Pipeline Progress</span>
            <span className={s.badgeAccent}>{sse.progress}%</span>
          </div>
          <div className={s.progressBar} style={{ height: 8, marginBottom: 12 }}>
            <div className={s.progressFill} style={{ width: `${Math.max(0, sse.progress)}%`, transition: 'width 0.3s ease' }} />
          </div>
          {sse.event && (
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', margin: 0 }}>
              <span className={s.badgeGreen} style={{ marginRight: 8 }}>{sse.event.step}</span>
              {sse.event.message}
              {sse.event.count != null && sse.event.total != null && (
                <span style={{ marginLeft: 8, color: 'var(--text-muted)' }}>({sse.event.count}/{sse.event.total})</span>
              )}
            </p>
          )}
          <div style={{ marginTop: 8 }}>
            <button className={s.btnDanger} onClick={() => { sse.cancel(); timer.stop() }} style={{ fontSize: '0.8rem' }}>✕ Cancel</button>
          </div>
        </div>
      )}

      {/* ── Single Pipeline Mode ── */}
      {mode === 'single' && (
      <>
      <div className={s.card}>
        <div className={s.cardHeader}><span className={s.cardTitle}>Pipeline Configuration</span></div>
        <div className={s.formGrid}>
          <div className={s.formGroupFull}>
            <label className={s.label} htmlFor="pipe-smiles">Molecule Input <Tooltip text="Enter a SMILES string, InChI, compound name (e.g. aspirin), or CAS number">ⓘ</Tooltip></label>
            <input
              id="pipe-smiles"
              className={s.inputMono}
              value={smiles}
              onChange={(e) => setSmiles(e.target.value)}
              placeholder="SMILES, InChI, compound name, or CAS number"
            />
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: 4 }}>Supports: SMILES · InChI · compound name · CAS number · MOL block</span>
          </div>
          <div className={s.formGroup}>
            <label className={s.label} htmlFor="pipe-name">Ligand Name <Tooltip text="Identifier for the ligand in output files">ⓘ</Tooltip></label>
            <input
              id="pipe-name"
              className={s.input}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="ligand"
            />
          </div>
          <FilePicker
            label="Receptor (PDBQT)"
            value={receptor}
            onChange={setReceptor}
            filters={[{ name: 'PDBQT Files', extensions: ['pdbqt'] }]}
            placeholder="Select receptor…"
          />
          <FilePicker
            label="Vina Config File"
            value={config}
            onChange={setConfig}
            filters={[{ name: 'Config Files', extensions: ['txt', 'conf'] }]}
            placeholder="Select config…"
          />
        </div>
        <div className={s.actions} style={{ marginTop: 16 }}>
          <button className={s.btnPrimary} onClick={handleRun} disabled={loading || sse.streaming || !smiles || !receptor || !config}>
            {loading ? <><span className={s.spinnerSmall} /> Running Pipeline…</> : '🚀 Launch Pipeline'}
          </button>
          {loading && <button className={s.btnDanger} onClick={() => { abort(); setLoading(false); timer.stop() }}>✕ Cancel</button>}
          <ElapsedTimer time={timer.formatted} running={timer.running} />
          <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
        </div>
      </div>

      {result && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Pipeline Result</span>
            <span className={s.badgeGreen}>Complete</span>
          </div>
          <p style={{ color: 'var(--text-secondary)', marginBottom: 8 }}>{result.message}</p>
          {result.score && (
            <div className={s.card} style={{ textAlign: 'center', marginBottom: 8 }}>
              <p className={s.label}>Best Docking Score</p>
              <strong style={{ fontSize: '1.8rem', color: 'var(--accent)' }}>{result.score} kcal/mol</strong>
            </div>
          )}
          {result.output_path && <PathDisplay label="Output" path={result.output_path} />}
        </div>
      )}
      </>
      )}

      {/* ── Batch Pipeline Mode ── */}
      {mode === 'batch' && (
      <>
      <div className={s.card}>
        <div className={s.cardHeader}><span className={s.cardTitle}>Batch Configuration</span></div>
        <div className={s.formGrid}>
          <FilePicker
            label="SMILES File (.smi)"
            value={smilesFile}
            onChange={setSmilesFile}
            filters={[{ name: 'SMILES Files', extensions: ['smi', 'csv', 'txt'] }]}
            placeholder="Select SMILES file…"
          />
          <FilePicker
            label="Receptor (PDBQT)"
            value={receptor}
            onChange={setReceptor}
            filters={[{ name: 'PDBQT Files', extensions: ['pdbqt'] }]}
            placeholder="Select receptor…"
          />
          <FilePicker
            label="Vina Config File"
            value={config}
            onChange={setConfig}
            filters={[{ name: 'Config Files', extensions: ['txt', 'conf'] }]}
            placeholder="Select config…"
          />

          {/* Collapsible advanced settings */}
          <div className={s.formGroupFull}>
            <button
              type="button"
              className={s.btnSecondary}
              onClick={() => setShowAdvanced(!showAdvanced)}
              style={{ fontSize: '0.78rem', padding: '6px 12px', width: 'fit-content' }}
            >
              {showAdvanced ? '▾' : '▸'} Advanced Settings
            </button>
          </div>

          {showAdvanced && (
            <>
            <div className={s.formGroup}>
              <label className={s.label} htmlFor="pipe-ff">Force Field <Tooltip text="Force field for energy minimization step — MMFF94 is recommended">ⓘ</Tooltip></label>
              <select id="pipe-ff" className={s.input} value={forceField} onChange={(e) => setForceField(e.target.value)}>
                <option value="MMFF94">MMFF94</option>
                <option value="UFF">UFF</option>
              </select>
            </div>
            <div className={s.formGroup}>
              <label className={s.label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input type="checkbox" checked={runFilters} onChange={(e) => setRunFilters(e.target.checked)} />
                Run PAINS Filters <Tooltip text="Pre-screen compounds for PAINS and reactive substructures before docking">ⓘ</Tooltip>
              </label>
            </div>
            <div className={s.formGroup}>
              <label className={s.label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input type="checkbox" checked={runAdmet} onChange={(e) => setRunAdmet(e.target.checked)} />
                Run ADMET Profiling <Tooltip text="Calculate drug-likeness and ADMET properties for each compound">ⓘ</Tooltip>
              </label>
            </div>
            </>
          )}
        </div>
        <div className={s.actions} style={{ marginTop: 16 }}>
          <button className={s.btnPrimary} onClick={handleBatch} disabled={loading || sse.streaming || !smilesFile || !receptor || !config}>
            {loading ? <><span className={s.spinnerSmall} /> Running Batch…</> : '📦 Launch Batch Pipeline'}
          </button>
          {loading && <button className={s.btnDanger} onClick={() => { abort(); setLoading(false); timer.stop() }}>✕ Cancel</button>}
          <ElapsedTimer time={timer.formatted} running={timer.running} />
        </div>
      </div>

      {batchResult && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Batch Result</span>
            <span className={s.badgeGreen}>Complete</span>
          </div>
          <p style={{ color: 'var(--text-secondary)', marginBottom: 8 }}>{batchResult.message}</p>
          <div className={s.statsGrid}>
            <div className={s.card}>
              <strong style={{ fontSize: '1.5rem', color: 'var(--accent)' }}>{batchResult.total_docked}</strong>
              <p className={s.label}>Total Docked <Tooltip text="Number of compounds that completed the full pipeline and were docked">ⓘ</Tooltip></p>
            </div>
            <div className={s.card}>
              <strong style={{ fontSize: '1.5rem', color: 'var(--green)' }}>{batchResult.best_score?.toFixed(2) ?? '—'}</strong>
              <p className={s.label}>Best Score <Tooltip text="Lowest (most favorable) Vina binding affinity across all docked compounds">ⓘ</Tooltip></p>
            </div>
          </div>
          {batchResult.steps.length > 0 && (
            <div className={s.tableScroll} style={{ marginTop: 12 }}>
              <table className={s.table}>
                <thead><tr><th>Step</th><th>Status</th><th>Count</th><th>Message</th></tr></thead>
                <tbody>
                  {batchResult.steps.map((st, i) => (
                    <tr key={i}>
                      <td>{st.step}</td>
                      <td><span className={st.status === 'done' ? s.badgeGreen : st.status === 'error' ? s.badgeRose : s.badgeAmber}>{st.status}</span></td>
                      <td>{st.count}</td>
                      <td style={{ color: 'var(--text-secondary)' }}>{st.message ?? ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {batchResult.results_dir && <PathDisplay label="Results" path={batchResult.results_dir} />}
        </div>
      )}
      </>
      )}

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}
    </PageShell>
  )
}
