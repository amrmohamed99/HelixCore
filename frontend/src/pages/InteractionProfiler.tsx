/* ================================================================
   Interaction Profiler — Protein-ligand contact detection
   ================================================================ */

import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import * as api from '@/lib/api'
import type { InteractionResponse, Interaction } from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { useSortableTable } from '@/hooks/useSortableTable'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useSessionField } from '@/hooks/useSessionField'
import { PageShell, FilePicker, Alert, Tooltip, EmptyState, TableSkeleton, ForceGraph } from '@/components/shared'
import type { ForceGraphData, GraphNode, GraphEdge } from '@/components/shared/ForceGraph'
import StructureViewer from '@/components/shared/StructureViewer'
import { downloadCSV } from '@/lib/export'
import s from '@/styles/shared.module.css'

type ISortKey = 'type' | 'residue' | 'distance'

export default function InteractionProfiler() {
  const location = useLocation()
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const [receptorPath, setReceptorPath] = useSessionField('interaction.receptorPath', '')
  const [ligandPath, setLigandPath] = useSessionField('interaction.ligandPath', '')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<InteractionResponse | null>(null)
  const [error, setError] = useState('')
  const [networkData, setNetworkData] = useState<ForceGraphData | null>(null)
  const { sorted, sortKey, sortDir, requestSort, sortIndicator } = useSortableTable<Interaction, ISortKey>(
    result?.interactions ?? [], 'distance',
  )

  /* Pre-fill from Docking page navigation */
  useEffect(() => {
    const st = location.state as { ligandName?: string; receptorPath?: string } | null
    if (st?.receptorPath) setReceptorPath(st.receptorPath)
  }, [location.state])

  const handleAnalyze = async () => {
    if (!receptorPath || !ligandPath) return
    setLoading(true)
    setError('')
    setResult(null)
    addLog(`Analyzing interactions…`)

    try {
      const res = await api.analyzeInteractions({ receptor_path: receptorPath, ligand_path: ligandPath })
      setResult(res)
      addLog(
        `✓ Found ${res.total_single_label} interacting atom pairs `
        + `(${res.total} labels: ${res.h_bonds} H-bonds, ${res.hydrophobic} hydrophobic, `
        + `${res.salt_bridges} salt bridges)`,
      )
      addToast(`${res.total_single_label} interacting atom pairs detected`, 'success')

      // Also build the network graph
      try {
        const net = await api.getInteractionNetwork({ receptor_path: receptorPath, ligand_path: ligandPath })
        setNetworkData({
          nodes: net.nodes as GraphNode[],
          edges: net.edges as GraphEdge[],
        })
      } catch { /* network is optional */ }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Analysis failed'
      setError(msg)
      addLog(`✗ Interaction error: ${msg}`)
      addToast(msg, 'error')
    } finally {
      setLoading(false)
    }
  }

  useKeyboardShortcuts([{ key: 'Enter', ctrl: true, action: handleAnalyze, enabled: !loading && !!receptorPath && !!ligandPath }])

  return (
    <PageShell emoji="🔗" title="Interaction Profiler" subtitle="Detect H-bonds, hydrophobic contacts, and salt bridges from docked poses" infoTooltip="Analyze protein-ligand interactions from docked poses. Detects hydrogen bonds, hydrophobic contacts, salt bridges, and other non-covalent interactions to understand binding mode." helpUrl="https://en.wikipedia.org/wiki/Protein%E2%80%93ligand_docking">

      <div className={s.card}>
        <div className={s.cardHeader}><span className={s.cardTitle}>Input Files</span></div>
        <div className={s.formGrid}>
          <FilePicker
            label="Receptor (PDBQT)"
            value={receptorPath}
            onChange={setReceptorPath}
            filters={[{ name: 'PDBQT', extensions: ['pdbqt', 'pdb'] }]}
            placeholder="Select receptor file…"
          />
          <FilePicker
            label="Ligand Pose (PDBQT)"
            value={ligandPath}
            onChange={setLigandPath}
            filters={[{ name: 'PDBQT', extensions: ['pdbqt'] }]}
            placeholder="Select docked ligand pose…"
          />
        </div>
        <div className={s.actions} style={{ marginTop: 16 }}>
          <button className={s.btnPrimary} onClick={handleAnalyze} disabled={loading || !receptorPath || !ligandPath}>
            {loading ? <><span className={s.spinnerSmall} /> Analyzing…</> : '🔗 Analyze Interactions'}
          </button>
          <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
        </div>
      </div>

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {loading && !result && <TableSkeleton rows={5} cols={3} />}

      {result && (
        <>
          <div className={s.card}>
            <div className={s.cardHeader}>
              <span className={s.cardTitle}>Summary</span>
              <span className={s.badgeGreen}>
                {result.total_single_label} atom pairs · {result.total} labels
              </span>
            </div>
            <div className={s.statsGrid}>
              <div className={s.card}>
                <strong style={{ color: 'var(--accent)', fontSize: '1.5rem' }}>{result.h_bonds}</strong>
                <p className={s.label}>H-Bonds <Tooltip text="Hydrogen bonds between donor and acceptor atoms — key for binding specificity">ⓘ</Tooltip></p>
              </div>
              <div className={s.card}>
                <strong style={{ color: 'var(--amber)', fontSize: '1.5rem' }}>{result.hydrophobic}</strong>
                <p className={s.label}>Hydrophobic <Tooltip text="Non-polar contacts between hydrophobic groups — drive binding affinity">ⓘ</Tooltip></p>
              </div>
              <div className={s.card}>
                <strong style={{ color: 'var(--violet)', fontSize: '1.5rem' }}>{result.salt_bridges}</strong>
                <p className={s.label}>Salt Bridges <Tooltip text="Charge-complementary contacts within 4.0 Å. A pair may also carry an H-bond label.">ⓘ</Tooltip></p>
              </div>
            </div>
            {result.dual_labeled_pairs > 0 && (
              <Alert
                variant="info"
                message={
                  `${result.dual_labeled_pairs} atom pair${result.dual_labeled_pairs === 1 ? '' : 's'} `
                  + `carry both H-bond and salt-bridge labels. Legacy single-label continuity: `
                  + `${result.total_single_label} total pairs, ${result.salt_bridges_single_label} salt bridges.`
                }
              />
            )}
          </div>

          {result.interactions.length === 0 && (
            <EmptyState icon="🔗" title="No Contacts Detected" description="Select a receptor PDB and a docked ligand PDBQT to analyze protein-ligand interactions. Run Docking first to generate poses." />
          )}

          {result.interactions.length > 0 && (
            <div className={s.card}>
              <div className={s.cardHeader}>
                <span className={s.cardTitle}>Contact Details</span>
                <button className={s.btnSecondary} style={{ fontSize: '0.75rem', padding: '4px 10px' }} onClick={() => downloadCSV(
                  ['Type', 'Residue', 'Protein_Atom', 'Ligand_Atom', 'Distance_A'],
                  result.interactions.map(c => [c.type, c.residue, c.receptor_atom ?? '', c.ligand_atom ?? '', c.distance]),
                  'interaction_contacts.csv'
                )}>📥 Export CSV</button>
              </div>
              <div className={s.tableScroll}>
                <table className={s.table}>
                  <thead>
                    <tr>
                      <th className={s.sortableHeader} onClick={() => requestSort('type')} aria-sort={sortKey === 'type' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Type<span className={s.sortIndicator}>{sortIndicator('type')}</span></th>
                      <th className={s.sortableHeader} onClick={() => requestSort('residue')} aria-sort={sortKey === 'residue' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Residue<span className={s.sortIndicator}>{sortIndicator('residue')}</span></th>
                      <th>Protein Atom</th>
                      <th>Ligand Atom</th>
                      <th className={s.sortableHeader} onClick={() => requestSort('distance')} aria-sort={sortKey === 'distance' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Distance (Å)<span className={s.sortIndicator}>{sortIndicator('distance')}</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((c, i) => (
                      <tr key={i}>
                        <td>
                          <span className={c.type === 'H-bond' ? s.badgeGreen : c.type === 'Hydrophobic' ? s.badgeAmber : s.badgeAccent}>
                            {c.type}
                          </span>
                        </td>
                        <td className={s.mono}>{c.residue}</td>
                        <td className={s.mono}>{c.receptor_atom ?? '—'}</td>
                        <td className={s.mono}>{c.ligand_atom ?? '—'}</td>
                        <td>{c.distance.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── Interaction Network Graph ── */}
          {networkData && networkData.nodes.length > 0 && (
            <div className={s.card}>
              <div className={s.cardHeader}>
                <span className={s.cardTitle}>🕸️ Interaction Network</span>
                <span className={s.badgeAccent}>{networkData.edges.length} edges</span>
              </div>
              <ForceGraph data={networkData} height={480} />
            </div>
          )}

          {/* ── 3D Binding Pose ── */}
          {receptorPath && ligandPath && (
            <div className={s.card}>
              <div className={s.cardHeader}><span className={s.cardTitle}>🧬 Binding Pose</span></div>
              <StructureViewer
                filePath={ligandPath}
                overlayFilePath={receptorPath}
                height={420}
                label={`${ligandPath.split(/[\\/]/).pop()} • ${receptorPath.split(/[\\/]/).pop()}`}
              />
            </div>
          )}
        </>
      )}
    </PageShell>
  )
}
