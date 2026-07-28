/* ================================================================
   ForceGraph — D3 force-directed interaction network visualization
   ================================================================ */

import { useRef, useEffect, useState, useCallback } from 'react'
import * as d3 from 'd3'
import s from '@/styles/shared.module.css'
import css from './ForceGraph.module.css'

export interface GraphNode {
  id: string
  label: string
  type: 'receptor' | 'ligand' | 'residue' | 'fragment'
  x?: number
  y?: number
  fx?: number | null
  fy?: number | null
}

export interface GraphEdge {
  source: string | GraphNode
  target: string | GraphNode
  type: 'hbond' | 'hydrophobic' | 'ionic' | 'pi_stack' | 'vdw' | 'covalent'
  strength?: number
  label?: string
}

export interface ForceGraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

interface ForceGraphProps {
  data: ForceGraphData
  width?: number
  height?: number
  /** Show edge labels */
  showLabels?: boolean
}

const NODE_COLORS: Record<GraphNode['type'], string> = {
  receptor: '#818cf8',
  ligand: '#34d399',
  residue: '#fbbf24',
  fragment: '#f87171',
}

const EDGE_COLORS: Record<GraphEdge['type'], string> = {
  hbond: '#60a5fa',
  hydrophobic: '#a78bfa',
  ionic: '#f87171',
  pi_stack: '#34d399',
  vdw: '#9ca3af',
  covalent: '#fbbf24',
}

export default function ForceGraph({ data, width = 700, height = 500, showLabels = true }: ForceGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [hoveredNode, setHoveredNode] = useState<string | null>(null)

  const renderGraph = useCallback(() => {
    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    if (!data.nodes.length) return

    const container = svg.append('g')

    // Zoom behavior
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 4])
      .on('zoom', (event) => container.attr('transform', event.transform))
    svg.call(zoom)

    // Force simulation
    const simulation = d3.forceSimulation<GraphNode>(data.nodes)
      .force('link', d3.forceLink<GraphNode, GraphEdge>(data.edges).id(d => d.id).distance(80))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(30))

    // Edges
    const link = container.append('g')
      .selectAll('line')
      .data(data.edges)
      .join('line')
      .attr('stroke', d => EDGE_COLORS[(d as GraphEdge).type] || '#9ca3af')
      .attr('stroke-width', d => Math.max(1, ((d as GraphEdge).strength || 0.5) * 3))
      .attr('stroke-opacity', 0.6)
      .attr('stroke-dasharray', d => (d as GraphEdge).type === 'vdw' ? '4,3' : 'none')

    // Edge labels
    let edgeLabels: d3.Selection<SVGTextElement, GraphEdge, SVGGElement, unknown> | null = null
    if (showLabels) {
      edgeLabels = container.append('g')
        .selectAll('text')
        .data(data.edges)
        .join('text')
        .text(d => (d as GraphEdge).label || (d as GraphEdge).type)
        .attr('font-size', '0.6rem')
        .attr('fill', 'var(--text-muted)')
        .attr('text-anchor', 'middle')
        .attr('dy', -4)
    }

    // Nodes
    const node = container.append('g')
      .selectAll('g')
      .data(data.nodes)
      .join('g')
      .call(d3.drag<SVGGElement, GraphNode>()
        .on('start', (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart()
          d.fx = d.x; d.fy = d.y
        })
        .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y })
        .on('end', (event, d) => {
          if (!event.active) simulation.alphaTarget(0)
          d.fx = null; d.fy = null
        })
      )

    node.append('circle')
      .attr('r', d => d.type === 'ligand' ? 14 : d.type === 'receptor' ? 12 : 10)
      .attr('fill', d => NODE_COLORS[d.type])
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
      .style('cursor', 'grab')

    node.append('text')
      .text(d => d.label)
      .attr('font-size', '0.7rem')
      .attr('fill', 'var(--text-primary)')
      .attr('text-anchor', 'middle')
      .attr('dy', -18)
      .style('pointer-events', 'none')

    node.on('mouseenter', (_, d) => setHoveredNode(d.id))
      .on('mouseleave', () => setHoveredNode(null))

    simulation.on('tick', () => {
      link
        .attr('x1', d => (d.source as GraphNode).x || 0)
        .attr('y1', d => (d.source as GraphNode).y || 0)
        .attr('x2', d => (d.target as GraphNode).x || 0)
        .attr('y2', d => (d.target as GraphNode).y || 0)

      if (edgeLabels) {
        edgeLabels
          .attr('x', d => (((d.source as GraphNode).x || 0) + ((d.target as GraphNode).x || 0)) / 2)
          .attr('y', d => (((d.source as GraphNode).y || 0) + ((d.target as GraphNode).y || 0)) / 2)
      }

      node.attr('transform', d => `translate(${d.x}, ${d.y})`)
    })

    return () => simulation.stop()
  }, [data, width, height, showLabels])

  useEffect(() => {
    const cleanup = renderGraph()
    return () => cleanup?.()
  }, [renderGraph])

  return (
    <div className={css.container}>
      <svg ref={svgRef} width={width} height={height} className={css.svg} />
      {/* Legend */}
      <div className={css.legend}>
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <div key={type} className={css.legendItem}>
            <span className={css.legendDot} style={{ background: color }} />
            <span>{type}</span>
          </div>
        ))}
        <div className={css.legendDivider} />
        {Object.entries(EDGE_COLORS).map(([type, color]) => (
          <div key={type} className={css.legendItem}>
            <span className={css.legendLine} style={{ background: color }} />
            <span>{type.replace('_', ' ')}</span>
          </div>
        ))}
      </div>
      {hoveredNode && (
        <div className={css.tooltip}>{hoveredNode}</div>
      )}
    </div>
  )
}
