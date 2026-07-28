import Alert from './Alert'
import type { ProteinIntegrityComparison, ProteinIntegrityReport as IntegrityReport } from '@/types/api'
import s from '@/styles/shared.module.css'

interface Props {
  report?: IntegrityReport | null
  comparison?: ProteinIntegrityComparison | null
}

function ChainCounts({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts)
  if (!entries.length) return <span className={s.mono}>No chains detected</span>
  return (
    <div className={s.floatingPills}>
      {entries.map(([chain, count]) => (
        <span key={chain} className={s.pill}>Chain {chain}: {count}</span>
      ))}
    </div>
  )
}

function Metric({ label, value, tone }: { label: string; value: string | number; tone?: string }) {
  return (
    <div
      style={{
        textAlign: 'center',
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-sm)',
        padding: 14,
      }}
    >
      <strong style={{ color: tone ?? 'var(--text-primary)', fontSize: '1.25rem' }}>{value}</strong>
      <p className={s.label} style={{ marginTop: 6 }}>{label}</p>
    </div>
  )
}

export default function ProteinIntegrityReport({ report, comparison }: Props) {
  const active = comparison?.after ?? report
  if (!active) return null

  const warnings = comparison?.warnings ?? active.warnings
  const isComparison = Boolean(comparison)
  const residueDelta = comparison?.residue_delta ?? 0
  const atomDelta = comparison?.atom_delta ?? 0

  return (
    <div className={s.card}>
      <div className={s.cardHeader}>
        <span className={s.cardTitle}>Protein Integrity Check</span>
        <span className={warnings.length ? s.badgeAmber : s.badgeGreen}>
          {warnings.length ? 'Review' : 'Looks OK'}
        </span>
      </div>

      {warnings.length > 0 && (
        <Alert
          variant="warning"
          message={`Check before docking: ${warnings.join('; ')}`}
        />
      )}

      <div className={s.statsGrid} style={{ marginTop: warnings.length ? 12 : 0 }}>
        <Metric
          label={isComparison ? 'Atoms After Cleaning' : 'Atoms'}
          value={active.atom_count.toLocaleString()}
          tone="var(--accent)"
        />
        <Metric
          label={isComparison ? 'Protein Residues After Cleaning' : 'Protein Residues'}
          value={active.residue_count.toLocaleString()}
          tone="var(--green)"
        />
        <Metric
          label={isComparison ? 'Protein Residues Removed' : 'Sequence Gaps'}
          value={isComparison ? residueDelta : active.sequence_gaps.length}
          tone={(isComparison ? residueDelta : active.sequence_gaps.length) ? 'var(--amber)' : undefined}
        />
        <Metric
          label={isComparison ? 'Atoms Removed' : 'Possible CA Breaks'}
          value={isComparison ? atomDelta.toLocaleString() : active.ca_breaks.length}
          tone={(isComparison ? atomDelta : active.ca_breaks.length) ? 'var(--red)' : undefined}
        />
      </div>

      <div style={{ marginTop: 14 }}>
        <p className={s.label}>Residues Per Chain</p>
        <ChainCounts counts={active.chain_residue_counts} />
      </div>

      {(active.sequence_gaps.length > 0 || active.ca_breaks.length > 0 || active.missing_backbone.length > 0) && (
        <div className={s.tableScroll} style={{ marginTop: 14 }}>
          <table className={s.table}>
            <thead>
              <tr>
                <th>Signal</th>
                <th>Chain</th>
                <th>Location</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {active.ca_breaks.slice(0, 8).map((b, i) => (
                <tr key={`break-${i}`}>
                  <td>CA distance</td>
                  <td>{b.chain}</td>
                  <td>{b.from} -&gt; {b.to}</td>
                  <td>{b.distance} Angstrom</td>
                </tr>
              ))}
              {active.sequence_gaps.slice(0, 8).map((g, i) => (
                <tr key={`gap-${i}`}>
                  <td>Residue gap</td>
                  <td>{g.chain}</td>
                  <td>{g.from} -&gt; {g.to}</td>
                  <td>{g.missing_count} missing number(s)</td>
                </tr>
              ))}
              {active.missing_backbone.slice(0, 8).map((m, i) => (
                <tr key={`bb-${i}`}>
                  <td>Missing backbone</td>
                  <td>{m.chain}</td>
                  <td>{m.resname} {m.residue}{m.icode}</td>
                  <td>{m.missing.join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
