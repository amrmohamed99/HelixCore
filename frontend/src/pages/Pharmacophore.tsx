/* ================================================================
   Pharmacophore — Modeling & Screening
   Generate pharmacophore features from a reference molecule,
   visualise with colored overlays, screen compound libraries,
   and save/load pharmacophore models as JSON.
   ================================================================ */

import { useState, useMemo } from 'react'
import * as api from '@/lib/api'
import type {
  PharmGenerateResponse,
  PharmScreenResponse,
  PharmScreenHit,
  PharmacophoreFeature,
} from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { useWorkspace } from '@/hooks/useWorkspace'
import { useSortableTable } from '@/hooks/useSortableTable'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useSessionField } from '@/hooks/useSessionField'
import {
  PageShell,
  FilePicker,
  Alert,
  Tooltip,
  Pagination,
  EmptyState,
  TableSkeleton,
  MoleculeEditor,
  CopyButton,
} from '@/components/shared'
import { downloadCSV } from '@/lib/export'
import s from '@/styles/shared.module.css'

/* Feature type → badge class + color swatch */
const FEATURE_BADGE: Record<string, { badge: string; color: string; label: string }> = {
  HBD: { badge: 'badgeBlue', color: '#3B82F6', label: 'H-Bond Donor' },
  HBA: { badge: 'badgeRose', color: '#EF4444', label: 'H-Bond Acceptor' },
  Hydrophobic: { badge: 'badgeAmber', color: '#EAB308', label: 'Hydrophobic' },
  Aromatic: { badge: 'badgePurple', color: '#A855F7', label: 'Aromatic' },
  PosIonizable: { badge: 'badgeGreen', color: '#22C55E', label: 'Pos-Ionizable' },
  NegIonizable: { badge: 'badgeOrange', color: '#F97316', label: 'Neg-Ionizable' },
}

type HitSortKey = 'name' | 'score' | 'matched_features'
const PAGE_SIZE = 20

