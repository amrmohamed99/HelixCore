/* ================================================================
   Heatmap — D3-based selectivity heatmap for multi-target docking
   ================================================================ */

import { useRef, useEffect, useCallback } from 'react'
import * as d3 from 'd3'
import css from './Heatmap.module.css'

export interface HeatmapData {
  /** Row labels (receptors) */
  rows: string[]
  /** Column labels (ligands) */
  cols: string[]
  /** Matrix values[row][col] — null means no data */
  values: (number | null)[][]
}

interface HeatmapProps {
  data: HeatmapData
  width?: number
  height?: number
  /** Color scheme: lower = better (green) for binding affinities */
  colorScale?: 'binding' | 'heat'
  title?: string
}

export default function Heatmap({ data, width = 700, height = 400, colorScale = 'binding', title }: HeatmapProps) {
  const svgRef = useRef<SVGSVGElement>(null)

  const renderHeatmap = useCallback(() => {
    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    if (!data.rows.length || !data.cols.length) return

    const margin = { top: 60, right: 30, bottom: 30, left: 100 }
    const innerW = width - margin.left - margin.right
    const innerH = height - margin.top - margin.bottom

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)

    // Flatten for domain
    const allValues = data.values.flat().filter((v): v is number => v != null)
    const minVal = d3.min(allValues) ?? -10
    const maxVal = d3.max(allValues) ?? 0

    // Scales
    const x = d3.scaleBand().domain(data.cols).range([0, innerW]).padding(0.05)
    const y = d3.scaleBand().domain(data.rows).range([0, innerH]).padding(0.05)

    const color = colorScale === 'binding'
      ? d3.scaleSequential(d3.interpolateRdYlGn).domain([maxVal, minVal])
      : d3.scaleSequential(d3.interpolateInferno).domain([minVal, maxVal])

    // Title
    if (title) {
      svg.append('text')
        .attr('x', width / 2)
        .attr('y', 20)
        .attr('text-anchor', 'middle')
        .attr('fill', 'var(--text-primary)')
        .attr('font-size', '0.85rem')
        .attr('font-weight', 600)
        .text(title)
    }

    // X axis (ligands) — top
    g.append('g')
      .selectAll('text')
      .data(data.cols)
      .join('text')
      .attr('x', d => (x(d) ?? 0) + x.bandwidth() / 2)
      .attr('y', -8)
      .attr('text-anchor', 'end')
      .attr('transform', d => `rotate(-45, ${(x(d) ?? 0) + x.bandwidth() / 2}, -8)`)
      .attr('font-size', '0.65rem')
      .attr('fill', 'var(--text-secondary)')
      .text(d => d.length > 12 ? d.slice(0, 12) + '…' : d)

    // Y axis (receptors) — left
    g.append('g')
      .selectAll('text')
      .data(data.rows)
      .join('text')
      .attr('x', -8)
      .attr('y', d => (y(d) ?? 0) + y.bandwidth() / 2)
      .attr('text-anchor', 'end')
      .attr('dominant-baseline', 'middle')
      .attr('font-size', '0.7rem')
      .attr('fill', 'var(--text-secondary)')
      .text(d => d)

    // Cells
    for (let ri = 0; ri < data.rows.length; ri++) {
      for (let ci = 0; ci < data.cols.length; ci++) {
        const val = data.values[ri]?.[ci]
        const rect = g.append('rect')
          .attr('x', x(data.cols[ci]) ?? 0)
          .attr('y', y(data.rows[ri]) ?? 0)
          .attr('width', x.bandwidth())
          .attr('height', y.bandwidth())
          .attr('rx', 2)
          .attr('fill', val != null ? color(val) : 'var(--bg-card)')
          .attr('stroke', 'var(--border)')
          .attr('stroke-width', 0.5)

        // Value text
        if (val != null) {
          g.append('text')
            .attr('x', (x(data.cols[ci]) ?? 0) + x.bandwidth() / 2)
            .attr('y', (y(data.rows[ri]) ?? 0) + y.bandwidth() / 2)
            .attr('text-anchor', 'middle')
            .attr('dominant-baseline', 'middle')
            .attr('font-size', '0.6rem')
            .attr('fill', Math.abs(val) > (maxVal + minVal) / 2 ? '#fff' : '#333')
            .text(val.toFixed(1))
        }

        // Tooltip on hover
        rect.append('title').text(
          val != null
            ? `${data.rows[ri]} × ${data.cols[ci]}: ${val.toFixed(2)} kcal/mol`
            : `${data.rows[ri]} × ${data.cols[ci]}: N/A`
        )
      }
    }

    // Color legend
    const legendW = 120
    const legendH = 10
    const legendX = innerW - legendW
    const defs = svg.append('defs')
    const gradient = defs.append('linearGradient').attr('id', 'heatmap-gradient')
    gradient.append('stop').attr('offset', '0%').attr('stop-color', color(minVal))
    gradient.append('stop').attr('offset', '100%').attr('stop-color', color(maxVal))

    const legendG = g.append('g').attr('transform', `translate(${legendX}, ${innerH + 15})`)
    legendG.append('rect').attr('width', legendW).attr('height', legendH).attr('rx', 2).style('fill', 'url(#heatmap-gradient)')
    legendG.append('text').attr('x', 0).attr('y', -2).attr('font-size', '0.6rem').attr('fill', 'var(--text-muted)').text(`${minVal.toFixed(1)}`)
    legendG.append('text').attr('x', legendW).attr('y', -2).attr('text-anchor', 'end').attr('font-size', '0.6rem').attr('fill', 'var(--text-muted)').text(`${maxVal.toFixed(1)}`)
  }, [data, width, height, colorScale, title])

  useEffect(() => { renderHeatmap() }, [renderHeatmap])

  return (
    <div className={css.container}>
      <svg ref={svgRef} width={width} height={height} className={css.svg} />
    </div>
  )
}
