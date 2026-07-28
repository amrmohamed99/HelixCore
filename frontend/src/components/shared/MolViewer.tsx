/* ================================================================
   MolViewer — 2D molecule structure preview via RDKit SVG
   ================================================================ */

import { useState, useEffect } from 'react'
import ms from './MolViewer.module.css'

const BASE = 'http://127.0.0.1:8299'

interface MolViewerProps {
  /** SMILES string to render */
  smiles: string
  /** SVG width in px */
  width?: number
  /** SVG height in px */
  height?: number
  /** Optional label below the structure */
  label?: string
}

export default function MolViewer({ smiles, width = 250, height = 200, label }: MolViewerProps) {
  const [svg, setSvg] = useState<string | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!smiles) { setSvg(null); return }

    let cancelled = false
    setError(false)
    setSvg(null)

    const encoded = encodeURIComponent(smiles)
    fetch(`${BASE}/api/system/mol-svg?smiles=${encoded}&width=${width}&height=${height}`)
      .then((res) => {
        if (!res.ok) throw new Error('SVG fetch failed')
        return res.text()
      })
      .then((text) => { if (!cancelled) setSvg(text) })
      .catch(() => { if (!cancelled) setError(true) })

    return () => { cancelled = true }
  }, [smiles, width, height])

  if (!smiles) return null

  return (
    <div className={ms.wrapper} style={{ width, minHeight: height }}>
      {svg ? (
        <div className={ms.svgContainer} dangerouslySetInnerHTML={{ __html: svg }} />
      ) : error ? (
        <div className={ms.fallback}>⚠️ Cannot render</div>
      ) : (
        <div className={ms.fallback}>Loading…</div>
      )}
      {label && <span className={ms.label}>{label}</span>}
    </div>
  )
}
