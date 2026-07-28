/* ================================================================
   Compare Compounds — side-by-side property comparison
   ================================================================ */

import { useState } from 'react'
import * as api from '@/lib/api'
import type { CompareResponse } from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useSessionField } from '@/hooks/useSessionField'
import { downloadCSV } from '@/lib/export'
import { PageShell, Alert, Tooltip, EmptyState, MoleculeEditor } from '@/components/shared'
import s from '@/styles/shared.module.css'

const PROPERTY_LABELS: Record<string, { label: string; unit?: string; tooltip: string }> = {
  mw: { label: 'Molecular Weight', unit: 'Da', tooltip: 'Exact molecular weight in Daltons' },
  logp: { label: 'LogP', tooltip: 'Octanol-water partition coefficient (lipophilicity)' },
  hbd: { label: 'H-Bond Donors', tooltip: 'Number of hydrogen bond donors' },
  hba: { label: 'H-Bond Acceptors', tooltip: 'Number of hydrogen bond acceptors' },
  tpsa: { label: 'TPSA', unit: 'Å²', tooltip: 'Topological polar surface area' },
  rotatable_bonds: { label: 'Rotatable Bonds', tooltip: 'Number of rotatable bonds' },
  rings: { label: 'Ring Count', tooltip: 'Total number of rings' },
  heavy_atoms: { label: 'Heavy Atoms', tooltip: 'Number of non-hydrogen atoms' },
  qed: { label: 'QED', tooltip: 'Quantitative Estimate of Druglikeness (0–1, higher is better)' },
  rule_of_5: { label: "Lipinski's Ro5", tooltip: "Rule of Five compliance (≤1 violation = Pass)" },
  ro5_violations: { label: 'Ro5 Violations', tooltip: 'Number of Lipinski Rule of Five violations' },
}

const PROPERTY_ORDER = ['mw', 'logp', 'hbd', 'hba', 'tpsa', 'rotatable_bonds', 'rings', 'heavy_atoms', 'qed', 'rule_of_5', 'ro5_violations']

function getBarPercent(value: number, min: number, max: number): number {
  if (max === min) return 50
  return Math.round(((value - min) / (max - min)) * 100)
}

function getPropertyColor(key: string, value: number, limits: Record<string, number>): string {
  const limit = limits[key]
  if (limit === undefined) return 'var(--accent)'
  if (value > limit) return 'var(--amber)'
  return 'var(--green)'
}

