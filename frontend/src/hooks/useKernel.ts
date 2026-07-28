/* ================================================================
   useKernel — hook for kernel dock functionality
   ================================================================ */

import { useCallback } from 'react'
import { useApp } from '@/context/AppContext'

export function useKernel() {
  const { state, dispatch, toggleDock } = useApp()

  const addLog = useCallback(
    (message: string) => {
      dispatch({ type: 'ADD_KERNEL_LOG', payload: message })
    },
    [dispatch]
  )

  const clearLogs = useCallback(() => {
    dispatch({ type: 'CLEAR_KERNEL_LOGS' })
  }, [dispatch])

  return {
    logs: state.kernelLogs,
    isOpen: state.dockOpen,
    toggle: toggleDock,
    addLog,
    clearLogs,
    backendStatus: state.backendStatus,
  }
}
