/* ================================================================
   useSortableTable — generic client-side column sorting for tables
   ================================================================ */

import { useState, useMemo, useCallback } from 'react'

export type SortDir = 'asc' | 'desc'

interface SortState<K extends string> {
  key: K
  dir: SortDir
}

/**
 * Provides column-based sorting for any array of objects.
 *
 * @param data - The raw data array.
 * @param defaultKey - Initial sort column key.
 * @param defaultDir - Initial sort direction.
 */
export function useSortableTable<T, K extends string>(
  data: T[],
  defaultKey: K,
  defaultDir: SortDir = 'asc',
) {
  const [sort, setSort] = useState<SortState<K>>({ key: defaultKey, dir: defaultDir })

  const requestSort = useCallback(
    (key: K) => {
      setSort((prev) =>
        prev.key === key
          ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
          : { key, dir: 'asc' },
      )
    },
    [],
  )

  const sorted = useMemo(() => {
    const copy = [...data]
    copy.sort((a, b) => {
      const av = (a as Record<string, unknown>)[sort.key]
      const bv = (b as Record<string, unknown>)[sort.key]

      if (av == null && bv == null) return 0
      if (av == null) return 1
      if (bv == null) return -1

      let cmp: number
      if (typeof av === 'number' && typeof bv === 'number') {
        cmp = av - bv
      } else {
        cmp = String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: 'base' })
      }

      return sort.dir === 'asc' ? cmp : -cmp
    })
    return copy
  }, [data, sort.key, sort.dir])

  /** Render a sortable column header indicator */
  const sortIndicator = useCallback(
    (key: K): string => {
      if (sort.key !== key) return ' ↕'
      return sort.dir === 'asc' ? ' ▲' : ' ▼'
    },
    [sort.key, sort.dir],
  )

  return {
    sorted,
    sortKey: sort.key,
    sortDir: sort.dir,
    requestSort,
    sortIndicator,
  }
}
