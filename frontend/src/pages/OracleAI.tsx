/* ================================================================
   Oracle AI — ML-based affinity prediction & rescoring
   ================================================================ */

import { useState, useEffect, useMemo } from 'react'
import * as api from '@/lib/api'
import type { OracleResponse, OraclePrediction } from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { usePipelineStep } from '@/hooks/usePipelineStep'
import { useWorkspace } from '@/hooks/useWorkspace'
import { useSortableTable } from '@/hooks/useSortableTable'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useAbortController } from '@/hooks/useAbortController'
import { PageShell, FilePicker, Alert, PathDisplay, Tooltip, Pagination, EmptyState, TableSkeleton } from '@/components/shared'
import HistogramChart from '@/components/shared/HistogramChart'
import { downloadCSV } from '@/lib/export'
import s from '@/styles/shared.module.css'

type OSortKey = 'ligand' | 'vina_score' | 'predicted_pKd' | 'confidence' | 'method'
const PAGE_SIZE = 20

export default function OracleAI() {
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const { markRunning, markDone, markError } = usePipelineStep('oracle')
  const { paths, ready } = useWorkspace()
  const [dockDir, setDockDir] = useState('')
  const [modelPath, setModelPath] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<OracleResponse | null>(null)
  const [error, setError] = useState('')
  const { getSignal, abort, isAborted } = useAbortController()
  const [page, setPage] = useState(1)
  const { sorted, sortKey, sortDir, requestSort, sortIndicator } = useSortableTable<OraclePrediction, OSortKey>(
    result?.predictions ?? [], 'predicted_pKd', 'desc',
  )

  const pKdValues = useMemo(
    () => result?.predictions.map(p => p.predicted_pKd) ?? [],
    [result],
  )

  useEffect(() => {
    if (ready && !dockDir) setDockDir(paths.dockingResults)
  }, [ready])

  const handlePredict = async () => {
    if (!dockDir) return
    markRunning()
    setLoading(true)
    setError('')
    setResult(null)
    addLog(`Oracle AI predicting affinity for ${dockDir}…`)

    try {
      const signal = getSignal()
      const res = await api.predictOracle({
        dock_dir: dockDir,
        model_path: modelPath || undefined,
      }, signal)
      setResult(res)
      addLog(`✓ Oracle predicted ${res.predictions.length} compounds`)
      addToast(`Oracle predicted ${res.predictions.length} compounds`, 'success')
      markDone()
    } catch (err: unknown) {
      if (isAborted()) { addLog('⚠ Oracle cancelled'); addToast('Oracle cancelled', 'info'); markError(); return }
      const msg = err instanceof Error ? err.message : 'Prediction failed'
      setError(msg)
      addLog(`✗ Oracle error: ${msg}`)
      addToast(msg, 'error')
      markError()
    } finally {
      setLoading(false)
    }
  }

  useKeyboardShortcuts([{ key: 'Enter', ctrl: true, action: handlePredict, enabled: !loading && !!dockDir }])

  return (
    <PageShell
      emoji="🤖"
      title="Oracle AI"
      subtitle="Thermodynamic binding affinity estimation with optional ML rescoring"
      infoTooltip="Converts Vina docking scores to predicted pKd values using thermodynamic relationships (ΔG = -RT·ln(Kd)). When a trained ML model is available, it re-ranks compounds using molecular descriptors for more accurate predictions."
      helpUrl="https://en.wikipedia.org/wiki/Quantitative_structure%E2%80%93activity_relationship"
      nextStep={{ label: 'Results', path: '/results' }}
    >
      <div className={s.card}>
        <div className={s.cardHeader}><span className={s.cardTitle}>Configuration</span></div>
        <div className={s.formGrid}>
          <FilePicker
            label="Docking Results Directory"
            value={dockDir}
            onChange={setDockDir}
            directory
            placeholder="Select docking output folder…"
          />
          <FilePicker
            label="Custom Model (optional)"
            value={modelPath}
            onChange={setModelPath}
            filters={[{ name: 'Model Files', extensions: ['pkl', 'joblib'] }]}
            placeholder="Default model used if empty"
          />
        </div>
        <div className={s.actions} style={{ marginTop: 16 }}>
          <button className={s.btnPrimary} onClick={handlePredict} disabled={loading || !dockDir}>
            {loading ? <><span className={s.spinnerSmall} /> Predicting…</> : '🤖 Run Oracle AI'}
          </button>
          {loading && <button className={s.btnDanger} onClick={() => { abort(); setLoading(false) }}>✕ Cancel</button>}
          <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
        </div>
      </div>

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {loading && !result && <TableSkeleton rows={5} cols={4} />}

      {result && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Predictions</span>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span className={s.badgeViolet}>{result.predictions.length} compounds</span>
              <button className={s.btnSecondary} style={{ fontSize: '0.75rem', padding: '4px 10px' }} onClick={() => downloadCSV(
                ['Ligand', 'Vina_Score', 'Predicted_pKd', 'Confidence', 'Method'],
                result.predictions.map(p => [p.ligand, p.vina_score, p.predicted_pKd, p.confidence, p.method]),
                'oracle_predictions.csv'
              )}>📥 Export CSV</button>
            </div>
          </div>
          {result.predictions.length === 0 ? (
            <EmptyState icon="🤖" title="No Predictions" description="No compounds found in the docking directory. Run the Docking step first to generate scored poses." />
          ) : (
            <>
            {pKdValues.length > 0 && (
              <HistogramChart
                data={pKdValues}
                title="Predicted pKd Distribution"
                unit="pKd"
                barColor="var(--violet)"
              />
            )}
            <div className={s.tableScroll}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th className={s.sortableHeader} onClick={() => requestSort('ligand')} aria-sort={sortKey === 'ligand' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Ligand<span className={s.sortIndicator}>{sortIndicator('ligand')}</span></th>
                    <th className={s.sortableHeader} onClick={() => requestSort('vina_score')} aria-sort={sortKey === 'vina_score' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Vina Score (kcal/mol)<span className={s.sortIndicator}>{sortIndicator('vina_score')}</span></th>
                    <th className={s.sortableHeader} onClick={() => requestSort('predicted_pKd')} aria-sort={sortKey === 'predicted_pKd' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Predicted pKd<span className={s.sortIndicator}>{sortIndicator('predicted_pKd')}</span></th>
                    <th className={s.sortableHeader} onClick={() => requestSort('confidence')} aria-sort={sortKey === 'confidence' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Confidence<span className={s.sortIndicator}>{sortIndicator('confidence')}</span></th>
                    <th className={s.sortableHeader} onClick={() => requestSort('method')} aria-sort={sortKey === 'method' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Method<span className={s.sortIndicator}>{sortIndicator('method')}</span></th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((p, i) => (
                      <tr key={i}>
                        <td className={s.mono}>{p.ligand}</td>
                        <td>{p.vina_score.toFixed(2)}</td>
                        <td style={{ color: p.predicted_pKd > 6 ? 'var(--green)' : 'var(--text-secondary)' }}>
                          {p.predicted_pKd.toFixed(3)}
                        </td>
                        <td><span className={p.confidence === 'medium' ? s.badgeGreen : s.badgeAccent}>{p.confidence}</span></td>
                        <td><span className={s.badgeAccent}>{p.method}</span></td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            <Pagination page={page} total={result.predictions.length} pageSize={PAGE_SIZE} onPageChange={setPage} />
            </>
          )}
          {result.csv_path && <PathDisplay label="CSV Report" path={result.csv_path ?? ''} />}
        </div>
      )}
    </PageShell>
  )
}