export default function CompareCompounds() {
  const { addLog } = useKernel()
  const { addToast } = useToast()

  const [smilesInput, setSmilesInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<CompareResponse | null>(null)
  const [error, setError] = useState('')
  const [showEditor, setShowEditor] = useState(false)
  const [showRo5, setShowRo5] = useState(false)
  const [ro5Mw, setRo5Mw] = useSessionField('compare.ro5Mw', '500')
  const [ro5Logp, setRo5Logp] = useSessionField('compare.ro5Logp', '5')
  const [ro5Hbd, setRo5Hbd] = useSessionField('compare.ro5Hbd', '5')
  const [ro5Hba, setRo5Hba] = useSessionField('compare.ro5Hba', '10')
  const [ro5MaxViol, setRo5MaxViol] = useSessionField('compare.ro5MaxViol', '1')

  const upperLimits: Record<string, number> = {
    mw: parseFloat(ro5Mw) || 500,
    logp: parseFloat(ro5Logp) || 5,
    hbd: parseInt(ro5Hbd) || 5,
    hba: parseInt(ro5Hba) || 10,
    tpsa: 140,
    rotatable_bonds: 10,
  }

  const parseSmilesInput = (): { smiles: string[]; names: string[] } => {
    const lines = smilesInput.trim().split('\n').filter(l => l.trim())
    const smiles: string[] = []
    const names: string[] = []
    for (const line of lines) {
      const parts = line.trim().split(/\s+/)
      smiles.push(parts[0])
      names.push(parts.length > 1 ? parts.slice(1).join(' ') : `Compound_${smiles.length}`)
    }
    return { smiles, names }
  }

  const handleCompare = async () => {
    const { smiles, names } = parseSmilesInput()
    if (smiles.length < 2) {
      setError('Enter at least 2 SMILES (one per line)')
      return
    }
    setLoading(true)
    setError('')
    setResult(null)
    addLog(`Comparing ${smiles.length} compounds…`)

    try {
      const res = await api.compareCompounds({
        smiles_list: smiles,
        names,
        ro5_mw: parseFloat(ro5Mw) || 500,
        ro5_logp: parseFloat(ro5Logp) || 5,
        ro5_hbd: parseInt(ro5Hbd) || 5,
        ro5_hba: parseInt(ro5Hba) || 10,
        ro5_max_violations: parseInt(ro5MaxViol) ?? 1,
      })
      setResult(res)
      addLog(`✓ Compared ${res.compounds.length} compounds`)
      addToast(`Compared ${res.compounds.length} compounds`, 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Comparison failed'
      setError(msg)
      addLog(`✗ Compare error: ${msg}`)
      addToast(msg, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleExport = () => {
    if (!result) return
    downloadCSV(
      ['Name', 'SMILES', 'MW', 'LogP', 'HBD', 'HBA', 'TPSA', 'Rotatable_Bonds', 'Rings', 'Heavy_Atoms', 'QED', 'Rule_of_5', 'Ro5_Violations'],
      result.compounds.map(c => [c.name, c.smiles, c.mw, c.logp, c.hbd, c.hba, c.tpsa, c.rotatable_bonds, c.rings, c.heavy_atoms, c.qed, c.rule_of_5, c.ro5_violations]),
      'compound_comparison.csv',
    )
  }

  useKeyboardShortcuts([
    { key: 'Enter', ctrl: true, action: handleCompare, enabled: !loading && smilesInput.trim().length > 0 },
  ])

  return (
    <>
    <PageShell
      emoji="⚖️"
      title="Compare Compounds"
      subtitle="Side-by-side molecular property comparison"
      infoTooltip="Enter 2–20 SMILES strings to compute and compare their physicochemical properties side-by-side."
    >
      {/* Input */}
      <div className={s.card}>
        <div className={s.cardHeader}>
          <span className={s.cardTitle}>SMILES Input</span>
          <Tooltip text="One SMILES per line. Optionally add a name after a space: 'CCO Ethanol'">ⓘ</Tooltip>
          <button
            className={s.btnSecondary}
            style={{ fontSize: '0.72rem', padding: '4px 10px' }}
            onClick={() => setShowEditor(true)}
          >
            ✏️ Draw
          </button>
        </div>
        <textarea
          className={s.input}
          style={{ minHeight: 120, fontFamily: 'var(--font-mono)', fontSize: '0.82rem', resize: 'vertical' }}
          value={smilesInput}
          onChange={e => setSmilesInput(e.target.value)}
          placeholder={`CCO Ethanol\nc1ccccc1 Benzene\nCC(=O)Oc1ccccc1C(O)=O Aspirin`}
        />
        <div style={{ marginTop: 12 }}>
          <button className={s.btnSecondary} style={{ fontSize: '0.75rem', padding: '4px 10px' }} onClick={() => setShowRo5(!showRo5)}>
            {showRo5 ? '▾' : '▸'} Ro5 Thresholds
          </button>
          {showRo5 && (
            <div className={s.formGrid} style={{ marginTop: 8 }}>
              <div className={s.formGroup}>
                <label className={s.label} htmlFor="cmp-mw">MW Limit <Tooltip text="Maximum molecular weight (default: 500 Da)">ⓘ</Tooltip></label>
                <input id="cmp-mw" className={s.inputMono} type="number" min={100} max={2000} step={10} value={ro5Mw} onChange={e => setRo5Mw(e.target.value)} />
              </div>
              <div className={s.formGroup}>
                <label className={s.label} htmlFor="cmp-logp">LogP Limit <Tooltip text="Maximum partition coefficient (default: 5)">ⓘ</Tooltip></label>
                <input id="cmp-logp" className={s.inputMono} type="number" min={-2} max={15} step={0.5} value={ro5Logp} onChange={e => setRo5Logp(e.target.value)} />
              </div>
              <div className={s.formGroup}>
                <label className={s.label} htmlFor="cmp-hbd">HBD Limit <Tooltip text="Maximum hydrogen bond donors (default: 5)">ⓘ</Tooltip></label>
                <input id="cmp-hbd" className={s.inputMono} type="number" min={0} max={20} step={1} value={ro5Hbd} onChange={e => setRo5Hbd(e.target.value)} />
              </div>
              <div className={s.formGroup}>
                <label className={s.label} htmlFor="cmp-hba">HBA Limit <Tooltip text="Maximum hydrogen bond acceptors (default: 10)">ⓘ</Tooltip></label>
                <input id="cmp-hba" className={s.inputMono} type="number" min={0} max={30} step={1} value={ro5Hba} onChange={e => setRo5Hba(e.target.value)} />
              </div>
              <div className={s.formGroup}>
                <label className={s.label} htmlFor="cmp-viol">Max Violations <Tooltip text="Maximum allowed Ro5 violations to pass (default: 1)">ⓘ</Tooltip></label>
                <input id="cmp-viol" className={s.inputMono} type="number" min={0} max={4} step={1} value={ro5MaxViol} onChange={e => setRo5MaxViol(e.target.value)} />
              </div>
            </div>
          )}
        </div>
        <div className={s.actions} style={{ marginTop: 12 }}>
          <button className={s.btnPrimary} onClick={handleCompare} disabled={loading || !smilesInput.trim()}>
            {loading ? <><span className={s.spinnerSmall} /> Comparing…</> : '⚖️ Compare'}
          </button>
          <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
        </div>
      </div>

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {!result && !loading && !error && (
        <EmptyState
          icon="⚖️"
          title="No Comparison Yet"
          description="Enter SMILES for 2 or more compounds to see their properties side by side."
        />
      )}

      {/* Comparison Table */}
      {result && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Property Comparison</span>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span className={s.badgeGreen}>{result.compounds.length} compounds</span>
              <button
                className={s.btnSecondary}
                style={{ fontSize: '0.75rem', padding: '4px 10px' }}
                onClick={handleExport}
              >
                📥 Export CSV
              </button>
            </div>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table className={s.table} style={{ minWidth: result.compounds.length * 140 + 180 }}>
              <thead>
                <tr>
                  <th style={{ minWidth: 160, position: 'sticky', left: 0, background: 'var(--bg-secondary)', zIndex: 1 }}>
                    Property
                  </th>
                  {result.compounds.map((c, i) => (
                    <th key={i} style={{ minWidth: 130, textAlign: 'center' }}>
                      <div style={{ fontWeight: 700, fontSize: '0.85rem' }}>{c.name}</div>
                      <div style={{ fontSize: '0.7rem', opacity: 0.6, fontFamily: 'var(--font-mono)', wordBreak: 'break-all', maxWidth: 130 }}>
                        {c.smiles.length > 30 ? c.smiles.slice(0, 27) + '…' : c.smiles}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {PROPERTY_ORDER.map(key => {
                  const info = PROPERTY_LABELS[key]
                  if (!info) return null
                  const ranges = result.property_ranges[key]
                  return (
                    <tr key={key}>
                      <td style={{ position: 'sticky', left: 0, background: 'var(--surface-1)', zIndex: 1, fontWeight: 500, fontSize: '0.82rem' }}>
                        <Tooltip text={info.tooltip}>
                          {info.label}{info.unit && <span style={{ opacity: 0.5, fontSize: '0.7rem' }}> ({info.unit})</span>}
                        </Tooltip>
                      </td>
                      {result.compounds.map((c, i) => {
                        const val = c[key as keyof typeof c]
                        const numVal = typeof val === 'number' ? val : null
                        const isRo5 = key === 'rule_of_5'
                        return (
                          <td key={i} style={{ textAlign: 'center', position: 'relative' }}>
                            {isRo5 ? (
                              <span
                                className={val === 'Pass' ? s.badgeGreen : s.badgeAmber}
                                style={{ fontSize: '0.75rem' }}
                              >
                                {String(val)}
                              </span>
                            ) : numVal !== null && ranges ? (
                              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
                                <span style={{
                                  fontFamily: 'var(--font-mono)',
                                  fontSize: '0.85rem',
                                  fontWeight: 600,
                                  color: getPropertyColor(key, numVal, upperLimits),
                                }}>
                                  {numVal}
                                </span>
                                <div style={{
                                  width: '80%',
                                  height: 4,
                                  background: 'var(--bg-secondary)',
                                  borderRadius: 2,
                                  overflow: 'hidden',
                                }}>
                                  <div style={{
                                    width: `${getBarPercent(numVal, ranges.min, ranges.max)}%`,
                                    height: '100%',
                                    background: getPropertyColor(key, numVal, upperLimits),
                                    borderRadius: 2,
                                    transition: 'width 0.3s',
                                  }} />
                                </div>
                              </div>
                            ) : (
                              <span style={{ opacity: 0.4 }}>{val != null ? String(val) : '—'}</span>
                            )}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Range summary */}
          <div style={{ marginTop: 16, padding: '12px 16px', background: 'var(--bg-secondary)', borderRadius: 8, fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
            <strong>Range Summary</strong> — {Object.entries(result.property_ranges).map(([key, r]) => {
              const info = PROPERTY_LABELS[key]
              return info ? `${info.label}: ${r.min}–${r.max} (avg ${r.mean})` : null
            }).filter(Boolean).join(' · ')}
          </div>
        </div>
      )}
    </PageShell>
    {showEditor && (
      <MoleculeEditor
        value=""
        onConfirm={(smi) => {
          setSmilesInput(prev => prev ? prev + '\n' + smi : smi)
          setShowEditor(false)
        }}
        onClose={() => setShowEditor(false)}
      />
    )}
    </>
  )
}
