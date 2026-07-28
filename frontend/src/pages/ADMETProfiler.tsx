/* ================================================================
   ADMET Profiler — Extended drug-likeness and ADMET properties
   ================================================================ */

import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import * as api from '@/lib/api'
import type { ADMETResponse, ADMETProfile } from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { useSortableTable } from '@/hooks/useSortableTable'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useSessionField } from '@/hooks/useSessionField'
import { PageShell, FilePicker, Alert, PathDisplay, Tooltip, MolViewer, EmptyState, Pagination, RadarChart, TableSkeleton, MoleculeEditor } from '@/components/shared'
import { downloadCSV } from '@/lib/export'
import s from '@/styles/shared.module.css'

type SortKey = keyof Pick<ADMETProfile, 'name' | 'mw' | 'logp' | 'hbd' | 'hba' | 'tpsa' | 'qed' | 'sa_score' | 'esol_logS' | 'rule_of_5'>

const PAGE_SIZE = 20

/* ---- BBB triage flag ------------------------------------------------------
   A three-threshold descriptor filter, not a trained permeability model. The
   thresholds and the per-rule verdicts come back from the API so the user can
   always see what produced the flag. ------------------------------------- */

const BBB_THRESHOLDS = 'MW < 450 Da · TPSA < 90 Å² · 0.5 ≤ LogP ≤ 4.5'

const BBB_FALLBACK_CAVEAT =
  'BBB triage flag — a three-threshold descriptor filter, not a trained blood-brain-barrier ' +
  'permeability model. Known false negatives (e.g. caffeine, which is CNS-active but falls ' +
  'below the LogP floor). Do not report it as a permeability prediction.'

/** True when the triage filter passed. Falls back to the deprecated field for older backends. */
function bbbFlag(p: ADMETProfile): boolean {
  return (p.bbb_triage?.flag ?? p.bbb_triage_flag ?? p.bbb_permeable) === true
}

/** The three rules, their descriptor values and which one decided the verdict. */
function bbbBasis(p: ADMETProfile): string {
  const criteria = p.bbb_triage?.criteria
  if (!criteria || criteria.length === 0) return BBB_THRESHOLDS
  return criteria
    .map(c => `${c.name} ${c.value ?? '—'} ${c.operator} ${c.threshold} → ${c.passed ? 'PASS' : 'FAIL'}`)
    .join(' · ')
}

function bbbCaveat(profiles: ADMETProfile[]): string {
  return profiles.find(p => p.bbb_triage?.caveat)?.bbb_triage?.caveat ?? BBB_FALLBACK_CAVEAT
}

