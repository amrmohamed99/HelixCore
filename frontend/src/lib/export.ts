/* ================================================================
   Export Utilities — client-side CSV / JSON / file download helpers
   ================================================================ */

const BASE_URL = 'http://127.0.0.1:8299'

/** Trigger a file download via an invisible <a> link. */
function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/**
 * Build a CSV string from headers + rows and download it.
 *
 * Handles escaping: values containing commas, quotes, or newlines
 * are wrapped in double quotes with inner quotes doubled.
 */
export function downloadCSV(
  headers: string[],
  rows: (string | number | boolean | null | undefined)[][],
  filename: string,
): void {
  const escape = (v: unknown): string => {
    const s = v == null ? '' : String(v)
    if (s.includes(',') || s.includes('"') || s.includes('\n')) {
      return `"${s.replace(/"/g, '""')}"`
    }
    return s
  }

  const lines = [
    headers.map(escape).join(','),
    ...rows.map((row) => row.map(escape).join(',')),
  ]
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  triggerDownload(blob, filename.endsWith('.csv') ? filename : `${filename}.csv`)
}

/**
 * Download a JSON object as a .json file.
 */
export function downloadJSON(data: unknown, filename: string): void {
  const str = JSON.stringify(data, null, 2)
  const blob = new Blob([str], { type: 'application/json' })
  triggerDownload(blob, filename.endsWith('.json') ? filename : `${filename}.json`)
}

/**
 * Download plain text content as a file.
 */
export function downloadText(content: string, filename: string): void {
  const blob = new Blob([content], { type: 'text/plain' })
  triggerDownload(blob, filename)
}

/**
 * Fetch a file from the backend and trigger a browser download.
 * Useful for server-generated SDF, PDF, or other binary files.
 */
export async function downloadFile(
  apiPath: string,
  filename: string,
  method: 'GET' | 'POST' = 'GET',
  body?: unknown,
): Promise<void> {
  const opts: RequestInit = { method }
  if (method === 'POST' && body) {
    opts.headers = { 'Content-Type': 'application/json' }
    opts.body = JSON.stringify(body)
  }

  const res = await fetch(`${BASE_URL}${apiPath}`, opts)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Download failed (${res.status})`)
  }

  const blob = await res.blob()
  triggerDownload(blob, filename)
}
