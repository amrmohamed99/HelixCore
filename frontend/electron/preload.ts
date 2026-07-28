import { contextBridge, ipcRenderer } from 'electron'

export interface FileFilter {
  name: string
  extensions: string[]
}

contextBridge.exposeInMainWorld('electronAPI', {
  /* Window controls */
  minimize: () => ipcRenderer.send('window:minimize'),
  maximize: () => ipcRenderer.send('window:maximize'),
  close: () => ipcRenderer.send('window:close'),
  isMaximized: () => ipcRenderer.invoke('window:is-maximized') as Promise<boolean>,

  /* File dialogs */
  selectFile: (filters?: FileFilter[]) =>
    ipcRenderer.invoke('dialog:open-file', filters) as Promise<string | null>,
  selectDirectory: () =>
    ipcRenderer.invoke('dialog:open-directory') as Promise<string | null>,

  /* App info */
  getAppVersion: () => ipcRenderer.invoke('app:version') as Promise<string>,
  getPlatform: () => ipcRenderer.invoke('app:platform') as Promise<string>,
  getBasePath: () => ipcRenderer.invoke('app:base-path') as Promise<string>,

  /* Workspace management */
  getWorkspace: () => ipcRenderer.invoke('app:get-workspace') as Promise<string>,
  getWorkspaceRoot: () => ipcRenderer.invoke('app:get-workspace-root') as Promise<string>,
  setWorkspace: (customPath?: string) =>
    ipcRenderer.invoke('app:set-workspace', customPath) as Promise<string | null>,

  /* Shell */
  showItemInFolder: (fullPath: string) => ipcRenderer.send('shell:show-item-in-folder', fullPath),

  /* Workspace validation */
  validateWorkspace: (wsPath: string) =>
    ipcRenderer.invoke('workspace:validate', wsPath) as Promise<{ valid: boolean; error?: string }>,

  /* Backend events */
  onBackendLog: (callback: (log: string) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, log: string) => callback(log)
    ipcRenderer.on('backend:log', handler)
    return () => { ipcRenderer.removeListener('backend:log', handler) }
  },

  onBackendReady: (callback: () => void) => {
    const handler = () => callback()
    ipcRenderer.on('backend:ready', handler)
    return () => { ipcRenderer.removeListener('backend:ready', handler) }
  },

  onBackendError: (callback: (error: string) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, error: string) => callback(error)
    ipcRenderer.on('backend:error', handler)
    return () => { ipcRenderer.removeListener('backend:error', handler) }
  },

  onBackendRestarting: (callback: (attempt: number) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, attempt: number) => callback(attempt)
    ipcRenderer.on('backend:restarting', handler)
    return () => { ipcRenderer.removeListener('backend:restarting', handler) }
  },

  onBackendFatal: (callback: (error: string) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, error: string) => callback(error)
    ipcRenderer.on('backend:fatal', handler)
    return () => { ipcRenderer.removeListener('backend:fatal', handler) }
  },

  /* Window state events */
  onMaximizeChange: (callback: (isMaximized: boolean) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, isMaximized: boolean) => callback(isMaximized)
    ipcRenderer.on('window:maximize-change', handler)
    return () => { ipcRenderer.removeListener('window:maximize-change', handler) }
  },
})
