/* ================================================================
   Pagination — Page navigation for large data tables
   ================================================================ */

import pg from './Pagination.module.css'

interface Props {
  /** Current page number (1-based) */
  page: number
  /** Total number of items */
  total: number
  /** Items per page */
  pageSize: number
  /** Callback when page changes */
  onPageChange: (page: number) => void
}

export default function Pagination({ page, total, pageSize, onPageChange }: Props) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  if (totalPages <= 1) return null

  const start = (page - 1) * pageSize + 1
  const end = Math.min(page * pageSize, total)

  return (
    <div className={pg.wrapper}>
      <span className={pg.info}>
        {start}–{end} of {total}
      </span>
      <div className={pg.controls}>
        <button
          className={pg.btn}
          disabled={page <= 1}
          onClick={() => onPageChange(1)}
          title="First page"
          aria-label="Go to first page"
        >
          «
        </button>
        <button
          className={pg.btn}
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          title="Previous page"
          aria-label="Go to previous page"
        >
          ‹
        </button>
        <span className={pg.current}>
          {page} / {totalPages}
        </span>
        <button
          className={pg.btn}
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          title="Next page"
          aria-label="Go to next page"
        >
          ›
        </button>
        <button
          className={pg.btn}
          disabled={page >= totalPages}
          onClick={() => onPageChange(totalPages)}
          title="Last page"
          aria-label="Go to last page"
        >
          »
        </button>
      </div>
    </div>
  )
}
