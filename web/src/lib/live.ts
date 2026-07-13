"use client"

import { useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useRef, useState } from "react"
import { keys } from "./api/hooks"
import { liveEvent, type LiveEvent } from "./api/schemas"

export type LiveStatus = "connecting" | "live" | "reconnecting" | "offline"

const BUFFER_SIZE = 200
const INVALIDATE_EVERY_MS = 3_000

export function parseLiveEvent(raw: string): LiveEvent | null {
  let json: unknown
  try {
    json = JSON.parse(raw)
  } catch {
    return null
  }
  const parsed = liveEvent.safeParse(json)
  return parsed.success ? parsed.data : null
}

export function useLiveEvents(appId: string, paused: boolean) {
  const [events, setEvents] = useState<LiveEvent[]>([])
  const [status, setStatus] = useState<LiveStatus>("connecting")
  const [generation, setGeneration] = useState(0)
  const client = useQueryClient()
  const pausedRef = useRef(paused)

  useEffect(() => {
    pausedRef.current = paused
  }, [paused])

  useEffect(() => {
    // Same-origin proxy route: the httpOnly session cookie rides along automatically.
    const source = new EventSource(`/api/relay/apps/${appId}/stream`)
    let lastInvalidate = 0

    const handle = (raw: MessageEvent<string>) => {
      const event = parseLiveEvent(raw.data)
      if (!event) return
      if (!pausedRef.current) {
        setEvents((current) => [event, ...current].slice(0, BUFFER_SIZE))
      }
      const now = Date.now()
      if (now - lastInvalidate > INVALIDATE_EVERY_MS) {
        lastInvalidate = now
        void client.invalidateQueries({ queryKey: ["apps", appId, "overview"] })
        void client.invalidateQueries({ queryKey: keys.endpoints(appId), exact: true })
      }
    }

    source.addEventListener("ready", () => setStatus("live"))
    source.addEventListener("attempt", handle)
    source.addEventListener("message", handle)
    // EventSource retries network drops by itself, but gives up for good on an HTTP error
    // such as a 401 after the session expired. Only the latter needs the user.
    source.onerror = () => setStatus(source.readyState === EventSource.CLOSED ? "offline" : "reconnecting")
    return () => source.close()
  }, [appId, client, generation])

  const reconnect = useCallback(() => {
    setStatus("connecting")
    setGeneration((g) => g + 1)
  }, [])

  return { events, status, reconnect, clear: () => setEvents([]) }
}
