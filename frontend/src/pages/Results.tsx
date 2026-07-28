/* ================================================================
   Results — Explore, rank, and export docking results
   ================================================================ */

import { useState, useEffect, useMemo } from 'react'
import * as api from '@/lib/api'
import type { LoadResultsResponse, CSVReportResponse, ConsensusResponse, PoseDecompResponse, Candidate, CSVRow } from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { usePipelineStep } from '@/hooks/usePipelineStep'
import { useWorkspace } from '@/hooks/useWorkspace'
import { useSortableTable } from '@/hooks/useSortableTable'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { PageShell, FilePicker, Alert, PathDisplay, ScoreChart, HistogramChart, Tooltip, Pagination, EmptyState, TableSkeleton, ReportDialog } from '@/components/shared'
import { downloadCSV } from '@/lib/export'
import s from '@/styles/shared.module.css'

type CandSortKey = 'name' | 'score'
type CSVSortKey = 'rank' | 'ligand' | 'score' | 'mw' | 'logp' | 'rule_of_5'
const PAGE_SIZE = 20

export default function Results() {
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const { markRunning, markDone, markError } = usePipelineStep('results')
  const { paths, ready } = useWorkspace()
  const [resultsDir, setResultsDir] = useState('')
  const [srcDir, setSrcDir] = useState('')
  const [topN, setTopN] = useState(10)
  const [loading, setLoading] = useState(false)
  const [candidates, setCandidates] = useState<LoadResultsResponse | null>(null)
  const [csvReport, setCsvReport] = useState<CSVReportResponse | null>(null)
  const [consensus, setConsensus] = useState<ConsensusResponse | null>(null)
  const [decomp, setDecomp] = useState<PoseDecompResponse | null>(null)
  const [error, setError] = useState('')
  const [candPage, setCandPage] = useState(1)
  const [csvPage, setCsvPage] = useState(1)

  /* Affinity range filter state */
  const [affinityMin, setAffinityMin] = useState('')
  const [affinityMax, setAffinityMax] = useState('')
  const [useTopN, setUseTopN] = useState(true)
  const [activeBinRange, setActiveBinRange] = useState<[number, number] | null>(null)

  /* Report dialog state */
  const [showReport, setShowReport] = useState(false)

  /** Candidates filtered by affinity range, then optionally capped to topN */
  const filteredCandidates = useMemo(() => {
    if (!candidates) return []
    let list = [...candidates.candidates]
    const lo = affinityMin !== '' ? parseFloat(affinityMin) : null
    const hi = affinityMax !== '' ? parseFloat(affinityMax) : null
    if (lo != null && !isNaN(lo)) list = list.filter(c => c.score >= lo)
    if (hi != null && !isNaN(hi)) list = list.filter(c => c.score <= hi)
    list.sort((a, b) => a.score - b.score)
    if (useTopN) list = list.slice(0, topN)
    return list
  }, [candidates, affinityMin, affinityMax, useTopN, topN])

  const allScores = useMemo(
    () => (candidates?.candidates ?? []).map(c => c.score),
    [candidates],
  )

  const { sorted: sortedCand, sortKey: candSortKey, sortDir: candSortDir, requestSort: reqCandSort, sortIndicator: candSortInd } = useSortableTable<Candidate, CandSortKey>(
    filteredCandidates, 'score',
  )
  const { sorted: sortedCSV, sortKey: csvSortKey, sortDir: csvSortDir, requestSort: reqCSVSort, sortIndicator: csvSortInd } = useSortableTable<CSVRow, CSVSortKey>(
    csvReport?.rows ?? [], 'rank',
  )

  useEffect(() => {
    if (ready) {
      if (!resultsDir) setResultsDir(paths.dockingResults)
      if (!srcDir) setSrcDir(paths.convertedPdbqt)
    }
  }, [ready])

  const handleLoad = async () => {
    if (!resultsDir) return
    markRunning()
    setLoading(true)
    setError('')
    setCandidates(null)
    setCsvReport(null)
    addLog(`Loading results from ${resultsDir}…`)

    try {
      const res = await api.loadResults(resultsDir)
      setCandidates(res)
      addLog(`✓ Loaded ${res.candidates.length} candidates`)
      addToast(`Loaded ${res.candidates.length} candidates`, 'success')
      markDone()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Load failed'
      setError(msg)
      addLog(`✗ Results error: ${msg}`)
      addToast(msg, 'error')
      markError()
    } finally {
      setLoading(false)
    }
  }

  const handleGenerateCSV = async () => {
    if (!resultsDir) return
    setError('')
    setLoading(true)
    addLog(`Generating CSV report…`)

    try {
      const res = await api.generateCSVReport({
        res_dir: resultsDir,
        src_dir: srcDir || undefined,
        top_n: topN,
      })
      setCsvReport(res)
      addLog(`✓ CSV report generated: ${res.rows.length} entries`)
      addToast(`CSV report generated: ${res.rows.length} entries`, 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'CSV generation failed'
      setError(msg)
      addLog(`✗ CSV error: ${msg}`)
      addToast(msg, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleExportTop = async () => {
    if (!resultsDir || !srcDir) return
    setError('')
    setLoading(true)
    addLog(`Exporting top ${topN} results…`)
    try {
      const res = await api.exportTop({ top_n: topN, src_dir: srcDir, results_dir: resultsDir })
      addLog(`✓ Exported ${res.exported} files to ${res.output_dir}`)
      if (res.missing?.length) addLog(`⚠ Missing original ligand files: ${res.missing.join(', ')}`)
      addToast(`Exported ${res.exported}/${res.total ?? topN} docked hits`, 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Export failed'
      setError(msg)
      addLog(`✗ Export error: ${msg}`)
      addToast(msg, 'error')
    } finally {
      setLoading(false)
    }
  }

  useKeyboardShortcuts([{ key: 'Enter', ctrl: true, action: handleLoad, enabled: !loading && !!resultsDir }])

  return (
    <PageShell emoji="📋" title="Results Explorer" subtitle="Browse, rank, and export docking candidates with ADMET properties" infoTooltip="Browse, rank, and export your docking candidates. Generate CSV reports with ADMET properties and use consensus scoring to combine multiple ranking metrics for robust hit selection." helpUrl="https://autodock-vina.readthedocs.io/en/latest/docking_basic.html#output">
      <div className={s.card}>
        <div className={s.cardHeader}><span className={s.cardTitle}>Configuration</span></div>
        <div className={s.formGrid}>
          <FilePicker label="Results Directory" value={resultsDir} onChange={setResultsDir} directory placeholder="Select results folder…" />
          <FilePicker label="Source Directory (for export)" value={srcDir} onChange={setSrcDir} directory placeholder="Optional source folder" />
          <div className={s.formGroup}>
            <label className={s.label} htmlFor="res-topn">Top N <Tooltip text="Number of top-scoring compounds to include in exports and CSV reports">ⓘ</Tooltip></label>
            <input id="res-topn" className={s.input} type="number" min={1} max={100} value={topN} onChange={(e) => setTopN(Number(e.target.value))} />
          </div>
        </div>
        <div className={s.actions} style={{ marginTop: 16 }}>
          <Tooltip text="Parse all docking output files and display ranked candidates"><button className={s.btnPrimary} onClick={handleLoad} disabled={loading || !resultsDir}>
            📋 Load Results
          </button></Tooltip>
          <Tooltip text="Create a CSV report with scores and ADMET properties"><button className={s.btnSecondary} onClick={handleGenerateCSV} disabled={loading || !resultsDir}>
            📊 Generate CSV
          </button></Tooltip>
          <Tooltip text="Copy the top-scoring ligand files to a separate folder"><button className={s.btnSecondary} onClick={handleExportTop} disabled={loading || !resultsDir || !srcDir}>
            📦 Export Top {topN}
          </button></Tooltip>
          <Tooltip text="Combine Vina score, MMFF energy, and contact score into a unified consensus ranking"><button
            className={s.btnOrange}
            onClick={async () => {
              setLoading(true)
              try {
                const res = await api.consensusScore({ results_dir: resultsDir, src_dir: srcDir || undefined })
                setConsensus(res)
                addLog(`✓ Consensus scoring: ${res.results.length} compounds ranked`)
                addToast(`${res.results.length} compounds consensus-ranked`, 'success')
              } catch (err: unknown) {
                const msg = err instanceof Error ? err.message : 'Consensus scoring failed'
                setError(msg)
              } finally {
                setLoading(false)
              }
            }}
            disabled={loading || !resultsDir}
          >
            🏆 Consensus Rank
          </button></Tooltip>
          <Tooltip text="Generate a PDF or HTML report from the loaded results"><button className={s.btnSecondary} onClick={() => setShowReport(true)} disabled={loading || !resultsDir}>
            📄 Report
          </button></Tooltip>
          <span className={s.kbdHint}><kbd className={s.kbd}>Ctrl</kbd>+<kbd className={s.kbd}>Enter</kbd></span>
        </div>
      </div>

      <ReportDialog open={showReport} onClose={() => setShowReport(false)} resultsDir={resultsDir || undefined} />

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {loading && !candidates && <TableSkeleton rows={5} cols={3} />}

      {candidates && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Candidates</span>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span className={s.badgeGreen}>{candidates.candidates.length} found</span>
              {filteredCandidates.length !== candidates.candidates.length && (
                <span className={s.badgeAmber}>{filteredCandidates.length} shown</span>
              )}
              <button className={s.btnSecondary} style={{ fontSize: '0.75rem', padding: '4px 10px' }} onClick={() => downloadCSV(
                ['Name', 'Score_kcal_mol'],
                filteredCandidates.map(c => [c.name, c.score]),
                'docking_candidates.csv'
              )}>📥 Export CSV</button>
            </div>
          </div>

          {/* ── Affinity Range Filter ── */}
          <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap', padding: '8px 0' }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <label className={s.label} htmlFor="res-affmin" style={{ margin: 0, minWidth: 'auto' }}>Affinity Range</label>
              <input
                id="res-affmin"
                className={s.inputMono}
                type="number"
                step="0.1"
                placeholder="Min"
                value={affinityMin}
                onChange={e => { setAffinityMin(e.target.value); setCandPage(1) }}
                style={{ width: 80 }}
              />
              <span style={{ color: 'var(--text-muted)' }}>→</span>
              <input
                className={s.inputMono}
                type="number"
                step="0.1"
                placeholder="Max"
                value={affinityMax}
                onChange={e => { setAffinityMax(e.target.value); setCandPage(1) }}
                style={{ width: 80 }}
              />
              <span className={s.label} style={{ margin: 0, minWidth: 'auto' }}>kcal/mol</span>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <Tooltip text={useTopN ? `Showing top ${topN} from filtered range` : 'Showing all compounds in range'}>
                <button
                  className={useTopN ? s.btnPrimary : s.btnSecondary}
                  style={{ fontSize: '0.75rem', padding: '4px 10px' }}
                  onClick={() => setUseTopN(v => !v)}
                >
                  {useTopN ? `Top ${topN}` : 'All in Range'}
                </button>
              </Tooltip>
              {(affinityMin !== '' || affinityMax !== '' || activeBinRange) && (
                <button
                  className={s.btnSecondary}
                  style={{ fontSize: '0.75rem', padding: '4px 10px' }}
                  onClick={() => { setAffinityMin(''); setAffinityMax(''); setActiveBinRange(null); setCandPage(1) }}
                >
                  ✕ Clear
                </button>
              )}
            </div>
          </div>

          {candidates.candidates.length === 0 ? (
            <EmptyState icon="📋" title="No Candidates" description="Select the docking results directory to load scored candidates. Run the Docking step first if you haven't yet." />
          ) : (
            <>
            {/* ── Charts side-by-side ── */}
            <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
              <HistogramChart
                data={allScores}
                title="Score Distribution"
                unit="kcal/mol"
                activeRange={activeBinRange}
                highlightRange={affinityMin !== '' || affinityMax !== '' ? [
                  affinityMin !== '' ? parseFloat(affinityMin) : -Infinity,
                  affinityMax !== '' ? parseFloat(affinityMax) : Infinity,
                ] : undefined}
                onBinClick={(min, max) => {
                  if (activeBinRange && Math.abs(activeBinRange[0] - min) < 0.01 && Math.abs(activeBinRange[1] - max) < 0.01) {
                    setActiveBinRange(null)
                    setAffinityMin('')
                    setAffinityMax('')
                  } else {
                    setActiveBinRange([min, max])
                    setAffinityMin(min.toFixed(2))
                    setAffinityMax(max.toFixed(2))
                  }
                  setCandPage(1)
                }}
              />
              <ScoreChart
                data={filteredCandidates
                  .slice(0, 15)
                  .map((c) => ({ label: c.name, value: c.score }))}
                title="Top Binding Affinities"
                unit="kcal/mol"
                highlightBelow={-6}
                lowerIsBetter
              />
            </div>

            {/* ── Candidates Table ── */}
            <div className={s.tableScroll}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th className={s.sortableHeader} onClick={() => reqCandSort('name')} aria-sort={candSortKey === 'name' ? (candSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Name<span className={s.sortIndicator}>{candSortInd('name')}</span></th>
                    <th className={s.sortableHeader} onClick={() => reqCandSort('score')} aria-sort={candSortKey === 'score' ? (candSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Score (kcal/mol)<span className={s.sortIndicator}>{candSortInd('score')}</span></th>
                  </tr>
                </thead>
                <tbody>
                  {sortedCand.slice((candPage - 1) * PAGE_SIZE, candPage * PAGE_SIZE).map((c, i) => (
                      <tr key={i}>
                        <td className={s.mono}>{c.name}</td>
                        <td style={{ color: c.score < -6 ? 'var(--green)' : 'var(--text-secondary)' }}>
                          {c.score.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            <Pagination page={candPage} total={filteredCandidates.length} pageSize={PAGE_SIZE} onPageChange={setCandPage} />
            </>
          )}
        </div>
      )}

      {csvReport && csvReport.rows.length > 0 && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>CSV Report</span>
            <span className={s.badgeAccent}>{csvReport.rows.length} entries</span>
          </div>
          <div className={s.tableScroll}>
            <table className={s.table}>
              <thead>
                <tr>
                  <th className={s.sortableHeader} onClick={() => reqCSVSort('rank')} aria-sort={csvSortKey === 'rank' ? (csvSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Rank<span className={s.sortIndicator}>{csvSortInd('rank')}</span></th>
                  <th className={s.sortableHeader} onClick={() => reqCSVSort('ligand')} aria-sort={csvSortKey === 'ligand' ? (csvSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Ligand<span className={s.sortIndicator}>{csvSortInd('ligand')}</span></th>
                  <th className={s.sortableHeader} onClick={() => reqCSVSort('score')} aria-sort={csvSortKey === 'score' ? (csvSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Score<span className={s.sortIndicator}>{csvSortInd('score')}</span></th>
                  <th className={s.sortableHeader} onClick={() => reqCSVSort('mw')} aria-sort={csvSortKey === 'mw' ? (csvSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>MW<span className={s.sortIndicator}>{csvSortInd('mw')}</span></th>
                  <th className={s.sortableHeader} onClick={() => reqCSVSort('logp')} aria-sort={csvSortKey === 'logp' ? (csvSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>LogP<span className={s.sortIndicator}>{csvSortInd('logp')}</span></th>
                  <th>HBD</th><th>HBA</th><th>TPSA</th>
                  <th className={s.sortableHeader} onClick={() => reqCSVSort('rule_of_5')} aria-sort={csvSortKey === 'rule_of_5' ? (csvSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}>Ro5<span className={s.sortIndicator}>{csvSortInd('rule_of_5')}</span></th>
                </tr>
              </thead>
              <tbody>
                {sortedCSV.slice((csvPage - 1) * PAGE_SIZE, csvPage * PAGE_SIZE).map((row) => (
                  <tr key={row.rank}>
                    <td>{row.rank}</td>
                    <td className={s.mono}>{row.ligand}</td>
                    <td>{row.score.toFixed(2)}</td>
                    <td>{row.mw?.toFixed(1) ?? '—'}</td>
                    <td>{row.logp?.toFixed(2) ?? '—'}</td>
                    <td>{row.hbd ?? '—'}</td>
                    <td>{row.hba ?? '—'}</td>
                    <td>{row.tpsa?.toFixed(1) ?? '—'}</td>
                    <td>
                      <span className={row.rule_of_5 === 'Pass' ? s.badgeGreen : row.rule_of_5 === 'Fail' ? s.badgeRose : s.badgeAmber}>
                        {row.rule_of_5}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={csvPage} total={csvReport.rows.length} pageSize={PAGE_SIZE} onPageChange={setCsvPage} />
          {csvReport.csv_path && (
            <PathDisplay label="CSV Saved" path={csvReport.csv_path ?? ''} />
          )}
        </div>
      )}

      {/* Consensus Scoring Results */}
      {consensus && consensus.results.length > 0 && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Consensus Ranking</span>
            <span className={s.badgeAccent}>{consensus.results.length} compounds</span>
          </div>
          <div className={s.tableScroll}>
            <table className={s.table}>
              <thead>
                <tr>
                  <th>Consensus #</th><th>Ligand</th><th>Vina Score</th><th>Vina Rank</th>
                  <th>MMFF Energy</th><th>Energy Rank</th><th>Contact</th><th>Contact Rank</th>
                </tr>
              </thead>
              <tbody>
                {consensus.results
                  .sort((a, b) => (a.consensus_rank ?? 999) - (b.consensus_rank ?? 999))
                  .map((r, i) => (
                    <tr key={i}>
                      <td><span className={s.badgeGreen}>#{r.consensus_rank ?? '—'}</span></td>
                      <td className={s.mono}>{r.ligand}</td>
                      <td>{r.vina_score?.toFixed(2) ?? '—'}</td>
                      <td>{r.vina_rank ?? '—'}</td>
                      <td>{r.mmff_energy?.toFixed(1) ?? '—'}</td>
                      <td>{r.energy_rank ?? '—'}</td>
                      <td>{r.contact_score?.toFixed(2) ?? '—'}</td>
                      <td>{r.contact_rank ?? '—'}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          {consensus.csv_path && <PathDisplay label="Consensus CSV" path={consensus.csv_path} />}
        </div>
      )}

      {/* Pose Decomposition */}
      {decomp && (
        <div className={s.card}>
          <div className={s.cardHeader}>
            <span className={s.cardTitle}>Pose Energy Decomposition</span>
            <span className={s.badgeAccent}>{decomp.ligand}</span>
          </div>
          <div className={s.formGrid}>
            <div className={s.formGroup}>
              <span className={s.label}>Total Score <Tooltip text="Sum of all Vina energy components for this docked pose">ⓘ</Tooltip></span>
              <strong className={s.mono}>{decomp.total_score?.toFixed(2) ?? '—'} kcal/mol</strong>
            </div>
          </div>
          <div className={s.tableScroll}>
            <table className={s.table}>
              <thead><tr><th>Component</th><th>Value</th></tr></thead>
              <tbody>
                {decomp.components.map((c, i) => (
                  <tr key={i}>
                    <td>{c.component}</td>
                    <td className={s.mono}>{c.value.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

    </PageShell>
  )
}
