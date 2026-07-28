/* ================================================================
   useWebSocket — real-time progress via WebSocket with task control
   ================================================================ */

import { useState, useRef, useCallback, useEffect } from 'react'

const WS_URL = 'ws://127.0.0.1:8299/api/ws/progress'

export interface WSProgressEvent {
  type: 'progress' | 'complete' | 'error' | 'connected' | 'task_list'
  task_id?: string
  status?: string
  label?: string
  current?: number
  total?: number
  progress?: number
  elapsed?: number
  message?: string
  detail?: Record<string, unknown>
  result?: Record<string, unknown>
  client_id?: string
  tasks?: WSProgressEvent[]
}

interface UseWebSocketReturn {
  connected: boolean
  clientId: string | null
  events: WSProgressEvent[]
  latestByTask: Record<string, WSProgressEvent>
  send: (action: string, taskId?: string) => void
  cancel: (taskId: string) => void
  pause: (taskId: string) => void
  resume: (taskId: string) => void
  skip: (taskId: string) => void
  listTasks: () => void
  clearEvents: () => void
}

export function useWebSocket(autoConnect = true): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [connected, setConnected] = useState(false)
  const [clientId, setClientId] = useState<string | null>(null)
  const [events, setEvents] = useState<WSProgressEvent[]>([])
  const [latestByTask, setLatestByTask] = useState<Record<string, WSProgressEvent>>({})

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    try {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        if (reconnectTimer.current) {
          clearTimeout(reconnectTimer.current)
          reconnectTimer.current = null
        }
      }

      ws.onmessage = (evt) => {
        try {
          const data: WSProgressEvent = JSON.parse(evt.data)

          if (data.type === 'connected') {
            setClientId(data.client_id ?? null)
            return
          }

          setEvents(prev => [...prev.slice(-200), data])

          if (data.task_id) {
            setLatestByTask(prev => ({ ...prev, [data.task_id!]: data }))
          }
        } catch {
          /* ignore malformed messages */
        }
      }

      ws.onclose = () => {
        setConnected(false)
        wsRef.current = null
        /* Auto-reconnect after 3s */
        reconnectTimer.current = setTimeout(connect, 3000)
      }

      ws.onerror = () => {
        ws.close()
      }
    } catch {
      /* Connection failed — retry in 3s */
      reconnectTimer.current = setTimeout(connect, 3000)
    }
  }, [])

  useEffect(() => {
    if (autoConnect) connect()
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
      }
    }
  }, [autoConnect, connect])

  const send = useCallback((action: string, taskId?: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action, task_id: taskId }))
    }
  }, [])

  const cancel = useCallback((taskId: string) => send('cancel', taskId), [send])
  const pause = useCallback((taskId: string) => send('pause', taskId), [send])
  const resume = useCallback((taskId: string) => send('resume', taskId), [send])
  const skip = useCallback((taskId: string) => send('skip', taskId), [send])
  const listTasks = useCallback(() => send('list'), [send])

  const clearEvents = useCallback(() => {
    setEvents([])
    setLatestByTask({})
  }, [])

  return { connected, clientId, events, latestByTask, send, cancel, pause, resume, skip, listTasks, clearEvents }
}
