/* ================================================================
   PipelineFlow — visual horizontal flow diagram showing pipeline progress
   ================================================================ */

import { useNavigate } from 'react-router-dom'
import type { PipelineStep, StepStatus } from '@/context/AppContext'
import pf from './PipelineFlow.module.css'

interface FlowNode {
  key: PipelineStep
  label: string
  emoji: string
  path: string
}

const nodes: FlowNode[] = [
  { key: 'fetch', label: 'Fetch', emoji: '🔬', path: '/fetch' },
  { key: 'pocket', label: 'Pocket', emoji: '🎯', path: '/pocket' },
  { key: 'batch', label: 'Ligands', emoji: '⚗️', path: '/batch' },
  { key: 'minimize', label: 'Minimize', emoji: '⚡', path: '/minimize' },
  { key: 'convert', label: 'Convert', emoji: '🔄', path: '/convert' },
  { key: 'docking', label: 'Docking', emoji: '🧲', path: '/docking' },
  { key: 'oracle', label: 'Oracle', emoji: '🤖', path: '/oracle' },
  { key: 'results', label: 'Results', emoji: '📋', path: '/results' },
]

interface Props {
  steps: Record<PipelineStep, StepStatus>
}

export default function PipelineFlow({ steps }: Props) {
  const navigate = useNavigate()

  const statusClass = (s: StepStatus) => {
    if (s === 'done') return pf.done
    if (s === 'running') return pf.running
    if (s === 'error') return pf.error
    return ''
  }

  return (
    <div className={pf.flow}>
      {nodes.map((node, i) => {
        const status = steps[node.key]
        const prevDone = i > 0 && steps[nodes[i - 1].key] === 'done'
        return (
          <span key={node.key} style={{ display: 'contents' }}>
            {i > 0 && (
              <div className={`${pf.connector} ${prevDone && status !== 'ready' ? pf.connectorDone : ''}`} />
            )}
            <div
              className={`${pf.node} ${statusClass(status)}`}
              onClick={() => navigate(node.path)}
              title={`${node.label} — ${status}`}
            >
              <div className={pf.nodeCircle}>{node.emoji}</div>
              <span className={pf.nodeLabel}>{node.label}</span>
            </div>
          </span>
        )
      })}
    </div>
  )
}