export default function ADMETProfiler() {
  const location = useLocation()
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const [mode, setMode] = useSessionField<'smiles' | 'file'>('admet.mode', 'smiles')
  const [smiles, setSmiles] = useSessionField('admet.smiles', '')
  const [filePath, setFilePath] = useSessionField('admet.filePath', '')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ADMETResponse | null>(null)
  const [error, setError] = useState('')
  const [page, setPage] = useState(1)
  const [selectedRadar, setSelectedRadar] = useState(0)
  const [showEditor, setShowEditor] = useState(false)
  const [showRo5, setShowRo5] = useState(false)
  const [ro5Mw, setRo5Mw] = useSessionField('admet.ro5Mw', '500')
  const [ro5Logp, setRo5Logp] = useSessionField('admet.ro5Logp', '5')
  const [ro5Hbd, setRo5Hbd] = useSessionField('admet.ro5Hbd', '5')
  const [ro5Hba, setRo5Hba] = useSessionField('admet.ro5Hba', '10')
  const [ro5MaxViol, setRo5MaxViol] = useSessionField('admet.ro5MaxViol', '1')
  const { sorted, sortKey, sortDir, requestSort, sortIndicator } = useSortableTable<ADMETProfile, SortKey>(
    result?.profiles ?? [], 'name',
  )

  /* Pre-fill from Results page navigation */
  useEffect(() => {
    const st = location.state as { smiles?: string } | null
    if (st?.smiles) {
      setSmiles(st.smiles)
      setMode('smiles')
    }
  }, [location.state])

  const handleProfile = async () => {
    const ro5 = {
      mw: parseFloat(ro5Mw) || 500,
      logp: parseFloat(ro5Logp) || 5,
      hbd: parseInt(ro5Hbd) || 5,
      hba: parseInt(ro5Hba) || 10,
      max_violations: parseInt(ro5MaxViol) ?? 1,
    }
    const payload = mode === 'smiles' ? { smiles, ro5 } : { file_path: filePath, ro5 }
    if (mode === 'smiles' && !smiles) return
    if (mode === 'file' && !filePath) return
    setLoading(true)
    setError('')
    setResult(null)
    addLog(`ADMET profiling…`)

    try {
      const res = await api.profileADMET(payload)
      setResult(res)
      addLog(`✓ Profiled ${res.profiles.length} compounds`)
      addToast(`Profiled ${res.profiles.length} compounds`, 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'ADMET profiling failed'
      setError(msg)
      addLog(`✗ ADMET error: ${msg}`)
      addToast(msg, 'error')
    } finally {
      setLoading(false)
    }
  }

  useKeyboardShortcuts([{ key: 'Enter', ctrl: true, action: handleProfile, enabled: !loading && (mode === 'smiles' ? !!smiles : !!filePath) }])

  return (
    <>
    <PageShell emoji="💊" title="ADMET Profiler" subtitle="QED, SA Score, ESOL solubility, BBB triage flag, Bertz complexity & Lipinski Ro5" infoTooltip="Calculate extended drug-likeness and ADMET properties including QED, Synthetic Accessibility, ESOL solubility, the BBB triage flag (a three-threshold descriptor filter, not a trained permeability model), and Lipinski Rule of Five for single compounds or batches." helpUrl="https://en.wikipedia.org/wiki/Lipinski%27s_rule_of_five">

      <div className={s.card}>
        <div className={s.cardHeader}><span className={s.cardTitle}>Input Mode</span></div>
        <div className={s.actions} style={{ marginBottom: 12 }}>
          <button className={mode === 'smiles' ? s.btnPrimary : s.btnSecondary} onClick={() => setMode('smiles')}>Single SMILES</button>
          <button className={mode === 'file' ? s.btnPrimary : s.btnSecondary} onClick={() => setMode('file')}>File / Directory</button>
        </div>

        {mode === 'smiles' ? (
          <div className={s.formGroup}>
            <label className={s.label} htmlFor="admet-smiles">Molecule Input <Tooltip text="Enter a SMILES string, InChI, compound name (e.g. aspirin), or CAS number (e.g. 50-78-2)">ⓘ</Tooltip></label>
            <input id="admet-smiles" className={s.inputMono} value={smiles} onChange={(e) => setSmiles(e.target.value)} placeholder="SMILES, InChI, compound name, or CAS number" />
            <button className={s.btnSecondary} style={{ marginTop: 4, fontSize: '0.75rem' }} onClick={() => setShowEditor(true)}>✏️ Draw Molecule</button>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: 4 }}>Supports: SMILES · InChI · compound name · CAS number · MOL block</span>
          </div>
        ) : (
          <FilePicker label="SMILES File or Directory" value={filePath} onChange={setFilePath} filters={[{ name: 'SMILES', extensions: ['smi', 'txt'] }]} placeholder="Select file or directory…" />
        )}

        <div style={{ marginTop: 12 }}>
          <button className={s.btnSecondary} style={{ fontSize: '0.75rem', padding: '4px 10px' }} onClick={() => setShowRo5(!showRo5)}>
            {showRo5 ? '▾' : '▸'} Ro5 Thresholds
          </button>
          {showRo5 && (
            <div className={s.formGrid} style={{ marginTop: 8 }}>
              <div className={s.formGroup}>
                <label className={s.label} htmlFor="admet-mw">MW Limit <Tooltip text="Maximum molecular weight (default: 500 Da)">ⓘ</Tooltip></label>
                <input id="admet-mw" className={s.inputMono} type="number" min={100} max={2000} step={10} value={ro5Mw} onChange={e => setRo5Mw(e.target.value)} />
              </div>
              <div className={s.formGroup}>
                <label className={s.label} htmlFor="admet-logp">LogP Limit <Tooltip text="Maximum partition coefficient (default: 5)">ⓘ</Tooltip></label>
                <input id="admet-logp" className={s.inputMono} type="number" min={-2} max={15} step={0.5} value={ro5Logp} onChange={e => setRo5Logp(e.target.value)} />
              </div>
              <div className={s.formGroup}>
                <label className={s.label} htmlFor="admet-hbd">HBD Limit <Tooltip text="Maximum hydrogen bond donors (default: 5)">ⓘ</Tooltip></label>
                <input id="admet-hbd" className={s.inputMono} type="number" min={0} max={20} step={1} value={ro5Hbd} onChange={e => setRo5Hbd(e.target.value)} />
              </div>
              <div className={s.formGroup}>
                <label className={s.label} htmlFor="admet-hba">HBA Limit <Tooltip text="Maximum hydrogen bond acceptors (default: 10)">ⓘ</Tooltip></label>
                <input id="admet-hba" className={s.inputMono} type="number" min={0} max={30} step={1} value={ro5Hba} onChange={e => setRo5Hba(e.target.value)} />
              </div>
              <div className={s.formGroup}>
                <label className={s.label} htmlFor="admet-viol">Max Violations <Tooltip text="Maximum allowed Ro5 violations to pass (default: 1)">ⓘ</Tooltip></label>
                <input id="admet-viol" className={s.inputMono} type="number" min={0} max={4} step={1} value={ro5MaxViol} onChange={e => setRo5MaxViol(e.target.value)} />
              </div>
            </div>
          )}
        </div>

        <div className={s.actions} style={{ marginTop: 16 }}>
          <button className={s.btnPrimary} onClick={handleProfile} disabled={loading || (mode === 'smiles' ? !smiles : !filePath)}>
            {loading ? <><span className={s.spinnerSmall} /> Profiling…</> : '💊 Run ADMET Profile'}
          </button>
          <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
        </div>
      </div>

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {loading && !result && <TableSkeleton rows={5} cols={12} />}

      {result && result.profiles.length === 0 && (
        <EmptyState icon="💊" title="No Profiles" description="Provide a directory of SDF/MOL files or paste SMILES to calculate ADMET properties. Use output from Batch Generate or Minimization." />
      )}

      {result && result.profiles.length > 0 && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>ADMET Profiles</span>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span className={s.badgeGreen}>{result.profiles.length} compounds</span>
              <button className={s.btnSecondary} style={{ fontSize: '0.75rem', padding: '4px 10px' }} onClick={() => downloadCSV(
                ['Name', 'SMILES', 'MW', 'LogP', 'HBD', 'HBA', 'TPSA', 'QED', 'SA_Score', 'ESOL_LogS', 'BBB_Triage_Flag', 'BBB_Triage_Basis', 'Rule_of_5'],
                result.profiles.map(p => [p.name, p.smiles ?? '', p.mw ?? '', p.logp ?? '', p.hbd ?? '', p.hba ?? '', p.tpsa ?? '', p.qed ?? '', p.sa_score ?? '', p.esol_logS ?? '', bbbFlag(p) ? 'Pass' : 'Fail', bbbBasis(p), p.rule_of_5]),
                'admet_profiles.csv'
              )}>📥 Export CSV</button>
            </div>
          </div>
          <div className={s.tableScroll}>
            <table className={s.table}>
              <thead>
                <tr>
                  <th className={s.sortableHeader} onClick={() => requestSort('name')} aria-sort={sortKey === 'name' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Name<span className={s.sortIndicator}>{sortIndicator('name')}</span></th>
                  <th style={{ width: 120 }}>Structure</th>
                  <th className={s.sortableHeader} onClick={() => requestSort('mw')} aria-sort={sortKey === 'mw' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>MW (Da)<span className={s.sortIndicator}>{sortIndicator('mw')}</span></th>
                  <th className={s.sortableHeader} onClick={() => requestSort('logp')} aria-sort={sortKey === 'logp' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>LogP<span className={s.sortIndicator}>{sortIndicator('logp')}</span></th>
                  <th className={s.sortableHeader} onClick={() => requestSort('hbd')} aria-sort={sortKey === 'hbd' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>HBD<span className={s.sortIndicator}>{sortIndicator('hbd')}</span></th>
                  <th className={s.sortableHeader} onClick={() => requestSort('hba')} aria-sort={sortKey === 'hba' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>HBA<span className={s.sortIndicator}>{sortIndicator('hba')}</span></th>
                  <th className={s.sortableHeader} onClick={() => requestSort('tpsa')} aria-sort={sortKey === 'tpsa' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>TPSA (Å²)<span className={s.sortIndicator}>{sortIndicator('tpsa')}</span></th>
                  <th className={s.sortableHeader} onClick={() => requestSort('qed')} aria-sort={sortKey === 'qed' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>QED<span className={s.sortIndicator}>{sortIndicator('qed')}</span></th>
                  <th className={s.sortableHeader} onClick={() => requestSort('sa_score')} aria-sort={sortKey === 'sa_score' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>SA<span className={s.sortIndicator}>{sortIndicator('sa_score')}</span></th>
                  <th className={s.sortableHeader} onClick={() => requestSort('esol_logS')} aria-sort={sortKey === 'esol_logS' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>ESOL<span className={s.sortIndicator}>{sortIndicator('esol_logS')}</span></th>
                  <th>BBB Triage <Tooltip text={`Three-threshold descriptor filter: ${BBB_THRESHOLDS}. Not a trained permeability model — hover a verdict to see which rule decided it.`}>ⓘ</Tooltip></th><th>Ro5</th>
                </tr>
              </thead>
              <tbody>
                {sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).map((p, i) => (
                  <tr key={i}>
                    <td className={s.mono}>{p.name}</td>
                    <td>{p.smiles && <MolViewer smiles={p.smiles} width={110} height={90} />}</td>
                    <td>{p.mw?.toFixed(1) ?? '—'}</td>
                    <td>{p.logp?.toFixed(2) ?? '—'}</td>
                    <td>{p.hbd ?? '—'}</td>
                    <td>{p.hba ?? '—'}</td>
                    <td>{p.tpsa?.toFixed(1) ?? '—'}</td>
                    <td style={{ color: (p.qed ?? 0) >= 0.6 ? 'var(--green)' : 'var(--amber)' }}>
                      {p.qed?.toFixed(3) ?? '—'}
                    </td>
                    <td style={{ color: (p.sa_score ?? 5) <= 4 ? 'var(--green)' : 'var(--amber)' }}>
                      {p.sa_score?.toFixed(1) ?? '—'}
                    </td>
                    <td>{p.esol_logS?.toFixed(2) ?? '—'}</td>
                    <td>
                      <Tooltip text={bbbBasis(p)}>
                        <span className={bbbFlag(p) ? s.badgeGreen : s.badgeAmber}>
                          {bbbFlag(p) ? 'Pass' : 'Fail'}
                        </span>
                      </Tooltip>
                    </td>
                    <td>
                      <span className={p.rule_of_5.startsWith('PASS') ? s.badgeGreen : s.badgeRose}>
                        {p.rule_of_5}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} total={result.profiles.length} pageSize={PAGE_SIZE} onPageChange={setPage} />
          <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: 8, lineHeight: 1.5 }}>
            <strong>BBB Triage</strong> applies three descriptor thresholds — {BBB_THRESHOLDS} — and
            passes only compounds satisfying all three. {bbbCaveat(result.profiles)}
          </p>
          {result.csv_path && <PathDisplay label="CSV Saved" path={result.csv_path} />}
        </div>
      )}

      {result && result.profiles.length > 0 && (() => {
        const prof = result.profiles[selectedRadar] ?? result.profiles[0]
        if (!prof) return null
        const axes = [
          { label: 'MW', value: prof.mw ?? 0, max: parseFloat(ro5Mw) || 500 },
          { label: 'LogP', value: prof.logp ?? 0, max: parseFloat(ro5Logp) || 5 },
          { label: 'HBD', value: prof.hbd ?? 0, max: parseInt(ro5Hbd) || 5 },
          { label: 'HBA', value: prof.hba ?? 0, max: parseInt(ro5Hba) || 10 },
          { label: 'TPSA', value: prof.tpsa ?? 0, max: 140 },
          { label: 'QED', value: prof.qed ?? 0, max: 1 },
          { label: 'SA', value: prof.sa_score ?? 0, max: 10 },
        ]
        return (
          <div className={s.card}>
            <div className={s.cardHeader}>
              <span className={s.cardTitle}>Drug-Likeness Radar</span>
              {result.profiles.length > 1 && (
                <select className={s.select} style={{ width: 'auto' }} value={selectedRadar} onChange={e => setSelectedRadar(Number(e.target.value))}>
                  {result.profiles.map((p, i) => <option key={i} value={i}>{p.name}</option>)}
                </select>
              )}
            </div>
            <RadarChart axes={axes} title={prof.name} />
          </div>
        )
      })()}
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
