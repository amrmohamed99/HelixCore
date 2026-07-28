/* ================================================================
   App Context — global state for theme, backend, kernel, system
   ================================================================ */

import { createContext, useContext, useReducer, useEffect, useCallback, useRef, type ReactNode } from 'react'
import type { SystemStats } from '@/types/api'
import { getSystemStats } from '@/lib/api'
import { loadSession, saveSession, SESSION_KEYS } from '@/lib/session'

/* ---- State shape ---- */

export type BackendStatus = 'starting' | 'online' | 'offline' | 'error'
export type Theme = 'dark' | 'light' | 'system'

/** Resolve the effective display theme from a Theme setting. */
function resolveTheme(theme: Theme): 'dark' | 'light' {
  if (theme === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return theme
}

interface KernelLog {
  id: number
  timestamp: string
  message: string
}

export type PipelineStep = 'fetch' | 'pocket' | 'batch' | 'minimize' | 'convert' | 'docking' | 'oracle' | 'results'
export type StepStatus = 'ready' | 'running' | 'done' | 'error'

export interface PinnedCompound {
  smiles: string
  name: string
  score?: number
  source?: string
}

export interface AppState {
  theme: Theme
  backendStatus: BackendStatus
  backendError: string | null
  kernelLogs: KernelLog[]
  systemStats: SystemStats | null
  dockOpen: boolean
  sidebarCollapsed: boolean
  pipelineSteps: Record<PipelineStep, StepStatus>
  pinnedCompounds: PinnedCompound[]
}

const initialPipeline: Record<PipelineStep, StepStatus> = {
  fetch: 'ready', pocket: 'ready', batch: 'ready', minimize: 'ready',
  convert: 'ready', docking: 'ready', oracle: 'ready', results: 'ready',
}

const initialState: AppState = {
  theme: (localStorage.getItem('helix-theme') as Theme) || 'dark',
  backendStatus: 'starting',
  backendError: null,
  kernelLogs: [],
  systemStats: null,
  dockOpen: loadSession(SESSION_KEYS.dockOpen, false),
  sidebarCollapsed: loadSession(SESSION_KEYS.sidebarCollapsed, false),
  pipelineSteps: loadSession(SESSION_KEYS.pipelineSteps, { ...initialPipeline }),
  pinnedCompounds: loadSession('helix.pinnedCompounds', []),
}

/* ---- Actions ---- */

type Action =
  | { type: 'SET_THEME'; payload: Theme }
  | { type: 'SET_BACKEND_STATUS'; payload: BackendStatus }
  | { type: 'SET_BACKEND_ERROR'; payload: string }
  | { type: 'ADD_KERNEL_LOG'; payload: string }
  | { type: 'CLEAR_KERNEL_LOGS' }
  | { type: 'SET_SYSTEM_STATS'; payload: SystemStats }
  | { type: 'TOGGLE_DOCK' }
  | { type: 'SET_DOCK_OPEN'; payload: boolean }
  | { type: 'SET_STEP_STATUS'; payload: { step: PipelineStep; status: StepStatus } }
  | { type: 'RESET_PIPELINE' }
  | { type: 'TOGGLE_SIDEBAR' }
  | { type: 'PIN_COMPOUND'; payload: PinnedCompound }
  | { type: 'UNPIN_COMPOUND'; payload: string }
  | { type: 'CLEAR_PINNED' }

let logIdCounter = 0

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_THEME':
      localStorage.setItem('helix-theme', action.payload)
      document.documentElement.setAttribute('data-theme', resolveTheme(action.payload))
      return { ...state, theme: action.payload }
    case 'SET_BACKEND_STATUS':
      return { ...state, backendStatus: action.payload }
    case 'SET_BACKEND_ERROR':
      return { ...state, backendStatus: 'error', backendError: action.payload }
    case 'ADD_KERNEL_LOG':
      return {
        ...state,
        kernelLogs: [
          ...state.kernelLogs.slice(-499),
          {
            id: ++logIdCounter,
            timestamp: new Date().toLocaleTimeString(),
            message: action.payload,
          },
        ],
      }
    case 'CLEAR_KERNEL_LOGS':
      return { ...state, kernelLogs: [] }
    case 'SET_SYSTEM_STATS':
      return { ...state, systemStats: action.payload }
    case 'TOGGLE_DOCK': {
      const nextDock = !state.dockOpen
      saveSession(SESSION_KEYS.dockOpen, nextDock)
      return { ...state, dockOpen: nextDock }
    }
    case 'SET_DOCK_OPEN':
      saveSession(SESSION_KEYS.dockOpen, action.payload)
      return { ...state, dockOpen: action.payload }
    case 'SET_STEP_STATUS': {
      const next = { ...state.pipelineSteps, [action.payload.step]: action.payload.status }
      saveSession(SESSION_KEYS.pipelineSteps, next)
      return { ...state, pipelineSteps: next }
    }
    case 'RESET_PIPELINE':
      saveSession(SESSION_KEYS.pipelineSteps, { ...initialPipeline })
      return { ...state, pipelineSteps: { ...initialPipeline } }
    case 'TOGGLE_SIDEBAR': {
      const next = !state.sidebarCollapsed
      saveSession(SESSION_KEYS.sidebarCollapsed, next)
      return { ...state, sidebarCollapsed: next }
    }
    case 'PIN_COMPOUND': {
      if (state.pinnedCompounds.some(p => p.smiles === action.payload.smiles)) return state
      const pinned = [...state.pinnedCompounds, action.payload]
      saveSession('helix.pinnedCompounds', pinned)
      return { ...state, pinnedCompounds: pinned }
    }
    case 'UNPIN_COMPOUND': {
      const pinned = state.pinnedCompounds.filter(p => p.smiles !== action.payload)
      saveSession('helix.pinnedCompounds', pinned)
      return { ...state, pinnedCompounds: pinned }
    }
    case 'CLEAR_PINNED':
      saveSession('helix.pinnedCompounds', [])
      return { ...state, pinnedCompounds: [] }
    default:
      return state
  }
}

