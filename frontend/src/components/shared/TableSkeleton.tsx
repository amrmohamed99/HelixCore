/* ================================================================
   TableSkeleton — Placeholder rows while a table result is loading
   ================================================================ */

import Skeleton from './Skeleton'
import s from '@/styles/shared.module.css'

interface Props {
  /** Number of placeholder rows */
  rows?: number
  /** Number of columns */
  cols?: number
}

export default function TableSkeleton({ rows = 5, cols = 4 }: Props) {
  return (
    <div className={s.tableScroll}>
      <table className={s.table}>
        <thead>
          <tr>
            {Array.from({ length: cols }, (_, c) => (
              <th key={c}><Skeleton width="60%" height="0.9em" /></th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }, (_, r) => (
            <tr key={r}>
              {Array.from({ length: cols }, (_, c) => (
                <td key={c}><Skeleton width={`${50 + Math.random() * 30}%`} height="0.9em" /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
