/* ================================================================
   useWorkspace — Resolve default workspace folders beside the app
   ================================================================ */

import { useEffect, useState } from 'react'

/** Canonical subfolder names for the pipeline workspace */
export const WORKSPACE_FOLDERS = {
  fetchedPdb:       'fetched_pdb',
  ligands3d:        'ligands_3d',
  minimized:        'minimized',
  convertedPdbqt:   'converted_pdbqt',
  dockingResults:   'docking_results',
  oraclePredictions:'oracle_predictions',
  results:          'results',
  pipelineOutput:   'pipeline_output',
} as const

export type WorkspacePaths = Record<keyof typeof WORKSPACE_FOLDERS, string>

/**
 * Resolves default workspace paths and validates the workspace directory.
 *
 * For portable exe builds the workspace root lives next to the
 * executable (`HelixCoreWorkspace/`).  Otherwise it falls back to
 * `%APPDATA%/HelixCore/workspace`.
 *
 * Returns an object keyed by logical folder name (e.g. `fetchedPdb`)
 * whose value is the absolute path (`<workspaceRoot>/fetched_pdb`).
 */
export function useWorkspace(): {
  basePath: string
  paths: WorkspacePaths
  ready: boolean
  valid: boolean
  error: string | null
  revalidate: () => void
} {
  const [workspaceRoot, setWorkspaceRoot] = useState('')
  const [valid, setValid] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const validate = async (root: string) => {
    if (!root) return
    try {
      if (window.electronAPI?.validateWorkspace) {
        const result = await window.electronAPI.validateWorkspace(root)
        setValid(result.valid)
        setError(result.valid ? null : result.error || 'Workspace directory is invalid or not writable')
      } else {
        setValid(true)
        setError(null)
      }
    } catch {
      setValid(true)
      setError(null)
    }
  }

  useEffect(() => {
    let cancelled = false

    const resolve = async () => {
      try {
        if (window.electronAPI?.getWorkspaceRoot) {
          const p = await window.electronAPI.getWorkspaceRoot()
          if (!cancelled) {
            setWorkspaceRoot(p)
            await validate(p)
          }
        } else if (window.electronAPI?.getBasePath) {
          const p = await window.electronAPI.getBasePath()
          const sep = p.includes('\\') ? '\\' : '/'
          const root = `${p}${sep}workspace`
          if (!cancelled) {
            setWorkspaceRoot(root)
            await validate(root)
          }
        } else {
          if (!cancelled) {
            setWorkspaceRoot('workspace')
            setValid(true)
          }
        }
      } catch {
        if (!cancelled) {
          setWorkspaceRoot('workspace')
          setValid(true)
        }
      }
    }

    resolve()
    return () => { cancelled = true }
  }, [])

  const sep = workspaceRoot.includes('\\') ? '\\' : '/'

  const paths = Object.fromEntries(
    Object.entries(WORKSPACE_FOLDERS).map(([key, folder]) =>
      [key, workspaceRoot ? `${workspaceRoot}${sep}${folder}` : ''],
    ),
  ) as WorkspacePaths

  const revalidate = () => { validate(workspaceRoot) }

  return { basePath: workspaceRoot, paths, ready: workspaceRoot !== '', valid, error, revalidate }
}
