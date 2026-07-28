/* ================================================================
   Sparkline — Inline SVG mini-chart for score trends
   ================================================================ */

interface SparklineProps {
  /** Array of numeric values to chart */
  data: number[]
  width?: number
  height?: number
  /** Stroke color */
  color?: string
  /** Fill below the line */
  filled?: boolean
}

export default function Sparkline({ data, width = 80, height = 24, color = 'var(--accent)', filled = true }: SparklineProps) {
  if (!data.length) return null

  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const pad = 2

  const points = data.map((v, i) => {
    const x = pad + (i / Math.max(data.length - 1, 1)) * (width - pad * 2)
    const y = height - pad - ((v - min) / range) * (height - pad * 2)
    return `${x},${y}`
  })

  const linePath = `M ${points.join(' L ')}`
  const fillPath = `${linePath} L ${width - pad},${height - pad} L ${pad},${height - pad} Z`

  return (
    <svg width={width} height={height} style={{ display: 'inline-block', verticalAlign: 'middle' }}>
      {filled && (
        <path d={fillPath} fill={color} fillOpacity={0.15} />
      )}
      <path d={linePath} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
      {/* Dot on last point */}
      {data.length > 1 && (
        <circle
          cx={parseFloat(points[points.length - 1].split(',')[0])}
          cy={parseFloat(points[points.length - 1].split(',')[1])}
          r={2}
          fill={color}
        />
      )}
    </svg>
  )
}
