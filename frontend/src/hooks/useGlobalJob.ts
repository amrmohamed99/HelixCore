import { useCallback, useEffect, useRef, useState } from 'react'
import { getCurrentJob, pauseJob, resumeJob, terminateJob } from '@/lib/api'
import type { JobSnapshot } from '@/types/api'

export function useGlobalJob() {
  const [job, setJob] = useState<JobSnapshot | null>(null)
  const [controlBusy, setControlBusy] = useState(false)
  const mounted = useRef(true)

  const refresh = useCallback(async () => {
    try {
      const current = await getCurrentJob()
      if (mounted.current) setJob(current)
    } catch {
      if (mounted.current) setJob(null)
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    refresh()
    const interval = setInterval(refresh, 750)
    return () => {
      mounted.current = false
      clearInterval(interval)
    }
  }, [refresh])

  const pause = useCallback(async () => {
    if (!job) return
    setControlBusy(true)
    try {
      const res = await pauseJob(job.id)
      setJob(res.job)
    } finally {
      setControlBusy(false)
    }
  }, [job])

  const resume = useCallback(async () => {
    if (!job) return
    setControlBusy(true)
    try {
      const res = await resumeJob(job.id)
      setJob(res.job)
    } finally {
      setControlBusy(false)
    }
  }, [job])

  const terminate = useCallback(async () => {
    if (!job) return
    setControlBusy(true)
    try {
      const res = await terminateJob(job.id)
      setJob(res.job)
    } finally {
      setControlBusy(false)
    }
  }, [job])

  return { job, controlBusy, pause, resume, terminate }
}
