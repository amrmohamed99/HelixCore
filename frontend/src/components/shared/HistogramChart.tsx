/* ================================================================
   HistogramChart — Vertical bar histogram for score distribution
   No external dependencies — pure SVG rendering with tooltip overlay
   Auto-bins via Sturges' rule (clamped 8–15). Clickable bars toggle
   range selection. Used by Results page for affinity distribution.
   ================================================================ */

import { useState, useRef, useMemo } from 'react'
import cs from './HistogramChart.module.css'

export interface HistogramBin {
  min: number
  max: number
  count: number
}

interface HistogramChartProps {
  /** Raw numeric values to bin */
  data: number[]
  /** Override automatic bin count */
  bins?: number
  /** Chart title */
  title?: string
  /** Axis unit label (e.g. "kcal/mol") */
  unit?: string
  /** Optional highlight range (bins overlapping are highlighted green) */
  highlightRange?: [number, number]
  /** Clicked-bin callback: receives bin min/max */
  onBinClick?: (min: number, max: number) => void
  /** Currently active bin range (for toggle styling) */
  activeRange?: [number, number] | null
  /** Bar color (CSS variable or hex). Defaults to accent. */
  barColor?: string
}

/** Sturges' rule for optimal bin count, clamped to [8, 15] */
function sturgeBins(n: number): number {
  if (n <= 1) return 1
  const k = Math.ceil(Math.log2(n) + 1)
  return Math.max(8, Math.min(15, k))
}

function buildBins(data: number[], numBins: number): HistogramBin[] {
  if (!data.length) return []
  const min = Math.min(...data)
  const max = Math.max(...data)
  const width = (max - min) / numBins || 1
  const bins: HistogramBin[] = Array.from({ length: numBins }, (_, i) => ({
    min: +(min + i * width).toFixed(4),
    max: +(min + (i + 1) * width).toFixed(4),
    count: 0,
  }))
  for (const v of data) {
    let idx = Math.floor((v - min) / width)
    if (idx >= numBins) idx = numBins - 1
    bins[idx].count++
  }
  return bins
}

