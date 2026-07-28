export interface FileFilter {
  name: string
  extensions: string[]
}

export interface ElectronAPI {
  minimize: () => void
  maximize: () => void
  close: () => void
  isMaximized: () => Promise<boolean>
  selectFile: (filters?: FileFilter[]) => Promise<string | null>
  selectDirectory: () => Promise<string | null>
  getAppVersion: () => Promise<string>
  getPlatform: () => Promise<string>
  getBasePath: () => Promise<string>
  getWorkspaceRoot: () => Promise<string>
  getWorkspace: () => Promise<string>
  setWorkspace: (customPath?: string) => Promise<string | null>
  validateWorkspace: (wsPath: string) => Promise<{ valid: boolean; error?: string }>
  showItemInFolder: (fullPath: string) => void
  onBackendLog: (callback: (log: string) => void) => () => void
  onBackendReady: (callback: () => void) => () => void
  onBackendError: (callback: (error: string) => void) => () => void
  onBackendRestarting: (callback: (attempt: number) => void) => () => void
  onBackendFatal: (callback: (error: string) => void) => () => void
  onMaximizeChange: (callback: (isMaximized: boolean) => void) => () => void
}

declare global {
  interface Window {
    electronAPI: ElectronAPI
  }
}
