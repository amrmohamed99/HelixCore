/* ================================================================
   Docking — AutoDock Vina molecular docking
   ================================================================ */

import { useState, useEffect } from 'react'
import * as api from '@/lib/api'
import type { DockingResponse, GridBox, DockingResult } from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { usePipelineStep } from '@/hooks/usePipelineStep'
import { useWorkspace } from '@/hooks/useWorkspace'
import { useTimer } from '@/hooks/useTimer'
import { useNotification } from '@/hooks/useNotification'
import { useSortableTable } from '@/hooks/useSortableTable'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useAbortController } from '@/hooks/useAbortController'
import { PageShell, FilePicker, Alert, PathDisplay, ScoreChart, ConfigProfiles, Tooltip, Pagination, EmptyState, TableSkeleton } from '@/components/shared'
import ElapsedTimer from '@/components/shared/ElapsedTimer'
import s from '@/styles/shared.module.css'

type DockSortKey = 'ligand' | 'score' | 'status'
const PAGE_SIZE = 20

export default function Docking() {
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const { markRunning, markDone, markError } = usePipelineStep('docking')
  const { paths, ready } = useWorkspace()
  const timer = useTimer()
  const { notify } = useNotification()
  const { getSignal, abort, isAborted } = useAbortController()
  const [ligandsDir, setLigandsDir] = useState('')
  const [receptor, setReceptor] = useState('')
  const [configPath, setConfigPath] = useState('')
  const [exhaustiveness, setExhaustiveness] = useState(8)
  const [seed, setSeed] = useState(42)
  const [loading, setLoading] = useState(false)
  const [gridDraft, setGridDraft] = useState({
    center_x: '',
    center_y: '',
    center_z: '',
    size_x: '',
    size_y: '',
    size_z: '',
  })
  const [grid, setGrid] = useState<GridBox | null>(null)
  const [result, setResult] = useState<DockingResponse | null>(null)
  const [error, setError] = useState('')
  const [dockPage, setDockPage] = useState(1)
  const { sorted: sortedDock, sortKey: dockSortKey, sortDir: dockSortDir, requestSort: reqDockSort, sortIndicator: dockSortInd } = useSortableTable<DockingResult, DockSortKey>(
    result?.results ?? [], 'score',
  )

  useEffect(() => {
    if (ready && !ligandsDir) setLigandsDir(paths.convertedPdbqt)
  }, [ready])

  const setGridField = (field: keyof GridBox, value: string) => {
    setGridDraft((prev) => ({ ...prev, [field]: value }))
    setGrid(null)
  }

  const handleApplyGrid = () => {
    const parsed: GridBox = {
      center_x: Number(gridDraft.center_x),
      center_y: Number(gridDraft.center_y),
      center_z: Number(gridDraft.center_z),
      size_x: Number(gridDraft.size_x),
      size_y: Number(gridDraft.size_y),
      size_z: Number(gridDraft.size_z),
    }

    if (Object.values(parsed).some((v) => !Number.isFinite(v))) {
      const msg = 'Enter valid numbers for all grid center and dimension fields.'
      setError(msg)
      addToast(msg, 'error')
      return
    }

    if (parsed.size_x <= 0 || parsed.size_y <= 0 || parsed.size_z <= 0) {
      const msg = 'Grid dimensions must be greater than zero.'
      setError(msg)
      addToast(msg, 'error')
      return
    }

    if (parsed.size_x > 126 || parsed.size_y > 126 || parsed.size_z > 126) {
      const msg = 'Grid dimensions must be 126 Å or smaller for Vina.'
      setError(msg)
      addToast(msg, 'error')
      return
    }

    setError('')
    setGrid(parsed)
    addLog(`✓ Manual grid applied: center=(${parsed.center_x}, ${parsed.center_y}, ${parsed.center_z}), size=(${parsed.size_x}, ${parsed.size_y}, ${parsed.size_z})`)
    addToast('Manual grid applied', 'success')
  }

  const handleDock = async () => {
    if (!ligandsDir || !receptor) return
    markRunning()
    setLoading(true)
    setError('')
    setResult(null)
    timer.start()
    addLog(`Docking: ${ligandsDir} → ${receptor}…`)

    try {
      const signal = getSignal()
      const res = await api.runDocking({
        ligands_dir: ligandsDir,
        receptor,
        config_path: configPath || undefined,
        grid: grid || undefined,
        exhaustiveness,
        seed,
      }, signal)
      setResult(res)
      const ok = res.results.filter((r) => r.status === 'ok').length
      addLog(`✓ Docking complete: ${ok}/${res.results.length} succeeded`)
      // Log error details for failed ligands
      for (const r of res.results) {
        if (r.status === 'error' && r.error_detail) addLog(`  ✗ ${r.ligand}: ${r.error_detail}`)
      }
      addToast(`Docking complete: ${ok}/${res.results.length} succeeded`, 'success')
      notify({ title: 'Docking Complete', body: `${ok}/${res.results.length} ligands docked successfully` })
      markDone()
    } catch (err: unknown) {
      if (isAborted()) { addLog('⚠ Docking cancelled'); addToast('Docking cancelled', 'info'); markError(); return }
      const msg = err instanceof Error ? err.message : 'Docking failed'
      setError(msg)
      addLog(`✗ Docking error: ${msg}`)
      addToast(msg, 'error')
      markError()
    } finally {
      setLoading(false)
      timer.stop()
    }
  }

  useKeyboardShortcuts([{ key: 'Enter', ctrl: true, action: handleDock, enabled: !loading && !!ligandsDir && !!receptor }])

  return (
    <PageShell
      emoji="🧲"
      title="Molecular Docking"
      subtitle="Run AutoDock Vina docking against a receptor"
      infoTooltip="Run AutoDock Vina molecular docking to predict binding poses and affinities of ligands against a protein receptor. Configure grid box, exhaustiveness, and receptor file."
      helpUrl="https://autodock-vina.readthedocs.io/en/latest/docking_basic.html"
      nextStep={{ label: 'Oracle AI', path: '/oracle' }}
    >
      <div className={s.card}>
        <div className={s.cardHeader}>
          <span className={s.cardTitle}>Docking Configuration</span>
          <ConfigProfiles
            getCurrent={() => ({ ligandsDir, receptor, configPath, exhaustiveness, seed, gridDraft, grid })}
            applyCurrent={(d) => {
              if (d.ligandsDir != null) setLigandsDir(String(d.ligandsDir))
              if (d.receptor != null) setReceptor(String(d.receptor))
              if (d.configPath != null) setConfigPath(String(d.configPath))
              if (d.exhaustiveness != null) setExhaustiveness(Number(d.exhaustiveness))
              if (d.seed != null) setSeed(Number(d.seed))
              if (d.gridDraft && typeof d.gridDraft === 'object') {
                setGridDraft(d.gridDraft as typeof gridDraft)
              }
              if (d.grid && typeof d.grid === 'object') {
                setGrid(d.grid as GridBox)
              }
            }}
          />
        </div>
        <div className={s.formGrid}>
          <FilePicker
            label="Ligands Directory (PDBQT)"
            value={ligandsDir}
            onChange={setLigandsDir}
            directory
            placeholder="Select ligands folder…"
          />
          <FilePicker
            label="Receptor File"
            value={receptor}
            onChange={setReceptor}
            filters={[
              { name: 'PDBQT Files', extensions: ['pdbqt'] },
              { name: 'PDB Files', extensions: ['pdb'] },
            ]}
            placeholder="Select receptor…"
          />
          <FilePicker
            label="Config File (optional)"
            value={configPath}
            onChange={setConfigPath}
            filters={[{ name: 'Config Files', extensions: ['txt', 'conf'] }]}
            placeholder="Select config…"
          />
          <div className={s.formGroup}>
            <label className={s.label} htmlFor="dock-exhaust">Exhaustiveness <Tooltip text="Search thoroughness (1–128). Default 8 is suitable for screening; 32+ recommended for publication-quality results.">ⓘ</Tooltip></label>
            <input
              id="dock-exhaust"
              className={s.input}
              type="number"
              min={1}
              max={128}
              value={exhaustiveness}
              onChange={(e) => setExhaustiveness(Number(e.target.value))}
            />
          </div>
          <div className={s.formGroup}>
            <label className={s.label} htmlFor="dock-seed">Random Seed <Tooltip text="Controls Vina's stochastic search. Keep this fixed for reproducible runs; use declared additional seeds for replicate experiments.">ⓘ</Tooltip></label>
            <input
              id="dock-seed"
              className={s.input}
              type="number"
              min={1}
              max={2147483647}
              step={1}
              value={seed}
              onChange={(e) => setSeed(Number(e.target.value))}
            />
          </div>
        </div>
        <div style={{ marginTop: 18, paddingTop: 18, borderTop: '1px solid var(--border)' }}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Manual Grid Box</span>
            <span className={grid ? s.badgeGreen : s.badgeAccent}>{grid ? 'Applied' : 'Manual'}</span>
          </div>
          <div className={s.formGrid}>
            <div className={s.formGroup}>
              <label className={s.label}>Position: X Center</label>
              <input className={s.inputMono} type="number" step="0.001" value={gridDraft.center_x} onChange={e => setGridField('center_x', e.target.value)} placeholder="0.000" />
            </div>
            <div className={s.formGroup}>
              <label className={s.label}>Position: Y Center</label>
              <input className={s.inputMono} type="number" step="0.001" value={gridDraft.center_y} onChange={e => setGridField('center_y', e.target.value)} placeholder="0.000" />
            </div>
            <div className={s.formGroup}>
              <label className={s.label}>Position: Z Center</label>
              <input className={s.inputMono} type="number" step="0.001" value={gridDraft.center_z} onChange={e => setGridField('center_z', e.target.value)} placeholder="0.000" />
            </div>
            <div className={s.formGroup}>
              <label className={s.label}>Scale: X Dimension</label>
              <input className={s.inputMono} type="number" min="1" max="126" step="0.001" value={gridDraft.size_x} onChange={e => setGridField('size_x', e.target.value)} placeholder="20.000" />
            </div>
            <div className={s.formGroup}>
              <label className={s.label}>Scale: Y Dimension</label>
              <input className={s.inputMono} type="number" min="1" max="126" step="0.001" value={gridDraft.size_y} onChange={e => setGridField('size_y', e.target.value)} placeholder="20.000" />
            </div>
            <div className={s.formGroup}>
              <label className={s.label}>Scale: Z Dimension</label>
              <input className={s.inputMono} type="number" min="1" max="126" step="0.001" value={gridDraft.size_z} onChange={e => setGridField('size_z', e.target.value)} placeholder="20.000" />
            </div>
          </div>
          <div className={s.actions} style={{ marginTop: 14 }}>
            <button className={s.btnPrimary} onClick={handleApplyGrid} title="Apply manual grid values">
              ✓ Apply Grid
            </button>
            {grid && (
              <span className={s.mono}>
                Center ({grid.center_x.toFixed(3)}, {grid.center_y.toFixed(3)}, {grid.center_z.toFixed(3)}) ·
                Size ({grid.size_x.toFixed(3)}, {grid.size_y.toFixed(3)}, {grid.size_z.toFixed(3)})
              </span>
            )}
          </div>
        </div>
        <div className={s.actions} style={{ marginTop: 16 }}>
          <button className={s.btnPrimary} onClick={handleDock} disabled={loading || !ligandsDir || !receptor || (!configPath && !grid)}>
            {loading ? <><span className={s.spinnerSmall} /> Docking…</> : '🧲 Run Docking'}
          </button>
          {loading && <button className={s.btnDanger} onClick={() => { abort(); setLoading(false); timer.stop() }}>✕ Cancel</button>}
          <ElapsedTimer time={timer.formatted} running={timer.running} />
          <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
        </div>
      </div>

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {loading && !result && <TableSkeleton rows={5} cols={3} />}

      {result && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Docking Results</span>
            <span className={s.badgeGreen}>{result.results.filter(r => r.status === 'ok').length} docked</span>
          </div>
          {result.results.length === 0 ? (
            <EmptyState icon="🧲" title="No Docking Results" description="Set your ligands directory (from Format Convert) and receptor file (from PDB Fetch), then click Run Docking." />
          ) : (
          <>
          <div className={s.tableScroll}>
            <table className={s.table}>
              <thead>
                <tr>
                  <th className={s.sortableHeader} onClick={() => reqDockSort('ligand')} aria-sort={dockSortKey === 'ligand' ? (dockSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Ligand<span className={s.sortIndicator}>{dockSortInd('ligand')}</span></th>
                  <th className={s.sortableHeader} onClick={() => reqDockSort('score')} aria-sort={dockSortKey === 'score' ? (dockSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Score (kcal/mol)<span className={s.sortIndicator}>{dockSortInd('score')}</span></th>
                  <th className={s.sortableHeader} onClick={() => reqDockSort('status')} aria-sort={dockSortKey === 'status' ? (dockSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Status<span className={s.sortIndicator}>{dockSortInd('status')}</span></th>
                </tr>
              </thead>
              <tbody>
                {sortedDock.slice((dockPage - 1) * PAGE_SIZE, dockPage * PAGE_SIZE).map((r, i) => (
                  <tr key={i}>
                    <td className={s.mono}>{r.ligand}</td>
                    <td style={{ color: r.score != null && r.score < -6 ? 'var(--green)' : 'var(--text-secondary)' }}>
                      {r.score?.toFixed(2) ?? '—'}
                    </td>
                    <td>
                      <span className={r.status === 'ok' ? s.badgeGreen : s.badgeRose}>{r.status}</span>
                      {r.status === 'error' && r.error_detail && (
                        <span className={s.errorDetail} title={r.error_detail}>
                          {r.error_detail}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={dockPage} total={result.results.length} pageSize={PAGE_SIZE} onPageChange={setDockPage} />
          <ScoreChart
            data={result.results
              .filter((r) => r.status === 'ok' && r.score != null)
              .sort((a, b) => (a.score ?? 0) - (b.score ?? 0))
              .map((r) => ({ label: r.ligand, value: r.score! }))}
            title="Docking Score Distribution"
            unit="kcal/mol"
            highlightBelow={-6}
            lowerIsBetter
          />
          <PathDisplay label="Results Directory" path={result.results_dir ?? ''} />
          </>
          )}
        </div>
      )}
    </PageShell>
  )
}
