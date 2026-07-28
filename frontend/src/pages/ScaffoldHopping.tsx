/* ================================================================
   Scaffold Hopping — SAR tools: Murcko, MCS, R-group, MMP
   ================================================================ */

import { useState } from 'react'
import * as api from '@/lib/api'
import type { ScaffoldHopResponse, ScaffoldHopResult } from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { useSortableTable } from '@/hooks/useSortableTable'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useSessionField } from '@/hooks/useSessionField'
import { PageShell, Alert, Tooltip, MolViewer, FilePicker, EmptyState, Pagination, TableSkeleton, CopyButton } from '@/components/shared'
import s from '@/styles/shared.module.css'

type SortKey = 'smiles' | 'scaffold' | 'similarity' | 'name'
const PAGE_SIZE = 20

const METHODS = [
  { value: 'murcko', label: '🏗️ Murcko Scaffold', desc: 'Bemis-Murcko framework decomposition' },
  { value: 'mcs', label: '🧩 MCS Search', desc: 'Maximum common substructure comparison' },
  { value: 'rgroup', label: '🔬 R-Group', desc: 'R-group decomposition and enumeration' },
  { value: 'mmp', label: '🔀 MMP', desc: 'Matched molecular pair analysis via BRICS' },
] as const

export default function ScaffoldHopping() {
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const [smiles, setSmiles] = useSessionField('scaffold.smiles', '')
  const [method, setMethod] = useSessionField('scaffold.method', 'murcko')
  const [libraryPath, setLibraryPath] = useSessionField('scaffold.libraryPath', '')
  const [maxResults, setMaxResults] = useSessionField('scaffold.maxResults', 50)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ScaffoldHopResponse | null>(null)
  const [error, setError] = useState('')
  const [page, setPage] = useState(1)
  const { sorted, sortKey, sortDir, requestSort, sortIndicator } = useSortableTable<ScaffoldHopResult, SortKey>(
    result?.results ?? [], 'similarity', 'desc',
  )

  const handleHop = async () => {
    if (!smiles.trim()) return
    setLoading(true); setError(''); setResult(null)
    addLog(`Scaffold hopping (${method})…`)
    try {
      const res = await api.scaffoldHop({
        smiles: smiles.trim(),
        method: method as 'murcko' | 'mcs' | 'rgroup' | 'mmp',
        library_path: libraryPath || undefined,
        max_results: maxResults,
      })
      setResult(res)
      setPage(1)
      addLog(`✓ ${res.count} results`)
      addToast(res.message, 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Scaffold hopping failed'
      setError(msg); addLog(`✗ ${msg}`); addToast(msg, 'error')
    } finally { setLoading(false) }
  }

  useKeyboardShortcuts([{ key: 'Enter', ctrl: true, action: handleHop, enabled: !loading && !!smiles.trim() }])

  return (
    <PageShell emoji="🔀" title="Scaffold Hopping" subtitle="Explore scaffold replacements and SAR analysis" infoTooltip="Scaffold hopping identifies compounds with similar biological activity but different core structures. Use Murcko decomposition, MCS comparison, R-group analysis, or matched molecular pair analysis to explore chemical space.">
      <div className={s.card}>
        <div className={s.cardHeader}><span className={s.cardTitle}>Configuration</span></div>
        <div className={s.formGrid}>
          <div className={s.formGroup} style={{ gridColumn: '1 / -1' }}>
            <label className={s.label} htmlFor="scaffold-ref">Reference SMILES <Tooltip text="SMILES of the reference compound whose scaffold you want to hop">ⓘ</Tooltip></label>
            <input id="scaffold-ref" className={s.inputMono} value={smiles} onChange={e => setSmiles(e.target.value)} placeholder="e.g. c1ccc(NC(=O)c2ccccc2)cc1" />
          </div>
          <div className={s.formGroup}>
            <label className={s.label} htmlFor="scaffold-method">Method</label>
            <select id="scaffold-method" className={s.select} value={method} onChange={e => setMethod(e.target.value)}>
              {METHODS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 4 }}>
              {METHODS.find(m => m.value === method)?.desc}
            </span>
          </div>
          <FilePicker
            label="Library File (optional)"
            value={libraryPath}
            onChange={setLibraryPath}
            filters={[{ name: 'SMILES/SDF', extensions: ['smi', 'sdf', 'csv'] }]}
            placeholder="Compound library for comparison…"
          />
          <div className={s.formGroup}>
            <label className={s.label} htmlFor="scaffold-max">Max Results</label>
            <input id="scaffold-max" className={s.input} type="number" min={1} max={500} value={maxResults} onChange={e => setMaxResults(Number(e.target.value))} />
          </div>
        </div>
        <div className={s.actions} style={{ marginTop: 16 }}>
          <button className={s.btnPrimary} onClick={handleHop} disabled={loading || !smiles.trim()}>
            {loading ? <><span className={s.spinnerSmall} /> Analyzing…</> : '🔀 Scaffold Hop'}
          </button>
          <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
        </div>
      </div>

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {loading && !result && <TableSkeleton rows={5} cols={4} />}

      {result && (
        <>
          {/* Summary */}
          <div className={s.card}>
            <div className={s.cardHeader}>
              <span className={s.cardTitle}>Results — {result.method.toUpperCase()}</span>
              <span className={s.badgeGreen}>{result.count} scaffolds</span>
            </div>
            <div className={s.statsGrid}>
              <div className={s.card}>
                <label className={s.label}>Reference</label>
                <MolViewer smiles={result.reference} width={120} height={90} />
                <span className={s.mono} style={{ fontSize: '0.7rem' }}>{result.reference}</span>
              </div>
              {result.reference_scaffold && (
                <div className={s.card}>
                  <label className={s.label}>Core Scaffold</label>
                  <MolViewer smiles={result.reference_scaffold} width={120} height={90} />
                  <span className={s.mono} style={{ fontSize: '0.7rem' }}>{result.reference_scaffold}</span>
                </div>
              )}
            </div>
          </div>

          {result.results.length === 0 ? (
            <EmptyState icon="🔀" title="No Results" description="Enter a reference SMILES and choose a hopping method to discover new scaffolds with similar bioactivity." />
          ) : (
            <div className={s.card}>
              <div className={s.cardHeader}>
                <span className={s.cardTitle}>Scaffold Variants</span>
              </div>
              <div className={s.tableScroll}>
                <table className={s.table}>
                  <thead>
                    <tr>
                      <th>Structure</th>
                      <th className={s.sortableHeader} onClick={() => requestSort('name')} aria-sort={sortKey === 'name' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Name<span className={s.sortIndicator}>{sortIndicator('name')}</span></th>
                      <th className={s.sortableHeader} onClick={() => requestSort('smiles')} aria-sort={sortKey === 'smiles' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>SMILES<span className={s.sortIndicator}>{sortIndicator('smiles')}</span></th>
                      <th className={s.sortableHeader} onClick={() => requestSort('similarity')} aria-sort={sortKey === 'similarity' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Similarity<span className={s.sortIndicator}>{sortIndicator('similarity')}</span></th>
                      <th>Scaffold</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((r, i) => (
                      <tr key={i}>
                        <td><MolViewer smiles={r.smiles} width={80} height={60} /></td>
                        <td>{r.name || '—'}</td>
                        <td className={s.mono} style={{ fontSize: '0.72rem', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {r.smiles} <CopyButton text={r.smiles} size="sm" />
                        </td>
                        <td>
                          <span className={r.similarity > 0.7 ? s.badgeGreen : r.similarity > 0.4 ? s.badgeAmber : s.badgeRose}>
                            {(r.similarity * 100).toFixed(1)}%
                          </span>
                        </td>
                        <td className={s.mono} style={{ fontSize: '0.72rem' }}>{r.scaffold || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination page={page} total={result.results.length} pageSize={PAGE_SIZE} onPageChange={setPage} />
            </div>
          )}
        </>
      )}
    </PageShell>
  )
}
