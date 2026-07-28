/* ================================================================
   Similarity Search — Find similar compounds across databases
   ================================================================ */

import { useState } from 'react'
import * as api from '@/lib/api'
import type { SimilarityResponse, SimilarityHit } from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { useSortableTable } from '@/hooks/useSortableTable'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useSessionField } from '@/hooks/useSessionField'
import { PageShell, FilePicker, Alert, PathDisplay, MolViewer, Tooltip, Pagination, EmptyState, TableSkeleton, CopyButton, MoleculeEditor } from '@/components/shared'
import { downloadCSV } from '@/lib/export'
import s from '@/styles/shared.module.css'

type SimSortKey = 'name' | 'score'
const PAGE_SIZE = 20

export default function Similarity() {
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const [query, setQuery] = useSessionField('similarity.query', '')
  const [method, setMethod] = useSessionField('similarity.method', 'Morgan')
  const [database, setDatabase] = useSessionField('similarity.database', 'PubChem')
  const [localDbPath, setLocalDbPath] = useSessionField('similarity.localDbPath', '')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<SimilarityResponse | null>(null)
  const [error, setError] = useState('')
  const [showEditor, setShowEditor] = useState(false)
  const [page, setPage] = useState(1)
  const { sorted, sortKey, sortDir, requestSort, sortIndicator } = useSortableTable<SimilarityHit, SimSortKey>(
    result?.hits ?? [], 'score', 'desc',
  )

  const handleSearch = async () => {
    if (!query) return
    setLoading(true)
    setError('')
    setResult(null)
    addLog(`Similarity search: ${query} (${method}, ${database})…`)

    try {
      const res = await api.searchSimilarity({
        query,
        method,
        database,
        local_db_path: database === 'Local' ? localDbPath : undefined,
      })
      setResult(res)
      addLog(`✓ Found ${res.hits.length} similar compounds`)
      addToast(`Found ${res.hits.length} similar compounds`, 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Search failed'
      setError(msg)
      addLog(`✗ Similarity error: ${msg}`)
      addToast(msg, 'error')
    } finally {
      setLoading(false)
    }
  }

  useKeyboardShortcuts([{ key: 'Enter', ctrl: true, action: handleSearch, enabled: !loading && !!query }])

  return (
    <>
    <PageShell emoji="🔍" title="Similarity Search" subtitle="Find structurally similar compounds using molecular fingerprints" infoTooltip="Search for structurally similar compounds using molecular fingerprints. Compare your query molecule against PubChem, ChEMBL, or a local database to find analogs." helpUrl="https://www.rdkit.org/docs/GettingStartedInPython.html#fingerprinting-and-molecular-similarity">
      <div className={s.card}>
        <div className={s.cardHeader}><span className={s.cardTitle}>Search Configuration</span></div>
        <div className={s.formGrid}>
          <div className={s.formGroupFull}>
            <label className={s.label} htmlFor="sim-query">Query Molecule <Tooltip text="Enter a compound name, SMILES, InChI, CAS number, or browse for a ligand file">ⓘ</Tooltip></label>
            <div className={s.inputWithBtn}>
              <input
                id="sim-query"
                className={s.inputMono}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="SMILES, InChI, compound name, CAS number, or file path"
              />
              <button
                className={s.btnSecondary}
                type="button"
                onClick={() => setShowEditor(true)}
                title="Open molecule editor"
              >
                ✏️ Draw
              </button>
              <button
                className={s.btnSecondary}
                type="button"
                onClick={async () => {
                  const file = await window.electronAPI?.selectFile([
                    { name: 'Ligand Files', extensions: ['pdb', 'mol2', 'sdf', 'mol', 'smi'] },
                  ])
                  if (file) setQuery(file)
                }}
              >
                Browse
              </button>
            </div>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: 4 }}>Supports: SMILES · InChI · compound name · CAS number · file path</span>
          </div>
          <div className={s.formGroup}>
            <label className={s.label} htmlFor="sim-method">Fingerprint Method <Tooltip text="Algorithm for molecular comparison — Morgan (ECFP) is most common for drug discovery, MACCS for substructure matching">ⓘ</Tooltip></label>
            <select id="sim-method" className={s.select} value={method} onChange={(e) => setMethod(e.target.value)}>
              <option value="Morgan">Morgan (ECFP)</option>
              <option value="MACCS">MACCS Keys</option>
              <option value="RDKit">RDKit</option>
            </select>
          </div>
          <div className={s.formGroup}>
            <label className={s.label} htmlFor="sim-db">Database Source <Tooltip text="Compound database to search against — PubChem for public compounds, ChEMBL for bioactive molecules">ⓘ</Tooltip></label>
            <select id="sim-db" className={s.select} value={database} onChange={(e) => setDatabase(e.target.value)}>
              <option value="PubChem">PubChem</option>
              <option value="ChEMBL">ChEMBL</option>
              <option value="Local">Local File</option>
            </select>
          </div>
          {database === 'Local' && (
            <FilePicker
              label="Local Database File"
              value={localDbPath}
              onChange={setLocalDbPath}
              filters={[{ name: 'Database Files', extensions: ['sdf', 'smi', 'csv'] }]}
              placeholder="Select local DB…"
            />
          )}
        </div>
        <div className={s.actions} style={{ marginTop: 16 }}>
          <button className={s.btnPrimary} onClick={handleSearch} disabled={loading || !query}>
            {loading ? <><span className={s.spinnerSmall} /> Searching…</> : '🔍 Search Similar'}
          </button>
          <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
        </div>
      </div>

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {loading && !result && <TableSkeleton rows={5} cols={4} />}

      {result && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Results</span>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span className={s.badgeAccent}>{result.hits.length} hits</span>
              <button className={s.btnSecondary} style={{ fontSize: '0.75rem', padding: '4px 10px' }} onClick={() => downloadCSV(
                ['Name', 'Score', 'SMILES'],
                result.hits.map(h => [h.name, h.score, h.smiles ?? '']),
                'similarity_hits.csv'
              )}>📥 Export CSV</button>
            </div>
          </div>
          {result.hits.length === 0 ? (
            <EmptyState icon="🔍" title="No Matches" description="No similar compounds found. Try a different query or fingerprint method." />
          ) : (
            <>
            <div className={s.tableScroll}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th className={s.sortableHeader} onClick={() => requestSort('name')} aria-sort={sortKey === 'name' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Name<span className={s.sortIndicator}>{sortIndicator('name')}</span></th>
                    <th className={s.sortableHeader} onClick={() => requestSort('score')} aria-sort={sortKey === 'score' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Similarity<span className={s.sortIndicator}>{sortIndicator('score')}</span></th>
                    <th>SMILES</th>
                    <th style={{ width: 120 }}>Structure</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((hit, i) => (
                    <tr key={i}>
                      <td>{hit.name}</td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <div className={s.progressBar} style={{ width: 80 }}>
                            <div
                              className={s.progressFill}
                              style={{
                                width: `${parseFloat(hit.score) * 100}%`,
                                background: parseFloat(hit.score) >= (method.includes('MACCS') ? 0.85 : method.includes('Morgan') ? 0.5 : 0.7) ? 'var(--green)' : 'var(--amber)',
                              }}
                            />
                          </div>
                          <span className={s.mono}>{hit.score}</span>
                        </div>
                      </td>
                      <td className={s.mono} style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {hit.smiles ?? '—'} {hit.smiles && <CopyButton text={hit.smiles} />}
                      </td>
                      <td>{hit.smiles && <MolViewer smiles={hit.smiles} width={110} height={90} />}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={page} total={result.hits.length} pageSize={PAGE_SIZE} onPageChange={setPage} />
            </>
          )}
          {result.report_path && (
            <PathDisplay label="Report" path={result.report_path ?? ''} />
          )}
        </div>
      )}
    </PageShell>
    {showEditor && (
      <MoleculeEditor
        value={query}
        onConfirm={(smi) => { setQuery(smi); setShowEditor(false) }}
        onClose={() => setShowEditor(false)}
      />
    )}
    </>
  )
}
