/* ================================================================
   Cluster Analysis — Chemical clustering of docking results
   ================================================================ */

import { useState } from 'react'
import * as api from '@/lib/api'
import type { ClusterResponse } from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { useSortableTable } from '@/hooks/useSortableTable'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useSessionField } from '@/hooks/useSessionField'
import type { ClusterMember } from '@/types/api'
import { PageShell, FilePicker, Alert, Tooltip, EmptyState, CopyButton } from '@/components/shared'
import { downloadCSV } from '@/lib/export'
import s from '@/styles/shared.module.css'

type CSortKey = 'name' | 'score'

export default function ClusterAnalysis() {
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const [resultsDir, setResultsDir] = useSessionField('cluster.resultsDir', '')
  const [srcDir, setSrcDir] = useSessionField('cluster.srcDir', '')
  const [cutoff, setCutoff] = useSessionField('cluster.cutoff', 0.4)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ClusterResponse | null>(null)
  const [error, setError] = useState('')
  const [expandedCluster, setExpandedCluster] = useState<number | null>(null)

  const expandedMembers = result?.clusters.find(c => c.cluster_id === expandedCluster)?.members ?? []
  const { sorted: sortedMembers, sortKey, sortDir, requestSort, sortIndicator } = useSortableTable<ClusterMember, CSortKey>(
    expandedMembers, 'score', 'asc',
  )

  const handleCluster = async () => {
    if (!resultsDir) return
    setLoading(true)
    setError('')
    setResult(null)
    addLog(`Clustering compounds (cutoff=${cutoff})…`)

    try {
      const res = await api.clusterCompounds({ results_dir: resultsDir, src_dir: srcDir || undefined, cutoff })
      setResult(res)
      addLog(`✓ ${res.num_clusters} clusters from ${res.total_compounds} compounds`)
      addToast(`${res.num_clusters} clusters found`, 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Clustering failed'
      setError(msg)
      addLog(`✗ Cluster error: ${msg}`)
      addToast(msg, 'error')
    } finally {
      setLoading(false)
    }
  }

  useKeyboardShortcuts([{ key: 'Enter', ctrl: true, action: handleCluster, enabled: !loading && !!resultsDir }])

  return (
    <PageShell emoji="🧩" title="Cluster Analysis" subtitle="Group docking results by structural similarity and pick diverse representatives" infoTooltip="Group docking results by Tanimoto structural similarity using Butina clustering. Identify diverse chemical scaffolds and pick representative compounds from each cluster." helpUrl="https://www.rdkit.org/docs/source/rdkit.ML.Cluster.Butina.html">

      <div className={s.card}>
        <div className={s.cardHeader}><span className={s.cardTitle}>Configuration</span></div>
        <div className={s.formGrid}>
          <FilePicker label="Results Directory" value={resultsDir} onChange={setResultsDir} directory placeholder="Docking results folder…" />
          <FilePicker label="Source Directory (PDB/SDF)" value={srcDir} onChange={setSrcDir} directory placeholder="Optional source structures…" />
          <div className={s.formGroup}>
            <label className={s.label} htmlFor="cluster-cutoff">Distance Cutoff <Tooltip text="Tanimoto distance threshold (0–1). Lower values create more, tighter clusters. 0.4 is a common default.">ⓘ</Tooltip></label>
            <input id="cluster-cutoff" className={s.input} type="number" min={0.1} max={1.0} step={0.05} value={cutoff} onChange={(e) => setCutoff(Number(e.target.value))} />
          </div>
        </div>
        <div className={s.actions} style={{ marginTop: 16 }}>
          <button className={s.btnPrimary} onClick={handleCluster} disabled={loading || !resultsDir}>
            {loading ? <><span className={s.spinnerSmall} /> Clustering…</> : '🧩 Run Clustering'}
          </button>
          <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
        </div>
      </div>

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {result && result.clusters.length === 0 && (
        <EmptyState icon="🧩" title="No Clusters" description="No clusters could be formed. Try a higher distance cutoff or provide more compounds." />
      )}

      {result && (
        <>
          <div className={s.card}>
            <div className={s.cardHeader}>
              <span className={s.cardTitle}>Overview</span>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span className={s.badgeGreen}>{result.num_clusters} clusters</span>
                <button className={s.btnSecondary} style={{ fontSize: '0.75rem', padding: '4px 10px' }} onClick={() => downloadCSV(
                  ['Cluster_ID', 'Name', 'Score', 'SMILES', 'Is_Centroid'],
                  result.clusters.flatMap(cl => cl.members.map(m => [cl.cluster_id, m.name, m.score, m.smiles ?? '', m.is_centroid ? 'Yes' : 'No'])),
                  'cluster_analysis.csv'
                )}>📥 Export CSV</button>
              </div>
            </div>
            <div className={s.statsGrid}>
              <div className={s.card}>
                <strong style={{ color: 'var(--accent)', fontSize: '1.5rem' }}>{result.total_compounds}</strong>
                <p className={s.label}>Compounds <Tooltip text="Total number of molecules in the clustering input">ⓘ</Tooltip></p>
              </div>
              <div className={s.card}>
                <strong style={{ color: 'var(--green)', fontSize: '1.5rem' }}>{result.num_clusters}</strong>
                <p className={s.label}>Clusters <Tooltip text="Number of distinct structural groups found by Butina clustering">ⓘ</Tooltip></p>
              </div>
              <div className={s.card}>
                <strong style={{ color: 'var(--amber)', fontSize: '1.5rem' }}>{result.singletons}</strong>
                <p className={s.label}>Singletons <Tooltip text="Compounds that don't cluster with any other molecule — structurally unique scaffolds">ⓘ</Tooltip></p>
              </div>
            </div>
          </div>

          {result.clusters.map((cl) => (
            <div key={cl.cluster_id} className={s.card}>
              <div
                className={s.cardHeader}
                style={{ cursor: 'pointer' }}
                onClick={() => setExpandedCluster(expandedCluster === cl.cluster_id ? null : cl.cluster_id)}
              >
                <span className={s.cardTitle}>Cluster {cl.cluster_id} ({cl.size} members)</span>
                <span>{expandedCluster === cl.cluster_id ? '▾' : '▸'}</span>
              </div>
              {expandedCluster === cl.cluster_id && (
                <div className={s.tableScroll}>
                  <table className={s.table}>
                    <thead>
                      <tr>
                        <th className={s.sortableHeader} onClick={() => requestSort('name')} aria-sort={sortKey === 'name' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Name<span className={s.sortIndicator}>{sortIndicator('name')}</span></th>
                        <th className={s.sortableHeader} onClick={() => requestSort('score')} aria-sort={sortKey === 'score' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Score<span className={s.sortIndicator}>{sortIndicator('score')}</span></th>
                        <th>SMILES</th><th>Role</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedMembers.map((m, i) => (
                        <tr key={i}>
                          <td className={s.mono}>{m.name}</td>
                          <td style={{ color: m.score < -6 ? 'var(--green)' : 'var(--text-secondary)' }}>{m.score.toFixed(2)}</td>
                          <td className={s.mono} style={{ maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.smiles ?? '—'} {m.smiles && <CopyButton text={m.smiles} />}</td>
                          <td>{m.is_centroid ? <span className={s.badgeAccent}>Centroid</span> : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </>
      )}
    </PageShell>
  )
}
