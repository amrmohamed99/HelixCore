/* ================================================================
   Pocket Analysis — Binding site detection & grid box calculation
   ================================================================ */

import { useState } from 'react'
import * as api from '@/lib/api'
import type { PocketAnalysisResponse, GridBoxResponse, DruggabilityResponse } from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { usePipelineStep } from '@/hooks/usePipelineStep'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useSessionField } from '@/hooks/useSessionField'
import { PageShell, FilePicker, Alert, PathDisplay, Tooltip, EmptyState } from '@/components/shared'
import { downloadCSV } from '@/lib/export'
import s from '@/styles/shared.module.css'

export default function PocketAnalysis() {
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const { markRunning, markDone, markError } = usePipelineStep('pocket')
  const [pdbPath, setPdbPath] = useSessionField('pocket.pdbPath', '')
  const [ligandName, setLigandName] = useSessionField('pocket.ligandName', '')
  const [ligandChain, setLigandChain] = useSessionField('pocket.ligandChain', '')
  const [ligandResseq, setLigandResseq] = useSessionField('pocket.ligandResseq', '')
  const [padding, setPadding] = useSessionField('pocket.padding', '8')
  const [loading, setLoading] = useState(false)
  const [pocket, setPocket] = useState<PocketAnalysisResponse | null>(null)
  const [grid, setGrid] = useState<GridBoxResponse | null>(null)
  const [druggability, setDruggability] = useState<DruggabilityResponse | null>(null)
  const [drugLoading, setDrugLoading] = useState(false)
  const [error, setError] = useState('')

  const handleAnalyze = async () => {
    if (!pdbPath) return
    markRunning()
    setLoading(true)
    setError('')
    setPocket(null)
    setGrid(null)
    setDruggability(null)
    addLog(`Analyzing pocket: ${pdbPath}…`)

    try {
      const ligandInstance = {
        ligand_name: ligandName || undefined,
        ligand_chain: ligandChain || undefined,
        ligand_resseq: ligandResseq ? Number(ligandResseq) : undefined,
      }
      const res = await api.analyzePocket({ pdb_path: pdbPath, ...ligandInstance })
      setPocket(res)
      addLog(`✓ Found ${res.residues.length} pocket residues`)

      const gridRes = await api.calculateGrid({ pdb_path: pdbPath, ...ligandInstance, padding: parseFloat(padding) || 8 })
      setGrid(gridRes)
      addLog(`✓ Grid box calculated`)
      addToast(`Found ${res.residues.length} pocket residues`, 'success')
      markDone()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Analysis failed'
      setError(msg)
      addLog(`✗ Pocket error: ${msg}`)
      addToast(msg, 'error')
      markError()
    } finally {
      setLoading(false)
    }
  }

  useKeyboardShortcuts([{ key: 'Enter', ctrl: true, action: handleAnalyze, enabled: !loading && !!pdbPath }])

  return (
    <PageShell
      emoji="🎯"
      title="Pocket Analysis"
      subtitle="Detect binding site residues and compute docking grid box"
      infoTooltip="Identify binding site residues near a co-crystallized ligand and compute the Vina docking grid box parameters for targeted docking."
      helpUrl="https://autodock-vina.readthedocs.io/en/latest/docking_basic.html"
      nextStep={{ label: 'Ligand Gen', path: '/batch' }}
    >
      <div className={s.card}>
        <div className={s.cardHeader}><span className={s.cardTitle}>Configuration</span></div>
        <div className={s.formGrid}>
          <FilePicker
            label="PDB File"
            value={pdbPath}
            onChange={setPdbPath}
            filters={[{ name: 'PDB Files', extensions: ['pdb'] }]}
            placeholder="Select PDB file…"
          />
          <div className={s.formGroup}>
            <label className={s.label} htmlFor="pocket-ligand">Ligand Name (optional) <Tooltip text="3-letter HET code of the co-crystallized ligand to define the binding pocket (e.g. ADP, BEN)">ⓘ</Tooltip></label>
            <input
              id="pocket-ligand"
              className={s.inputMono}
              value={ligandName}
              onChange={(e) => setLigandName(e.target.value.toUpperCase())}
              placeholder="e.g. ADP"
            />
          </div>
          <div className={s.formGroup}>
            <label className={s.label} htmlFor="pocket-chain">Ligand Chain (optional) <Tooltip text="Exact PDB chain ID for the ligand instance, such as A or B.">ⓘ</Tooltip></label>
            <input
              id="pocket-chain"
              className={s.inputMono}
              maxLength={1}
              value={ligandChain}
              onChange={(e) => setLigandChain(e.target.value.toUpperCase())}
              placeholder="e.g. A"
            />
          </div>
          <div className={s.formGroup}>
            <label className={s.label} htmlFor="pocket-resseq">Ligand Residue Number (optional) <Tooltip text="Exact PDB residue sequence number. Use with ligand name and chain to avoid combining multiple instances.">ⓘ</Tooltip></label>
            <input
              id="pocket-resseq"
              className={s.inputMono}
              type="number"
              step={1}
              value={ligandResseq}
              onChange={(e) => setLigandResseq(e.target.value)}
              placeholder="e.g. 1"
            />
          </div>
          <div className={s.formGroup}>
            <label className={s.label} htmlFor="pocket-padding">Grid Padding (Å) <Tooltip text="Extra space added to each dimension of the grid box beyond the pocket/protein bounds. Standard range: 4–12 Å.">ⓘ</Tooltip></label>
            <input
              id="pocket-padding"
              className={s.inputMono}
              type="number"
              min={2}
              max={30}
              step={0.5}
              value={padding}
              onChange={(e) => setPadding(e.target.value)}
              placeholder="8"
            />
          </div>
        </div>
        <div className={s.actions} style={{ marginTop: 16 }}>
          <button className={s.btnPrimary} onClick={handleAnalyze} disabled={loading || !pdbPath}>
            {loading ? <><span className={s.spinnerSmall} /> Analyzing…</> : '🎯 Analyze Pocket'}
          </button>
          <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
        </div>
      </div>

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {!pocket && !loading && !error && (
        <EmptyState icon="🎯" title="No Pockets Detected" description="Select a PDB file above to detect binding pockets and compute a docking grid box." />
      )}

      {pocket && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Pocket Residues</span>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span className={s.badgeGreen}>{pocket.residues.length} residues</span>
              <button className={s.btnSecondary} style={{ fontSize: '0.75rem', padding: '4px 10px' }} onClick={() => {
                const headers = ['Residue', 'Ligand_Atoms', 'Contacts']
                const rows: (string | number)[][] = pocket.residues.map(r => [r, pocket.ligand_atom_count, pocket.contact_count])
                if (grid) {
                  headers.push('Center_X', 'Center_Y', 'Center_Z', 'Size_X', 'Size_Y', 'Size_Z')
                  rows.forEach(row => row.push(grid.grid.center_x, grid.grid.center_y, grid.grid.center_z, grid.grid.size_x, grid.grid.size_y, grid.grid.size_z))
                }
                downloadCSV(headers, rows, 'pocket_analysis.csv')
              }}>📥 Export CSV</button>
            </div>
          </div>
          <div className={s.floatingPills}>
            {pocket.residues.map((r) => <span key={r} className={s.pill}>{r}</span>)}
          </div>
          <div className={s.formGrid} style={{ marginTop: 16 }}>
            <div className={s.formGroup}>
              <span className={s.label}>Ligand Atoms <Tooltip text="Number of heavy (non-hydrogen) atoms in the co-crystallized ligand">ⓘ</Tooltip></span>
              <span>{pocket.ligand_atom_count}</span>
            </div>
            <div className={s.formGroup}>
              <span className={s.label}>Contacts <Tooltip text="Number of protein-ligand atomic contacts detected within the binding site">ⓘ</Tooltip></span>
              <span>{pocket.contact_count}</span>
            </div>
          </div>
        </div>
      )}

      {grid && (
        <div className={s.card}>
          <div className={s.cardHeader}><span className={s.cardTitle}>Grid Box</span></div>
          <div className={s.formGrid}>
            <div className={s.formGroup}><span className={s.label}>Center X <Tooltip text="X-coordinate of the grid box center in Angstroms">ⓘ</Tooltip></span><span className={s.mono}>{grid.grid.center_x.toFixed(3)}</span></div>
            <div className={s.formGroup}><span className={s.label}>Center Y <Tooltip text="Y-coordinate of the grid box center in Angstroms">ⓘ</Tooltip></span><span className={s.mono}>{grid.grid.center_y.toFixed(3)}</span></div>
            <div className={s.formGroup}><span className={s.label}>Center Z <Tooltip text="Z-coordinate of the grid box center in Angstroms">ⓘ</Tooltip></span><span className={s.mono}>{grid.grid.center_z.toFixed(3)}</span></div>
            <div className={s.formGroup}><span className={s.label}>Size X <Tooltip text="Width of the docking search space along X axis">ⓘ</Tooltip></span><span className={s.mono}>{grid.grid.size_x.toFixed(1)}</span></div>
            <div className={s.formGroup}><span className={s.label}>Size Y <Tooltip text="Width of the docking search space along Y axis">ⓘ</Tooltip></span><span className={s.mono}>{grid.grid.size_y.toFixed(1)}</span></div>
            <div className={s.formGroup}><span className={s.label}>Size Z <Tooltip text="Width of the docking search space along Z axis">ⓘ</Tooltip></span><span className={s.mono}>{grid.grid.size_z.toFixed(1)}</span></div>
          </div>
          {grid.output_path && <PathDisplay label="Config Saved" path={grid.output_path} />}
        </div>
      )}

      {/* Druggability Assessment */}
      {pocket && (
        <div className={s.card}>
          <div className={s.cardHeader}><span className={s.cardTitle}>Druggability Assessment</span></div>
          <div className={s.actions}>
            <button
              className={s.btnOrange}
              onClick={async () => {
                setDrugLoading(true)
                try {
                  const res = await api.assessDruggability({
                    pdb_path: pdbPath,
                    ligand_name: ligandName || undefined,
                    ligand_chain: ligandChain || undefined,
                    ligand_resseq: ligandResseq ? Number(ligandResseq) : undefined,
                  })
                  setDruggability(res)
                  addLog(`✓ Druggability: ${res.druggable ? 'DRUGGABLE' : 'Non-druggable'} (${res.confidence})`)
                  addToast(`Druggability: ${res.confidence}`, 'success')
                } catch (err: unknown) {
                  const msg = err instanceof Error ? err.message : 'Druggability failed'
                  addToast(msg, 'error')
                } finally {
                  setDrugLoading(false)
                }
              }}
              disabled={drugLoading}
            >
              {drugLoading ? <><span className={s.spinnerSmall} /> Assessing…</> : '💊 Assess Druggability'}
            </button>
          </div>
          {druggability && (
            <>
              <div className={s.statsGrid} style={{ marginTop: 12 }}>
                <div className={s.card}>
                  <strong style={{ fontSize: '1.4rem', color: druggability.druggable ? 'var(--green)' : 'var(--red)' }}>
                    {druggability.druggable ? '✓ Druggable' : '✗ Non-druggable'}
                  </strong>
                  <p className={s.label}>Verdict <Tooltip text="Whether the pocket is likely suitable for small-molecule drug binding">ⓘ</Tooltip></p>
                </div>
                <div className={s.card}>
                  <strong className={s.mono}>{druggability.confidence}</strong>
                  <p className={s.label}>Confidence <Tooltip text="How confident the druggability prediction is based on pocket properties">ⓘ</Tooltip></p>
                </div>
                <div className={s.card}>
                  <strong className={s.mono}>{druggability.residue_count}</strong>
                  <p className={s.label}>Residues <Tooltip text="Number of amino acid residues lining the binding pocket">ⓘ</Tooltip></p>
                </div>
              </div>
              <div className={s.formGrid} style={{ marginTop: 12 }}>
                <div className={s.formGroup}>
                  <span className={s.label}>Volume <Tooltip text="Estimated pocket cavity volume in cubic Angstroms — larger pockets can accommodate bigger ligands">ⓘ</Tooltip></span>
                  <span className={s.mono}>{druggability.volume?.toFixed(1) ?? '—'} ų</span>
                </div>
                <div className={s.formGroup}>
                  <span className={s.label}>Hydrophobicity <Tooltip text="Fraction of hydrophobic residues lining the pocket — higher values favor small-molecule binding">ⓘ</Tooltip></span>
                  <span className={s.mono}>{druggability.hydrophobicity_ratio != null ? `${(druggability.hydrophobicity_ratio * 100).toFixed(0)}%` : '—'}</span>
                </div>
              </div>
              {druggability.notes.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  {druggability.notes.map((n, i) => <p key={i} style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>• {n}</p>)}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </PageShell>
  )
}
