/* ================================================================
   MoleculeEditor — modal SMILES editor with live 2D preview,
   common templates, and name resolution
   ================================================================ */

import { useState, useCallback, useRef, useEffect } from 'react'
import MolViewer from './MolViewer'
import s from '@/styles/shared.module.css'

const BASE = 'http://127.0.0.1:8299'

interface MoleculeEditorProps {
  /** Current SMILES value */
  value: string
  /** Called when the user confirms a SMILES selection */
  onConfirm: (smiles: string) => void
  /** Called when the modal is closed without confirming */
  onClose: () => void
}

/* ---- Common molecular templates ---- */
const TEMPLATES = [
  { label: 'Benzene', smiles: 'c1ccccc1' },
  { label: 'Cyclohexane', smiles: 'C1CCCCC1' },
  { label: 'Pyridine', smiles: 'c1ccncc1' },
  { label: 'Pyrimidine', smiles: 'c1ccnc(n1)' },
  { label: 'Imidazole', smiles: 'c1cn[nH]c1' },
  { label: 'Piperidine', smiles: 'C1CCNCC1' },
  { label: 'Morpholine', smiles: 'C1COCCN1' },
  { label: 'Indole', smiles: 'c1ccc2[nH]ccc2c1' },
  { label: 'Naphthalene', smiles: 'c1ccc2ccccc2c1' },
  { label: 'Phenol', smiles: 'Oc1ccccc1' },
  { label: 'Aniline', smiles: 'Nc1ccccc1' },
  { label: 'Benzoic Acid', smiles: 'OC(=O)c1ccccc1' },
  { label: 'Acetamide', smiles: 'CC(N)=O' },
  { label: 'Ethanol', smiles: 'CCO' },
  { label: 'Acetic Acid', smiles: 'CC(O)=O' },
  { label: 'Sulfonamide', smiles: 'NS(=O)=O' },
]

const COMMON_DRUGS = [
  { label: 'Aspirin', smiles: 'CC(=O)Oc1ccccc1C(O)=O' },
  { label: 'Ibuprofen', smiles: 'CC(C)Cc1ccc(cc1)C(C)C(O)=O' },
  { label: 'Caffeine', smiles: 'Cn1c(=O)c2c(ncn2C)n(C)c1=O' },
  { label: 'Paracetamol', smiles: 'CC(=O)Nc1ccc(O)cc1' },
  { label: 'Metformin', smiles: 'CN(C)C(=N)NC(N)=N' },
  { label: 'Benzamidine', smiles: 'NC(=N)c1ccccc1' },
]

