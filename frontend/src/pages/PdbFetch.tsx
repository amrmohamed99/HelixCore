/* ================================================================
   PDB Fetch — Download receptor structures
   ================================================================ */

import { useState, useEffect } from 'react'
import * as api from '@/lib/api'
import type { FetchPDBResponse, UniprotInfo, DrugInfo } from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { usePipelineStep } from '@/hooks/usePipelineStep'
import { useWorkspace } from '@/hooks/useWorkspace'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { PageShell, FilePicker, Alert, PathDisplay, Tooltip, MolViewer, EmptyState, CopyButton } from '@/components/shared'
import s from '@/styles/shared.module.css'
import p from './PdbFetch.module.css'

export default function PdbFetch() {
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const { markRunning, markDone, markError } = usePipelineStep('fetch')
  const { paths, ready } = useWorkspace()
  const [pdbId, setPdbId] = useState('')
  const [outputDir, setOutputDir] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<FetchPDBResponse | null>(null)
  const [uniprot, setUniprot] = useState<UniprotInfo | null>(null)
  const [drug, setDrug] = useState<DrugInfo | null>(null)
  const [drugLoading, setDrugLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (ready && !outputDir) setOutputDir(paths.fetchedPdb)
  }, [ready])

  const handleFetch = async () => {
    if (!pdbId || !outputDir) return
    markRunning()
    setLoading(true)
    setError('')
    setResult(null)
    setUniprot(null)
    setDrug(null)
    addLog(`Fetching PDB: ${pdbId}…`)

    try {
      const res = await api.fetchPDB({ pdb_id: pdbId, output_dir: outputDir })
      setResult(res)
      addLog(`✓ PDB fetched: ${res.message}`)
      addToast(`PDB ${pdbId} fetched successfully`, 'success')
      markDone()

      try {
        const info = await api.getUniprotInfo(pdbId)
        setUniprot(info)
        addLog(`✓ UniProt data loaded for ${pdbId}`)
      } catch {
        addLog(`⚠ UniProt data not available for ${pdbId}`)
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Fetch failed'
      setError(msg)
      addLog(`✗ Fetch error: ${msg}`)
      addToast(msg, 'error')
      markError()
    } finally {
      setLoading(false)
    }
  }

  const handleFindDrugs = async () => {
    if (!pdbId) return
    setDrugLoading(true)
    setDrug(null)
    addLog(`Searching drug controls for ${pdbId}…`)

    try {
      const res = await api.findDrugControls(pdbId)
      setDrug(res)
      if (res) {
        addLog(`✓ Drug control found: ${res.name}`)
        addToast(`Drug found: ${res.name}`, 'success')
      } else {
        addLog(`⚠ No drug controls found for ${pdbId}`)
        addToast('No approved drugs or high-affinity binders found', 'info')
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Drug search failed'
      addLog(`✗ Drug search error: ${msg}`)
      addToast(msg, 'error')
    } finally {
      setDrugLoading(false)
    }
  }

  useKeyboardShortcuts([{ key: 'Enter', ctrl: true, action: handleFetch, enabled: !loading && !!pdbId && !!outputDir }])

  return (
    <PageShell
      emoji="🔬"
      title="PDB Fetch"
      subtitle="Download receptor structures from RCSB PDB"
      infoTooltip="Download unmodified protein structure files from the RCSB Protein Data Bank. Use Prepare Receptor next to clean and convert the structure for docking."
      helpUrl="https://www.rcsb.org/docs/general-help/organization-of-3d-structures-in-the-protein-data-bank"
      nextStep={{ label: 'Prepare Receptor', path: '/prepare' }}
    >
      <div className={s.card}>
        <div className={s.cardHeader}>
          <span className={s.cardTitle}>Configuration</span>
        </div>
        <div className={s.formGrid}>
          <div className={s.formGroup}>
            <label className={s.label} htmlFor="pdb-id">PDB ID <Tooltip text="4-character Protein Data Bank identifier (e.g. 1AKE, 3PTB)">ⓘ</Tooltip></label>
            <input
              id="pdb-id"
              className={s.inputMono}
              value={pdbId}
              onChange={(e) => setPdbId(e.target.value.toUpperCase())}
              placeholder="e.g. 1AKE"
              maxLength={4}
            />
          </div>
          <FilePicker
            label="Output Directory"
            value={outputDir}
            onChange={setOutputDir}
            directory
            placeholder="Select folder…"
          />
        </div>
        <div className={`${s.actions} ${p.actionsRow}`}>
          <Tooltip text="Download and save the unmodified PDB file from RCSB"><button className={s.btnPrimary} onClick={handleFetch} disabled={loading || !pdbId || !outputDir}>
            {loading ? <><span className={s.spinnerSmall} /> Fetching…</> : '🔬 Fetch PDB'}
          </button></Tooltip>
          <Tooltip text="Search ChEMBL for approved drugs or experimental binders against this target"><button
            className={s.btnOrange}
            onClick={handleFindDrugs}
            disabled={drugLoading || !pdbId}
          >
            {drugLoading ? <><span className={s.spinnerSmall} /> Searching…</> : '🔑 Find Drugs'}
          </button></Tooltip>
          <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
        </div>
      </div>

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {!result && !loading && !error && (
        <EmptyState icon="🧬" title="No Structure Loaded" description="Enter a 4-character PDB ID above to fetch a receptor structure from RCSB." />
      )}

      {result && (
        <div className={s.card}>
          <div className={s.cardHeader}><span className={s.cardTitle}>Result</span><span className={s.badgeGreen}>Success</span></div>
          <p className={p.resultMsg}>{result.message}</p>
          {result.pdb_path && <PathDisplay label="Fetched PDB" path={result.pdb_path} />}
        </div>
      )}

      {/* ── Intelligence Report ── */}
      {uniprot && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Intelligence Report</span>
          </div>
          <div className={p.reportBlock}>
            <p className={p.reportHeading}>
              — UniProt Summary ({uniprot.accession}) —
            </p>
            <p>Gene: <strong className={p.reportHighlight}>{uniprot.gene}</strong> | Organism: <strong className={p.reportHighlight}>{uniprot.organism}</strong></p>
            {uniprot.chembl_id && <p>ChEMBL Target ID: <strong className={p.reportAccent}>{uniprot.chembl_id}</strong></p>}
            <p>Entry Name: <strong className={p.reportHighlight}>{uniprot.entry_name}</strong></p>

            <p className={p.sectionLabel}>[FUNCTION]</p>
            <p>{uniprot.function}</p>

            {uniprot.bio_processes.length > 0 && (
              <>
                <p className={p.sectionLabel}>[BIOLOGICAL PROCESS (GO)]</p>
                <p>{uniprot.bio_processes.join(', ')}</p>
              </>
            )}

            {uniprot.pathways.length > 0 && (
              <>
                <p className={p.sectionLabel}>[PATHWAYS]</p>
                <div className={`${s.floatingPills} ${p.pillsGap}`}>
                  {uniprot.pathways.map((pw) => <span key={pw} className={s.pill}>{pw}</span>)}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── Interaction Network ── */}
      {uniprot?.network_image_url && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={`${s.cardTitle} ${p.networkTitle}`}>Interaction Network</span>
          </div>
          <div className={p.networkWrap}>
            <img
              src={uniprot.network_image_url}
              alt={`STRING interaction network for ${uniprot.gene}`}
              className={p.networkImg}
            />
          </div>
        </div>
      )}

      {/* ── Drug Control Results ── */}
      {drug && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Drug Control</span>
            <span className={drug.source === 'approved_drug' ? s.badgeGreen : s.badgeAmber}>
              {drug.source === 'approved_drug' ? 'Approved Drug' : 'Experimental Binder'}
            </span>
          </div>
          <div className={s.formGrid}>
            <div className={s.formGroup}>
              <span className={s.label}>Name <Tooltip text="Drug compound name from ChEMBL database">ⓘ</Tooltip></span>
              <span className={p.bold}>{drug.name}</span>
            </div>
            <div className={s.formGroup}>
              <span className={s.label}>ChEMBL ID <Tooltip text="Unique identifier in the ChEMBL bioactivity database">ⓘ</Tooltip></span>
              <span className={s.mono}>{drug.chembl_id}</span>
            </div>
            {drug.smiles && (
              <div className={s.formGroupFull}>
                <span className={s.label}>SMILES <Tooltip text="Simplified Molecular Input Line Entry System — a text representation of the molecular structure">ⓘ</Tooltip></span>
                <span className={`${s.mono} ${p.smilesText}`}>{drug.smiles} <CopyButton text={drug.smiles} /></span>
                <MolViewer smiles={drug.smiles} width={200} height={160} />
              </div>
            )}
            {drug.affinity_type && drug.affinity_value && (
              <div className={s.formGroup}>
                <span className={s.label}>Affinity ({drug.affinity_type}) <Tooltip text="Binding affinity measurement — lower IC50/Ki values indicate stronger binding">ⓘ</Tooltip></span>
                <span className={s.mono}>{drug.affinity_value}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </PageShell>
  )
}
