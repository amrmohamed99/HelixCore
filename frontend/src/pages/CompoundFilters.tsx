/* ================================================================
   Compound Filters — PAINS + structural alert scanning
   ================================================================ */

import { useState } from 'react'
import * as api from '@/lib/api'
import type { FilterResponse, FilteredCompound } from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { useSortableTable } from '@/hooks/useSortableTable'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { PageShell, FilePicker, Alert, PathDisplay, Tooltip, MolViewer, EmptyState, Pagination, TableSkeleton, CopyButton } from '@/components/shared'
import { downloadCSV } from '@/lib/export'
import s from '@/styles/shared.module.css'

type SortKey = 'name' | 'smiles' | 'passed'
const PAGE_SIZE = 20

export default function CompoundFilters() {
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const [inputPath, setInputPath] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<FilterResponse | null>(null)
  const [error, setError] = useState('')
  const [page, setPage] = useState(1)
  const { sorted, sortKey, sortDir, requestSort, sortIndicator } = useSortableTable<FilteredCompound, SortKey>(
    result?.compounds ?? [], 'name',
  )

  const handleScan = async () => {
    if (!inputPath) return
    setLoading(true)
    setError('')
    setResult(null)
    addLog(`Scanning compounds: ${inputPath}…`)

    try {
      const res = await api.scanFilters({ input_path: inputPath })
      setResult(res)
      addLog(`✓ Scanned ${res.total} compounds — ${res.passed} passed, ${res.flagged} flagged`)
      addToast(`${res.passed} passed / ${res.flagged} flagged`, 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Scan failed'
      setError(msg)
      addLog(`✗ Filter error: ${msg}`)
      addToast(msg, 'error')
    } finally {
      setLoading(false)
    }
  }

  useKeyboardShortcuts([{ key: 'Enter', ctrl: true, action: handleScan, enabled: !loading && !!inputPath }])

  return (
    <PageShell emoji="🛡️" title="Compound Filters" subtitle="Screen compounds for PAINS patterns and structural alerts before docking" infoTooltip="Screen your compound library for PAINS (Pan-Assay Interference) patterns and structural alerts before docking. Remove molecules with problematic reactive groups that cause false positives." helpUrl="https://en.wikipedia.org/wiki/Pan-assay_interference_compounds">

      <div className={s.card}>
        <div className={s.cardHeader}><span className={s.cardTitle}>Input</span></div>
        <FilePicker
          label="SMILES File or Directory"
          value={inputPath}
          onChange={setInputPath}
          filters={[{ name: 'SMILES / SDF', extensions: ['smi', 'txt', 'sdf'] }]}
          placeholder="Select SMILES file or compound directory…"
        />
        <div className={s.actions} style={{ marginTop: 16 }}>
          <button className={s.btnPrimary} onClick={handleScan} disabled={loading || !inputPath}>
            {loading ? <><span className={s.spinnerSmall} /> Scanning…</> : '🛡️ Scan Compounds'}
          </button>
          <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
        </div>
      </div>

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {loading && !result && <TableSkeleton rows={5} cols={5} />}

      {result && (
        <>
          <div className={s.card}>
            <div className={s.cardHeader}>
              <span className={s.cardTitle}>Summary</span>
              <span className={s.badgeGreen}>{result.total} scanned</span>
            </div>
            <div className={s.statsGrid}>
              <div className={s.card}>
                <strong style={{ color: 'var(--green)', fontSize: '1.5rem' }}>{result.passed}</strong>
                <p className={s.label}>Passed <Tooltip text="Compounds free of all PAINS and structural alerts">ⓘ</Tooltip></p>
              </div>
              <div className={s.card}>
                <strong style={{ color: result.flagged > 0 ? 'var(--rose)' : 'var(--text-muted)', fontSize: '1.5rem' }}>{result.flagged}</strong>
                <p className={s.label}>Flagged <Tooltip text="Compounds containing at least one problematic substructure pattern">ⓘ</Tooltip></p>
              </div>
            </div>
            {result.report_path && <PathDisplay label="Report CSV" path={result.report_path} />}
          </div>

          <div className={s.card}>
            <div className={s.cardHeader}>
              <span className={s.cardTitle}>Compound Details</span>
              <button className={s.btnSecondary} style={{ fontSize: '0.75rem', padding: '4px 10px' }} onClick={() => downloadCSV(
                ['Name', 'SMILES', 'Passed', 'PAINS_Free', 'PAINS_Matches', 'Alert_Free', 'Alerts'],
                result.compounds.map(c => [c.name, c.smiles, c.passed ? 'PASS' : 'FAIL', c.pains_free ? 'Yes' : 'No', c.pains_matches.join('; '), c.alert_free ? 'Yes' : 'No', c.alerts.join('; ')]),
                'compound_filters.csv'
              )}>📥 Export CSV</button>
            </div>
            {sorted.length === 0 ? (
              <EmptyState icon="🛡️" title="No Compounds" description="Point to a directory with docking results or SDF files to screen for PAINS and structural alerts." />
            ) : (
            <>
            <div className={s.tableScroll}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th className={s.sortableHeader} onClick={() => requestSort('name')} aria-sort={sortKey === 'name' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Name<span className={s.sortIndicator}>{sortIndicator('name')}</span></th>
                    <th>SMILES</th>
                    <th style={{ width: 120 }}>Structure</th>
                    <th>PAINS</th>
                    <th>Alerts</th>
                    <th className={s.sortableHeader} onClick={() => requestSort('passed')} aria-sort={sortKey === 'passed' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Status<span className={s.sortIndicator}>{sortIndicator('passed')}</span></th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((c, i) => (
                    <tr key={i}>
                      <td className={s.mono}>{c.name}</td>
                      <td className={s.mono} style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.smiles} <CopyButton text={c.smiles} /></td>
                      <td>{c.smiles && <MolViewer smiles={c.smiles} width={110} height={90} />}</td>
                      <td>{c.pains_free ? '✅' : <span style={{ color: 'var(--rose)' }}>{c.pains_matches.join(', ')}</span>}</td>
                      <td>{c.alert_free ? '✅' : <span style={{ color: 'var(--rose)' }}>{c.alerts.join(', ')}</span>}</td>
                      <td>
                        <span className={c.passed ? s.badgeGreen : s.badgeRose}>
                          {c.passed ? 'PASS' : 'FAIL'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={page} total={result.compounds.length} pageSize={PAGE_SIZE} onPageChange={setPage} />
            </>
            )}
          </div>
        </>
      )}
    </PageShell>
  )
}
