/* ================================================================
   RadarChart — Pure SVG radar / spider chart for ADMET properties
   ================================================================ */

import rc from './RadarChart.module.css'

interface RadarAxis {
  label: string
  value: number
  /** Maximum possible value for this axis (for normalization) */
  max: number
}

interface RadarChartProps {
  axes: RadarAxis[]
  /** Chart diameter in px */
  size?: number
  /** Chart title */
  title?: string
  /** Fill color */
  color?: string
}

export default function RadarChart({
  axes,
  size = 280,
  title,
  color = 'var(--accent)',
}: RadarChartProps) {
  if (axes.length < 3) return null

  const cx = size / 2
  const cy = size / 2
  const r = size / 2 - 40
  const n = axes.length
  const angleStep = (2 * Math.PI) / n

  const getPoint = (index: number, ratio: number) => {
    const angle = index * angleStep - Math.PI / 2
    return {
      x: cx + r * ratio * Math.cos(angle),
      y: cy + r * ratio * Math.sin(angle),
    }
  }

  /* Grid rings at 25%, 50%, 75%, 100% */
  const rings = [0.25, 0.5, 0.75, 1.0]

  /* Data polygon */
  const dataPoints = axes.map((a, i) => {
    const ratio = Math.min(a.value / a.max, 1)
    return getPoint(i, ratio)
  })
  const dataPath = dataPoints.map((p, i) => (i === 0 ? `M${p.x},${p.y}` : `L${p.x},${p.y}`)).join(' ') + 'Z'

  return (
    <div className={rc.wrapper}>
      {title && <div className={rc.title}>{title}</div>}
      <svg viewBox={`0 0 ${size} ${size}`} className={rc.svg}>
        {/* Grid rings */}
        {rings.map((ratio) => (
          <polygon
            key={ratio}
            points={Array.from({ length: n }, (_, i) => {
              const p = getPoint(i, ratio)
              return `${p.x},${p.y}`
            }).join(' ')}
            className={rc.ring}
          />
        ))}

        {/* Axis lines */}
        {axes.map((_, i) => {
          const p = getPoint(i, 1)
          return <line key={i} x1={cx} y1={cy} x2={p.x} y2={p.y} className={rc.axis} />
        })}

        {/* Data polygon */}
        <polygon points={dataPath.replace(/[MLZ]/g, ' ').trim()} className={rc.data} style={{ fill: color, stroke: color }} />

        {/* Data dots */}
        {dataPoints.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={3} className={rc.dot} style={{ fill: color }} />
        ))}

        {/* Axis labels */}
        {axes.map((a, i) => {
          const p = getPoint(i, 1.22)
          return (
            <text key={i} x={p.x} y={p.y} className={rc.label} textAnchor="middle" dominantBaseline="middle">
              {a.label}
            </text>
          )
        })}
      </svg>
    </div>
  )
}
