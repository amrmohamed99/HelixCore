/* ================================================================
   Analog Generator — BRICS / bioisostere / random-walk analogs
   ================================================================ */

import { useState } from 'react'
import * as api from '@/lib/api'
import type { AnalogResponse, AnalogCompound } from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { useSortableTable } from '@/hooks/useSortableTable'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useSessionField } from '@/hooks/useSessionField'
import { PageShell, Alert, Tooltip, MolViewer, EmptyState, Pagination, TableSkeleton, CopyButton, MoleculeEditor } from '@/components/shared'
import { downloadCSV } from '@/lib/export'
import s from '@/styles/shared.module.css'

type SortKey = 'name' | 'smiles' | 'mw' | 'similarity'
const PAGE_SIZE = 20

const METHODS = [
  { value: 'fragment', label: 'BRICS Fragments' },
  { value: 'bioisostere', label: 'Bioisostere' },
  { value: 'walk', label: 'Random Walk' },
  { value: 'all', label: 'All Methods' },
] as const

export default function AnalogGenerator() {
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const [smiles, setSmiles] = useSessionField('analog.smiles', '')
  const [method, setMethod] = useSessionField('analog.method', 'fragment')
  const [maxAnalogs, setMaxAnalogs] = useSessionField('analog.maxAnalogs', 20)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AnalogResponse | null>(null)
  const [error, setError] = useState('')
  const [showEditor, setShowEditor] = useState(false)
  const [page, setPage] = useState(1)
  const { sorted, sortKey, sortDir, requestSort, sortIndicator } = useSortableTable<AnalogCompound, SortKey>(
    result?.analogs ?? [], 'similarity', 'desc',
  )

  const handleGenerate = async () => {
    if (!smiles.trim()) return
    setLoading(true)
    setError('')
    setResult(null)
    addLog(`Generating analogs (${method}, max ${maxAnalogs})…`)

    try {
      const res = await api.generateAnalogs({ smiles: smiles.trim(), method, max_analogs: maxAnalogs })
      setResult(res)
      addLog(`✓ ${res.count} analogs generated`)
      addToast(`${res.count} analogs generated`, 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Analog generation failed'
      setError(msg)
      addLog(`✗ ${msg}`)
      addToast(msg, 'error')
    } finally {
      setLoading(false)
    }
  }

  useKeyboardShortcuts([{ key: 'Enter', ctrl: true, action: handleGenerate, enabled: !loading && !!smiles.trim() }])

  return (
    <>
    <PageShell emoji="🧬" title="Analog Generator" subtitle="Produce structural analogs via BRICS fragmentation, bioisosteric replacement, or random walk" infoTooltip="Generate structural analogs of a lead compound using BRICS fragmentation, bioisosteric replacement, or random molecular walk to explore chemical space around a hit." helpUrl="https://www.rdkit.org/docs/source/rdkit.Chem.BRICS.html">

      <div className={s.card}>
        <div className={s.cardHeader}><span className={s.cardTitle}>Input</span></div>
        <div className={s.formGrid}>
          <div className={s.formGroupFull}>
            <label className={s.label} htmlFor="analog-parent">Parent Molecule <Tooltip text="Enter a SMILES string, InChI, compound name (e.g. aspirin), or CAS number (e.g. 50-78-2)">ⓘ</Tooltip></label>
            <input id="analog-parent" className={`${s.input} ${s.inputMono}`} placeholder="SMILES, InChI, compound name, or CAS number" value={smiles} onChange={(e) => setSmiles(e.target.value)} />
            <button className={s.btnSecondary} style={{ marginTop: 4, fontSize: '0.75rem' }} onClick={() => setShowEditor(true)}>✏️ Draw Molecule</button>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: 4 }}>Supports: SMILES · InChI · compound name · CAS number · MOL block</span>
          </div>
          <div className={s.formGroup}>
            <label className={s.label} htmlFor="analog-method">Method <Tooltip text="Analog generation strategy — BRICS for fragment-based, bioisostere for functional group swaps, walk for random perturbations">ⓘ</Tooltip></label>
            <select id="analog-method" className={s.input} value={method} onChange={(e) => setMethod(e.target.value)}>
              {METHODS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
          </div>
          <div className={s.formGroup}>
            <label className={s.label} htmlFor="analog-max">Max Analogs <Tooltip text="Maximum number of analogs to generate — actual count may be lower depending on the method">ⓘ</Tooltip></label>
            <input id="analog-max" className={s.input} type="number" min={1} max={200} value={maxAnalogs} onChange={(e) => setMaxAnalogs(Number(e.target.value))} />
          </div>
        </div>
        <div className={s.actions} style={{ marginTop: 16 }}>
          <button className={s.btnPrimary} onClick={handleGenerate} disabled={loading || !smiles.trim()}>
            {loading ? <><span className={s.spinnerSmall} /> Generating…</> : '🧬 Generate Analogs'}
          </button>
          <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
        </div>
      </div>

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {loading && !result && <TableSkeleton rows={5} cols={5} />}

      {result && result.analogs.length === 0 && (
        <EmptyState icon="🧬" title="No Analogs Found" description="Enter a SMILES string above and click Generate. You can copy a SMILES from the Docking or Results page." />
      )}

      {result && result.analogs.length > 0 && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Analogs</span>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span className={s.badgeGreen}>{result.count} found</span>
              <button className={s.btnSecondary} style={{ fontSize: '0.75rem', padding: '4px 10px' }} onClick={() => downloadCSV(
                ['Name', 'SMILES', 'MW', 'Similarity'],
                result.analogs.map(a => [a.name ?? '', a.smiles, a.mw ?? '', a.similarity != null ? (a.similarity * 100).toFixed(1) + '%' : '']),
                'analogs.csv'
              )}>📥 Export CSV</button>
            </div>
          </div>
          <div className={s.tableScroll}>
            <table className={s.table}>
              <thead>
                <tr>
                  <th>#</th>
                  <th className={s.sortableHeader} onClick={() => requestSort('name')} aria-sort={sortKey === 'name' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Name<span className={s.sortIndicator}>{sortIndicator('name')}</span></th>
                  <th>SMILES</th>
                  <th style={{ width: 120 }}>Structure</th>
                  <th className={s.sortableHeader} onClick={() => requestSort('mw')} aria-sort={sortKey === 'mw' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>MW<span className={s.sortIndicator}>{sortIndicator('mw')}</span></th>
                  <th className={s.sortableHeader} onClick={() => requestSort('similarity')} aria-sort={sortKey === 'similarity' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Similarity<span className={s.sortIndicator}>{sortIndicator('similarity')}</span></th>
                </tr>
              </thead>
              <tbody>
                {sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((a, i) => (
                  <tr key={i}>
                    <td>{(page - 1) * PAGE_SIZE + i + 1}</td>
                    <td>{a.name || '—'}</td>
                    <td className={s.mono} style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>{a.smiles} <CopyButton text={a.smiles} /></td>
                    <td>{a.smiles && <MolViewer smiles={a.smiles} width={110} height={90} />}</td>
                    <td>{a.mw?.toFixed(1) ?? '—'}</td>
                    <td style={{ color: (a.similarity ?? 0) >= 0.7 ? 'var(--green)' : 'var(--text-secondary)' }}>
                      {a.similarity != null ? `${(a.similarity * 100).toFixed(0)}%` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} total={result.analogs.length} pageSize={PAGE_SIZE} onPageChange={setPage} />
        </div>
      )}
    </PageShell>
    {showEditor && (
      <MoleculeEditor
        value={smiles}
        onConfirm={(smi) => { setSmiles(smi); setShowEditor(false) }}
        onClose={() => setShowEditor(false)}
      />
    )}
    </>
  )
}
