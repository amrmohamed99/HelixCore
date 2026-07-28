/* ================================================================
   Project Manager — save / load / delete workspace snapshots
   ================================================================ */

import { useEffect, useState } from 'react'
import * as api from '@/lib/api'
import type { Project } from '@/types/api'
import { useKernel } from '@/hooks/useKernel'
import { useToast } from '@/context/ToastContext'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useProjectState } from '@/hooks/useProjectState'
import { PageShell, Alert, FilePicker, Tooltip, ConfirmDialog, EmptyState } from '@/components/shared'
import s from '@/styles/shared.module.css'

const EMPTY: Project = { id: '', name: '', target_name: '', pdb_id: '', receptor_path: '', notes: '', created: '' }

export default function ProjectManager() {
  const { addLog } = useKernel()
  const { addToast } = useToast()
  const [projects, setProjects] = useState<Project[]>([])
  const [editing, setEditing] = useState<Project | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const { saveToProject, restoreFromProject } = useProjectState()

  useKeyboardShortcuts([
    { key: 's', ctrl: true, action: () => { if (editing) handleSave() }, enabled: !!editing },
  ])

  const refresh = async () => {
    try {
      const res = await api.listProjects()
      setProjects(res.projects)
    } catch { /* silent */ }
  }

  useEffect(() => { refresh() }, [])

  const handleSave = async () => {
    if (!editing || !editing.name.trim()) return
    setLoading(true)
    setError('')
    try {
      await api.saveProject(editing)
      addLog(`✓ Project saved: ${editing.name}`)
      addToast('Project saved', 'success')
      setEditing(null)
      refresh()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Save failed'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleLoad = async (id: string) => {
    setLoading(true)
    try {
      const p = await api.loadProject(id)
      setEditing(p)
      addLog(`Loaded project: ${p.name}`)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Load failed'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await api.deleteProject(id)
      addLog(`Deleted project: ${id}`)
      addToast('Project deleted', 'success')
      refresh()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Delete failed'
      setError(msg)
    }
  }

  return (
    <PageShell emoji="📁" title="Project Manager" subtitle="Save, load, and manage workspace snapshots for your drug discovery campaigns" infoTooltip="Save and organize your drug discovery campaigns as project snapshots. Store target name, PDB ID, receptor paths, and notes to resume work later." helpUrl="https://en.wikipedia.org/wiki/Drug_discovery">

      {error && <Alert variant="error" message={error} onDismiss={() => setError('')} />}

      {/* Editor card */}
      <div className={s.card}>
        <div className={s.cardHeader}>
          <span className={s.cardTitle}>{editing ? `Editing: ${editing.name || 'New project'}` : 'New Project'}</span>
          {!editing && (
            <button className={s.btnPrimary} onClick={() => setEditing({ ...EMPTY })}>
              + New
            </button>
          )}
        </div>

        {editing && (
          <>
            <div className={s.formGrid}>
              <div className={s.formGroup}>
                <label className={s.label} htmlFor="proj-name">Project Name * <Tooltip text="Unique name for your drug discovery campaign">ⓘ</Tooltip></label>
                <input id="proj-name" className={s.input} value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} placeholder="My Campaign" />
              </div>
              <div className={s.formGroup}>
                <label className={s.label} htmlFor="proj-target">Target Name <Tooltip text="Name of the protein target being studied (e.g. CDK2, EGFR)">ⓘ</Tooltip></label>
                <input id="proj-target" className={s.input} value={editing.target_name ?? ''} onChange={(e) => setEditing({ ...editing, target_name: e.target.value })} placeholder="e.g. CDK2" />
              </div>
              <div className={s.formGroup}>
                <label className={s.label} htmlFor="proj-pdb">PDB ID <Tooltip text="4-character PDB identifier associated with this project">ⓘ</Tooltip></label>
                <input id="proj-pdb" className={`${s.input} ${s.inputMono}`} value={editing.pdb_id ?? ''} onChange={(e) => setEditing({ ...editing, pdb_id: e.target.value })} placeholder="e.g. 3PTB" />
              </div>
              <FilePicker label="Receptor Path" value={editing.receptor_path ?? ''} onChange={(v) => setEditing({ ...editing, receptor_path: v })} placeholder="Path to receptor PDBQT…" />
              <div className={s.formGroupFull}>
                <label className={s.label} htmlFor="proj-notes">Notes <Tooltip text="Free-form notes about campaign progress, findings, and next steps">ⓘ</Tooltip></label>
                <textarea id="proj-notes" className={s.input} rows={3} value={editing.notes ?? ''} onChange={(e) => setEditing({ ...editing, notes: e.target.value })} placeholder="Campaign notes…" />
              </div>
            </div>
            <div className={s.actions} style={{ marginTop: 16 }}>
              <button className={s.btnPrimary} onClick={handleSave} disabled={loading || !editing.name.trim()}>
                {loading ? <><span className={s.spinnerSmall} /> Saving…</> : '💾 Save Project'}
              </button>
              <button className={s.btnSecondary} onClick={() => setEditing(null)}>Cancel</button>
            </div>
          </>
        )}
      </div>

      {/* Projects list */}
      <div className={s.card}>
        <div className={s.cardHeader}><span className={s.cardTitle}>Saved Projects</span></div>
        {projects.length === 0 ? (
          <EmptyState icon="📁" title="No Saved Projects" description="Create a new project to save and organize your drug discovery campaigns." action={{ label: '+ New Project', onClick: () => setEditing({ ...EMPTY }) }} />
        ) : (
          <div className={s.tableScroll}>
            <table className={s.table}>
              <thead>
                <tr><th>Name</th><th>Target</th><th>PDB</th><th>Created</th><th style={{ width: 220 }}>Actions</th></tr>
              </thead>
              <tbody>
                {projects.map((p) => (
                  <tr key={p.id}>
                    <td className={s.mono}>{p.name}</td>
                    <td>{p.target_name || '—'}</td>
                    <td className={s.mono}>{p.pdb_id || '—'}</td>
                    <td>{p.created ? new Date(p.created).toLocaleDateString() : '—'}</td>
                    <td>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        <button className={s.btnSmall} onClick={() => handleLoad(p.id)}>Open</button>
                        <Tooltip text="Save the current page inputs and pipeline state into this project"><button className={s.btnSmall} onClick={() => saveToProject(p)}>💾 Save Session</button></Tooltip>
                        <Tooltip text="Restore all saved page inputs and pipeline state from this project"><button className={s.btnSmall} onClick={async () => { await restoreFromProject(p.id); refresh() }}>📂 Restore</button></Tooltip>
                        <button className={`${s.btnSmall} ${s.btnSecondary}`} onClick={() => setDeleteTarget(p.id)} aria-label="Delete project">🗑</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Project"
        message="This project snapshot will be permanently deleted. This action cannot be undone."
        confirmLabel="Delete"
        danger
        onConfirm={() => {
          if (deleteTarget) handleDelete(deleteTarget)
          setDeleteTarget(null)
        }}
        onCancel={() => setDeleteTarget(null)}
      />
    </PageShell>
  )
}