export default function MoleculeEditor({ value, onConfirm, onClose }: MoleculeEditorProps) {
  const [smiles, setSmiles] = useState(value || '')
  const [nameQuery, setNameQuery] = useState('')
  const [resolving, setResolving] = useState(false)
  const [resolveError, setResolveError] = useState('')
  const [activeTab, setActiveTab] = useState<'edit' | 'templates' | 'drugs'>('edit')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  /* ---- Resolve name → SMILES via backend ---- */
  const handleResolve = useCallback(async () => {
    if (!nameQuery.trim()) return
    setResolving(true)
    setResolveError('')
    try {
      const res = await fetch(`${BASE}/api/resolve/molecule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input: nameQuery.trim() }),
      })
      if (!res.ok) throw new Error('Resolution failed')
      const data = await res.json()
      if (data.smiles) {
        setSmiles(data.smiles)
        setResolveError('')
      } else {
        setResolveError('Could not resolve to SMILES')
      }
    } catch {
      setResolveError('Resolution failed — check compound name')
    } finally {
      setResolving(false)
    }
  }, [nameQuery])

  /* ---- Insert template at cursor / append ---- */
  const insertSmiles = useCallback((smi: string) => {
    setSmiles(prev => (prev ? prev + '.' + smi : smi))
  }, [])

  return (
    <div
      role="dialog"
      aria-labelledby="mol-editor-title"
      aria-modal="true"
      style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
    }} onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div style={{
        background: 'var(--surface-1)',
        border: '1px solid var(--border)',
        borderRadius: 12,
        width: 680,
        maxWidth: '95vw',
        maxHeight: '90vh',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '0 20px 60px rgba(0,0,0,0.4)',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 20px', borderBottom: '1px solid var(--border)',
        }}>
          <span id="mol-editor-title" style={{ fontWeight: 700, fontSize: '1rem' }}>✏️ Molecule Editor</span>
          <button
            onClick={onClose}
            aria-label="Close editor"
            style={{
              background: 'none', border: 'none', color: 'var(--text-secondary)',
              fontSize: '1.2rem', cursor: 'pointer', padding: '4px 8px',
            }}
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div style={{ padding: '16px 20px', overflowY: 'auto', flex: 1 }}>
          {/* Tabs */}
          <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
            {(['edit', 'templates', 'drugs'] as const).map(tab => (
              <button
                key={tab}
                className={tab === activeTab ? s.btnPrimary : s.btnSecondary}
                style={{ fontSize: '0.78rem', padding: '5px 12px' }}
                onClick={() => setActiveTab(tab)}
              >
                {tab === 'edit' ? '✏️ Edit' : tab === 'templates' ? '🧩 Scaffolds' : '💊 Drugs'}
              </button>
            ))}
          </div>

          {activeTab === 'edit' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* SMILES input */}
              <div>
                <label className={s.label} htmlFor="moled-smiles" style={{ marginBottom: 4 }}>SMILES</label>
                <input
                  id="moled-smiles"
                  ref={inputRef}
                  className={s.inputMono}
                  value={smiles}
                  onChange={e => setSmiles(e.target.value)}
                  placeholder="Enter SMILES string…"
                  style={{ width: '100%' }}
                  onKeyDown={e => { if (e.key === 'Enter' && e.ctrlKey && smiles) onConfirm(smiles) }}
                />
              </div>

              {/* Name resolver */}
              <div>
                <label className={s.label} htmlFor="moled-name" style={{ marginBottom: 4 }}>
                  Resolve by Name <span style={{ opacity: 0.5, fontSize: '0.7rem' }}>(compound name, CAS, InChI)</span>
                </label>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    id="moled-name"
                    className={s.input}
                    value={nameQuery}
                    onChange={e => setNameQuery(e.target.value)}
                    placeholder="e.g. aspirin, caffeine, 50-78-2"
                    style={{ flex: 1 }}
                    onKeyDown={e => { if (e.key === 'Enter') handleResolve() }}
                  />
                  <button
                    className={s.btnSecondary}
                    onClick={handleResolve}
                    disabled={resolving || !nameQuery.trim()}
                    style={{ whiteSpace: 'nowrap' }}
                  >
                    {resolving ? '…' : '🔍 Resolve'}
                  </button>
                </div>
                {resolveError && (
                  <span style={{ color: 'var(--red)', fontSize: '0.75rem', marginTop: 4, display: 'block' }}>
                    {resolveError}
                  </span>
                )}
              </div>

              {/* Quick edit buttons */}
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <span className={s.label} style={{ width: '100%', marginBottom: 2 }}>Quick Add</span>
                {[
                  { l: '—OH', s: 'O' },
                  { l: '—NH₂', s: 'N' },
                  { l: '—COOH', s: 'C(=O)O' },
                  { l: '—CH₃', s: 'C' },
                  { l: '—F', s: 'F' },
                  { l: '—Cl', s: 'Cl' },
                  { l: '—Br', s: 'Br' },
                  { l: '=O', s: '=O' },
                  { l: '—CN', s: 'C#N' },
                  { l: '—NO₂', s: '[N+](=O)[O-]' },
                ].map(fg => (
                  <button
                    key={fg.l}
                    className={s.btnSecondary}
                    style={{ fontSize: '0.72rem', padding: '3px 8px' }}
                    onClick={() => setSmiles(prev => prev + fg.s)}
                    title={`Append ${fg.l} (${fg.s})`}
                  >
                    {fg.l}
                  </button>
                ))}
                <button
                  className={s.btnDanger}
                  style={{ fontSize: '0.72rem', padding: '3px 8px', marginLeft: 'auto' }}
                  onClick={() => setSmiles('')}
                >
                  Clear
                </button>
              </div>
            </div>
          )}

          {activeTab === 'templates' && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 8 }}>
              {TEMPLATES.map(t => (
                <button
                  key={t.label}
                  className={s.card}
                  style={{
                    cursor: 'pointer', textAlign: 'center', padding: '10px 8px',
                    border: smiles === t.smiles ? '2px solid var(--accent)' : undefined,
                    transition: 'border-color 0.2s',
                  }}
                  onClick={() => insertSmiles(t.smiles)}
                >
                  <MolViewer smiles={t.smiles} width={100} height={70} />
                  <span style={{ fontSize: '0.72rem', fontWeight: 500, marginTop: 4, display: 'block' }}>
                    {t.label}
                  </span>
                  <span style={{ fontSize: '0.65rem', opacity: 0.5, fontFamily: 'var(--font-mono)' }}>
                    {t.smiles}
                  </span>
                </button>
              ))}
            </div>
          )}

          {activeTab === 'drugs' && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 8 }}>
              {COMMON_DRUGS.map(d => (
                <button
                  key={d.label}
                  className={s.card}
                  style={{
                    cursor: 'pointer', textAlign: 'center', padding: '10px 8px',
                    border: smiles === d.smiles ? '2px solid var(--accent)' : undefined,
                    transition: 'border-color 0.2s',
                  }}
                  onClick={() => setSmiles(d.smiles)}
                >
                  <MolViewer smiles={d.smiles} width={130} height={90} />
                  <span style={{ fontSize: '0.78rem', fontWeight: 600, marginTop: 4, display: 'block' }}>
                    {d.label}
                  </span>
                </button>
              ))}
            </div>
          )}

          {/* Live preview */}
          {smiles && (
            <div style={{
              marginTop: 16, padding: 12,
              background: 'var(--bg-secondary)', borderRadius: 8,
              display: 'flex', alignItems: 'center', gap: 16,
            }}>
              <MolViewer smiles={smiles} width={180} height={140} />
              <div style={{ flex: 1 }}>
                <span className={s.label}>Preview</span>
                <p style={{
                  fontFamily: 'var(--font-mono)', fontSize: '0.8rem',
                  wordBreak: 'break-all', color: 'var(--text-primary)', marginTop: 4,
                }}>
                  {smiles}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          display: 'flex', justifyContent: 'flex-end', gap: 8,
          padding: '12px 20px', borderTop: '1px solid var(--border)',
        }}>
          <button className={s.btnSecondary} onClick={onClose}>Cancel</button>
          <button
            className={s.btnPrimary}
            onClick={() => onConfirm(smiles)}
            disabled={!smiles.trim()}
          >
            ✓ Use This SMILES
          </button>
        </div>
      </div>
    </div>
  )
}