export default function HistogramChart({
  data,
  bins: binOverride,
  title,
  unit = '',
  highlightRange,
  onBinClick,
  activeRange,
  barColor,
}: HistogramChartProps) {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const [tooltip, setTooltip] = useState<{ x: number; y: number; bin: HistogramBin } | null>(null)

  const numBins = binOverride ?? sturgeBins(data.length)
  const bins = useMemo(() => buildBins(data, numBins), [data, numBins])
  const maxCount = Math.max(...bins.map(b => b.count), 1)

  if (!data.length) return null

  /* SVG layout */
  const marginLeft = 40
  const marginBottom = 50
  const marginTop = 12
  const marginRight = 12
  const chartW = 420
  const chartH = 200
  const totalW = marginLeft + chartW + marginRight
  const totalH = marginTop + chartH + marginBottom
  const barGap = 2
  const barW = (chartW - barGap * bins.length) / bins.length

  const isActive = (bin: HistogramBin) =>
    activeRange != null && bin.min >= activeRange[0] - 0.001 && bin.max <= activeRange[1] + 0.001

  const isHighlighted = (bin: HistogramBin) => {
    if (!highlightRange) return false
    return bin.max > highlightRange[0] && bin.min < highlightRange[1]
  }

  const handleMouseMove = (e: React.MouseEvent, bin: HistogramBin) => {
    if (!wrapperRef.current) return
    const rect = wrapperRef.current.getBoundingClientRect()
    setTooltip({ x: e.clientX - rect.left + 12, y: e.clientY - rect.top - 16, bin })
  }

  /* Y-axis tick values */
  const yTicks = useMemo(() => {
    const step = Math.max(1, Math.ceil(maxCount / 5))
    const ticks: number[] = []
    for (let v = 0; v <= maxCount; v += step) ticks.push(v)
    if (ticks[ticks.length - 1] < maxCount) ticks.push(maxCount)
    return ticks
  }, [maxCount])

  return (
    <div className={cs.wrapper} ref={wrapperRef} style={{ position: 'relative' }}>
      {title && <div className={cs.title}>{title}</div>}
      <svg
        viewBox={`0 0 ${totalW} ${totalH}`}
        className={cs.svg}
        preserveAspectRatio="xMinYMin meet"
      >
        {/* Y axis */}
        <line
          x1={marginLeft}
          y1={marginTop}
          x2={marginLeft}
          y2={marginTop + chartH}
          stroke="var(--border)"
          strokeWidth={1}
        />

        {/* X axis */}
        <line
          x1={marginLeft}
          y1={marginTop + chartH}
          x2={marginLeft + chartW}
          y2={marginTop + chartH}
          stroke="var(--border)"
          strokeWidth={1}
        />

        {/* Y grid lines + labels */}
        {yTicks.map(v => {
          const y = marginTop + chartH - (v / maxCount) * chartH
          return (
            <g key={`y-${v}`}>
              <line
                x1={marginLeft}
                y1={y}
                x2={marginLeft + chartW}
                y2={y}
                stroke="var(--border)"
                strokeWidth={0.5}
                strokeDasharray="3,3"
                opacity={0.5}
              />
              <text
                x={marginLeft - 6}
                y={y + 3}
                textAnchor="end"
                className={cs.axisLabel}
              >
                {v}
              </text>
            </g>
          )
        })}

        {/* Bars */}
        {bins.map((bin, i) => {
          const barH = (bin.count / maxCount) * chartH
          const x = marginLeft + i * (barW + barGap) + barGap / 2
          const y = marginTop + chartH - barH

          const active = isActive(bin)
          const highlighted = isHighlighted(bin)
          const fill = active
            ? 'var(--green)'
            : highlighted
              ? 'var(--green)'
              : barColor || 'var(--accent)'

          return (
            <g key={i}>
              <rect
                x={x}
                y={y}
                width={Math.max(barW, 1)}
                height={Math.max(barH, 0)}
                rx={2}
                fill={fill}
                opacity={active ? 1 : 0.8}
                className={`${cs.bar} ${active ? cs.barActive : ''}`}
                onClick={() => onBinClick?.(bin.min, bin.max)}
                onMouseMove={e => handleMouseMove(e, bin)}
                onMouseLeave={() => setTooltip(null)}
              />
              {/* Count label above bar (only when bar is tall enough) */}
              {bin.count > 0 && barH > 12 && (
                <text
                  x={x + barW / 2}
                  y={y - 3}
                  textAnchor="middle"
                  className={cs.countLabel}
                >
                  {bin.count}
                </text>
              )}
            </g>
          )
        })}

        {/* X axis labels (bin edge values, show every other if crowded) */}
        {bins.map((bin, i) => {
          const step = bins.length > 12 ? 2 : 1
          if (i % step !== 0 && i !== bins.length - 1) return null
          const x = marginLeft + i * (barW + barGap) + barGap / 2
          return (
            <text
              key={`x-${i}`}
              x={x}
              y={marginTop + chartH + 14}
              textAnchor="middle"
              className={cs.axisLabel}
              transform={`rotate(-30, ${x}, ${marginTop + chartH + 14})`}
            >
              {bin.min.toFixed(1)}
            </text>
          )
        })}

        {/* Last edge label */}
        {bins.length > 0 && (() => {
          const lastBin = bins[bins.length - 1]
          const x = marginLeft + bins.length * (barW + barGap) + barGap / 2
          return (
            <text
              x={x}
              y={marginTop + chartH + 14}
              textAnchor="middle"
              className={cs.axisLabel}
              transform={`rotate(-30, ${x}, ${marginTop + chartH + 14})`}
            >
              {lastBin.max.toFixed(1)}
            </text>
          )
        })()}

        {/* Unit label */}
        {unit && (
          <text
            x={marginLeft + chartW / 2}
            y={totalH - 4}
            textAnchor="middle"
            className={cs.axisUnit}
          >
            {unit}
          </text>
        )}
      </svg>

      {/* Hover tooltip */}
      {tooltip && (
        <div
          className={cs.tooltip}
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          <span className={cs.tooltipRange}>
            {tooltip.bin.min.toFixed(2)} → {tooltip.bin.max.toFixed(2)}
          </span>
          <span className={cs.tooltipCount}>({tooltip.bin.count} compounds)</span>
        </div>
      )}
    </div>
  )
}
