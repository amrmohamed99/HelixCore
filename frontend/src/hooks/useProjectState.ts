/* ================================================================
   useProjectState — save / restore full session state to a project
   ================================================================ */

import { useCallback } from 'react'
import * as api from '@/lib/api'
import { loadSession, saveSession } from '@/lib/session'
import type { Project } from '@/types/api'
import { useToast } from '@/context/ToastContext'
import { useKernel } from '@/hooks/useKernel'

const PREFIX = 'helix:'

/**
 * Collect all `helix:*` keys from localStorage into a plain object.
 */
function collectSessionData(): Record<string, unknown> {
  const data: Record<string, unknown> = {}
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i)
    if (key?.startsWith(PREFIX)) {
      try {
        data[key] = JSON.parse(localStorage.getItem(key) ?? 'null')
      } catch {
        data[key] = localStorage.getItem(key)
      }
    }
  }
  return data
}

/**
 * Restore all `helix:*` keys from a saved session object.
 */
function restoreSessionData(data: Record<string, unknown>): void {
  for (const [key, value] of Object.entries(data)) {
    if (key.startsWith(PREFIX)) {
      try {
        localStorage.setItem(key, JSON.stringify(value))
      } catch { /* ignore */ }
    }
  }
}

/**
 * Collect pipeline step statuses from the session.
 */
function collectPipelineState(): Record<string, unknown> {
  return loadSession<Record<string, unknown>>('pipeline-steps', {})
}

export function useProjectState() {
  const { addToast } = useToast()
  const { addLog } = useKernel()

  /**
   * Save the current app session into an existing project.
   */
  const saveToProject = useCallback(async (project: Project) => {
    const updated: Project = {
      ...project,
      pipeline_state: collectPipelineState(),
      session_data: collectSessionData(),
    }
    try {
      await api.saveProject(updated)
      addLog(`✓ Session saved to project: ${project.name}`)
      addToast(`Session saved to "${project.name}"`, 'success')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Save failed'
      addToast(msg, 'error')
    }
  }, [addLog, addToast])

  /**
   * Restore an app session from a loaded project.
   */
  const restoreFromProject = useCallback(async (projectId: string) => {
    try {
      const project: Project = await api.loadProject(projectId)
      if (project.session_data && typeof project.session_data === 'object') {
        restoreSessionData(project.session_data as Record<string, unknown>)
      }
      if (project.pipeline_state && typeof project.pipeline_state === 'object') {
        saveSession('pipeline-steps', project.pipeline_state)
      }
      addLog(`✓ Session restored from project: ${project.name}`)
      addToast(`Session restored from "${project.name}" — reload page for full effect`, 'success')
      return project
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Restore failed'
      addToast(msg, 'error')
      return null
    }
  }, [addLog, addToast])

  return { saveToProject, restoreFromProject }
}
