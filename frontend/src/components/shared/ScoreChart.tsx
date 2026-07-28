/* ================================================================
   ScoreChart — Horizontal bar chart for docking / prediction scores
   No external dependencies — pure SVG rendering
   ================================================================ */

import cs from './ScoreChart.module.css'

interface ScoreEntry {
  label: string
  value: number
}

interface ScoreChartProps {
  data: ScoreEntry[]
  /** Chart title */
  title?: string
  /** Unit label for the axis (e.g. "kcal/mol") */
  unit?: string
  /** Max bars to display */
  maxBars?: number
  /** Color for bars (CSS variable or hex). Defaults to accent. */
  barColor?: string
  /** Threshold below which bars are highlighted green */
  highlightBelow?: number
  /** Render lower numeric values as longer bars, useful for docking affinities */
  lowerIsBetter?: boolean
}

export default function ScoreChart({
  data,
  title,
  unit = '',
  maxBars = 15,
  barColor,
  highlightBelow,
  lowerIsBetter = false,
}: ScoreChartProps) {
  if (!data.length) return null

  const items = data.slice(0, maxBars)
  const values = items.map((d) => d.value)
  const minVal = Math.min(...values)
  const maxVal = Math.max(...values)
  const range = maxVal - minVal || 1

  const barH = 24
  const gap = 4
  const labelW = 120
  const chartW = 400
  const padding = 40
  const totalW = labelW + chartW + padding
  const totalH = items.length * (barH + gap) + 30

  const scale = (v: number) => (
    lowerIsBetter ? (maxVal - v) / range : (v - minVal) / range
  ) * chartW

  return (
    <div className={cs.wrapper}>
      {title && <div className={cs.title}>{title}</div>}
      <svg
        viewBox={`0 0 ${totalW} ${totalH}`}
        className={cs.svg}
        preserveAspectRatio="xMinYMin meet"
      >
        {/* Axis line */}
        <line
          x1={labelW}
          y1={0}
          x2={labelW}
          y2={totalH - 20}
          stroke="var(--border)"
          strokeWidth={1}
        />

        {items.map((item, i) => {
          const y = i * (barH + gap)
          const w = scale(item.value)
          const isHigh = highlightBelow !== undefined && item.value < highlightBelow
          const fill = isHigh ? 'var(--green)' : barColor || 'var(--accent)'

          return (
            <g key={i}>
              {/* Label */}
              <text
                x={labelW - 8}
                y={y + barH / 2 + 4}
                textAnchor="end"
                className={cs.label}
              >
                {item.label.length > 16 ? item.label.slice(0, 15) + '…' : item.label}
              </text>

              {/* Bar */}
              <rect
                x={labelW + 1}
                y={y + 2}
                width={Math.max(w, 2)}
                height={barH - 4}
                rx={3}
                fill={fill}
                opacity={0.85}
                className={cs.bar}
              />

              {/* Value */}
              <text
                x={labelW + Math.max(w, 2) + 6}
                y={y + barH / 2 + 4}
                className={cs.value}
              >
                {item.value.toFixed(2)}
              </text>
            </g>
          )
        })}

        {/* Unit label */}
        {unit && (
          <text
            x={labelW + chartW / 2}
            y={totalH - 4}
            textAnchor="middle"
            className={cs.unit}
          >
            {unit}
          </text>
        )}
      </svg>
    </div>
  )
}
