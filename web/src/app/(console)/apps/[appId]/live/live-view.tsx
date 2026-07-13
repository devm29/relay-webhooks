"use client"

import { Activity, Pause, Play, RotateCw, Send } from "lucide-react"
import { useParams } from "next/navigation"
import { useMemo, useState } from "react"
import { DeliverySheet } from "@/components/delivery-sheet"
import { EmptyState } from "@/components/empty-state"
import { QueryError } from "@/components/query-error"
import { RowButton } from "@/components/row-button"
import { SendEventDialog } from "@/components/send-event-dialog"
import { PageBody, PageHeader } from "@/components/shell/page-header"
import { DeliveryStatusPill, HttpStatus, StatusDot } from "@/components/status"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAttempts, useEndpoints } from "@/lib/api/hooks"
import type { AttemptLog, LiveEvent } from "@/lib/api/schemas"
import { clockTime, endpointName, latency } from "@/lib/format"
import { useLiveEvents, type LiveStatus } from "@/lib/live"

type Row = {
  id: string
  at: string
  eventType: string
  endpointId: string
  deliveryId: string
  statusCode: number | null
  error: string | null
  latencyMs: number | null
  attempt: number | null
  deliveryStatus: AttemptLog["delivery_status"] | null
  fresh: boolean
}

function fromLive(event: LiveEvent): Row | null {
  if (event.kind !== "attempt" || !event.endpoint_id || !event.delivery_id) return null
  return {
    id: event.id,
    at: event.at,
    eventType: event.event_type,
    endpointId: event.endpoint_id,
    deliveryId: event.delivery_id,
    statusCode: event.status_code,
    error: event.outcome === "failed" && event.status_code === null ? "timed out or unreachable" : null,
    latencyMs: event.latency_ms,
    attempt: event.attempt_number,
    deliveryStatus: event.delivery_status,
    fresh: true,
  }
}

function fromHistory(attempt: AttemptLog): Row {
  return {
    id: attempt.id,
    at: attempt.started_at,
    eventType: attempt.event_type,
    endpointId: attempt.endpoint_id,
    deliveryId: attempt.delivery_id,
    statusCode: attempt.status_code,
    error: attempt.error,
    latencyMs: attempt.latency_ms,
    attempt: attempt.attempt_number,
    deliveryStatus: attempt.delivery_status,
    fresh: false,
  }
}

const STATUS_COPY: Record<LiveStatus, string> = {
  connecting: "Connecting",
  live: "Live",
  reconnecting: "Reconnecting",
  offline: "Disconnected",
}

export function LiveView() {
  const { appId } = useParams<{ appId: string }>()
  const [paused, setPaused] = useState(false)
  const [endpointFilter, setEndpointFilter] = useState<string>("all")
  const [selected, setSelected] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const live = useLiveEvents(appId, paused)
  const history = useAttempts(appId, undefined, 100)
  const endpoints = useEndpoints(appId)

  const endpointNames = useMemo(() => {
    const map = new Map<string, string>()
    for (const endpoint of endpoints.data?.data ?? []) {
      map.set(endpoint.id, endpointName(endpoint))
    }
    return map
  }, [endpoints.data])

  const rows = useMemo(() => {
    const seen = new Set<string>()
    const merged: Row[] = []
    for (const row of [
      ...live.events.map(fromLive),
      ...(history.data?.data ?? []).map(fromHistory),
    ]) {
      if (!row || seen.has(row.id)) continue
      if (endpointFilter !== "all" && row.endpointId !== endpointFilter) continue
      seen.add(row.id)
      merged.push(row)
    }
    return merged.slice(0, 150)
  }, [live.events, history.data, endpointFilter])

  return (
    <>
      <PageHeader
        title="Live log"
        subtitle={
          <span className="inline-flex items-center gap-1.5">
            <StatusDot tone={live.status === "live" ? "success" : "warning"} pulse={live.status === "live" && !paused} />
            {paused ? "Paused" : STATUS_COPY[live.status]}
          </span>
        }
        actions={
          <>
            {live.status === "offline" && (
              <Button variant="secondary" size="sm" onClick={live.reconnect}>
                <RotateCw /> Reconnect
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={() => setPaused((p) => !p)} aria-pressed={paused}>
              {paused ? <Play /> : <Pause />}
              {paused ? "Resume" : "Pause"}
            </Button>
            <Button size="sm" onClick={() => setSending(true)}>
              <Send /> Send event
            </Button>
          </>
        }
      />
      <PageBody>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-[13px] text-muted-foreground">
            Every delivery attempt as it happens, streamed from Postgres LISTEN/NOTIFY.
          </p>
          <Select value={endpointFilter} onValueChange={setEndpointFilter}>
            <SelectTrigger className="h-8 w-56 rounded-lg text-[13px]" aria-label="Filter by endpoint">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All endpoints</SelectItem>
              {[...endpointNames].map(([id, name]) => (
                <SelectItem key={id} value={id}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="overflow-hidden rounded-xl border border-border/60 bg-card shadow-xs">
          {history.isError && rows.length === 0 ? (
            <QueryError error={history.error} onRetry={history.refetch} retrying={history.isFetching} />
          ) : rows.length === 0 && !history.isPending ? (
            <EmptyState
              icon={Activity}
              title="Waiting for traffic"
              description="Send a test event or publish from your backend. Attempts appear here within a second."
              action={<Button onClick={() => setSending(true)}>Send test event</Button>}
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="w-24 text-[12px]">Time</TableHead>
                  <TableHead className="text-[12px]">Event</TableHead>
                  <TableHead className="hidden text-[12px] md:table-cell">Endpoint</TableHead>
                  <TableHead className="w-20 text-[12px]">Status</TableHead>
                  <TableHead className="w-24 text-right text-[12px]">Latency</TableHead>
                  <TableHead className="hidden w-20 text-right text-[12px] sm:table-cell">Attempt</TableHead>
                  <TableHead className="hidden w-28 text-[12px] lg:table-cell">Delivery</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow
                    key={row.id}
                    className={`h-11 cursor-pointer hover:bg-accent/50 ${row.fresh ? "animate-row-in" : ""}`}
                    onClick={() => setSelected(row.deliveryId)}
                  >
                    <TableCell className="font-mono text-[12px] text-muted-foreground tabular-nums">
                      {clockTime(row.at)}
                    </TableCell>
                    <TableCell>
                      <RowButton label={`Open delivery of ${row.eventType}`} onClick={() => setSelected(row.deliveryId)}>
                        {row.eventType}
                      </RowButton>
                    </TableCell>
                    <TableCell className="hidden max-w-56 truncate text-[13px] md:table-cell">
                      {endpointNames.get(row.endpointId) ?? row.endpointId}
                    </TableCell>
                    <TableCell>
                      <HttpStatus code={row.statusCode} error={row.error} />
                    </TableCell>
                    <TableCell className="text-right text-[13px] tabular-nums">{latency(row.latencyMs)}</TableCell>
                    <TableCell className="hidden text-right text-[13px] text-muted-foreground tabular-nums sm:table-cell">
                      #{row.attempt}
                    </TableCell>
                    <TableCell className="hidden lg:table-cell">
                      {row.deliveryStatus && <DeliveryStatusPill status={row.deliveryStatus} />}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </PageBody>
      <DeliverySheet appId={appId} deliveryId={selected} onOpenChange={(open) => !open && setSelected(null)} />
      <SendEventDialog appId={appId} open={sending} onOpenChange={setSending} />
    </>
  )
}
