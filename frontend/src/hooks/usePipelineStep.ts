/* ================================================================
   usePipelineStep — hook for pages to report pipeline step status
   ================================================================ */

import { useCallback } from 'react'
import { useApp, type PipelineStep, type StepStatus } from '@/context/AppContext'

export function usePipelineStep(step: PipelineStep) {
  const { state, dispatch } = useApp()

  const setStatus = useCallback(
    (status: StepStatus) => {
      dispatch({ type: 'SET_STEP_STATUS', payload: { step, status } })
    },
    [dispatch, step]
  )

  const markRunning = useCallback(() => setStatus('running'), [setStatus])
  const markDone = useCallback(() => setStatus('done'), [setStatus])
  const markError = useCallback(() => setStatus('error'), [setStatus])

  return {
    status: state.pipelineSteps[step],
    setStatus,
    markRunning,
    markDone,
    markError,
  }
}
