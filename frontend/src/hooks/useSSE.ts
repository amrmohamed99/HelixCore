/* ================================================================
   useSSE — consume Server-Sent Events from a POST endpoint
   ================================================================ */

import { useState, useRef, useCallback } from 'react'

const BASE_URL = 'http://127.0.0.1:8299'

export interface SSEEvent {
  step: string
  message: string
  progress: number
  elapsed: number
  count?: number
  total?: number
  detail?: Record<string, unknown>
}

interface UseSSEReturn {
  /** Current progress 0–100 (-1 on error) */
  progress: number
  /** Latest event received */
  event: SSEEvent | null
  /** All received events */
  events: SSEEvent[]
  /** Whether the stream is currently active */
  streaming: boolean
  /** Start streaming from a POST endpoint (path relative to API base) */
  start: (path: string, body: unknown) => void
  /** Cancel the current stream */
  cancel: () => void
}

/**
 * Hook that opens a streaming POST request and parses SSE events.
 *
 * Uses `fetch` + `ReadableStream` instead of `EventSource` because
 * the native `EventSource` API only supports GET requests.
 */
export function useSSE(): UseSSEReturn {
  const [progress, setProgress] = useState(0)
  const [event, setEvent] = useState<SSEEvent | null>(null)
  const [events, setEvents] = useState<SSEEvent[]>([])
  const [streaming, setStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const cancel = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setStreaming(false)
  }, [])

  const start = useCallback((path: string, body: unknown) => {
    cancel()
    setProgress(0)
    setEvent(null)
    setEvents([])
    setStreaming(true)

    const ac = new AbortController()
    abortRef.current = ac

    ;(async () => {
      try {
        const res = await fetch(`${BASE_URL}${path}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal: ac.signal,
        })

        if (!res.ok || !res.body) {
          const text = await res.text()
          const errEvt: SSEEvent = { step: 'error', message: text || 'Stream failed', progress: -1, elapsed: 0 }
          setEvent(errEvt)
          setEvents(prev => [...prev, errEvt])
          setStreaming(false)
          return
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const parsed: SSEEvent = JSON.parse(line.slice(6))
                setEvent(parsed)
                setProgress(parsed.progress)
                setEvents(prev => [...prev, parsed])
              } catch {
                // skip malformed lines
              }
            }
          }
        }
      } catch (err: unknown) {
        if ((err as Error)?.name !== 'AbortError') {
          const errEvt: SSEEvent = { step: 'error', message: (err as Error)?.message ?? 'Stream error', progress: -1, elapsed: 0 }
          setEvent(errEvt)
          setEvents(prev => [...prev, errEvt])
        }
      } finally {
        setStreaming(false)
      }
    })()
  }, [cancel])

  return { progress, event, events, streaming, start, cancel }
}
