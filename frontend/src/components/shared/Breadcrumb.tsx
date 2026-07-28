/* ================================================================
   Breadcrumb — shows hierarchical navigation path
   ================================================================ */

import { Link, useLocation } from 'react-router-dom'
import bc from './Breadcrumb.module.css'

/** Map route segments to display labels */
const labelMap: Record<string, string> = {
  dashboard: 'Dashboard',
  fetch: 'PDB Fetch',
  pocket: 'Pocket Analysis',
  batch: 'Batch Generate',
  minimize: 'Minimization',
  convert: 'Format Convert',
  pipeline: 'Auto Pipeline',
  docking: 'Docking',
  similarity: 'Similarity',
  oracle: 'Oracle AI',
  results: 'Results',
  filters: 'Compound Filters',
  admet: 'ADMET Profiler',
  interactions: 'Interaction Profiler',
  cluster: 'Cluster Analysis',
  analogs: 'Analog Generator',
  projects: 'Project Manager',
  about: 'About',
}

export default function Breadcrumb() {
  const { pathname } = useLocation()
  const segments = pathname.split('/').filter(Boolean)

  if (segments.length === 0) return null

  return (
    <nav className={bc.breadcrumb} aria-label="Breadcrumb">
      <Link to="/dashboard" className={bc.crumbLink}>Home</Link>
      {segments.map((seg, i) => {
        const path = '/' + segments.slice(0, i + 1).join('/')
        const label = labelMap[seg] || seg
        const isLast = i === segments.length - 1
        return (
          <span key={path}>
            <span className={bc.separator}>/</span>{' '}
            {isLast ? (
              <span className={bc.current}>{label}</span>
            ) : (
              <Link to={path} className={bc.crumbLink}>{label}</Link>
            )}
          </span>
        )
      })}
    </nav>
  )
}