/* ---- Context ---- */

interface AppContextValue {
  state: AppState
  dispatch: React.Dispatch<Action>
  toggleTheme: () => void
  toggleDock: () => void
  toggleSidebar: () => void
  pinCompound: (compound: PinnedCompound) => void
  unpinCompound: (smiles: string) => void
  clearPinned: () => void
}

const AppContext = createContext<AppContextValue | null>(null)

/* ---- Provider ---- */

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState)

  const toggleTheme = useCallback(() => {
    const order: Theme[] = ['dark', 'light', 'system']
    const next = order[(order.indexOf(state.theme) + 1) % order.length]
    dispatch({ type: 'SET_THEME', payload: next })
  }, [state.theme])

  const toggleDock = useCallback(() => {
    dispatch({ type: 'TOGGLE_DOCK' })
  }, [])

  const toggleSidebar = useCallback(() => {
    dispatch({ type: 'TOGGLE_SIDEBAR' })
  }, [])

  const pinCompound = useCallback((compound: PinnedCompound) => {
    dispatch({ type: 'PIN_COMPOUND', payload: compound })
  }, [])

  const unpinCompound = useCallback((smiles: string) => {
    dispatch({ type: 'UNPIN_COMPOUND', payload: smiles })
  }, [])

  const clearPinned = useCallback(() => {
    dispatch({ type: 'CLEAR_PINNED' })
  }, [])

  /* Apply initial theme */
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', resolveTheme(state.theme))
  }, [])

  /* Re-apply theme when OS preference changes (for 'system' mode) */
  useEffect(() => {
    if (state.theme !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = () => {
      document.documentElement.setAttribute('data-theme', resolveTheme('system'))
    }
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [state.theme])

  /* Track last backend status so we only log actual transitions */
  const lastStatusRef = useRef<BackendStatus>(state.backendStatus)

  /* Listen for backend IPC events */
  useEffect(() => {
    if (!window.electronAPI) return

    const unsubLog = window.electronAPI.onBackendLog((log) => {
      dispatch({ type: 'ADD_KERNEL_LOG', payload: log })
    })

    const unsubReady = window.electronAPI.onBackendReady(() => {
      if (lastStatusRef.current !== 'online') {
        dispatch({ type: 'ADD_KERNEL_LOG', payload: '✓ Backend is online' })
      }
      dispatch({ type: 'SET_BACKEND_STATUS', payload: 'online' })
      lastStatusRef.current = 'online'
    })

    const unsubError = window.electronAPI.onBackendError((error) => {
      if (lastStatusRef.current !== 'error') {
        dispatch({ type: 'ADD_KERNEL_LOG', payload: `✗ Backend error: ${error}` })
      }
      dispatch({ type: 'SET_BACKEND_ERROR', payload: error })
      lastStatusRef.current = 'error'
    })

    const unsubRestarting = window.electronAPI.onBackendRestarting?.((attempt) => {
      dispatch({ type: 'ADD_KERNEL_LOG', payload: `⟳ Backend crashed — restarting (attempt ${attempt}/3)...` })
      dispatch({ type: 'SET_BACKEND_STATUS', payload: 'starting' })
      lastStatusRef.current = 'starting'
    })

    const unsubFatal = window.electronAPI.onBackendFatal?.((error) => {
      dispatch({ type: 'ADD_KERNEL_LOG', payload: `✗ FATAL: ${error}` })
      dispatch({ type: 'SET_BACKEND_ERROR', payload: error })
      lastStatusRef.current = 'error'
    })

    return () => {
      unsubLog()
      unsubReady()
      unsubError()
      unsubRestarting?.()
      unsubFatal?.()
    }
  }, [])

  /* Fallback: if the IPC backend:ready event was lost (race condition),
     poll the health endpoint directly until we detect the backend. */
  useEffect(() => {
    if (state.backendStatus === 'online') return

    const check = async () => {
      try {
        const res = await fetch('http://127.0.0.1:8299/api/health')
        if (res.ok) {
          if (lastStatusRef.current !== 'online') {
            dispatch({ type: 'ADD_KERNEL_LOG', payload: '✓ Backend is online' })
          }
          dispatch({ type: 'SET_BACKEND_STATUS', payload: 'online' })
          lastStatusRef.current = 'online'
        }
      } catch {
        /* not ready yet */
      }
    }

    const interval = setInterval(check, 2000)
    return () => clearInterval(interval)
  }, [state.backendStatus])

  /* Poll system stats when backend is online */
  useEffect(() => {
    if (state.backendStatus !== 'online') return

    const poll = async () => {
      try {
        const stats = await getSystemStats()
        dispatch({ type: 'SET_SYSTEM_STATS', payload: stats })
      } catch {
        /* silently ignore until next poll */
      }
    }

    poll()
    const interval = setInterval(poll, 5000)
    return () => clearInterval(interval)
  }, [state.backendStatus])

  return (
    <AppContext.Provider value={{ state, dispatch, toggleTheme, toggleDock, toggleSidebar, pinCompound, unpinCompound, clearPinned }}>
      {children}
    </AppContext.Provider>
  )
}

/* ---- Hook ---- */

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}
