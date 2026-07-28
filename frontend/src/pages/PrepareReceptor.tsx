/* ================================================================
   Prepare Receptor — PDB cleaning & PDBQT conversion wizard
   ================================================================ */

import { useState, useEffect } from 'react'
import * as api from '@/lib/api'
import type { PDBAnalysis, PrepareReceptorResponse } from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { useWorkspace } from '@/hooks/useWorkspace'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { PageShell, FilePicker, Alert, PathDisplay, Tooltip, EmptyState, ProteinIntegrityReport } from '@/components/shared'
import s from '@/styles/shared.module.css'

type WizardStep = 'input' | 'configure' | 'done'

export default function PrepareReceptor() {
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const { paths, ready } = useWorkspace()

  /* ---- state ---- */
  const [step, setStep] = useState<WizardStep>('input')
  const [pdbPath, setPdbPath] = useState('')
  const [pdbId, setPdbId] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState<PDBAnalysis | null>(null)
  const [preparing, setPreparing] = useState(false)
  const [result, setResult] = useState<PrepareReceptorResponse | null>(null)
  const [error, setError] = useState('')

  /* ---- cleaning options ---- */
  const [removeWater, setRemoveWater] = useState(true)
  const [removeLigands, setRemoveLigands] = useState(true)
  const [removeIons, setRemoveIons] = useState(true)
  const [addHydrogens, setAddHydrogens] = useState(true)
  const [keepChain, setKeepChain] = useState('')

  useEffect(() => {
    // paths.fetchedPdb is a directory — use it only as the initial browse location,
    // not as the file value (the endpoint expects a .pdb file, not a folder).
  }, [ready])

  /* ---- handlers ---- */
  const handleAnalyze = async () => {
    if (!pdbPath && !pdbId) return
    setAnalyzing(true)
    setError('')
    setAnalysis(null)
    setResult(null)
    addLog(`Analyzing PDB: ${pdbId || pdbPath}…`)

    try {
      const res = await api.analyzePDB(pdbPath, pdbId || undefined)
      setAnalysis(res)
      setPdbPath(res.pdb_path)
      setKeepChain('')
      setStep('configure')
      addLog(`✓ PDB analyzed — ${res.chains.length} chains, ${res.ligands.length} ligands, ${res.water_count} waters, ${res.ions.length} ion types`)
      addToast('PDB analyzed successfully', 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Analysis failed'
      setError(msg)
      addLog(`✗ PDB analysis error: ${msg}`)
      addToast(msg, 'error')
    } finally {
      setAnalyzing(false)
    }
  }

  const handlePrepare = async () => {
    if (!analysis) return
    setPreparing(true)
    setError('')
    addLog(`Preparing receptor: ${analysis.pdb_path}…`)

    try {
      const res = await api.prepareReceptor({
        pdb_path: analysis.pdb_path,
        keep_chain: keepChain || undefined,
        remove_water: removeWater,
        remove_ligands: removeLigands,
        remove_ions: removeIons,
        add_hydrogens: addHydrogens,
      })
      setResult(res)
      setStep('done')
      addLog(`✓ Receptor prepared: ${res.message}`)
      addToast('Receptor preparation complete', 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Preparation failed'
      setError(msg)
      addLog(`✗ Preparation error: ${msg}`)
      addToast(msg, 'error')
    } finally {
      setPreparing(false)
    }
  }

  const handleReset = () => {
    setStep('input')
    setAnalysis(null)
    setResult(null)
    setError('')
    setPdbId('')
    setKeepChain('')
  }

  useKeyboardShortcuts([
    { key: 'Enter', ctrl: true, action: step === 'input' ? handleAnalyze : handlePrepare, enabled: step !== 'done' },
  ])

  /* ---- wizard step indicator ---- */
  const stepLabels = [
    { key: 'input', label: '1. Select PDB', emoji: '📂' },
    { key: 'configure', label: '2. Configure', emoji: '⚙️' },
    { key: 'done', label: '3. Result', emoji: '✅' },
  ]
  const stepIndex = stepLabels.findIndex(sl => sl.key === step)

  return (
    <PageShell
      emoji="🧹"
      title="Prepare Receptor"
      subtitle="Clean PDB structures and convert to PDBQT for docking"
      infoTooltip="Remove waters, ligands, and ions from PDB files, select a chain, add hydrogens, and convert to PDBQT format for AutoDock Vina."
      helpUrl="https://openbabel.org/docs/FileFormats/Overview.html"
      nextStep={{ label: 'Pocket Analysis', path: '/pocket' }}
    >
      {/* Wizard stepper */}
      <div className={s.card} style={{ padding: '12px 16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {stepLabels.map((sl, i) => (
            <div
              key={sl.key}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                opacity: i <= stepIndex ? 1 : 0.4,
                fontWeight: i === stepIndex ? 600 : 400,
                fontSize: '0.85rem',
                transition: 'all 0.2s',
              }}
            >
              <span
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: i <= stepIndex ? 'var(--accent)' : 'var(--bg-secondary)',
                  color: i <= stepIndex ? '#fff' : 'var(--text-secondary)',
                  fontSize: '0.75rem',
                  fontWeight: 700,
                  flexShrink: 0,
                }}
              >
                {i < stepIndex ? '✓' : sl.emoji}
              </span>
              <span style={{ color: i === stepIndex ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                {sl.label}
              </span>
              {i < stepLabels.length - 1 && (
                <div style={{
                  width: 32,
                  height: 2,
                  background: i < stepIndex ? 'var(--accent)' : 'var(--bg-secondary)',
                  borderRadius: 1,
                  transition: 'background 0.3s',
                }} />
              )}
            </div>
          ))}
        </div>
      </div>

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {/* Step 1: Input */}
      {step === 'input' && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Select PDB Source</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div>
              <label className={s.label} htmlFor="prep-pdb">PDB ID (fetch from RCSB)</label>
              <div style={{ display: 'flex', gap: 8 }}>
                <input
                  id="prep-pdb"
                  className={s.input}
                  style={{ maxWidth: 160, textTransform: 'uppercase', fontFamily: 'var(--font-mono)' }}
                  value={pdbId}
                  onChange={e => setPdbId(e.target.value.toUpperCase())}
                  placeholder="e.g. 3PTB"
                  maxLength={8}
                />
                <span className={s.label} style={{ alignSelf: 'center', opacity: 0.5 }}>— or —</span>
              </div>
            </div>

            <FilePicker
              label="Local PDB File"
              value={pdbPath}
              onChange={setPdbPath}
              filters={[
                { name: 'PDB Files', extensions: ['pdb'] },
                { name: 'All Files', extensions: ['*'] },
              ]}
              placeholder="Select a .pdb file…"
            />
          </div>

          <div className={s.actions} style={{ marginTop: 16 }}>
            <button
              className={s.btnPrimary}
              onClick={handleAnalyze}
              disabled={analyzing || (!pdbPath && !pdbId)}
            >
              {analyzing ? <><span className={s.spinnerSmall} /> Analyzing…</> : '🔍 Analyze PDB'}
            </button>
            <span className={s.kbdHint}>
              <kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd>
            </span>
          </div>
        </div>
      )}

      {/* Step 2: Configure */}
      {step === 'configure' && analysis && (
        <>
          {/* Analysis summary */}
          <div className={s.card}>
            <div className={s.cardHeader}>
              <span className={s.cardTitle}>PDB Analysis</span>
              <span className={s.badgeGreen}>{analysis.atom_count.toLocaleString()} atoms</span>
            </div>
            <div className={s.statsGrid}>
              <div className={s.card} style={{ textAlign: 'center' }}>
                <strong style={{ color: 'var(--accent)', fontSize: '1.4rem' }}>{analysis.chains.length}</strong>
                <p className={s.label}>
                  Chains <Tooltip text={`Chains: ${analysis.chains.join(', ') || 'none'}`}>ⓘ</Tooltip>
                </p>
              </div>
              <div className={s.card} style={{ textAlign: 'center' }}>
                <strong style={{ color: 'var(--amber)', fontSize: '1.4rem' }}>{analysis.ligands.length}</strong>
                <p className={s.label}>
                  Ligands <Tooltip text={`Ligands: ${analysis.ligands.join(', ') || 'none'}`}>ⓘ</Tooltip>
                </p>
              </div>
              <div className={s.card} style={{ textAlign: 'center' }}>
                <strong style={{ color: 'var(--blue)', fontSize: '1.4rem' }}>{analysis.water_count}</strong>
                <p className={s.label}>Waters</p>
              </div>
              <div className={s.card} style={{ textAlign: 'center' }}>
                <strong style={{ color: 'var(--red)', fontSize: '1.4rem' }}>{analysis.ions.length}</strong>
                <p className={s.label}>
                  Ion Types <Tooltip text={`Ions: ${analysis.ions.join(', ') || 'none'}`}>ⓘ</Tooltip>
                </p>
              </div>
            </div>
          </div>

          {analysis.integrity && <ProteinIntegrityReport report={analysis.integrity} />}

          {/* Cleaning options */}
          <div className={s.card}>
            <div className={s.cardHeader}>
              <span className={s.cardTitle}>Cleaning Options</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
              <label className={s.label} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input type="checkbox" checked={removeWater} onChange={e => setRemoveWater(e.target.checked)} />
                Remove waters ({analysis.water_count})
              </label>
              <label className={s.label} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input type="checkbox" checked={removeLigands} onChange={e => setRemoveLigands(e.target.checked)} />
                Remove ligands ({analysis.ligands.length})
              </label>
              <label className={s.label} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input type="checkbox" checked={removeIons} onChange={e => setRemoveIons(e.target.checked)} />
                Remove ions ({analysis.ions.length})
              </label>
              <label className={s.label} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input type="checkbox" checked={addHydrogens} onChange={e => setAddHydrogens(e.target.checked)} />
                Add hydrogens <Tooltip text="Add polar hydrogens and compute Gasteiger partial charges">ⓘ</Tooltip>
              </label>
            </div>

            {/* Chain selector */}
            {analysis.chains.length > 1 && (
              <div style={{ marginTop: 16 }}>
                <label className={s.label} htmlFor="prep-chain">Keep Chain (leave empty for all)</label>
                <select
                  id="prep-chain"
                  className={s.select}
                  value={keepChain}
                  onChange={e => setKeepChain(e.target.value)}
                  style={{ maxWidth: 160 }}
                >
                  <option value="">All chains</option>
                  {analysis.chains.map(c => (
                    <option key={c} value={c}>Chain {c}</option>
                  ))}
                </select>
              </div>
            )}

            <div className={s.actions} style={{ marginTop: 16 }}>
              <button className={s.btnSecondary} onClick={() => setStep('input')}>
                ← Back
              </button>
              <button
                className={s.btnPrimary}
                onClick={handlePrepare}
                disabled={preparing}
              >
                {preparing ? <><span className={s.spinnerSmall} /> Preparing…</> : '🧹 Prepare Receptor'}
              </button>
              <span className={s.kbdHint}>
                <kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd>
              </span>
            </div>
          </div>
        </>
      )}

      {/* Step 3: Results */}
      {step === 'done' && result && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Preparation Complete</span>
            <span className={s.badgeGreen}>Success</span>
          </div>

          <div className={s.statsGrid}>
            <div className={s.card} style={{ textAlign: 'center' }}>
              <strong style={{ color: 'var(--blue)', fontSize: '1.4rem' }}>{result.removed_waters}</strong>
              <p className={s.label}>Waters Removed</p>
            </div>
            <div className={s.card} style={{ textAlign: 'center' }}>
              <strong style={{ color: 'var(--amber)', fontSize: '1.4rem' }}>{result.removed_ligands}</strong>
              <p className={s.label}>Ligand Atoms Removed</p>
            </div>
            <div className={s.card} style={{ textAlign: 'center' }}>
              <strong style={{ color: 'var(--red)', fontSize: '1.4rem' }}>{result.removed_ions}</strong>
              <p className={s.label}>Ions Removed</p>
            </div>
          </div>

          <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div>
              <span className={s.label}>Preparation Engine</span>
              <span className={s.mono}>{result.prep_engine ?? 'meeko'}</span>
            </div>
            <div>
              <span className={s.label}>Clean PDB</span>
              <PathDisplay path={result.clean_pdb_path} />
            </div>
            <div>
              <span className={s.label}>Output PDBQT</span>
              <PathDisplay path={result.output_path} />
            </div>
          </div>

          <div className={s.actions} style={{ marginTop: 16 }}>
            <button className={s.btnSecondary} onClick={handleReset}>
              🔄 Prepare Another
            </button>
          </div>

          {result.warnings?.length ? (
            <div style={{ marginTop: 12 }}>
              <Alert variant="warning" message={result.warnings.join(' ')} />
            </div>
          ) : null}
        </div>
      )}

      {step === 'done' && result?.integrity && <ProteinIntegrityReport comparison={result.integrity} />}

      {/* Empty state */}
      {step === 'input' && !analyzing && !error && (
        <EmptyState
          icon="🧹"
          title="No Receptor Prepared"
          description="Enter a PDB ID or select a local PDB file to clean and convert for docking."
        />
      )}
    </PageShell>
  )
}