export default function Pharmacophore() {
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const { paths } = useWorkspace()

  /* ── Generate panel state ── */
  const [smiles, setSmiles] = useSessionField('pharm.smiles', '')
  const [include3D, setInclude3D] = useState(false)
  const [genLoading, setGenLoading] = useState(false)
  const [genResult, setGenResult] = useState<PharmGenerateResponse | null>(null)
  const [showEditor, setShowEditor] = useState(false)
  const [showModelMgmt, setShowModelMgmt] = useState(false)

  /* ── Screen panel state ── */
  const [libSource, setLibSource] = useSessionField('pharm.libSource', '')
  const [mode, setMode] = useSessionField<'2d' | '3d'>('pharm.mode', '2d')
  const [threshold, setThreshold] = useState(0.5)
  const [screenLoading, setScreenLoading] = useState(false)
  const [screenResult, setScreenResult] = useState<PharmScreenResponse | null>(null)
  const [hitPage, setHitPage] = useState(1)

  /* ── Save/Load state ── */
  const [modelName, setModelName] = useState('')
  const [saveDir, setSaveDir] = useState('')
  const [loadPath, setLoadPath] = useState('')

  const [error, setError] = useState('')

  const { sorted: sortedHits, sortKey, sortDir, requestSort, sortIndicator } = useSortableTable<PharmScreenHit, HitSortKey>(
    screenResult?.hits ?? [], 'score',
  )

  /* Keyboard shortcuts */
  useKeyboardShortcuts([
    { key: 'Enter', ctrl: true, action: handleGenerate, enabled: !genLoading && !!smiles },
  ])

  /* ────────── Handlers ────────── */

  async function handleGenerate() {
    if (!smiles.trim()) return
    setGenLoading(true)
    setError('')
    setGenResult(null)
    addLog(`Generating pharmacophore for ${smiles}…`)
    try {
      const res = await api.generatePharmacophore({ smiles, include_3d: include3D })
      setGenResult(res)
      addLog(`✓ ${res.features.length} features extracted`)
      addToast(res.message, 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Pharmacophore generation failed'
      setError(msg)
      addLog(`✗ ${msg}`)
      addToast(msg, 'error')
    } finally {
      setGenLoading(false)
    }
  }

  async function handleScreen() {
    if (!smiles.trim() || !libSource.trim()) return
    setScreenLoading(true)
    setError('')
    setScreenResult(null)
    setHitPage(1)
    addLog(`Screening library (${mode}) against ${smiles}…`)
    try {
      const res = await api.screenPharmacophore({
        reference_smiles: smiles,
        library_source: libSource,
        mode,
        threshold,
      })
      setScreenResult(res)
      addLog(`✓ ${res.hits.length} hits from ${res.total_screened} compounds`)
      addToast(res.message, 'success')
      if (res.warning) addToast(res.warning, 'warning')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Screening failed'
      setError(msg)
      addLog(`✗ ${msg}`)
      addToast(msg, 'error')
    } finally {
      setScreenLoading(false)
    }
  }

  async function handleSave() {
    if (!genResult || !modelName.trim() || !saveDir.trim()) return
    try {
      const res = await api.savePharmacophore({
        name: modelName,
        reference_smiles: genResult.smiles,
        features: genResult.features,
        output_dir: saveDir,
      })
      addToast(res.message, 'success')
      addLog(`✓ ${res.message}`)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Save failed'
      addToast(msg, 'error')
    }
  }

  async function handleLoad() {
    if (!loadPath.trim()) return
    try {
      const res = await api.loadPharmacophore(loadPath)
      setSmiles(res.reference_smiles)
      setGenResult({
        smiles: res.reference_smiles,
        features: res.features,
        svg: null,
        feature_counts: countFeatures(res.features),
        message: `Loaded model "${res.name}"`,
      })
      setModelName(res.name)
      addToast(`Loaded pharmacophore model "${res.name}"`, 'success')
      addLog(`✓ Loaded model: ${res.name}`)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Load failed'
      addToast(msg, 'error')
    }
  }

  function countFeatures(feats: PharmacophoreFeature[]): Record<string, number> {
    const counts: Record<string, number> = {}
    for (const f of feats) counts[f.type] = (counts[f.type] || 0) + 1
    return counts
  }

  /* ────────── Render ────────── */

  return (
    <PageShell
      emoji="💎"
      title="Pharmacophore Modeling"
      subtitle="Extract pharmacophore features, visualise, and screen compound libraries"
      infoTooltip="Generate pharmacophore models from a reference compound revealing key interaction features (H-bond donors/acceptors, hydrophobic regions, aromatic rings, ionizable groups). Screen libraries using 2D fingerprints or 3D alignment."
    >
      {/* ──── Generate Card ──── */}
      <div className={s.card}>
        <div className={s.cardHeader}>
          <span className={s.cardTitle}>Reference Molecule</span>
        </div>
        <div className={s.formGrid}>
          <div className={s.formGroup} style={{ gridColumn: '1 / -1' }}>
            <label className={s.label}>
              SMILES <Tooltip text="Enter or draw the SMILES of your reference compound">ⓘ</Tooltip>
            </label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                className={s.inputMono}
                value={smiles}
                onChange={e => setSmiles(e.target.value)}
                placeholder="e.g. c1ccc(cc1)C(=O)O"
                style={{ flex: 1 }}
              />
              <button className={s.btnSecondary} onClick={() => setShowEditor(true)}>✏️ Draw</button>
              <CopyButton text={smiles} />
            </div>
          </div>
          <div className={s.formGroup}>
            <label className={s.label}>
              <input type="checkbox" checked={include3D} onChange={e => setInclude3D(e.target.checked)} />
              {' '}Include 3D coordinates <Tooltip text="Generate a 3D conformer and extract spatial feature positions">ⓘ</Tooltip>
            </label>
          </div>
        </div>
        <div className={s.actions} style={{ marginTop: 16 }}>
          <Tooltip text="Extract pharmacophore features and generate SVG overlay">
            <button className={s.btnPrimary} onClick={handleGenerate} disabled={genLoading || !smiles.trim()}>
              💎 Generate Pharmacophore
            </button>
          </Tooltip>
          <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
        </div>
      </div>

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {genLoading && <TableSkeleton rows={3} cols={3} />}

      {/* ──── Pharmacophore Results ──── */}
      {genResult && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Pharmacophore Features</span>
            <span className={s.badgeGreen}>{genResult.features.length} features</span>
          </div>

          {/* SVG overlay + feature summary side by side */}
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
            {/* SVG molecule with pharmacophore highlights */}
            {genResult.svg && (
              <div
                style={{ flex: '0 0 auto', maxWidth: 460, border: '1px solid var(--border)', borderRadius: 8, overflow: 'hidden', background: 'var(--bg-card)' }}
                dangerouslySetInnerHTML={{ __html: genResult.svg }}
              />
            )}

            {/* Feature count badges */}
            <div style={{ flex: 1, minWidth: 200 }}>
              <div className={s.statsGrid} style={{ gap: 8 }}>
                {Object.entries(genResult.feature_counts).map(([type, count]) => {
                  const info = FEATURE_BADGE[type]
                  return (
                    <div key={type} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0' }}>
                      <span
                        style={{
                          width: 14,
                          height: 14,
                          borderRadius: '50%',
                          background: info?.color ?? '#888',
                          display: 'inline-block',
                          flexShrink: 0,
                        }}
                      />
                      <span style={{ fontWeight: 600 }}>{info?.label ?? type}</span>
                      <span className={s.badgeAccent}>{count}</span>
                    </div>
                  )
                })}
              </div>

              {/* Feature detail table */}
              <div className={s.tableScroll} style={{ marginTop: 12 }}>
                <table className={s.table}>
                  <thead>
                    <tr>
                      <th>Type</th>
                      <th>Atoms</th>
                      {include3D && <><th>X</th><th>Y</th><th>Z</th></>}
                    </tr>
                  </thead>
                  <tbody>
                    {genResult.features.map((f, i) => {
                      const info = FEATURE_BADGE[f.type]
                      return (
                        <tr key={i}>
                          <td>
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                              <span style={{ width: 10, height: 10, borderRadius: '50%', background: info?.color ?? '#888', display: 'inline-block' }} />
                              {f.type}
                            </span>
                          </td>
                          <td className={s.mono}>{f.atoms.join(', ')}</td>
                          {include3D && (
                            <>
                              <td className={s.mono}>{f.x?.toFixed(2) ?? '—'}</td>
                              <td className={s.mono}>{f.y?.toFixed(2) ?? '—'}</td>
                              <td className={s.mono}>{f.z?.toFixed(2) ?? '—'}</td>
                            </>
                          )}
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* ── Save / Load ── */}
          <div style={{ borderTop: '1px solid var(--border)', marginTop: 16, paddingTop: 16 }}>
            <button
              type="button"
              className={s.btnSecondary}
              onClick={() => setShowModelMgmt(!showModelMgmt)}
              style={{ fontSize: '0.78rem', padding: '6px 12px', marginBottom: showModelMgmt ? 12 : 0 }}
            >
              {showModelMgmt ? '▾' : '▸'} Save / Load Model
            </button>
            {showModelMgmt && (
              <>
              <div className={s.formGrid}>
                <div className={s.formGroup}>
                  <label className={s.label} htmlFor="pharm-model">Model Name</label>
                  <input id="pharm-model" className={s.input} value={modelName} onChange={e => setModelName(e.target.value)} placeholder="my_pharmacophore" />
                </div>
                <FilePicker label="Save Directory" value={saveDir} onChange={setSaveDir} directory placeholder="Select output folder…" />
                <div className={s.formGroup} style={{ alignSelf: 'end' }}>
                  <button className={s.btnSecondary} onClick={handleSave} disabled={!modelName || !saveDir}>
                    💾 Save Model
                  </button>
                </div>
              </div>
              <div className={s.formGrid} style={{ marginTop: 8 }}>
                <FilePicker label="Load Model (.pharm.json)" value={loadPath} onChange={setLoadPath} placeholder="Select pharmacophore JSON…" />
                <div className={s.formGroup} style={{ alignSelf: 'end' }}>
                  <button className={s.btnSecondary} onClick={handleLoad} disabled={!loadPath}>
                    📂 Load Model
                  </button>
                </div>
              </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* ──── Screening Card ──── */}
      <div className={s.card}>
        <div className={s.cardHeader}>
          <span className={s.cardTitle}>Library Screening</span>
        </div>
        <div className={s.formGrid}>
          <FilePicker
            label="Compound Library"
            value={libSource}
            onChange={setLibSource}
            placeholder="Select .smi, .sdf, or directory of .mol files…"
          />
          <div className={s.formGroup}>
            <label className={s.label}>
              Screening Mode <Tooltip text="2D uses pharmacophore fingerprints (fast). 3D uses conformer alignment (accurate but slower).">ⓘ</Tooltip>
            </label>
            <select className={s.select} value={mode} onChange={e => setMode(e.target.value as '2d' | '3d')}>
              <option value="2d">2D Fingerprint</option>
              <option value="3d">3D Alignment</option>
            </select>
          </div>
          <div className={s.formGroup}>
            <label className={s.label}>
              Similarity Threshold <Tooltip text="Minimum similarity score (0–1) to include as a hit">ⓘ</Tooltip>
            </label>
            <input
              className={s.input}
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={threshold}
              onChange={e => setThreshold(Number(e.target.value))}
            />
          </div>
        </div>
        <div className={s.actions} style={{ marginTop: 16 }}>
          <Tooltip text="Screen the library against the reference pharmacophore">
            <button
              className={s.btnOrange}
              onClick={handleScreen}
              disabled={screenLoading || !smiles.trim() || !libSource.trim()}
            >
              🔬 Screen Library
            </button>
          </Tooltip>
        </div>
      </div>

      {screenLoading && <TableSkeleton rows={5} cols={4} />}

      {/* ──── Screening Results ──── */}
      {screenResult && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Screening Results</span>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span className={s.badgeGreen}>{screenResult.hits.length} hits</span>
              <span className={s.badgeAccent}>{screenResult.total_screened} screened</span>
              <span className={s.badgeAmber}>{screenResult.mode.toUpperCase()}</span>
              <button
                className={s.btnSecondary}
                style={{ fontSize: '0.75rem', padding: '4px 10px' }}
                onClick={() => downloadCSV(
                  ['Name', 'SMILES', 'Score', 'Matched_Features'],
                  sortedHits.map(h => [h.name, h.smiles, h.score, h.matched_features]),
                  'pharmacophore_hits.csv',
                )}
              >
                📥 Export CSV
              </button>
            </div>
          </div>

          {screenResult.warning && (
            <Alert variant="warning" message={screenResult.warning} />
          )}

          {screenResult.hits.length === 0 ? (
            <EmptyState icon="🔬" title="No Hits" description="No compounds exceeded the similarity threshold. Try lowering the threshold or switching between 2D/3D screening." />
          ) : (
            <>
              <div className={s.tableScroll}>
                <table className={s.table}>
                  <thead>
                    <tr>
                      <th className={s.sortableHeader} onClick={() => requestSort('name')} aria-sort={sortKey === 'name' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                        Name<span className={s.sortIndicator}>{sortIndicator('name')}</span>
                      </th>
                      <th>SMILES</th>
                      <th className={s.sortableHeader} onClick={() => requestSort('score')} aria-sort={sortKey === 'score' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                        Score<span className={s.sortIndicator}>{sortIndicator('score')}</span>
                      </th>
                      <th className={s.sortableHeader} onClick={() => requestSort('matched_features')} aria-sort={sortKey === 'matched_features' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                        Matched<span className={s.sortIndicator}>{sortIndicator('matched_features')}</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedHits.slice((hitPage - 1) * PAGE_SIZE, hitPage * PAGE_SIZE).map((h, i) => (
                      <tr key={i}>
                        <td className={s.mono}>{h.name}</td>
                        <td className={s.mono} style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          <Tooltip text={h.smiles}><span>{h.smiles}</span></Tooltip>
                        </td>
                        <td style={{ color: h.score >= 0.7 ? 'var(--green)' : 'var(--text-secondary)' }}>
                          {h.score.toFixed(4)}
                        </td>
                        <td>
                          <span className={s.badgeAccent}>{h.matched_features}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination page={hitPage} total={screenResult.hits.length} pageSize={PAGE_SIZE} onPageChange={setHitPage} />
            </>
          )}
        </div>
      )}

      {/* ── Molecule Editor Modal ── */}
      {showEditor && (
        <MoleculeEditor
          value={smiles}
          onConfirm={(smi: string) => { setSmiles(smi); setShowEditor(false) }}
          onClose={() => setShowEditor(false)}
        />
      )}
    </PageShell>
  )
}
