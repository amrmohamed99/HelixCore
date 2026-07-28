/* ================================================================
   generateReport — Build an HTML pipeline report for download
   ================================================================ */

import type { StepStatus, PipelineStep } from '@/context/AppContext'

interface ReportInput {
  steps: Record<PipelineStep, StepStatus>
  appVersion?: string
}

const STEP_LABELS: Record<PipelineStep, string> = {
  fetch: 'Fetch PDB',
  pocket: 'Pocket Analysis',
  batch: 'Batch Generate',
  minimize: 'Minimization',
  convert: 'Convert to PDBQT',
  docking: 'Molecular Docking',
  oracle: 'Oracle AI',
  results: 'Results Explorer',
}

const STATUS_COLORS: Record<StepStatus, string> = {
  ready: '#64748b',
  running: '#d97706',
  done: '#34d399',
  error: '#f43f5e',
}

export function generateReport({ steps, appVersion = '3.0' }: ReportInput): string {
  const now = new Date()
  const timestamp = now.toLocaleString()
  const total = Object.keys(steps).length
  const completed = Object.values(steps).filter((s) => s === 'done').length
  const errored = Object.values(steps).filter((s) => s === 'error').length

  const stepRows = (Object.entries(steps) as [PipelineStep, StepStatus][])
    .map(
      ([key, status]) => `
      <tr>
        <td style="padding:8px 12px;border-bottom:1px solid #1e293b">${STEP_LABELS[key]}</td>
        <td style="padding:8px 12px;border-bottom:1px solid #1e293b">
          <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${STATUS_COLORS[status]};margin-right:8px;vertical-align:middle"></span>
          ${status.charAt(0).toUpperCase() + status.slice(1)}
        </td>
      </tr>`
    )
    .join('')

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Helix Core — Pipeline Report</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{background:#0f1117;color:#e2e8f0;font-family:'Segoe UI',-apple-system,sans-serif;padding:40px}
  .header{text-align:center;margin-bottom:40px}
  .header h1{font-size:28px;background:linear-gradient(90deg,#e2e8f0,#3385ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:4px}
  .header p{color:#64748b;font-size:13px}
  .summary{display:flex;gap:16px;justify-content:center;margin-bottom:32px}
  .stat{background:#1a1f2e;border:1px solid #1e293b;border-radius:10px;padding:16px 32px;text-align:center}
  .stat .num{font-size:28px;font-weight:700;color:#3385ff}
  .stat .lbl{font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-top:4px}
  table{width:100%;max-width:600px;margin:0 auto;border-collapse:collapse;background:#1a1f2e;border-radius:10px;overflow:hidden}
  thead th{background:#151821;padding:10px 12px;text-align:left;font-size:12px;color:#64748b;text-transform:uppercase;letter-spacing:1px}
  tbody td{font-size:13px}
  .footer{text-align:center;margin-top:32px;color:#334155;font-size:11px}
</style>
</head>
<body>
  <div class="header">
    <h1>🧬 Helix Core Pipeline Report</h1>
    <p>Generated ${timestamp} — v${appVersion}</p>
  </div>
  <div class="summary">
    <div class="stat"><div class="num">${completed}/${total}</div><div class="lbl">Steps Completed</div></div>
    <div class="stat"><div class="num">${errored}</div><div class="lbl">Errors</div></div>
  </div>
  <table>
    <thead><tr><th>Pipeline Step</th><th>Status</th></tr></thead>
    <tbody>${stepRows}</tbody>
  </table>
  <div class="footer">Helix Core Drug Discovery Suite — Report Export</div>
</body>
</html>`
}

/** Trigger an HTML report download in the browser */
export function downloadReport(input: ReportInput): void {
  const html = generateReport(input)
  const blob = new Blob([html], { type: 'text/html' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `helix-pipeline-report-${Date.now()}.html`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
