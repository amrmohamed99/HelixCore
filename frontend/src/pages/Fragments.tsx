/* ================================================================
   Fragments — Fragment-Based Drug Design
   Decompose molecules, link/grow fragments, browse library
   ================================================================ */

import { useState, useEffect } from 'react'
import * as api from '@/lib/api'
import type {
  FragmentDecomposeResponse, FragmentLinkResponse, FragmentGrowResponse,
  FragmentLibraryResponse, FragmentLibraryEntry,
} from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useSessionField } from '@/hooks/useSessionField'
import { PageShell, Alert, Tooltip, MolViewer, EmptyState, Pagination, TableSkeleton, CopyButton } from '@/components/shared'
import s from '@/styles/shared.module.css'
import css from './Fragments.module.css'

type Tab = 'decompose' | 'link' | 'grow' | 'library'
const PAGE_SIZE = 20

export default function Fragments() {
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const [tab, setTab] = useState<Tab>('decompose')

  /* ── Decompose state ── */
  const [decompSmiles, setDecompSmiles] = useSessionField('frag.decompSmiles', '')
  const [decompMethod, setDecompMethod] = useSessionField('frag.decompMethod', 'brics')
  const [decompResult, setDecompResult] = useState<FragmentDecomposeResponse | null>(null)
  const [selectedFragments, setSelectedFragments] = useState<Set<string>>(new Set())

  /* ── Link state ── */
  const [linkFrags, setLinkFrags] = useSessionField('frag.linkFrags', '')
  const [linkMax, setLinkMax] = useSessionField('frag.linkMax', 50)
  const [linkResult, setLinkResult] = useState<FragmentLinkResponse | null>(null)

  /* ── Grow state ── */
  const [growCore, setGrowCore] = useSessionField('frag.growCore', '')
  const [growMax, setGrowMax] = useSessionField('frag.growMax', 50)
  const [growResult, setGrowResult] = useState<FragmentGrowResponse | null>(null)

  /* ── Library state ── */
  const [library, setLibrary] = useState<FragmentLibraryResponse | null>(null)
  const [libCategory, setLibCategory] = useState('')
  const [libPage, setLibPage] = useState(1)

  /* ── Shared state ── */
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleDecompose = async () => {
    if (!decompSmiles.trim()) return
    setLoading(true); setError(''); setDecompResult(null)
    addLog(`Decomposing fragment (${decompMethod})…`)
    try {
      const res = await api.decomposeFragment({ smiles: decompSmiles.trim(), method: decompMethod as 'brics' | 'recap' | 'murcko' })
      setDecompResult(res)
      setSelectedFragments(new Set())
      addLog(`✓ ${res.count} fragments found`)
      addToast(`${res.count} fragments found`, 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Decomposition failed'
      setError(msg); addLog(`✗ ${msg}`); addToast(msg, 'error')
    } finally { setLoading(false) }
  }

  const handleLink = async () => {
    const frags = linkFrags.split('\n').map(s => s.trim()).filter(Boolean)
    if (frags.length < 2) { setError('Need at least 2 fragments to link'); return }
    setLoading(true); setError(''); setLinkResult(null)
    addLog(`Linking ${frags.length} fragments…`)
    try {
      const res = await api.linkFragments({ fragments: frags, max_results: linkMax })
      setLinkResult(res)
      addLog(`✓ ${res.count} products`)
      addToast(`${res.count} linked products`, 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Linking failed'
      setError(msg); addLog(`✗ ${msg}`); addToast(msg, 'error')
    } finally { setLoading(false) }
  }

  const handleGrow = async () => {
    if (!growCore.trim()) return
    setLoading(true); setError(''); setGrowResult(null)
    addLog(`Growing fragment…`)
    try {
      const res = await api.growFragment({ core: growCore.trim(), max_results: growMax })
      setGrowResult(res)
      addLog(`✓ ${res.count} grown analogs`)
      addToast(`${res.count} grown analogs`, 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Growing failed'
      setError(msg); addLog(`✗ ${msg}`); addToast(msg, 'error')
    } finally { setLoading(false) }
  }

  const handleLoadLibrary = async () => {
    setLoading(true); setError('')
    try {
      const res = await api.getFragmentLibrary(libCategory || undefined)
      setLibrary(res)
      setLibPage(1)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Library load failed'
      setError(msg); addToast(msg, 'error')
    } finally { setLoading(false) }
  }

  useEffect(() => { if (tab === 'library' && !library) handleLoadLibrary() }, [tab])

  const sendToLink = () => {
    if (selectedFragments.size >= 2) {
      setLinkFrags(Array.from(selectedFragments).join('\n'))
      setTab('link')
    }
  }

  const sendToGrow = (smi: string) => {
    setGrowCore(smi)
    setTab('grow')
  }

  useKeyboardShortcuts([
    { key: 'Enter', ctrl: true, action: tab === 'decompose' ? handleDecompose : tab === 'link' ? handleLink : tab === 'grow' ? handleGrow : handleLoadLibrary, enabled: !loading },
  ])

  const toggleFragment = (smi: string) => {
    setSelectedFragments(prev => {
      const next = new Set(prev)
      next.has(smi) ? next.delete(smi) : next.add(smi)
      return next
    })
  }

  return (
    <PageShell emoji="🧪" title="Fragment-Based Drug Design" subtitle="Decompose, link, grow, and browse fragment libraries" infoTooltip="Fragment-based drug design (FBDD) identifies small molecular fragments and combines them into lead compounds. Use BRICS/RECAP decomposition to break down molecules, link fragments together, or grow a core fragment.">
      {/* ── Tab bar ── */}
      <div className={css.tabBar}>
        {([['decompose', '🔬 Decompose'], ['link', '🔗 Link'], ['grow', '🌱 Grow'], ['library', '📚 Library']] as [Tab, string][]).map(([t, label]) => (
          <button key={t} className={`${css.tab} ${tab === t ? css.tabActive : ''}`} onClick={() => setTab(t)}>{label}</button>
        ))}
      </div>

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {/* ── DECOMPOSE ── */}
      {tab === 'decompose' && (
        <>
          <div className={s.card}>
            <div className={s.cardHeader}><span className={s.cardTitle}>Decompose Molecule</span></div>
            <div className={s.formGrid}>
              <div className={s.formGroup}>
                <label className={s.label} htmlFor="frag-smiles">SMILES <Tooltip text="Enter the SMILES string of the molecule to decompose into fragments">ⓘ</Tooltip></label>
                <input id="frag-smiles" className={s.inputMono} value={decompSmiles} onChange={e => setDecompSmiles(e.target.value)} placeholder="e.g. c1ccc(NC(=O)c2ccccc2)cc1" />
              </div>
              <div className={s.formGroup}>
                <label className={s.label} htmlFor="frag-method">Method</label>
                <select id="frag-method" className={s.select} value={decompMethod} onChange={e => setDecompMethod(e.target.value)}>
                  <option value="brics">BRICS</option>
                  <option value="recap">RECAP</option>
                  <option value="murcko">Murcko Scaffold</option>
                </select>
              </div>
            </div>
            <div className={s.actions} style={{ marginTop: 16 }}>
              <button className={s.btnPrimary} onClick={handleDecompose} disabled={loading || !decompSmiles.trim()}>
                🔬 Decompose
              </button>
              {selectedFragments.size >= 2 && (
                <button className={s.btnSecondary} onClick={sendToLink}>
                  🔗 Link {selectedFragments.size} Selected
                </button>
              )}
              <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
            </div>
          </div>

          {loading && !decompResult && <TableSkeleton rows={3} cols={2} />}

          {decompResult && decompResult.fragments.length > 0 && (
            <div className={s.card}>
              <div className={s.cardHeader}>
                <span className={s.cardTitle}>Fragments</span>
                <span className={s.badgeGreen}>{decompResult.count} found</span>
              </div>
              <div className={css.fragGrid}>
                {decompResult.fragments.map((frag, i) => (
                  <div
                    key={i}
                    className={`${css.fragCard} ${selectedFragments.has(frag) ? css.fragCardSelected : ''}`}
                    onClick={() => toggleFragment(frag)}
                  >
                    <MolViewer smiles={frag} width={140} height={100} />
                    <div className={css.fragSmiles}>
                      <span className={s.mono} style={{ fontSize: '0.72rem' }}>{frag}</span>
                      <CopyButton text={frag} size="sm" />
                    </div>
                    <div className={css.fragActions}>
                      <button className={s.linkBtn} onClick={(e) => { e.stopPropagation(); sendToGrow(frag) }} title="Use as core for growing">🌱 Grow</button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {decompResult && decompResult.fragments.length === 0 && (
            <EmptyState icon="🔬" title="No Fragments" description="The molecule could not be decomposed with this method." />
          )}
        </>
      )}

      {/* ── LINK ── */}
      {tab === 'link' && (
        <>
          <div className={s.card}>
            <div className={s.cardHeader}><span className={s.cardTitle}>Link Fragments</span></div>
            <div className={s.formGrid}>
              <div className={s.formGroup} style={{ gridColumn: '1 / -1' }}>
                <label className={s.label} htmlFor="frag-link">Fragment SMILES <Tooltip text="Enter one SMILES per line (minimum 2 fragments)">ⓘ</Tooltip></label>
                <textarea
                  id="frag-link"
                  className={s.inputMono}
                  value={linkFrags}
                  onChange={e => setLinkFrags(e.target.value)}
                  placeholder={"c1ccccc1\nC1CCNCC1"}
                  rows={4}
                  style={{ resize: 'vertical' }}
                />
              </div>
              <div className={s.formGroup}>
                <label className={s.label} htmlFor="frag-linkmax">Max Products</label>
                <input id="frag-linkmax" className={s.input} type="number" min={1} max={500} value={linkMax} onChange={e => setLinkMax(Number(e.target.value))} />
              </div>
            </div>
            <div className={s.actions} style={{ marginTop: 16 }}>
              <button className={s.btnPrimary} onClick={handleLink} disabled={loading || linkFrags.split('\n').filter(l => l.trim()).length < 2}>
                🔗 Link Fragments
              </button>
              <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
            </div>
          </div>

          {loading && !linkResult && <TableSkeleton rows={3} cols={2} />}

          {linkResult && linkResult.products.length > 0 && (
            <div className={s.card}>
              <div className={s.cardHeader}>
                <span className={s.cardTitle}>Linked Products</span>
                <span className={s.badgeGreen}>{linkResult.count} products</span>
              </div>
              <div className={css.fragGrid}>
                {linkResult.products.map((prod, i) => (
                  <div key={i} className={css.fragCard}>
                    <MolViewer smiles={prod} width={140} height={100} />
                    <div className={css.fragSmiles}>
                      <span className={s.mono} style={{ fontSize: '0.72rem' }}>{prod}</span>
                      <CopyButton text={prod} size="sm" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {linkResult && linkResult.products.length === 0 && (
            <EmptyState icon="🔗" title="No Products" description="BRICS could not generate linked products from these fragments." />
          )}
        </>
      )}

      {/* ── GROW ── */}
      {tab === 'grow' && (
        <>
          <div className={s.card}>
            <div className={s.cardHeader}><span className={s.cardTitle}>Grow Fragment</span></div>
            <div className={s.formGrid}>
              <div className={s.formGroup}>
                <label className={s.label} htmlFor="frag-core">Core Fragment SMILES <Tooltip text="SMILES of the fragment to grow with common substituents">ⓘ</Tooltip></label>
                <input id="frag-core" className={s.inputMono} value={growCore} onChange={e => setGrowCore(e.target.value)} placeholder="e.g. c1ccncc1" />
              </div>
              <div className={s.formGroup}>
                <label className={s.label} htmlFor="frag-growmax">Max Results</label>
                <input id="frag-growmax" className={s.input} type="number" min={1} max={500} value={growMax} onChange={e => setGrowMax(Number(e.target.value))} />
              </div>
            </div>
            <div className={s.actions} style={{ marginTop: 16 }}>
              <button className={s.btnPrimary} onClick={handleGrow} disabled={loading || !growCore.trim()}>
                🌱 Grow Fragment
              </button>
              <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
            </div>
          </div>

          {loading && !growResult && <TableSkeleton rows={3} cols={2} />}

          {growResult && growResult.grown.length > 0 && (
            <div className={s.card}>
              <div className={s.cardHeader}>
                <span className={s.cardTitle}>Grown Analogs</span>
                <span className={s.badgeGreen}>{growResult.count} analogs</span>
              </div>
              <div className={css.fragGrid}>
                {growResult.grown.map((smi, i) => (
                  <div key={i} className={css.fragCard}>
                    <MolViewer smiles={smi} width={140} height={100} />
                    <div className={css.fragSmiles}>
                      <span className={s.mono} style={{ fontSize: '0.72rem' }}>{smi}</span>
                      <CopyButton text={smi} size="sm" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {growResult && growResult.grown.length === 0 && (
            <EmptyState icon="🌱" title="No Growth" description="Could not grow the core fragment." />
          )}
        </>
      )}

      {/* ── LIBRARY ── */}
      {tab === 'library' && (
        <>
          <div className={s.card}>
            <div className={s.cardHeader}><span className={s.cardTitle}>Fragment Library</span></div>
            <div className={s.formGrid}>
              <div className={s.formGroup}>
                <label className={s.label} htmlFor="frag-category">Category Filter</label>
                <select id="frag-category" className={s.select} value={libCategory} onChange={e => { setLibCategory(e.target.value); setLibrary(null) }}>
                  <option value="">All Categories</option>
                  {library?.categories.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className={s.formGroup} style={{ display: 'flex', alignItems: 'flex-end' }}>
                <button className={s.btnSecondary} onClick={handleLoadLibrary} disabled={loading}>
                  🔄 Refresh
                </button>
              </div>
            </div>
          </div>

          {loading && !library && <TableSkeleton rows={5} cols={4} />}

          {library && library.fragments.length > 0 && (
            <div className={s.card}>
              <div className={s.cardHeader}>
                <span className={s.cardTitle}>Library Entries</span>
                <span className={s.badgeGreen}>{library.total} fragments</span>
              </div>
              <div className={s.tableScroll}>
                <table className={s.table}>
                  <thead>
                    <tr>
                      <th>Structure</th><th>Name</th><th>SMILES</th><th>Category</th><th>MW</th><th>Ro3</th><th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {library.fragments.slice((libPage - 1) * PAGE_SIZE, libPage * PAGE_SIZE).map((entry: FragmentLibraryEntry, i: number) => (
                      <tr key={i}>
                        <td><MolViewer smiles={entry.smiles} width={80} height={60} /></td>
                        <td>{entry.name}</td>
                        <td className={s.mono} style={{ fontSize: '0.75rem' }}>{entry.smiles} <CopyButton text={entry.smiles} size="sm" /></td>
                        <td><span className={s.badgeAccent}>{entry.category}</span></td>
                        <td>{entry.mw.toFixed(1)}</td>
                        <td><span className={entry.rule_of_3 ? s.badgeGreen : s.badgeAmber}>{entry.rule_of_3 ? 'Pass' : 'Fail'}</span></td>
                        <td>
                          <button className={s.linkBtn} onClick={() => sendToGrow(entry.smiles)} title="Grow this fragment">🌱</button>
                          <button className={s.linkBtn} onClick={() => { setDecompSmiles(entry.smiles); setTab('decompose') }} title="Decompose">🔬</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination page={libPage} total={library.fragments.length} pageSize={PAGE_SIZE} onPageChange={setLibPage} />
            </div>
          )}

          {library && library.fragments.length === 0 && (
            <EmptyState icon="📚" title="Empty Library" description="No fragments found in this category." />
          )}
        </>
      )}
    </PageShell>
  )
}
