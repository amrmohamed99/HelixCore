import type { ProcessingFailure } from '@/types/api'
import s from '@/styles/shared.module.css'

interface FailureDetailsProps {
  failures?: ProcessingFailure[]
}

export default function FailureDetails({ failures = [] }: FailureDetailsProps) {
  if (failures.length === 0) return null

  return (
    <div className={s.card} style={{ marginTop: 16 }}>
      <div className={s.cardHeader}>
        <span className={s.cardTitle}>Failure Details</span>
        <span className={s.badgeRose}>{failures.length} retained</span>
      </div>
      <div className={s.tableScroll}>
        <table className={s.table}>
          <thead>
            <tr>
              <th>Item</th>
              <th>Reason</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {failures.map((failure, index) => (
              <tr key={`${failure.item}-${failure.reason}-${index}`}>
                <td className={s.mono}>{failure.item}</td>
                <td><span className={s.badgeRose}>{failure.reason}</span></td>
                <td>{failure.detail || 'No additional detail'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
